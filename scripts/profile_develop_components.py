"""Isolated CPU full-development profiling and exact no-op experiments.

This script patches functions only inside its process. It changes no application code.
"""
from __future__ import annotations

import argparse
import contextlib
import dataclasses
import functools
import hashlib
import importlib
import json
import platform
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

import numba
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'vendor'))
from desktop.imaging import read_photo
from shared.film_profiles import init_film_params
from spektrafilm import Simulator, digest_params

develop = importlib.import_module('spektrafilm.model.develop')
couplers = importlib.import_module('spektrafilm.model.couplers')
grain = importlib.import_module('spektrafilm.model.grain')
curves = importlib.import_module('spektrafilm.model.density_curves')
filters = importlib.import_module('spektrafilm.utils.fast_gaussian_filter')


class Timings:
    """Nested inclusive/exclusive timings; component totals are not additive."""
    def __init__(self):
        self.samples = defaultdict(list)
        self.self_samples = defaultdict(list)
        self.stack = []
        self.sigma_samples = defaultdict(list)

    def wrap(self, function, label, sigma_index=None):
        @functools.wraps(function)
        def measured(*args, **kwargs):
            frame = [time.perf_counter(), 0.0]
            self.stack.append(frame)
            if sigma_index is not None:
                sigma = args[sigma_index] if len(args) > sigma_index else kwargs.get('sigma', 0)
                self.sigma_samples[label].append(dict(
                    sigma=np.asarray(sigma).tolist(), shape=list(np.shape(args[0])),
                    fir_radius=np.floor(3*np.asarray(sigma)+.5).astype(int).tolist(),
                ))
            try:
                return function(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - frame[0]
                self.stack.pop()
                self.samples[label].append(elapsed)
                self.self_samples[label].append(elapsed - frame[1])
                if self.stack:
                    self.stack[-1][1] += elapsed
        return measured

    def report(self):
        return {label: dict(calls=len(samples), inclusive_seconds=sum(samples),
                           exclusive_seconds=sum(self.self_samples[label]),
                           max_call_seconds=max(samples), individual_seconds=samples)
                for label, samples in self.samples.items()}


def make_params(stock, grain_amount=18, physical_edge=None):
    p = init_film_params(stock)
    p.io.input_color_space = 'sRGB'
    p.io.input_cctf_decoding = True
    p.io.scan_film = p.film.is_positive
    p.camera.auto_exposure = False
    p.settings.use_enlarger_lut = True
    p.settings.use_scanner_lut = True
    p.settings.preview_mode = False
    p.film_render.grain.active = grain_amount > 0
    p.film_render.grain.particle_area_um2 = .2*(grain_amount/25)**2
    p.film_render.grain.uniformity = (.97, .97, .97)
    p.film_render.grain.blur = .65
    p.film_render.grain.blur_dye_clouds_um = 1.
    p.film_render.halation.active = True
    p.film_render.halation.halation_amount = 12/25
    p.film_render.halation.scatter_amount = 12/25
    if physical_edge is not None:
        # Preserve the original sensor's physical pixel pitch for the sample.
        p.camera.film_format_mm = 35 * physical_edge[0] / physical_edge[1]
    return p


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=Path('M:/2026/2026-06 #北京/DSC06823.ARW'))
    parser.add_argument('--edge', type=int, default=2048)
    parser.add_argument('--repeat', type=int, default=3)
    parser.add_argument('--stock', default='kodak_portra_400')
    parser.add_argument('--output', type=Path, default=ROOT/'output/profile-develop-components.json')
    parser.add_argument('--decode-cache', type=Path, default=ROOT/'output/develop-profile-source-2048.png')
    args = parser.parse_args()
    start = time.perf_counter()
    source_sha = hashlib.sha256(args.source.read_bytes()).hexdigest()
    meta_path = args.decode_cache.with_suffix('.json')
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    if (args.decode_cache.exists() and meta.get('source_sha256') == source_sha
            and meta.get('requested_edge') == args.edge):
        with Image.open(args.decode_cache) as image_file:
            image = image_file.convert('RGB')
        source_size = meta['source_size']
        decode_mode = 'validated local RGB8 sample cache'
    else:
        image = read_photo(str(args.source), args.edge)
        source_size = image.info['source_size']
        args.decode_cache.parent.mkdir(parents=True, exist_ok=True)
        image.save(args.decode_cache)
        meta_path.write_text(json.dumps(dict(source=str(args.source), source_sha256=source_sha,
            requested_edge=args.edge, source_size=source_size)), encoding='utf8')
        decode_mode = 'rawpy AHD half-size bounded decode then Lanczos sample'
    decoded_seconds = time.perf_counter() - start
    values = np.asarray(image, dtype=np.float64) / 255
    physical_edge = (max(image.size), max(source_size))
    params = digest_params(make_params(args.stock, physical_edge=physical_edge))
    simulator = Simulator(params)
    # JIT warmup with a real small source before measuring stages.
    tiny = np.ascontiguousarray(values[:32, :48])
    warm = Simulator(digest_params(make_params(args.stock)))
    warm.process(tiny)
    # Compile large-sigma recursive path and lognormal too; JIT time is not profiling work.
    filters.fast_gaussian_filter(np.ones((16, 24, 3)), 5.)
    grain.fast_lognormal_from_mean_std(np.ones((16, 24, 3)), np.full((16, 24, 3), .1))
    exposed_start = time.perf_counter()
    log_raw = simulator.process_tap(values, inject='rgb_in', collect='log_e_film')
    exposed_seconds = time.perf_counter() - exposed_start
    node = next(n for n in simulator._pipeline._topology if n.label == 'filming.develop')
    pixel_size_um = simulator._pipeline._resize_service.pixel_size_um
    # One full-size warm run removes compilation / page-fault first-use bias.
    node.run(log_raw)

    labels = [
        (develop, 'develop_simple', 'curve.exposure_to_density'),
        (develop, 'apply_density_correction_dir_couplers', 'dir.total'),
        (develop, 'apply_grain', 'grain.total'),
        (couplers, 'compute_density_curves_before_dir_couplers', 'dir.curve_reference'),
        (couplers, 'compute_exposure_correction_dir_couplers', 'dir.exposure_correction'),
        (couplers, 'interpolate_exposure_to_density', 'dir.curve_interpolation'),
        (couplers, 'contract', 'dir.matrix_contract'),
        (couplers, 'fast_gaussian_filter', 'dir.gaussian', 1),
        (couplers, 'fast_exponential_filter', 'dir.exponential', 1),
        (grain, '_apply_grain_from_density_curves', 'grain.sublayer_transform'),
        (grain, 'layer_particle_model', 'grain.layer_particle_model'),
        (grain, 'add_micro_structure', 'grain.microstructure'),
        (grain, 'fast_lognormal_from_mean_std', 'grain.lognormal_sampling'),
        (grain, 'fast_gaussian_filter', 'grain.gaussian', 1),
        (grain.scipy.stats.poisson, 'rvs', 'grain.scipy_poisson'),
        (filters, 'fast_gaussian_filter', 'exp.internal_gaussians', 1),
        (filters, '_gaussian_filter_2d_small', 'filter.fir_2d', 1),
        (filters, '_gaussian_filter_2d_large', 'filter.iir_2d', 1),
    ]
    # np.interp is only patched for grain's calls via a lightweight proxy.
    class NumpyProxy:
        def __getattr__(self, name):
            return getattr(np, name)

    component_samples, total_seconds = [], []
    for repetition in range(args.repeat):
        timing = Timings()
        proxy = NumpyProxy()
        proxy.interp = timing.wrap(np.interp, 'grain.layer_curve_interpolation')
        with contextlib.ExitStack() as stack:
            for module, name, label, *sigma in labels:
                stack.enter_context(patch.object(module, name, timing.wrap(
                    getattr(module, name), label, sigma[0] if sigma else None)))
            stack.enter_context(patch.object(grain, 'np', proxy))
            start = time.perf_counter()
            result = node.run(log_raw)
            elapsed = time.perf_counter() - start
        total_seconds.append(elapsed)
        component_samples.append(dict(repetition=repetition, develop_seconds=elapsed,
                                      components=timing.report(), gaussian_calls=timing.sigma_samples))
        print(json.dumps(dict(repetition=repetition, develop_seconds=elapsed,
              components={k:round(v['inclusive_seconds'],4) for k,v in timing.report().items()})), flush=True)

    summary = {}
    for label in component_samples[0]['components']:
        summary[label] = dict(
            median_inclusive_seconds=statistics.median(s['components'][label]['inclusive_seconds'] for s in component_samples),
            median_exclusive_seconds=statistics.median(s['components'][label]['exclusive_seconds'] for s in component_samples),
            calls_per_develop=component_samples[0]['components'][label]['calls'],
        )

    # Exact-opportunity experiment: radius zero FIR is the identity under the
    # current truncation. Return a copy to preserve original aliasing behavior.
    def original_small(image, sigma, truncate):
        if sigma <= 0:
            return image.copy()
        kernel, radius = filters._gaussian_kernel_1d(float(sigma), float(truncate))
        output = np.empty_like(image)
        filters._fir_2d_fused(image, output, kernel, radius)
        return output
    def skip_identity_fir(image, sigma, truncate):
        if sigma > 0 and int(truncate * sigma + .5) == 0:
            return image.copy()
        return original_small(image, sigma, truncate)

    # Disable only random microstructure for exact A/B. Particle layers seed
    # themselves, so their output remains deterministic with grain active.
    deterministic_params = digest_params(make_params(args.stock, physical_edge=physical_edge))
    deterministic_params.film_render.grain.micro_structure = (0., 0.)
    deterministic = Simulator(deterministic_params)
    deterministic.process_tap(values, inject='rgb_in', collect='rgb_pre')
    deterministic_node = next(n for n in deterministic._pipeline._topology if n.label == 'filming.develop')
    baseline_times, changed_times = [], []
    for _ in range(args.repeat):
        with patch.object(filters, '_gaussian_filter_2d_small', side_effect=original_small):
            start = time.perf_counter()
            reference = deterministic_node.run(log_raw)
            baseline_times.append(time.perf_counter()-start)
        with patch.object(filters, '_gaussian_filter_2d_small', side_effect=skip_identity_fir):
            start = time.perf_counter()
            actual = deterministic_node.run(log_raw)
            changed_times.append(time.perf_counter()-start)
    difference = np.abs(reference-actual)

    # Explicit zero-weight DIR test, independent of the default weight (.06).
    normalized_curves = np.asarray(params.film.data.density_curves)
    normalized_curves = normalized_curves-np.nanmin(normalized_curves, axis=0)
    density = develop.develop_simple(log_raw, np.asarray(params.film.data.log_exposure), normalized_curves)
    matrix = couplers.compute_dir_couplers_matrix(params.film_render.dir_couplers)
    max_density = np.nanmax(normalized_curves, axis=0)
    diffusion = params.film_render.dir_couplers
    args_dir = (log_raw, density, max_density, matrix,
                diffusion.diffusion_size_um/pixel_size_um, diffusion.diffusion_tail_um/pixel_size_um)
    def legacy_dir(log_raw, density, density_max, matrix, sigma, tail_sigma, weight):
        correction = couplers.contract('ijk, km->ijm', density, matrix)
        gaussian = couplers.fast_gaussian_filter(correction, sigma)
        gaussian *= 1-weight
        tail = couplers.fast_exponential_filter(correction, tail_sigma)
        tail *= weight
        gaussian += tail
        output = np.empty_like(log_raw)
        np.subtract(log_raw, gaussian, out=output)
        return output
    zero_times, skipped_times = [], []
    for _ in range(args.repeat):
        start = time.perf_counter()
        zero_reference = legacy_dir(*args_dir, 0)
        zero_times.append(time.perf_counter()-start)
        start = time.perf_counter()
        zero_actual = couplers.compute_exposure_correction_dir_couplers(*args_dir, diffusion_exp_tail_weight=0)
        skipped_times.append(time.perf_counter()-start)

    report = dict(
        measured_at=time.strftime('%Y-%m-%d %H:%M:%S %z'),
        source=dict(path=str(args.source), sha256=source_sha, source_dimensions=list(source_size),
                    sample_dimensions=list(image.size), sample_path=str(args.decode_cache), decode_mode=decode_mode,
                    source_unchanged=hashlib.sha256(args.source.read_bytes()).hexdigest()==source_sha),
        environment=dict(os=platform.platform(), python=sys.version, numba_threads=numba.get_num_threads(),
                         cpu=platform.processor(), gpu_used=False),
        scope='full-mode filming.develop from cached real-source log_e_film; excludes RAW decode, expose, print, scan, encode, UI and GPU; sample preserves source physical pixel pitch',
        decode_seconds=decoded_seconds, expose_seconds=exposed_seconds, physical_pixel_size_um=pixel_size_um,
        parameters=dict(stock=args.stock, dir=dataclasses.asdict(diffusion), grain=dataclasses.asdict(params.film_render.grain)),
        develop_times_seconds=total_seconds, median_develop_seconds=statistics.median(total_seconds),
        component_summary=summary, repetitions=component_samples,
        exact_experiments=dict(
            skip_radius_zero_fir=dict(baseline_seconds=baseline_times, candidate_seconds=changed_times,
                max_abs_error=float(difference.max()), exactly_equal=bool(np.array_equal(reference,actual)),
                speedup=statistics.median(baseline_times)/statistics.median(changed_times),
                grain_active=True, microstructure_disabled_for_exact_comparison=True),
            skip_zero_weight_dir_tail=dict(baseline_seconds=zero_times, candidate_seconds=skipped_times,
                exactly_equal=bool(np.array_equal(zero_reference,zero_actual)),
                speedup=statistics.median(zero_times)/statistics.median(skipped_times),
                applies_to_default_parameters=diffusion.diffusion_tail_weight==0),
        ),
        notes=[
            'Nested component inclusive times overlap; use exclusive times for additive attribution.',
            'Physical pixel pitch is preserved from the original RAW so sublayer blur/microstructure exercise the real export-scale branches.',
            'Reduced-size total time must not be scaled linearly into a 24/61 MP guarantee; cache, memory bandwidth, thread scheduling and thermal state differ.',
            'Radius-zero shortcut preserves the exact finite FIR operation and output ownership; it does not change the Gaussian formula.',
            'DIR tail optimization matters only when its weight is zero, or symmetric Gaussian skip at weight one; default Portra is weight 0.06.',
            'Curve interpolation currently allocates zeros then immediately overwrites that array with fast_interp output; candidate removal avoids an allocation without changing math, but zero-page laziness means time savings need separate measurement.',
        ],
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(dict(output=str(args.output), median_develop_seconds=report['median_develop_seconds'],
                         experiments=report['exact_experiments'])), flush=True)


if __name__ == '__main__':
    main()
