"""Compare experimental Vulkan density interpolation with the CPU reference."""
import argparse
import json
import sys
import time
import hashlib
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vendor"))
sys.path.insert(0, str(ROOT))

from desktop.gpu_prototype import SpectralGpuPrototype
from shared.film_profiles import init_film_params
from spektrafilm.utils.fast_interp import fast_interp


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--width", type=int, default=6000)
    parser.add_argument("--height", type=int, default=4000)
    parser.add_argument("--curves", type=int, default=4096)
    parser.add_argument("--stock", default="kodak_portra_400")
    parser.add_argument("--backend", choices=("Vulkan","D3D12","Metal"), default="Vulkan")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--edge", type=int, default=0)
    parser.add_argument("--output", type=Path, default=ROOT / "output/gpu-density-prototype.json")
    args = parser.parse_args()

    rng = np.random.default_rng(71)
    params = init_film_params(args.stock)
    source_record={}
    if args.source:
        from desktop.imaging import read_photo
        from spektrafilm import Simulator, digest_params
        source_hash=hashlib.sha256(args.source.read_bytes()).hexdigest()
        image=read_photo(str(args.source),args.edge or None)
        params.io.input_color_space="sRGB"
        params.io.input_cctf_decoding=True
        params.camera.auto_exposure=False
        values=np.asarray(image,dtype=np.float64)/255
        exposure_start=time.perf_counter()
        source=Simulator(digest_params(params)).process_tap(
            values,inject="rgb_in",collect="log_e_film"
        )
        source_record={"path":str(args.source),"sha256":source_hash,
            "source_size":list(image.info.get("source_size",image.size)),
            "sample_size":list(image.size),"expose_seconds":round(time.perf_counter()-exposure_start,4)}
    else:
        source = np.ascontiguousarray(
            rng.uniform(-8, 0, (args.height, args.width, 3)), dtype=np.float64
        )
    axis = np.asarray(params.film.data.log_exposure)
    curves = np.asarray(params.film.data.density_curves)
    curves = curves - np.nanmin(curves, axis=0)
    gpu = SpectralGpuPrototype(backend=args.backend)
    fast_interp(source[:1,:min(64,source.shape[1])],axis,curves)
    gpu.interpolate_density(source[:1,:min(64,source.shape[1])],axis,curves)
    cpu_times=[]
    gpu_times=[]
    for _ in range(args.repeat):
        start = time.perf_counter()
        reference = fast_interp(source, axis, curves)
        cpu_times.append(time.perf_counter() - start)
        start = time.perf_counter()
        actual = gpu.interpolate_density(source, axis, curves)
        gpu_times.append(time.perf_counter() - start)
    max_error=0.0
    sum_error=0.0
    reference_flat=reference.reshape(-1)
    actual_flat=actual.reshape(-1)
    for start in range(0,len(reference_flat),262144):
        error=np.abs(reference_flat[start:start+262144]-actual_flat[start:start+262144])
        max_error=max(max_error,float(error.max()))
        sum_error+=float(error.sum())
    cpu_seconds=float(np.median(cpu_times))
    gpu_seconds=float(np.median(gpu_times))
    report = {
        "adapter": dict(gpu.adapter.info),
        "dimensions": [source.shape[1], source.shape[0]],
        "source":source_record,
        "stock": args.stock,
        "curve_count": len(axis),
        "cpu_seconds": round(cpu_seconds, 4),
        "gpu_seconds_upload_dispatch_readback": round(gpu_seconds, 4),
        "gpu_speedup": round(cpu_seconds / gpu_seconds, 3),
        "cpu_times_seconds":cpu_times,
        "gpu_times_seconds":gpu_times,
        "max_abs_error": max_error,
        "mean_abs_error": sum_error/reference.size,
        "output_shape": list(actual.shape),
        "output_dtype": str(actual.dtype),
    }
    if args.source:
        report["source"]["unchanged"]=hashlib.sha256(args.source.read_bytes()).hexdigest()==source_hash
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
