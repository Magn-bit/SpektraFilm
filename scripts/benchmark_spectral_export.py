"""Measure one full-resolution desktop spectral render and its peak memory."""
import argparse
import ctypes
import json
import os
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

import numpy as np
import numba
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor"))

from desktop.imaging import (
    Settings, _SPECTRAL_CONTEXTS, _SPECTRAL_CONTEXTS_LOCK,
    _SPECTRAL_CONTEXT_SIGNATURES, render,
)
from spektrafilm import Simulator, init_params
import spektrafilm.model.develop as develop_module
import spektrafilm.model.grain as grain_module
from spektrafilm.runtime.params_builder import digest_params


class ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def process_memory_mib():
    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    get_info = ctypes.WinDLL("psapi").GetProcessMemoryInfo
    get_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessMemoryCounters), wintypes.DWORD]
    if not get_info(wintypes.HANDLE(-1), ctypes.byref(counters), counters.cb):
        return None, None
    return (
        round(counters.WorkingSetSize / 1024**2, 1),
        round(counters.PeakWorkingSetSize / 1024**2, 1),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--width", type=int, default=6000)
    parser.add_argument("--height", type=int, default=4000)
    parser.add_argument("--stock", default="kodak_portra_400")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--edge", type=int, default=0, help="Read-only source proxy edge; 0 keeps full dimensions")
    parser.add_argument("--numba-threads", type=int)
    parser.add_argument("--compute",choices=("auto","cpu"),default="auto")
    parser.add_argument("--output", type=Path, default=ROOT / "output/spectral-export-benchmark.json")
    args = parser.parse_args()
    os.environ['SPEKTRAFILM_COMPUTE']=args.compute
    if args.numba_threads is not None:
        numba.set_num_threads(args.numba_threads)

    if args.source:
        from desktop.imaging import read_photo
        source = read_photo(str(args.source), args.edge or None)
        pixels = np.asarray(source)
        args.width, args.height = source.size
    else:
        pixels = np.random.default_rng(17).integers(
            0, 256, (args.height, args.width, 3), dtype=np.uint8
        )
        source = Image.fromarray(pixels)
    settings = Settings(stock=args.stock, spectral=True)
    params = init_params(settings.stock, settings.paper)
    params.io.input_color_space = "sRGB"
    params.io.input_cctf_decoding = True
    params.io.scan_film = params.film.is_positive
    params.camera.auto_exposure = False
    params.camera.exposure_compensation_ev = settings.exposure
    params.settings.use_enlarger_lut = True
    params.settings.use_scanner_lut = True
    params.settings.preview_mode = False
    params.settings.preview_max_size = max(args.width, args.height)
    params.film_render.grain.active = settings.grain > 0
    params.film_render.grain.particle_area_um2 = 0.2 * (settings.grain / 25) ** 2
    params.film_render.grain.uniformity=(.97,.97,.97)
    params.film_render.grain.blur=.65
    params.film_render.grain.blur_dye_clouds_um=1.0
    params.film_render.halation.active = settings.halation > 0
    params.film_render.halation.halation_amount = settings.halation / 25
    params.film_render.halation.scatter_amount = settings.halation / 25
    simulator = Simulator(digest_params(params))
    signature = (
        settings.exposure, settings.grain,settings.grain_size,settings.grain_type,settings.halation,
        False, pixels.shape[:2],
    )
    with _SPECTRAL_CONTEXTS_LOCK:
        _SPECTRAL_CONTEXTS[(settings.stock, settings.paper)] = simulator
        _SPECTRAL_CONTEXT_SIGNATURES[(settings.stock, settings.paper)] = signature

    baseline_working_set = process_memory_mib()[0]
    stage_state = {"active": None}
    component_state = {"active": None}
    stage_lock = threading.Lock()
    stage_peaks = {}
    stage_end = {}
    component_peaks = {}
    component_end = {}
    component_seconds = {}
    stop_sampling = threading.Event()

    def sample_memory():
        while not stop_sampling.wait(0.02):
            working_set = process_memory_mib()[0]
            if working_set is None:
                continue
            with stage_lock:
                label = stage_state["active"]
                if label is not None:
                    stage_peaks[label] = max(stage_peaks.get(label, 0), working_set)
                component = component_state["active"]
                if component is not None:
                    component_peaks[component] = max(
                        component_peaks.get(component, 0), working_set
                    )

    import desktop.imaging as imaging_module
    import spektrafilm.runtime.stages.scanning as scanning_module
    scan = simulator._pipeline._scanning_stage
    film = simulator._pipeline._filming_stage
    for module, name, label in (
        (develop_module, "develop_simple", "develop.curve_interpolation"),
        (develop_module, "apply_density_correction_dir_couplers", "develop.dir_couplers"),
        (develop_module, "apply_grain", "develop.grain"),
        (grain_module, "layer_particle_model", "grain.layer_sampling"),
        (grain_module, "add_micro_structure", "grain.micro_structure"),
        (grain_module, "fast_gaussian_filter", "grain.gaussian_filter"),
        (scan, "_apply_blur_and_unsharp", "scan.blur_unsharp"),
        (scan, "_apply_cctf_encoding", "scan.output_encoding"),
        (scanning_module, "add_glare", "scan.glare"),
        (scanning_module.colour, "XYZ_to_RGB", "scan.xyz_to_rgb"),
        (imaging_module, "compress_output_gamut", "scan.gamut"),
        (film, "_rgb_to_film_raw", "film.spectral_upsampling"),
    ):
        original_call = getattr(module, name)

        def measured_component(*values, _call=original_call, _label=label, **kwargs):
            with stage_lock:
                previous = component_state["active"]
                component_state["active"] = _label
            began = time.perf_counter()
            try:
                return _call(*values, **kwargs)
            finally:
                component_seconds[_label] = component_seconds.get(_label, 0) + time.perf_counter()-began
                component_end[_label] = process_memory_mib()[0]
                with stage_lock:
                    component_state["active"] = previous

        setattr(module, name, measured_component)

    for node in simulator._pipeline._topology:
        original_run = node.run

        def measured_run(*values, _run=original_run, _label=node.label):
            with stage_lock:
                stage_state["active"] = _label
            try:
                return _run(*values)
            finally:
                stage_end[_label] = process_memory_mib()[0]
                with stage_lock:
                    stage_state["active"] = None

        object.__setattr__(node, "run", measured_run)

    sampler = threading.Thread(target=sample_memory, daemon=True)
    sampler.start()
    start = time.perf_counter()
    try:
        rendered = render(source, settings)
    finally:
        elapsed = time.perf_counter() - start
        stop_sampling.set()
        sampler.join()
    process_peak = process_memory_mib()[1]

    report = {
        "dimensions": [args.width, args.height],
        "megapixels": round(args.width * args.height / 1_000_000, 3),
        "mode": "full spectral, default grain, final-resolution render",
        "numba_threads": numba.get_num_threads(),
        "compute_requested":args.compute,
        "seconds": round(elapsed, 3),
        "peak_working_set_mib": process_peak,
        "baseline_working_set_mib": baseline_working_set,
        "stage_peak_working_set_mib": stage_peaks,
        "stage_end_working_set_mib": stage_end,
        "component_peak_working_set_mib": component_peaks,
        "component_end_working_set_mib": component_end,
        "component_timings_seconds": component_seconds,
        "stage_timings_seconds": simulator.get_timings(),
        "output_size": list(rendered.size),
        "note": "Render timing excludes file encoding and disk I/O.",
    }
    from desktop.compute import status
    report['compute']=status()
    report['source']=str(args.source) if args.source else 'fixed synthetic random RGB8 seed=17'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
