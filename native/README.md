# Native spectral GPU work

The shared WGSL density kernels in `shaders/` and
`desktop/gpu_gamut_prototype.py` preserve individual stages of the existing
spectral model. They do not yet form a complete native spectral pipeline.
Windows development rendering can opt into the validated CAM16-UCS output-gamut
stage through `desktop/compute.py`; all other stages retain their existing
implementations. This does not imply subsecond end-to-end rendering or export.

The Windows path explicitly requests Vulkan. D3D12 was also compared on the
same physical RTX 3070 Ti Laptop GPU, with adapter device ID recorded because
the D3D12 device name on this host incorrectly says RTX 5090. Vulkan has lower
numerical error in the recorded CAM16 fixture and is the selected production
adapter. Android Vulkan and macOS Metal remain planned integrations; neither
has been compiled and validated on target hardware in this workspace.

Install `requirements.txt` for the desktop application. The development-only
entry `requirements-gpu-dev.txt` also pins wgpu 0.33.0. Run
`scripts/benchmark_gpu_density_interp.py` for the density stage, or
`scripts/benchmark_gpu_gamut.py --backend Vulkan` for CAM16-UCS. Density tests
accept a read-only source photo; benchmark inputs are never written. Reports go
under `output/` and distinguish warm stage transfer/dispatch/readback from
device creation, RAW development, other spectral stages and file encoding.

The gamut adapter serializes access, releases temporary buffers in `finally`,
uses explicit staging map/unmap, supports cancellation between bounded strips
and preserves the complete output dimensions. The validated integration is
restricted to linear sRGB, `cam16ucs`, default chroma knee `(0,1,6)` and
lightness knee `(0.7,1,2.2)`. Other specifications retain the CPU reference.

See [stage validation and packaging](docs/gpu-stage-validation.md),
[engine decisions](../docs/gpu-performance-engine.md) and
[GPU notices](../licenses/GPU-NOTICE.md). Final pipeline adoption still needs
color/grain comparisons, spatial-filter halo correctness, actual 61/100MP peak
memory measurements, packaged application smoke tests and per-device testing.
