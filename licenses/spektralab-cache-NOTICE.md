# SpektraLab cache/detail reference

The working/proxy/full-result budget separation, pin/LRU lifecycle, atomic
publication, and viewport detail approach were studied against SpektraLab
2.2.0, commit `2201f5fa4d256b0c742b46b8e31f8176a12ca6ea`.

Source: https://github.com/JamesQiu2005/SpektraLab

Reference files: `app/SpektraLab/Sources/Services/WorkingCopies.swift`,
`Services/AppSettings.swift`, `Engine/FullRender.swift`, and
`Engine/FullDetail.swift`.

Copyright SpektraLab contributors. GNU GPL version 3; the full license is
preserved in `spektralab-composition/GPL-3.0.txt` and the project's `LICENSE`.

Changes: independently implemented Python/NumPy lossless array maps, per-output
colour-domain final-result reuse, Qt task cancellation and bounded display
patch publication. This project retains its existing direct-gamut native render
pipeline and does not use a matrix conversion as a replacement for that output.
