"""Verify and time the isolated GPU blur against the upstream CPU formula.

Measures host-to-host work, including upload, submission, waiting and readback.
The CPU reference is Spektrafilm's existing FIR/YVV approximation, not an
analytic Gaussian; equal models and boundaries matter for this comparison.
No production route imports this prototype.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vendor"))
sys.path.insert(0, str(ROOT))

from desktop.gpu_blur_prototype import GaussianGpuPrototype
from spektrafilm.utils.fast_gaussian_filter import fast_gaussian_filter


def error_record(reference, actual):
    maximum = total = squared = 0.0
    left = reference.reshape(-1)
    right = actual.reshape(-1)
    for start in range(0, reference.size, 262_144):
        error = np.abs(left[start:start+262_144] - right[start:start+262_144])
        maximum = max(maximum, float(error.max()))
        total += float(error.sum())
        squared += float(np.dot(error, error))
    return {"max_abs_error": maximum, "mean_abs_error": total/reference.size,
            "rms_abs_error": float(np.sqrt(squared/reference.size))}


def verify(gpu, image, sigma, *, label, truncate=3.0):
    expected = fast_gaussian_filter(image, sigma, truncate)
    actual = gpu.filter(image, sigma, truncate)
    errors = error_record(expected, actual)
    # A scale-aware absolute bound for float32 output, including signed
    # values and near-zero pixels where relative error is uninformative.
    bound = 5e-6*max(1.0, float(np.max(np.abs(image))))
    record = {"case": label, "shape": list(image.shape),
              "sigma": np.asarray(sigma).tolist(), "truncate": truncate,
              "finite": bool(np.isfinite(actual).all()),
              "shape_preserved": actual.shape == image.shape,
              "dtype": str(actual.dtype), "error_bound": bound, **errors}
    record["passed"] = bool(record["finite"] and record["shape_preserved"]
                            and actual.dtype == np.float32
                            and errors["max_abs_error"] <= bound)
    if not record["passed"]:
        raise AssertionError(json.dumps(record))
    return record


def correctness_suite(gpu, height, width, sigmas):
    rng = np.random.default_rng(117)
    image = rng.uniform(-.5, 2.0, (height, width))
    records = [verify(gpu, image, sigma, label="signed_random") for sigma in sigmas]
    # DC gain, boundaries, a broad gradient and an impulse expose errors
    # that average random-image metrics alone can conceal.
    small_height, small_width = min(height, 97), min(width, 129)
    constant = np.full((small_height, small_width), 1.25)
    ramp = np.linspace(-.5, 2, small_height*small_width).reshape(small_height, small_width)
    edge = np.full((small_height, small_width), -.5)
    edge[:max(1, small_height//2), :max(1, small_width//2)] = 2
    impulse = np.zeros_like(edge)
    impulse[0, 0] = 1
    impulse[-1, -1] = 2
    for label, values in (("constant", constant), ("ramp", ramp),
                          ("edge", edge), ("corner_impulses", impulse)):
        for sigma in sigmas:
            records.append(verify(gpu, values, sigma, label=label))
    for shape in ((1, 1), (1, 9), (9, 1), (3, 7)):
        values = rng.uniform(-.5, 2, shape)
        for sigma in (1.0, 2.9, 3.0, 100.0):
            records.append(verify(gpu, values, sigma, label="tiny_reflect_or_replication"))
    rgb = rng.uniform(-.5, 2.0, (small_height, small_width, 3))
    for sigma in (0, -1, .5, 100, [.1, 5, 100]):
        records.append(verify(gpu, rgb, sigma, label="rgb_scalar_or_per_channel"))
    records.append(verify(gpu, ramp, 1.0, label="custom_fir_truncation", truncate=4))
    # Band boundaries must carry recursive state exactly: this is not a
    # finite-halo tile approximation. All segment sizes traverse identically.
    original_segment = gpu.segment_length
    segmented = rng.uniform(-.5, 2, (37, 83))
    outputs = []
    try:
        for segment in (1, 31, 256, 512):
            gpu.segment_length = segment
            outputs.append(gpu.filter(segmented, 100))
        equal = all(np.array_equal(outputs[0], output) for output in outputs[1:])
        if not equal:
            raise AssertionError("Recursive state changed at GPU band boundaries")
        records.append({"case": "segment_invariance", "segments": [1, 31, 256, 512],
                        "sigma": 100, "bit_identical": equal, "passed": equal})
    finally:
        gpu.segment_length = original_segment
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, default=768)
    parser.add_argument("--height", type=int, default=512)
    parser.add_argument("--channels", type=int, choices=(1, 3), default=1)
    parser.add_argument("--sigmas", default="0.1,0.5,1,2.9,3,5,20,100")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--segment-length", type=int, default=256)
    parser.add_argument("--backend", choices=("Vulkan", "D3D12", "Metal"), default="Vulkan")
    parser.add_argument("--skip-extended-checks", action="store_true",
                        help="Only compare the measured image; run the default suite separately first")
    parser.add_argument("--output", type=Path, default=ROOT / "output/gpu-blur-prototype.json")
    args = parser.parse_args()
    sigmas = [float(item) for item in args.sigmas.split(",")]
    if min(args.width, args.height, args.repeat) < 1 or not sigmas or not np.isfinite(sigmas).all():
        parser.error("Positive dimensions/repeat and finite sigmas required")
    gpu = GaussianGpuPrototype(backend=args.backend, segment_length=args.segment_length)
    # Compile CPU specializations and GPU pipelines outside measured runs.
    warm = np.random.default_rng(7).uniform(-.5, 2.0, (16, 19))
    for sigma in (.5, 5):
        fast_gaussian_filter(warm, sigma)
        gpu.filter(warm, sigma)
    correctness = [] if args.skip_extended_checks else correctness_suite(
        gpu, args.height, args.width, sigmas)
    shape = (args.height, args.width) + ((3,) if args.channels == 3 else ())
    source = np.random.default_rng(23).uniform(-.5, 2.0, shape)
    measurements = []
    for sigma in sigmas:
        cpu_times, gpu_times, stages = [], [], []
        for _ in range(args.repeat):
            started = time.perf_counter()
            expected = fast_gaussian_filter(source, sigma)
            cpu_times.append(time.perf_counter()-started)
            started = time.perf_counter()
            actual = gpu.filter(source, sigma)
            gpu_times.append(time.perf_counter()-started)
            stages.append(gpu.last_timings)
        errors = error_record(expected, actual)
        bound = 5e-6*max(1.0, float(np.max(np.abs(source))))
        valid = actual.shape == source.shape and np.isfinite(actual).all() and errors["max_abs_error"] <= bound
        if not valid:
            raise AssertionError(f"Timing image failed validation: {sigma}: {errors}")
        cpu_median, gpu_median = float(np.median(cpu_times)), float(np.median(gpu_times))
        measurements.append({"sigma": sigma, "cpu_median_seconds": cpu_median,
            "gpu_host_to_host_median_seconds": gpu_median, "speedup": cpu_median/gpu_median,
            "cpu_seconds": cpu_times, "gpu_host_to_host_seconds": gpu_times,
            "gpu_stages": stages, "shape_preserved": True, "passed": True, **errors})
        print(json.dumps({"sigma": sigma, "cpu_s": cpu_median, "gpu_s": gpu_median,
                          "max_abs_error": errors["max_abs_error"]}), flush=True)
    report = {"prototype_only": True, "adapter": dict(gpu.adapter.info),
        "wgpu_version": gpu._wgpu.__version__, "shape": list(shape),
        "input_dtype": str(source.dtype), "output_dtype": str(actual.dtype),
        "backend": args.backend, "segment_length": args.segment_length,
        "reference": "vendor/spektrafilm/utils/fast_gaussian_filter.py; FIR<3, YVV>=3",
        "boundaries": {"FIR": "reflect", "YVV": "sample replication"},
        "timing_scope": "host-to-host, original dimensions, upload/dispatch/wait/readback included",
        "plane_bytes": args.height*args.width*4,
        "correctness_checks": correctness, "measurements": measurements,
        "limitations": ["Metal requires separate Mac validation",
            "Full float32 plane allocation; recursive segmentation does not remove that memory requirement",
            "One blur stage, not full film rendering or end-to-end app response",
            "No Android device benchmark or production integration"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Passed {len(correctness)} extended checks; report: {args.output}")


if __name__ == "__main__":
    main()
