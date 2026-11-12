# SpektraLab colour-tool reference

The four-region parametric-curve construction, movable-endpoint domain rules,
and encoded-RGB channel-mixer parameter contract are adapted from SpektraLab
2.2.0, commit `2201f5fa4d256b0c742b46b8e31f8176a12ca6ea`.

Source: https://github.com/JamesQiu2005/SpektraLab

Reference files: `app/SpektraLab/Sources/Model/CurveMath.swift`,
`app/SpektraLab/Sources/Model/Adjustments.swift`, and
`app/SpektraLab/Sources/Engine/Layer2Kernel.swift`.

Copyright SpektraLab contributors. GNU GPL version 3; the full license is
preserved in `spektralab-composition/GPL-3.0.txt` and the project's `LICENSE`.

Changes: portable Python/C++ parameter validation and composed curve tables,
Vulkan processing, bounded CPU reference, persistence and cache integration.
Existing PCHIP point interpolation and OKLab grading remain this project's
implementations. The global wheel extends that OKLab grading, rather than
copying the reference application's cosine RGB-offset colour-balance formula.
No proprietary Lightroom or Capture One code is included.
