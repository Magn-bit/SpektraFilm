"""Validate and time experimental Vulkan CAM16-UCS against the actual CPU path."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"vendor"))

from desktop.gpu_gamut_prototype import GamutGpuPrototype
from spektrafilm.utils.gamut_compression import OutputGamutCompressSpec,compress_rgb


def validation_values():
    """Fixed boundary, near-black, bright and out-of-gamut finite samples."""
    rng=np.random.default_rng(5219)
    cube=np.asarray(np.meshgrid(*([[-0.001,0,1e-8,1e-5,.02,.18,.5,1,1.01,2,8]]*3),indexing="ij")).reshape(3,-1).T
    neutral=np.repeat(np.concatenate(([0],np.geomspace(1e-12,16,192)))[:,None],3,axis=1)
    ordinary=rng.uniform(0,1,(8000,3))
    dark=rng.uniform(0,1,(4000,3))*10**rng.uniform(-10,-2,(4000,1))
    vivid=rng.exponential(.8,(6000,3))
    vivid[np.arange(len(vivid)),rng.integers(0,3,len(vivid))]=0
    # Small negatives are common at colour-matrix boundaries. Deliberately
    # pathological negative luminance is recorded separately, never sanitized.
    negative=rng.uniform(-.05,1.2,(4000,3))
    return np.ascontiguousarray(np.concatenate([cube,neutral,ordinary,dark,vivid,negative]),dtype=np.float64)


def compare(reference,actual):
    import colour
    finite=np.all(np.isfinite(reference),axis=-1)&np.all(np.isfinite(actual),axis=-1)
    errors=np.abs(reference[finite]-actual[finite])
    cs=colour.RGB_COLOURSPACES["sRGB"]
    def lab(rgb):
        xyz=colour.RGB_to_XYZ(rgb,"sRGB",apply_cctf_decoding=False)
        return colour.XYZ_to_Lab(xyz,illuminant=cs.whitepoint)
    de=colour.delta_E(lab(reference[finite]),lab(actual[finite]),method="CIE 2000")
    worst=int(np.argmax(np.max(np.where(finite[:,None],np.abs(reference-actual),-1),axis=-1)))
    return {
        "samples":len(reference),"finite_reference_pixels":int(np.all(np.isfinite(reference),axis=-1).sum()),
        "finite_gpu_pixels":int(np.all(np.isfinite(actual),axis=-1).sum()),
        "finite_mask_disagreements":int(np.count_nonzero(np.all(np.isfinite(reference),axis=-1)!=np.all(np.isfinite(actual),axis=-1))),
        "cpu_nan_components":int(np.isnan(reference).sum()),"gpu_nan_components":int(np.isnan(actual).sum()),
        "max_abs_linear_rgb_error":float(errors.max()),"mean_abs_linear_rgb_error":float(errors.mean()),
        "p99_abs_linear_rgb_error":float(np.quantile(errors,.99)),
        "delta_e_2000_max":float(np.nanmax(de)),"delta_e_2000_mean":float(np.nanmean(de)),
        "delta_e_2000_p99":float(np.nanquantile(de,.99)),"worst_sample":worst,
        "worst_cpu":reference[worst].tolist(),"worst_gpu":actual[worst].tolist(),
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--width",type=int,default=1000)
    parser.add_argument("--height",type=int,default=1000)
    parser.add_argument("--repeat",type=int,default=3)
    parser.add_argument("--backend",choices=("Vulkan","D3D12"),default="Vulkan")
    parser.add_argument("--gpu-strip-pixels",type=int,default=0,
                        help="GPU strip pixel budget (0: one device-sized buffer per call)")
    parser.add_argument("--cpu-strip-rows",type=int,default=0,
                        help="Optional bounded-memory CPU strip height (0: whole array)")
    parser.add_argument("--output",type=Path,default=ROOT/"output/gpu-gamut-prototype.json")
    args=parser.parse_args()
    if args.width<=0 or args.height<=0 or args.repeat<1 or min(args.cpu_strip_rows,args.gpu_strip_pixels)<0:
        parser.error("Dimensions and repeat must be positive; strip budgets cannot be negative")
    init=time.perf_counter()
    gpu=GamutGpuPrototype(backend=args.backend,max_pixels_per_dispatch=args.gpu_strip_pixels)
    try:
        init_seconds=time.perf_counter()-init
        spec=OutputGamutCompressSpec()
        probe=validation_values()
        with np.errstate(all="ignore"):
            reference=compress_rgb(probe,spec,output_color_space="sRGB")
        actual=gpu.compress_rgb(probe)
        validation=compare(reference,actual)
        validation["worst_input"]=probe[validation["worst_sample"]].tolist()
        # Keep the performance fixture deterministic, physical and separate from
        # the small adversarial correctness set. CPU and GPU consume the same
        # float32-representable input, isolating calculation rather than casting.
        rng=np.random.default_rng(71)
        source=rng.uniform(0,1.5,(args.height,args.width,3)).astype(np.float32)
        start=time.perf_counter()
        if args.cpu_strip_rows:
            reference=np.empty(source.shape,dtype=np.float64)
            for row in range(0,args.height,args.cpu_strip_rows):
                stop=min(row+args.cpu_strip_rows,args.height)
                reference[row:stop]=compress_rgb(source[row:stop],spec,output_color_space="sRGB")
        else:
            reference=compress_rgb(source,spec,output_color_space="sRGB")
        cpu_seconds=time.perf_counter()-start
        times=[]
        for _ in range(args.repeat):
            start=time.perf_counter()
            actual=gpu.compress_rgb(source)
            times.append(time.perf_counter()-start)
        perf_error=np.abs(actual.astype(np.float64)-reference)
        report={
            "scope":"Isolated float32 CAM16-UCS gamut stage prototype; not production render or export timing",
            "adapter":dict(gpu.adapter.info),"backend_required":args.backend,
            "device_name_warning":"Physical hardware is RTX 3070 Ti Laptop (NVIDIA device_id=9376); D3D12 reports a spoofed 5090 name",
            "versions":{"numpy":np.__version__,"wgpu":gpu._wgpu.__version__,"python":sys.version.split()[0]},
            "initialization_seconds":init_seconds,"cmax_cpu_setup_seconds":gpu.setup_seconds,
            "colour_model":"Colour 0.4.7 CAM16 (Li2017) UCS; same Cmax table and spec as CPU",
            "validation":validation,"dimensions":[args.width,args.height],
            "cpu_strip_rows":args.cpu_strip_rows,
            "gpu_strip_pixels":args.gpu_strip_pixels,
            "cpu_seconds":cpu_seconds,"gpu_seconds_upload_dispatch_readback":times,
            "gpu_median_seconds_upload_dispatch_readback":float(np.median(times)),
            "speedup_complete_call":cpu_seconds/float(np.median(times)),
            "performance_max_abs_linear_rgb_error":float(perf_error.max()),
            "performance_mean_abs_linear_rgb_error":float(perf_error.mean()),
            "performance_gpu_nan_components":int(np.isnan(actual).sum()),
            "production_changed":False,
        }
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(report,ensure_ascii=False,indent=2))
    finally:
        gpu.close()


if __name__=="__main__":
    main()
