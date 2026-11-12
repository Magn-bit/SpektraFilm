# Shared native editor and scene-linear RAW development

Updated 2026-11-08. This records the actual implementation and evidence; no
proprietary Lightroom or Capture One rendering algorithm is claimed.

## What the reference engine already contains

The checked-in SpektraLab source has substantially more functionality than the
former SpektraFilm product wiring exposed. `spk_solve` supplies seven exposure
meters and the neutral filter pack. `spk_scene_latitude` probes the real film/
paper pipeline with a neutral ramp, measures scene stop percentiles and returns
a fit as an explicit `params_delta`. Existing physical parameters include
separate scatter, back reflection, anti-halation removal, optical size, boost/
highlight protection, DIR coupling, film-curve gamma, and many print controls.

`pipeline/view_process.cpp` already provides a native GPU view layer for encoded
ProPhoto: basic grading, five curves, color balance, vignette, geometry and
output transforms. It does not implement the product's HSL, vibrance, primary
calibration or vector masks, and its adjustment contract differs from saved
SpektraFilm settings. It remains unchanged to preserve upstream behavior.

## Product editor boundary

`spk_editor_process(engine, image, request_json, output_rgb, elapsed_ms)` is the
new C boundary. `pipeline/editor_process.hpp` exposes the same implementation
to Android's direct C++ executor without constructing a second engine.

- Input and output are packed float32 RGB, identical dimensions. The caller
  owns output storage and may supply the same buffer as input or a memmap.
- `stage=pre` converts the source to sRGB coordinates and applies WB/primary
  calibration; `post` applies the editing operations; `all` performs both.
- Source space/transfer are explicit. Supported encoded sources are sRGB,
  Display P3, ProPhoto and Adobe RGB; a known linear source is also accepted.
- Pre defaults to no clamping, retaining negative matrix output and superwhite
  headroom. All-stage exposure defaults to `settings.exposure`; pre/post default
  to zero, overridable by `exposure_ev`. Post defaults to final sRGB clamping.
- The shared schema uses existing snake_case Settings fields. Curves are
  `master/red/green/blue/luma` point arrays. HSL is eight overlapping bands.
  Color grading uses three OKLab wheels. Brush/linear/radial masks follow
  `shared/local_masks.py`, including flow, erasing, feather and inversion.
- Mask coordinates remain those of the oriented full source before crop and
  geometry. Requests provide `source_width/height`, `origin_x/y` and
  `pixel_scale_x/y`. A full-frame proxy can therefore use source coordinates
  while an arbitrary final-size tile uses its actual source origin.
- GPU scratch is processed in strips, with two/three live RGB planes. Brush
  segments use a spatial index of 64 px cells instead of testing every segment
  against every photograph pixel. Texture and clarity have a source-size halo;
  original halo rows are preserved when the caller processes in place.
- This is a native GPU editing path, with no LUT or smaller-image substitution.
  Geometry, crop and output encoding remain downstream responsibilities.

`desktop/native_spectral.py` provides `process_editor`, `editor_request`,
`solve_spectral` and `scene_latitude`. The two analysis helpers only return
suggestions; the controller owns explicit application and undo.

`pipeline/editor_analyze.hpp` adds stateless native analysis for Android's
existing executor, using its GPU/Colour/Blob/SetupCache and resolved Params.
It returns the same solve/latitude JSON. A complete-frame proxy is required;
the analysis never commits settings. It shares the upstream meter, real ramp,
scene statistics and fit math. Images larger than 1600 px are reduced solely
for analysis with a bounded stratified sample.

## RAW source and display are separate

`spektrafilm_raw.dll` is independent of GPU initialization and compiles the
same LibRaw 0.22.3 source that Android vendors. Its metadata probe does not
unpack a sensor. Only selected photos should be demosaiced; adding a large
batch must remain metadata/thumbnail work.

Auto routing probes the layout before unpacking. Conventional three-color
Bayer with square pixels and unapplied as-shot WB uses the upstream headroom
path: max-normalized WB before integer AHD, actual camera-to-ProPhoto matrix
in float, restored exposure, retained negative and superwhite output. Other
layouts explicitly select compatible16. The chosen policy, limitation reason,
actual WB/matrix/black/white levels, geometry and timings are returned. There
is no hidden retry that disguises compatible16 as expanded headroom.

This does not recover sensor-clipped highlights, replace AHD with an all-float
sensor pipeline, or guarantee every commercial RAW compression. Unsupported
formats still fail with the decoder's actual error. The compatible path is
quantized RGB16 development, not a claim of sensor-level latitude recovery.

`desktop/raw_development.py` exposes metadata-only `probe_raw`, zero-full-copy
native-owned `decode_raw`, and `read_developed_raw` for the existing Pillow
source contract. Preview requests use half-size development and a bounded
proxy; final requests use the complete dimensions. The source ndarray is
read-only and remains alive until its final derived view is released.

The natural starting exposure is a robust one-percent highlight baseline,
bounded to -2..+3 EV. It is metadata, never clipped or baked into the source.
It is fixed by path/mtime/size/full dimensions in an LRU of 256 entries, so a
preview and final render of the same input use identical initial placement.
The UI's zero exposure is relative to that baseline. `source_metadata(image)`
also describes source color space and transfer independently of the RGB8
display surface. Optical defringe should operate on the proper encoded sRGB
development, with its baseline then cleared to avoid applying it twice.

## Key-node validation

On the NVIDIA GeForce RTX 3070 Ti Laptop GPU, the Windows Release native build
and four targeted GPU integration checks passed. They cover: HSL/curves/
three-way grading/vector masks against the existing Python reference; negative
exposure applied before source superwhite clamping; exact source-coordinate
mask agreement between arbitrary full-size tiles; and original halo retention
across 512-row boundaries during in-place texture/clarity processing. The four
checks took 0.75 s after engine initialization. No hash tests were added.

A 1920 x 1280 float test with contrast, vibrance, texture, clarity, HSL and a
radial exposure mask took 16.7 ms warm, of which 15.6 ms was the native editor
call. The first call including Vulkan/engine initialization took 1.285 s. This
is an editor-stage measurement, not a full RAW-to-file export claim.

Sony ILCE-7CR `DSC09118.ARW` developed at 9564 x 6376 without resizing. Native
full RAW development took 1.259 s with eight workers, including 75 ms unpack,
791 ms process and 392 ms float conversion. Creating the full display and
initializing the GPU for its source transform brought the complete call to
3.718 s. The 1600 px preview's half-size native decode took 301 ms. Negative
source matrix output was preserved. A DxO linear DNG also developed through
the explicitly identified compatible16 route. These are local fixtures, not
an all-camera or all-device performance guarantee.

Android compiling the shared editor source does not establish actual device
performance or export quality. Its final device measurements remain a separate
integration checkpoint. The new stateless analysis source was compiled by the
Windows toolchain; mobile invocation still needs its JNI integration check.

## Remaining color and memory boundaries

The editing stage retains sRGB-coordinate float headroom until requested
clamping, but the older spectral C result is RGBA16 in its chosen output
space. A future wide-gamut export must request a wide spectral working space,
apply an explicit target transform/ICC once, and avoid confusing the current
sRGB export with preserved ProPhoto output. A float spectral-result ABI would
be required to eliminate its UNORM16 boundary completely.

Full RAW development still needs a full native source vector and LibRaw's
demosaic working storage. Processing strips bound edit/GPU scratch, not sensor
decode memory. Serialize full RAW jobs, evict idle sources, and avoid retaining
all imported RAW frames. A true file-backed sensor/float decode is a separate
memory improvement; it has not been implemented or represented as complete.

## Native optics and worker lifetime fix

The original full-size LCP remap used repeated NumPy coordinates and SciPy
`map_coordinates` per channel/strip; conservative purple-fringe selection
used several whole-strip filters. Those stages measured 8.28 s and 8.76 s on
the same 61 MP fixture. They are now implemented through `native_optics.py`.
Profile matching, sample interpolation and safe auto-zoom policy remain in
the existing lens module.

LCP applies one native CPU/OpenMP pass using double coordinates and a direct
four-sample bilinear read. All eight EXIF orientations map directly between
oriented and calibration coordinates, without a whole-frame un-orientation
buffer. RGB8/RGB16 input is accepted directly, with float RGB output. Negative
and superwhite floating samples remain intact. Conservative defringe uses
the exact existing purple/thin-edge/contrast/near-neutral conditions in a GPU
strip pass with a four-row source halo. Corrected-pixel counting covers only
each strip's core. Optional in-place processing preserves original halo rows.

Two focused checks passed: all eight LCP orientations with chromatic correction
against the existing SciPy mapping (2e-6 tolerance), and defringe against the
existing filter selection/count including 512-row boundaries and in-place
processing. On `DSC09118.ARW`, Sony FE 20mm F1.8 G's locally matched Adobe LCP
processed the original 9564 x 6376 float frame in 446 ms; GPU defringe took
311 ms and corrected five pixels. These are separate processing-stage timings,
excluding RAW decode, metadata/profile discovery and encoding.

A newly exposed Windows lifecycle failure was isolated separately: merely
probing RAW metadata from an MSVC-created Qt worker caused heap corruption on
thread exit, even with no decode, image owner, QML or OpenMP calculation. The
cause was a nontrivial `thread_local std::string` destructor in the statically
linked MinGW RAW bridge. Replacing it with trivially destructible per-thread
character buffers and function-local strings preserved the ABI and eliminated
the problem. The metadata-only Qt worker, decode/GC Qt worker, and actual RAW
editor import followed by `Controller.close()`/`waitForDone()` all exited
normally after the fix. `test_raw_thread_lifecycle.py` retains this regression
as a subprocess check so a native crash is observable by the test runner.

## Memory ownership and cache controls

The RAW display surface is now built in 256-row stripes. The original native
float source remains attached to the Pillow image for full-resolution editing
and export, while the RGB8 surface is quantised without materialising a second
full-frame `clip`/multiply/round chain. `raw_development.memory_info()` reports
live native source bytes; `raw_development.clear_cache()` only clears the small
baseline-exposure metadata cache and cannot invalidate a NumPy source still in
use. Native ownership is released once the last source view is gone.

Large spectral output uses a file-backed float32 mapping. Its finalizer removes
the temporary file only after the root and every derived view have died;
`native_spectral.memory_info()` reports active mapping bytes so an active export
is never mistaken for a disposable disk cache. Preview sessions are bounded by
`set_cache_limits(max_entries, source_bytes, retained_bytes)` and full export
sessions remain transient. `clear_sessions()` releases retained sessions, and
`trim_memory(keep_free_bytes)` calls the native `spk_trim_memory` ABI to flush
and trim idle GPU pool storage while preserving live session sources, negatives
and caller-owned result buffers.

The render/editor/analysis/trim calls share the native engine mutex and should
remain on one serial worker lane. Full RAW decode, optics and export should be
serialized as one large-image job; preview work may use a latest-wins queue but
must not overlap another full decode. These controls bound retained memory;
they do not change source dimensions or silently substitute a preview for an
export.

## Capture-side restoration

The shared GPU editor accepts three independent settings in the 0..100 range:
`sharpening`, `noise_luminance` and `noise_color`, all defaulting to zero.
Restoration runs in `pre` after source conversion/WB/calibration; `all` performs
it once before post colour, while `post` ignores the fields. This deliberately
keeps noise reduction ahead of spectral development and simulated film grain.

Luminance and opponent-chroma noise use separate edge-aware bilateral weights,
followed by a luminance-only, thresholded unsharp pass with a local overshoot
bound. These are native, independent operations rather than aliases for
texture or clarity. The source-space support is two pixels for noise and one
for sharpening, composed with subsequent detail operators and an interpolation
safety margin. Spatial scale follows the source/proxy pixel ratio. Inputs may
retain negative samples and values above one until an explicit final clamp.

One targeted actual Vulkan fixture passed in 0.276 s on the local RTX 3070 Ti
runtime. It verifies noise variance reduction away from a step edge, retention
of edge contrast, increased clean-edge slope under sharpening, in-place
agreement across the 512-row boundary, a haloed arbitrary tile, fractional
preview scaling, float headroom, exact disabled-zero identity and post-stage
non-application. This is correctness evidence for the shared shader, not a
mobile or full RAW-to-file latency measurement.

## Levels, HDR endpoints and automatic proposals

`settings.levels` contains immutable `master`, `red`, `green`, `blue` channels,
each with input `black`/`white` in 0..1, `gamma` in .1..10 and `output_black`/
`output_white` in 0..1. Input handles remain ordered with a minimum gap .0001.
An edited channel maps input endpoints to 0..1, applies exponent `1/gamma`,
then maps to its output endpoints. Individual RGB channels run before master.
Identity channels bypass every operation, preserving float headroom. The old
`black_point`/`white_point`/`gamma` retain their existing legacy semantics.
Independent `whites`/`blacks` in -100..100 use linear luminance weights confined
to the bright and dark endpoints. They do not alias highlights/shadows or levels.
These are post-side adjustments and reuse the cached spectral film output.
Independent `brightness` in -100..100 applies a linear gain weighted around
perceptual midtones, tapering to zero at black and white; it is not exposure EV.
Its zero value bypasses all work, and the operation remains post-side so a
brightness drag reuses the existing film result.

`shared.auto_adjust.analyze_auto` accepts original/bounded RGB plus its stated
primaries/transfer and returns `{kind, changes, confidence, reason}` without
mutating the source or settings. White balance uses un-clipped near-neutral
samples and a numerical fit to the existing Bradford temperature/tint model.
Automatic levels uses robust master endpoints, retaining channel edits; tone
returns absolute exposure plus conservative highlight/shadow changes. For
RAW tone/levels, the caller includes the baseline exposure but not the user's
current tone edits. Repeating a proposal against the same input is stable.
Geometry uses bounded Canny/Hough detection and requires at least three
consistent near-horizontal/vertical lines; uncertain scenes return no changes.
These independent estimators do not claim recovered LR/C1 private algorithms.

The geometry estimator has three explicit modes. `geometry` uses consistent
near-axis Hough lines for rotation. `geometry_vertical` fits only distributed
vertical line segments, and `geometry_full` fits both vertical and horizontal
families against the same bounded homography used by preview and export. The
perspective solve is absolute (it does not add to existing values), preserves
crop/scale/flip/quarter-turn fields, rejects weak or boundary solutions, and
returns no changes for flat or texture-only scenes. It is intentionally a
conservative architectural-line estimator rather than a claim of a commercial
camera viewpoint algorithm.

Lens correction is a separate calibration path in `desktop/lens.py`. It reads
real local Adobe LCP `PerspectiveModel` profiles from the configured Adobe
Camera Raw profile roots, matches normalized camera/make/lens/focal metadata,
and applies radial/tangential distortion plus lateral chromatic correction when
the profile supplies all required data. Ambiguous, unsupported, out-of-range,
or missing profiles remain unchanged. LCP projection calibration is optical
lens distortion; it does not infer camera viewpoint perspective. Purple-fringe
removal remains a conservative edge heuristic and is not represented as an
LCP chromatic model. Vignette correction is not currently included.

One bounded GPU/CPU integration fixture passed in 1.612 s: actual shader levels
and HDR agreement, settings round-trip, immutable source, film-cache reuse,
exact reset, known-cast white balance, automatic level/tone proposals, refusal
on a flat frame and a reliable three-degree grid correction. No large RAW
decode/export benchmark was repeated at this integration point.

The brightness integration fixture passed in .848 s: actual GPU/CPU agreement,
separate behaviour from exposure EV, source immutability, settings round-trip,
spectral cache reuse and exact reset. Controller auto tests also verify that
RAW baseline is consumed once, repeated automatic tone does not accumulate
exposure, history applies one reversible transaction, stale proposals do not
overwrite newer edits, and automatic rotation replaces the absolute angle
while retaining crop. Mask overlay tests cover rotation/keystone/crop and
recolouring, plus a 2333 x 1555 source projected into the 1024 px guide compared
with alpha recovered from actual native-mask compositing. Mean coverage error
stays below .001 and the 99th percentile below .006 for that bounded fixture.
