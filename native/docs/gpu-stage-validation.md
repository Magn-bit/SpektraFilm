# GPU stage validation and desktop packaging

Recorded on 2026-11-07, Windows, Python 3.12.14, NumPy 2.3.5, Colour 0.4.7,
wgpu-py 0.33.0 and wgpu-native 29.0.1.1. Physical GPU: NVIDIA GeForce RTX 3070 Ti
Laptop, PCI vendor `4318`, device `9376`, driver `621.01`. The D3D12 adapter name
is modified on this host and incorrectly reports RTX 5090; it is the same
device ID as Vulkan and is not a second physical GPU.

## Verified stage and limits

`desktop/gpu_gamut_prototype.py` transcribes Colour's CAM16/Li2017 model, uses
the current CPU Cmax table and executes both forward and inverse transforms in
float32 WGSL. This is the CAM16-UCS output-gamut stage, not spectral exposure,
film development, DIR, grain, paper exposure, RAW decoding or export encoding.
No source/export resizing is introduced.

The production adapter only accepts default output compression in linear sRGB:
`algorithm=cam16ucs`, `knee=(0,1,6)`, `lightness_compression=(0.7,1,2.2)`.
`supports_spec` checks this contract; `compress_for_spec` rejects other specs.
Diagnostic modes and custom knees in `compress_rgb` are not covered by that
integration contract. CPU routing remains the caller's explicit policy.

The fixture contains 23,524 cube-boundary, near-black, neutral, saturated,
superwhite and small-negative RGB samples. Both backends produce finite results
where the CPU fixture is finite, including exact black. Zero-angle handling is
explicit because D3D12 `atan2(0,0)` produced NaN before that boundary fix.
Undefined chroma for certain negative CAM colors follows Colour's neutral
inverse behavior. No blanket input/output clipping hides errors.

| Warm isolated stage | Vulkan | D3D12 |
|---|---:|---:|
| 1MP transfer + dispatch + readback median (5 runs) | 9.953 ms | 8.829 ms |
| 24MP transfer + dispatch + readback median (3 runs) | 345.14 ms | 375.28 ms |
| Fixture maximum linear RGB absolute error | 0.00000673 | 0.00009531 |
| Fixture maximum CIEDE2000 | 0.000647 | 0.003473 |
| Fixture CPU/GPU finite-mask disagreements | 0 | 0 |

Reports: `output/gpu-gamut-prototype-1mp.json`,
`output/gpu-gamut-prototype-24mp.json` and their `d3d12` equivalents.
24MP CPU reference runs use 128-row strips; the final two runs took 13.73 and
13.14 seconds. These sequential measurements are affected by host load and do
not establish a universal speed ratio. Device/table/shader setup is separately
reported (about 2.7–2.9 seconds including adapter enumeration); the table itself
took about 0.45–0.59 seconds. The initial small correctness dispatch warms the
pipeline before timing. Benchmark GPU strip budget `0` allows one buffer up to
the device limit. Production uses bounded strips instead.

The full application still contains CPU work and transfer boundaries. These
stage numbers must never be described as full-image import, preview or export
times. Vulkan is preferred here for its lower numerical error and 24MP result;
other hardware/driver combinations need their own correctness and timing runs.

## Resources and cancellation

The default strip budget is 4,194,304 pixels, about 48 MiB per packed RGB buffer.
Input, output and staging buffers are released in `finally`; readback is
explicitly mapped/unmapped. The persistent table and device are released by
idempotent `close()` or the context manager. A per-instance lock serializes
device use and closure. Noncontiguous/float64 input is converted one strip at
a time with `nditer`, avoiding an additional full-image float32 input copy.
The final float32 result retains the full source shape. This bounds temporary
GPU allocation, not the application's complete resident memory.

Cancellation is checked before and between strips. Submitted GPU work completes
before cancellation is observed; it cannot be interrupted mid-dispatch.
Nonempty real RGB shape, finite float32 input, knee parameters and closed-device
state are validated. A seven-pixel strip check covers odd dimensions and a
noncontiguous float64 source; shape, spec gate, invalid input, cancellation and
repeated closure were exercised. There is no 61/100MP device/peak-memory result
yet, and no claim of bounded spatial-filter halo behavior.

## PyInstaller distribution

wgpu 0.33.0's installed wheel registers its official hook through
`pyinstaller40:hook-dirs`. The hook collects `wgpu/resources` data (especially
`combined_header.h`), the platform native library and the dynamically selected
`wgpu.backends.auto` / `wgpu.backends.wgpu_native` modules. Both native headers
and the matching library must travel together. The Windows script now checks
the pinned wheel and resources before packaging, explicitly includes the native
backend and copies wgpu distribution metadata/license. The existing `licenses/`
bundle includes BSD-2-Clause wgpu-py, MIT/Apache wgpu-native and BSD-3-Clause
Colour notices; the shader source keeps its Colour and spektrafilm attribution.

Use the matching native wheel for the target architecture. Do not copy a DLL
from the Windows development host into macOS or Android builds. A frozen-app
GPU smoke test must run with development `PYTHONPATH` / `WGPU_LIB_PATH` cleared,
confirm `wgpu/resources/wgpu_native-release.dll` plus `combined_header.h` and
check an actual GPU result. Presence in the bundle is separate from runtime
driver/device availability. Keep CPU reference routing for unsupported devices
and specs. See `licenses/GPU-NOTICE.md` for pinned sources.

The official hook is documented at
<https://github.com/pygfx/wgpu-py/blob/main/docs/guide.rst#freezing-apps>.
The installed 0.33.0 hook and wheel metadata were inspected directly; a final
frozen build must additionally verify hook execution in its build log.

## Platform status

Windows Vulkan is the only currently selected application GPU stage. D3D12 has
the isolated measurements above; it is not an automatic alternate backend.
macOS build configuration includes the native wgpu hook for a future native
Mac build, but `desktop.compute` currently gates the application path to Windows.
No Mac/Xcode or Apple Silicon device was available, so no Metal compilation,
Metal timing, app signature/notarization or Apple release is asserted. A future
Metal path needs explicit selection, numerical fixtures, large-photo memory
tests and native-host packaging. Android needs a separate wgpu-native C/JNI
integration and Vulkan device tests; its Python 3.10 runtime cannot simply use
the desktop wgpu 0.33 wheel, which requires Python 3.11 or newer.
