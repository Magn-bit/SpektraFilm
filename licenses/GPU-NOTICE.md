# GPU implementation notices

These notices supplement the project's GPL-3.0 license and existing third-party
notices. The optional Windows compute implementation retains the original
spektrafilm spectral model; the WGSL code in `desktop/gpu_gamut_prototype.py`
adapts the CAM16/Li2017 equations and fixed viewing setup from Colour 0.4.7 and
the output-gamut compression structure/table from Andrea Volpato's spektrafilm.
The adaptation uses float32 GPU arithmetic, stable knee/logarithm expressions,
explicit zero-angle handling and bounded GPU transfer strips. It does not copy
code from proprietary Lightroom, Capture One or SpektraLab applications.

| Component | Version / source | Retained license |
|---|---|---|
| wgpu-py | 0.33.0; <https://github.com/pygfx/wgpu-py> | `wgpu-py-BSD-2-Clause.txt`; Copyright (c) 2019–2023 Almar Klein, Korijn van Golen |
| wgpu-native | 29.0.1.1; commit `6aed50955d934ac36049ba8d002034841633ae02`; <https://github.com/gfx-rs/wgpu-native> | `wgpu-native-LICENSE-MIT.txt` and `wgpu-native-LICENSE-APACHE.txt`; Copyright (c) 2021 The gfx-rs developers |
| Colour | 0.4.7; <https://github.com/colour-science/colour> | `Colour-BSD-3-Clause.txt`; Copyright 2013 Colour Developers |
| spektrafilm | Bundled version recorded in `THIRD-PARTY.md` | Project `LICENSE` / `SPEKTRAFILM_LICENSE.txt`; GPL-3.0 code and separately licensed profile data |

The wgpu-native license texts were taken unmodified from the pinned upstream
commit above. The Python and Colour texts were copied unmodified from their
installed wheel license files. wgpu-py's official PyInstaller hook retains the
native library and its corresponding `combined_header.h`; the desktop packaging
commands additionally retain the wgpu distribution metadata and its license.

The driver and operating-system graphics libraries are provided by the host;
they are not copied from the development machine into the application package.
The current source and Python wheel checks do not constitute a signed or
notarized release, Metal validation, or Android GPU-device validation.
