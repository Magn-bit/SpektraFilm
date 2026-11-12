# SpektraLab 2.2 physical composition integration

Reference: SpektraLab 2.2.0, source revision
`2201f5fa4d256b0c742b46b8e31f8176a12ca6ea` (2026-11-08), inspected
2026-11-09. Source paths: `engine/src/pipeline/overscan.cpp`,
`engine/src/core/params.*`, `app/SpektraLab/Sources/FilmEdge/`,
`Features/FilmEdge/FilmEdgeSteps.swift`, and the native half-frame tests.
Attribution: `licenses/spektralab-composition/NOTICE.md`.

## Physical model and module boundary

- 135 has 35 mm film width and a measured 36.25 × 24.3 mm gate. Perforations
  use 4.75 mm pitch, 1.98 × 2.80 mm holes and 0.50 mm corner radius.
- Half frames have 18 × 24 mm gates and 19 mm advance. The source is
  18 + 1 + 18 mm, with unexposed film between the two photographs.
- 120 is 61 mm wide without perforations. Available gates include 6×4.5,
  6×6, 6×7, 6×8, 6×9, 6×12 and 6×17; 135 also supports XPan.
- Stock words are actual manufacturer labels, e.g. `EASTMAN 5219`. The native
  renderer owns Kodak/Fuji/Ilford/cine edge-print families and DX marks.
- The rebate/date back is exposed on the negative before halation and grain;
  the native scanner illuminates holes after development. It is not a graphic
  rectangle drawn around a finished photograph.

`shared/composition_edge.native_overscan_options` maps UI options to the exact
native names and enums. `desktop/film_canvas.render_film_edge` performs
source-precision preparation, physical gate crop, scene exposure, pair-source
assembly and post-tool projection. `desktop/native_spectral.render_film_canvas`
is the explicit API allowed to return an expanded native canvas. Ordinary
photo rendering retains its strict same-size guard. Source RGB conversion uses
the native `spk_output_transform` matrix and its CAT02 whitepoint adaptation;
there is no separate color library guessing the engine's source transform.

A pair decodes and white-balances each photograph independently, combines
unclipped linear ProPhoto sources and runs one common stock/paper pipeline.
Per-hole print trims use the native `Request.pair` path on the cached negative:

```python
{"left": {"print": {"brightnessStops": -settings.print_exposure,
                     "yFilterShift": settings.print_y / 100,
                     "mFilterShift": settings.print_m / 100,
                     "preflashExposure": settings.preflash_exposure},
          "adjustments": {"enabled": False}},
 "right": {...}, "turned": False, "printEffects": True}
```

The existing full post editor (including source-coordinate masks, curves,
levels/HDR) is preserved independently for each hole. Only its adjustment
delta is projected back through the exact native gate quad; neutral pixels
avoid another resample. Large projection scratch uses disk-backed float32 and
96-row coordinate strips. Independent print effects therefore remain native;
two separately completed film renders are never pasted into a physical pair.

## Qt workspace

Physical film presets and graphic paper layouts are separate. A compact, initially collapsed native-thumbnail selector offers 135, 120 6×6, filed, XPan, 120 6×7 and a two-source half-frame. Only explicitly opened templates are generated, one at a time; main canvas requests take priority. The
large photo canvas is followed by a stable-width, internally scrolling sidebar
and a fixed export area. No duplicate style dropdown or decorative rules are
added. Framing separates current-photo rotation from whole-group rotation,
supports linked position/zoom and swaps, and retains correct drag axes after
rotation. A vertical pair starts with the first source at the top.

The film section exposes gauge, full/filed scan, actual gate family, carrier,
light/black holes, stock wording, frame number, fog and leaks. Date backs
support EXIF/manual date, LCD/dots/data style, frame/rebate placement, corner,
exposure and size. RAW EXIF lookup runs in the worker, not the GUI thread.
The source's historical `StockGauges` table limits known 135-only materials;
unknown extensions keep physical format choices but use neutral `FILM` words
and no invented DX number. Missing capture dates stay absent until the user
enters a date; the app does not fabricate a capture timestamp.

Native preview work coalesces the latest options after 55 ms and never queues
each slider move. Native pixels and `spk_overscan_geometry` quads are displayed
directly; there is no Pillow film-border fallback. Multi-strip preview follows
the original-source layout at a bounded proxy size. Physical output reopens
original sources; a selected long edge is the only requested reduction. Preview
and export share stable camera/frame identity.

Paper, instant-print and contact-sheet layouts remain separate graphic output.
TIFF/PNG use RGB16 and highest-quality JPEG uses quality 100, with real ICC.

## Verification and remaining size validation

- Original composition suite: 6/6 passed.
- `scripts/verify_composition_frames.py`: 6 actual card choices, keyboard,
  36 large-source/window fitting checks; zero QML errors.
- `scripts/verify_physical_composition.py`: real Sony A7CR
  9564 × 6376 RAW as a bounded 1000 px preview; native 135 and 120 6×6
  canvases; two independent RGB16 originals exported as 2525 × 2334 TIFF16,
  valid ICC and more than 256 output values; vertical pair and native date
  exposure; zero QML errors. Evidence: `output/composition-native-review/`.
- Independent native print check: changing only the second hole by +1 EV
  changes its mean RGB by 0.2170 while the first hole changes by exactly 0.0.
  Request mapping is recorded in `independent-print.json`.

The bounded real-RAW preview is not a claim that a full 61/100 MP overscan
export has been performance-accepted. The native global-canvas bounded path
is being validated separately; one representative full-source check is needed
after that interface stabilizes. No preview upscaling or same-size striped
executor is used as a substitute for a physical full-source export.


## 2026-11-09 screenshot refinement

The sidebar ScrollView has an explicit shrinkable viewport and content height; the opaque output footer participates in the layout. Six physical style thumbnails no longer occupy the initial viewport. Existing developed/source proxies remain visible while the native canvas is preparing, and native failures offer a retry. The independent half-frame print bridge now forwards each source's preflash exposure rather than replacing it with zero. New bounded evidence is recorded in `output/lab-frames-papers-review/`; it supplements the original full-source export validation without repeating large RAW exports.
