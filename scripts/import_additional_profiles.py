"""Build isolated, explicitly modeled Spektrafilm candidates from pinned MIT data.

Run with .venv/Scripts/python.exe scripts/import_additional_profiles.py --verify
No production/vendor files are written. The generated profiles require the
runtime sidecars: their DIR couplers and particle sizes are not stock calibrated.

Digitized values and parts of the density preparation below derive from
Jan Lohse's spectral_film_lut, MIT (2026). See the copied LICENSE and provenance.
This reads numeric dictionaries from AST; it never executes downloaded modules.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
from pathlib import Path
import sys
import urllib.request

import colour
import numpy as np
from scipy import ndimage
from scipy.interpolate import PchipInterpolator
from scipy.optimize import least_squares
from scipy.special import ndtr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vendor"))
RESEARCH = ROOT / "output/film-profile-research"
SOURCE = RESEARCH / "evidence/spectral_film_lut"
COMMIT = "bcbcfc6861f49cc706dc5d00ea048e4853060aab"
REPO = "https://github.com/JanLohse/spectral_film_lut"
DATA = "src/spectral_film_lut/"
STOCKS = {
    "fujifilm_velvia_50": ("reversal_film/fuji_velvia_50.py", "4a9c61abee7c319d0ec0ac62ff758f3314628c983c905d1d579a6c6fc301f26c"),
    "agfa_vista_100": ("negative_film/agfa_vista_100.py", "57d9455c7eb56f25ae5e21dfcbcc30cf2359e25e9d59f357e0b0e3d5630c9410"),
    "fujifilm_natura_1600": ("negative_film/fuji_natura_1600.py", "5c6afce79b702ea74496f9f63e43695fdd39ba2164c7ff010da71227ae2949fa"),
}
DEPENDENCIES = {
    "LICENSE": "3cdc90b3e7727be6e5930102fadeaf35cf3d3bd7c492b90d6d16fb9ad8c3a1bd",
    DATA + "densiometry.py": "c04ea67f57bfef6852ac50d0306291f98b59c1509ff3a4dbd98ea2bc9564ba75",
}
SHAPE = colour.SpectralShape(380, 780, 5)
WAVELENGTHS = SHAPE.wavelengths
EXPOSURES = np.linspace(-3, 4, 256)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_file(relative, expected):
    path = SOURCE / relative
    if not path.exists():
        url = f"https://raw.githubusercontent.com/JanLohse/spectral_film_lut/{COMMIT}/{relative}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(urllib.request.urlopen(url, timeout=30).read())
    if digest(path) != expected:
        raise ValueError(f"Pinned source hash mismatch: {path}")
    return path


def literal_assignment(path, name):
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            try:
                return ast.literal_eval(node.value)
            except ValueError:
                continue
    raise ValueError(f"Missing literal {name}")


def film_values(path):
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == "FilmData":
            return {kw.arg: ast.literal_eval(kw.value) for kw in node.value.keywords}
    raise ValueError(f"Missing FilmData literals in {path}")


def gaussian_spectrum(values):
    """Jan Lohse's Gaussian edge extrapolation, on the engine's 5 nm grid."""
    sd = colour.SpectralDistribution(values).interpolate(SHAPE)
    x, y = sd.wavelengths, sd.values

    def tail(a_x, a_y, b_x, b_y, w):
        slope = (a_y - b_y) / (a_x - b_x)
        if abs(slope) < 1e-12:
            return np.full(w.shape, a_y)
        a_y = math.copysign(max(abs(a_y), 0.001), a_y)
        d = 30 * slope / abs(a_y) ** 0.75
        a = a_y / max(np.exp(-d**2), 1e-10)
        c = a / slope * -2 * d * np.exp(-d**2)
        b = a_x - c * d
        return a * np.exp(-((w - b) ** 2) / max(c**2, 0.0001))

    lo, hi = WAVELENGTHS < x[0], WAVELENGTHS > x[-1]
    result = np.interp(WAVELENGTHS, x, y)
    result[lo] = tail(x[0], y[0], x[1], y[1], WAVELENGTHS[lo])
    result[hi] = tail(x[-1], y[-1], x[-2], y[-2], WAVELENGTHS[hi])
    return np.maximum(result, 0)


def status_weights(path, label):
    values = literal_assignment(path, label)
    weights = []
    for v in values:
        sd = colour.SpectralDistribution(v).extrapolate(SHAPE, extrapolator_kwargs={"method": "linear"})
        sd.values = 10 ** sd.values
        sd.interpolate(SHAPE)
        weights.append(sd.values / np.sum(sd.values))
    return np.array(weights).T


def split_reference_density(reference):
    """Source's peak/valley partition, not measured individual dye spectra."""
    def extreme(lo, hi, which):
        indexes = np.flatnonzero((WAVELENGTHS >= lo) & (WAVELENGTHS <= hi))
        return indexes[which(reference[indexes])]
    r = extreme(600, 750, np.argmax)
    g = extreme(500, 600, np.argmax)
    b = extreme(400, 500, np.argmax)
    bg = WAVELENGTHS[extreme(WAVELENGTHS[b], WAVELENGTHS[g], np.argmin)]
    gr = WAVELENGTHS[extreme(WAVELENGTHS[g], WAVELENGTHS[r], np.argmin)]
    masks = np.stack([WAVELENGTHS >= gr, (WAVELENGTHS > bg) & (WAVELENGTHS < gr), WAVELENGTHS <= bg]).astype(float)
    masks = ndimage.gaussian_filter(masks, sigma=(0, 25 / 5))
    return (masks * reference).T, {"blue_green_cut_nm": bg, "green_red_cut_nm": gr, "smoothing_sigma_nm": 25}


def extend_curve(x, y):
    """Source's assumed logistic shoulder; not extra measured exposure range."""
    gamma = np.max(np.gradient(y, x))
    end_gamma = np.mean(np.gradient(y, x)[-4:])
    step = (x[-1] - x[0]) / len(x)
    count = max(5, math.floor(4.5 / gamma / step))
    xx = np.linspace(0, count * step, count)
    yy = 3 / (1 + np.exp(-4 * gamma / 3 * xx))
    start = np.argmin(abs(np.gradient(yy, xx) - end_gamma))
    xx, yy = xx[start:], yy[start:]
    return np.r_[x, xx[1:] + x[-1] - xx[0]], np.r_[y, yy[1:] + y[-1] - yy[0]]


def fit_cdfs(target, positive):
    models, layers, errors = [], [], []
    sign = -1 if positive else 1
    for ch in range(3):
        yy = target[:, ch]
        amp = float(np.max(yy))
        center = EXPOSURES[np.argmin(abs(yy - amp / 2))]
        initial = np.r_[center + np.array([-0.5, 0, 0.5]), np.full(3, amp / 3), np.full(3, 0.6)]
        def evaluate(p):
            return p[3:6] * ndtr(sign * (EXPOSURES[:, None] - p[:3]) / p[6:])
        opt = least_squares(lambda p: evaluate(p).sum(axis=1) - yy, initial,
                            bounds=(np.r_[[-7] * 3, [1e-8] * 3, [0.05] * 3], np.r_[[8] * 3, [max(10, amp * 2)] * 3, [5] * 3]),
                            max_nfev=3000, ftol=1e-10, xtol=1e-10, gtol=1e-10)
        order = np.argsort(opt.x[:3])
        model = [opt.x[:3][order], opt.x[3:6][order], opt.x[6:][order]]
        layer = evaluate(opt.x)[:, order]
        error = layer.sum(axis=1) - yy
        models.append(model)
        layers.append(layer)
        errors.append({"rmse_density": float(np.sqrt(np.mean(error**2))), "max_abs_density": float(np.max(abs(error))), "solver_success": bool(opt.success)})
    layers = np.stack(layers, axis=2)
    return layers.sum(axis=1), layers, {"model_type": "cdfs", "centers": np.array(models)[:, 0], "amplitudes": np.array(models)[:, 1], "sigmas": np.array(models)[:, 2]}, errors


def convert(stock, path, density_path):
    from spektrafilm.utils.spectral_upsampling import rgb_to_smooth_spectrum

    raw = film_values(path)
    positive = raw["film_type"] == "positive"
    log_h_ref = math.log10(12.5 / raw["iso"])
    measured_axes, measured_curves = [], []
    for curve in raw["sensiometric_curve"]:
        x = np.array(sorted(curve))
        y = np.array([curve[v] for v in x])
        if not positive:
            x, y = extend_curve(x, y)
        measured_axes.append(x)
        measured_curves.append(y)
    # Clamp beyond each prepared support instead of unconstrained polynomial extrapolation.
    sampled = np.stack([PchipInterpolator(x, y)(np.clip(EXPOSURES + log_h_ref, x[0], x[-1])) for x, y in zip(measured_axes, measured_curves)], axis=1)
    d_min = np.min(sampled, axis=0)
    zero_curves = sampled - d_min
    base = gaussian_spectrum(raw["d_min_sd"]) if "d_min_sd" in raw else np.zeros(81)
    source_details = {}
    if "spectral_density" in raw:
        dyes = np.stack([gaussian_spectrum(v) for v in raw["spectral_density"]], axis=1)
        source_details["dye_source"] = "three digitized spectral-density curves"
    else:
        reference = gaussian_spectrum(raw["d_ref_sd"])
        dyes, cuts = split_reference_density(np.maximum(reference - base, 0))
        source_details.update(dye_source="modeled split of total reference spectrum minus minimum spectrum", **cuts)
    status = status_weights(density_path, "STATUS_A" if positive else "STATUS_M")
    dyes /= np.sum(dyes * status, axis=0)
    if positive:
        unmix = np.linalg.inv(status.T @ dyes)
    else:
        apd_raw = literal_assignment(density_path, "APD")
        apd = colour.MultiSpectralDistributions(apd_raw).align(SHAPE).values
        apd /= apd.sum(axis=0)
        cdd_to_cid = np.array([[0.75573, 0.05901, 0.16134], [0.22197, 0.96928, 0.07406], [0.02230, -0.02829, 0.76460]])
        unmix = np.linalg.inv(apd.T @ dyes @ cdd_to_cid.T)
    transformed = zero_curves @ unmix.T
    # Enforce physical nonnegative monotone layer amounts after approximate unmixing.
    monotone = np.maximum(transformed, 0)
    monotone = np.minimum.accumulate(monotone, axis=0) if positive else np.maximum.accumulate(monotone, axis=0)
    physical_adjustment = float(np.max(abs(monotone - transformed)))
    base += dyes @ np.linalg.solve(status.T @ dyes, d_min - status.T @ base)
    base_clamp = float(max(0, -np.min(base)))
    base = np.maximum(base, 0)
    curves, layers, model, errors = fit_cdfs(monotone, positive)
    # Match the host engine's actual D55 Hanatos midgray spectrum at log raw = 0.
    logs = np.stack([colour.SpectralDistribution(v).align(SHAPE, extrapolator_kwargs={"method": "linear"}).align(SHAPE).values for v in raw["log_sensitivity"]], axis=1)
    logs = np.clip(logs, -12, 12)
    sensitivity = 10**logs
    gray_spectrum = rgb_to_smooth_spectrum(np.array([[[0.184] * 3]]), "sRGB", False, "D55")
    sensitivity /= gray_spectrum @ sensitivity
    slide_gray_calibration = None
    if positive:
        # A slide is viewed directly, so its neutral anchor must be solved on
        # transmittance, not by forcing the three dye amounts to be identical.
        from spektrafilm.config import STANDARD_OBSERVER_CMFS
        from spektrafilm.model.illuminants import standard_illuminant
        light = standard_illuminant("D50")
        cmfs = np.asarray(STANDARD_OBSERVER_CMFS[:])
        normalization = np.sum(light * cmfs[:, 1])
        white_xy = colour.XYZ_to_xy(light @ cmfs / normalization)
        def scan_gray(offsets):
            amounts = np.array([np.interp(offsets[c], EXPOSURES, curves[:, c]) for c in range(3)])
            spectral = 10 ** -(dyes @ amounts + base) * light
            xyz = spectral @ cmfs / normalization
            return colour.XYZ_to_RGB(xyz, "sRGB", illuminant=white_xy, apply_cctf_encoding=False)
        result = least_squares(lambda x: np.log(np.maximum(scan_gray(x), 1e-10) / 0.184), np.zeros(3), bounds=(-1.5, 1.5),
                               max_nfev=100, xtol=1e-11, ftol=1e-11, gtol=1e-11)
        assert np.linalg.norm(result.fun) < 1e-5
        sensitivity *= 10 ** result.x
        slide_gray_calibration = {"method": "modeled D55 18.4% gray exposed, viewed under D50, solve three log-exposure offsets to linear sRGB [0.184]*3", "log10_exposure_offsets": result.x.tolist(), "stops_offsets": (result.x / np.log10(2)).tolist(), "gray_linear_srgb": scan_gray(result.x).tolist(), "measured_calibration": False}
    logs = np.log10(sensitivity)
    gray_offsets = np.array(slide_gray_calibration["log10_exposure_offsets"]) if slide_gray_calibration else np.zeros(3)
    gray_amount = np.array([np.interp(gray_offsets[ch], EXPOSURES, curves[:, ch]) for ch in range(3)])
    info = {"stock": stock, "name": raw["name"].replace("Fuji ", "Fujifilm "), "type": raw["film_type"], "support": "film", "stage": "filming", "use": "still", "antihalation": "weak", "target_print": None if positive else "fujifilm_crystal_archive_typeii", "channel_model": "color", "densitometer": "status_A" if positive else "status_M", "log_sensitivity_density_over_min": 0.2, "reference_illuminant": "D55", "viewing_illuminant": "D50"}
    assumptions = ["According to the upstream author these values digitize manufacturer graphs; original factory datasheets not independently cross-checked here. No new laboratory measurements.", "Source linear log-sensitivity extrapolation, bounded to [-12,12]; Gaussian dye/base spectral tails; 380-780 nm, 5 nm sampling.", "Absolute H axis reanchored by log10(12.5/ISO); each sensitivity normalized on engine D55 Hanatos 18.4% gray; positive-film neutral speed further solved on spectral transmittance.", "Status A inverse or source APD/CDD-to-CID inverse; small nonnegative/monotone projections recorded.", "Negative shoulder extended by source's assumed logistic curve; prepared H-D supports clamped outside endpoints.", "Three normal-CDF sublayers fitted to curves; these are numerical components, not measured physical emulsions.", "Identity Hanatos adaptation; no stock-specific adaptation surface, DIR-coupler, halation or particle-area calibration.", "Antihalation=weak and sensitivity density-over-min=0.2 are host schema defaults, not measured stock attributes; D50 is a selected viewing condition."]
    profile = {
        "metadata": {"version": "candidate-1", "copyright": "Digitized dataset and preparation portions: Copyright (c) 2026 Jan Lohse. MIT License.", "created": "2026-11-07", "license": "MIT; include Jan Lohse copyright and full MIT permission notice in LICENSE-data-MIT.txt. Host engine is separately GPLv3; no existing CC BY-SA profile arrays are copied.", "citation": f"{REPO}/tree/{COMMIT}", "datasource": "Modeled research candidate converted from " + str(path.relative_to(ROOT)).replace("\\", "/") + ". " + " ".join(assumptions)},
        "info": info,
        "data": {"wavelengths": WAVELENGTHS, "log_sensitivity": logs, "hanatos2025_adaptation_window_params": [0, 1, 1200, 1], "hanatos2025_adaptation_surface_params": np.zeros((3, 15)), "channel_density": dyes, "base_density": base, "midscale_neutral_density": dyes @ gray_amount + base, "log_exposure": EXPOSURES, "density_curves": curves, "density_curves_layers": layers, "density_curves_model": model},
    }
    provenance = {"stock": stock, "source_url": f"{REPO}/blob/{COMMIT}/{DATA}{STOCKS[stock][0]}", "source_sha256": digest(path), "density_source_sha256": digest(density_path), "source_iso": raw["iso"], "source_year": raw.get("year"), "source_color_masking": raw.get("color_masking"), "assumptions": assumptions, "source_details": source_details, "source_domains": {key: [{"n": len(v), "min": min(v), "max": max(v)} for v in raw[key]] for key in ["log_sensitivity", "sensiometric_curve"]}, "density_fit": errors, "monotone_projection_max_density": physical_adjustment, "base_nonnegative_clamp_max_density": base_clamp, "slide_gray_calibration": slide_gray_calibration, "license": "MIT (Jan Lohse); manufacturer trademarks and original datasheets are separate", "grain_rms_source": raw.get("rms"), "grain_calibrated": False, "dir_couplers_calibrated": False}
    return profile, provenance


def json_safe(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def write_json(path, value):
    path.write_text(json.dumps(json_safe(value), indent=2, allow_nan=False) + "\n", encoding="utf-8")


def verification(profile, output):
    from spektrafilm import Simulator, digest_params
    from spektrafilm.profiles.io import _validate_profile, load_profile, profile_from_dict
    from spektrafilm.runtime.params_schema import RuntimePhotoParams
    from spektrafilm.utils.gamut_compression import OutputGamutCompressSpec

    film = profile_from_dict(profile)
    _validate_profile(film, film.info.stock)
    data = film.data
    for field in ["log_sensitivity", "channel_density", "base_density", "midscale_neutral_density", "log_exposure", "density_curves", "density_curves_layers"]:
        assert np.isfinite(getattr(data, field)).all(), field
    assert np.all(np.diff(data.log_exposure) > 0)
    assert np.max(abs(data.density_curves_layers.sum(axis=1) - data.density_curves)) < 1e-12
    assert np.all((np.diff(data.density_curves, axis=0) * (-1 if film.is_positive else 1)) >= -1e-12)
    params = RuntimePhotoParams(film=film, print=load_profile("fujifilm_crystal_archive_typeii"))
    params.io.input_color_space = "sRGB"
    params.io.scan_film = film.is_positive
    params.io.output_cctf_encoding = False
    params.io.output_gamut_compress = OutputGamutCompressSpec(algorithm="off")
    params.camera.auto_exposure = False
    params.debug.deactivate_spatial_effects = True
    params.debug.deactivate_stochastic_effects = True
    params.settings.neutral_print_filters_from_database = False
    params.scanner.unsharp_mask = (0, 0)
    params.enlarger.c_filter_neutral = params.enlarger.m_filter_neutral = params.enlarger.y_filter_neutral = 0
    params = digest_params(params)
    params.film_render.dir_couplers.active = False
    # Reuse the existing per-film spectral LUT while solving only enlarger filters.
    simulator = Simulator(params)
    pipeline = simulator._pipeline
    gray = np.array([[[0.184] * 3]])

    def render_filters(filters):
        pipeline.enlarger.c_filter_neutral, pipeline.enlarger.m_filter_neutral, pipeline.enlarger.y_filter_neutral = filters
        return simulator.process(gray)[0, 0]

    neutral = None
    if film.is_negative:
        solutions = []
        for fixed in range(3):
            variable = [i for i in range(3) if i != fixed]
            def filters_for(x):
                values = np.zeros(3)
                values[variable] = x
                return values
            def residual(x):
                rgb = np.maximum(render_filters(filters_for(x)), 1e-10)
                return np.log(rgb[[0, 2]] / rgb[1])
            result = least_squares(residual, [40, 40], bounds=(0, 250), max_nfev=100, diff_step=1e-3, xtol=1e-9, ftol=1e-9, gtol=1e-9)
            filters = filters_for(result.x)
            solutions.append((float(np.linalg.norm(residual(result.x))), float(filters.sum()), filters, result.success))
        best = min(solutions, key=lambda s: (round(s[0], 6), s[1]))
        rgb = render_filters(best[2])
        neutral = {"paper": params.print.info.stock, "illuminant": params.enlarger.illuminant, "cmy_cc": best[2].tolist(), "method": "numerical 18.4% D55 gray chromaticity solve on exact spectral print+scan path; minimum one filter fixed at zero", "log_rgb_ratio_residual_norm": best[0], "gray_output_linear_srgb": rgb.tolist(), "solver_success": bool(best[3]), "measured_calibration": False, "dir_couplers_active": False, "black_white_correction": [params.scanner.black_correction, params.scanner.white_correction]}
        assert best[0] < 0.005, neutral
    levels = np.array([0, 0.003, 0.01, 0.03, 0.09, 0.184, 0.36, 0.72, 1.0, 2.0])
    grayscale = np.repeat(levels[None, :, None], 3, axis=2)
    cc = colour.CCS_COLOURCHECKERS["ColorChecker 2005"]
    xyz = colour.xyY_to_XYZ(np.array(list(cc.data.values())))
    patches = np.clip(colour.XYZ_to_RGB(xyz, "sRGB", illuminant=cc.illuminant, apply_cctf_encoding=False), 0, 1)[None]
    gray_out = simulator.process(grayscale)
    chart_out = simulator.process(patches)
    assert np.isfinite(gray_out).all() and np.isfinite(chart_out).all()
    assert np.all(np.diff(np.mean(gray_out, axis=2).ravel()) >= -1e-6)
    pipeline.io.input_cctf_decoding = True
    encoded_chart_out = simulator.process(colour.cctf_encoding(patches, function="sRGB"))
    encoding_error = float(np.max(abs(encoded_chart_out - chart_out)))
    assert encoding_error < 1e-10
    pipeline.io.input_cctf_decoding = False
    np.savez(output / f"{film.info.stock}.diagnostic.npz", gray_input=grayscale, gray_output=gray_out, colorchecker_input=patches, colorchecker_output=chart_out)
    return {"schema_valid": True, "all_numeric_fields_finite": True, "layer_sum_max_error": float(np.max(abs(data.density_curves_layers.sum(axis=1) - data.density_curves))), "grayscale_monotone": True, "gray_output_linear_srgb": gray_out.tolist(), "chart_finite": True, "chart_range_linear_srgb": [float(chart_out.min()), float(chart_out.max())], "negative_output_values": int(np.sum(chart_out < 0)), "above_one_values": int(np.sum(chart_out > 1)), "encoded_vs_linear_max_abs_error": encoding_error, "neutral_print": neutral, "simulation": "actual vendor Simulator; Hanatos2025, direct spectral enlarger/scanner, stock-calibrated spatial/grain/DIR effects unavailable and disabled"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--output", type=Path, default=RESEARCH / "candidates")
    args = parser.parse_args()
    # Keep this research importer isolated from every production profile directory.
    args.output = args.output.resolve()
    if RESEARCH.resolve() not in args.output.parents:
        parser.error("Candidate output must be a subdirectory of output/film-profile-research")
    args.output.mkdir(parents=True, exist_ok=True)
    density_path = source_file(DATA + "densiometry.py", DEPENDENCIES[DATA + "densiometry.py"])
    license_path = source_file("LICENSE", DEPENDENCIES["LICENSE"])
    (args.output / "LICENSE-data-MIT.txt").write_bytes(license_path.read_bytes())
    report = {}
    for stock, (relative, expected_hash) in STOCKS.items():
        path = source_file(DATA + relative, expected_hash)
        profile, provenance = convert(stock, path, density_path)
        target = args.output / f"{stock}.json"
        write_json(target, profile)
        provenance["profile_sha256"] = digest(target)
        if args.verify:
            provenance["verification"] = verification(profile, args.output)
        write_json(args.output / f"{stock}.provenance.json", provenance)
        runtime = {"stock": stock, "candidate_status": "modeled; visual and stock-reference validation pending", "film_render.dir_couplers.active": False, "film_render.grain.active": False, "film_render.halation.active": False, "settings.neutral_print_filters_from_database": False}
        if args.verify:
            runtime["neutral_print"] = provenance["verification"]["neutral_print"]
        write_json(args.output / f"{stock}.runtime.json", runtime)
        report[stock] = {"sha256": provenance["profile_sha256"], "density_fit": provenance["density_fit"], "verification": provenance.get("verification")}
        print(stock, "written", "and verified" if args.verify else "(not yet verified)", flush=True)
    write_json(args.output / "summary.json", report)
    (args.output / "CHANGELOG.txt").write_text("2026-11-07: Converted pinned Jan Lohse MIT digitized numerical data into independent modeled candidates; source spectra and curves were interpolated/extrapolated, normalized and fit. No existing Spektrafilm film profile arrays copied. See per-stock provenance for assumptions and verification.\n", encoding="utf-8")


if __name__ == "__main__":
    main()
