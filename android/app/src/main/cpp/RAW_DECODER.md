# Offline LibRaw decoder

The Android native library is `spektra_raw`. It embeds the vendored LibRaw
0.22.3 decoder and postprocessing implementation, JPEG decoding and Android
zlib. It does not load Lightroom, Capture One, a network service, rawspeed or
Adobe DNG SDK. LibRaw's normal per-instance/thread decoder state is retained;
OpenMP is not enabled.

## JNI contract

Class: `com.spektra.film.RawImageDecoder`. Calls doing IO/development belong on a
worker thread. Handles are independent. Each handle permits one operation at a
time; cancel/progress/close may be called concurrently.

| Method | Result |
| --- | --- |
| `nativeCreate()` | `Long` opaque handle |
| `nativeInfo(handle, sourcePath)` | `IntArray [orientedFullWidth, orientedFullHeight, rawWidth, rawHeight, flip]` |
| `nativeDevelop(handle, sourcePath, outputPath, halfSize, callback)` | `IntArray [actualOutputWidth, actualOutputHeight]` |
| `nativeProgress(handle)` | `Int` from 0 through 10000 |
| `nativeCancel(handle)` | Requests cancellation; LibRaw callback/write boundary performs it |
| `nativeClear(handle)` | `Boolean`: false while busy, otherwise clears error/cancel/progress |
| `nativeLastError(handle)` | Last operation error text; empty after clear/new successful start |
| `nativeClose(handle)` | Cancels, removes handle, releases after active operation unwinds |
| `nativeVersion()` | Linked LibRaw version string |

`callback` may be null. Its `onProgress(stage: String, fraction: Double): Boolean`
method runs synchronously on the native caller's worker thread. Return true to
continue, false to cancel. If a Java callback throws, the original Java exception
is preserved while native state unwinds. Progress is monotonic; Java can query
10000 after a successful return.

Errors become `IOException` (IO/corruption), `UnsupportedOperationException`
(unsupported file/decoder/output), `CancellationException`,
`IllegalArgumentException` (invalid paths), `IllegalStateException` (busy/closed
handle), or `OutOfMemoryError`. Unsupported input never falls back to an embedded
JPEG or pretends a processed image was produced.

Inputs and outputs must be absolute, regular, seekable local paths; the Android
caller streams SAF input into its private cache before calling JNI. Input/output
must differ. Output is first written to a same-directory mode-0600 temporary
file, flushed/closed, and atomically renamed on success. Cancellation/failure
removes the temporary file and preserves a pre-existing completed destination.
The caller owns removal of completed cache files.

## Pixel contract

The cache has no header: `width * height * 6` bytes, row-major RGB, unsigned
16-bit little-endian, three channels, no alpha, no padding. Orientation is
already applied, including mirrored/transposed variants, with the origin at the
top left. Primaries and transfer are sRGB. No EXIF rotation should be applied a
second time. Dimensions returned by `nativeDevelop` are authoritative.

The explicit LibRaw development settings match the Windows decoder:

- Camera white balance; no automatic WB override.
- sRGB output color, 16-bit output, gamma power `1 / 2.4`, toe slope `12.92`.
- Highlight reconstruction mode `5` (`ReconstructDefault`).
- Auto-bright enabled and threshold `.01`, brightness `1` (LibRaw itself skips
  histogram scaling for highlight reconstruction modes).
- AHD demosaic and camera-recorded orientation.
- `half_size=false` for export; no thumbnail extraction. A preview caller may
  explicitly request `half_size=true`.

LibRaw retains its own full-frame decode/process buffers; RAW development is not
a scanline decoder. The bridge adds only one output scanline and streams it to
disk, avoiding `dcraw_make_mem_image`'s second full-frame RGB allocation and any
full-resolution Java Bitmap. Gamma and flip mapping follow the vendored LibRaw
`mem_image.cpp`, `file_write.cpp` and `curves.cpp` implementation. The validation
program compares streamed output byte-for-byte with official LibRaw memory
output under the same parameters.

LibRaw 0.22.3's `imgdata.rawparams.max_raw_memory_mb` is explicitly set to
512 MiB instead of its 2048 MiB default. This caps allocations checked by the
RAW unpackers and related LibRaw paths; it is not a cap on all decode/demosaic
buffers or total process RSS. A 150 MP 16-bit Bayer mosaic alone is about
286 MiB, while its later processing buffers require additional memory. Kotlin
separately estimates `rawWidth * rawHeight * 12 + 96 MiB` against available and
total system memory before admission. A job exceeding a LibRaw allocation limit
fails through the existing explicit memory error; it is never silently reduced
in resolution. The full-size export setting remains `half_size=false`.

## Builds and validation

The normal Android Gradle CMake integration builds both `spektra_raw` and the
existing `spektra_stream_jpeg` library. Only `arm64-v8a` is configured by the app.
The standalone native targets can also build without Gradle:

```powershell
& '.tools/android-sdk/cmake/3.22.1/bin/cmake.exe' -S android/app/src/main/cpp -B output/native-raw-arm64 -G Ninja '-DCMAKE_TOOLCHAIN_FILE=D:/Project/SpektraFilm/.tools/android-sdk/ndk/27.2.12479018/build/cmake/android.toolchain.cmake' -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-26 -DCMAKE_BUILD_TYPE=Release '-DCMAKE_MAKE_PROGRAM=D:/Project/SpektraFilm/.tools/android-sdk/cmake/3.22.1/bin/ninja.exe' -DSPEKTRA_RAW_BUILD_PROBE=ON
& '.tools/android-sdk/cmake/3.22.1/bin/cmake.exe' --build output/native-raw-arm64 --target spektra_raw spektra_raw_probe spektra_stream_jpeg --parallel 6
```

The same core can build and execute on Linux/WSL with g++, CMake, Ninja and zlib
development files. JPEG remains vendored:

```sh
cmake -S android/app/src/main/cpp -B /var/tmp/spektra-raw-host -G Ninja -DCMAKE_BUILD_TYPE=Release -DSPEKTRA_RAW_BUILD_PROBE=ON
cmake --build /var/tmp/spektra-raw-host --target spektra_raw_probe spektra_raw_validation --parallel 6
/var/tmp/spektra-raw-host/spektra_raw_validation output/native-raw-validation output/offline-engine/pixel4xl-raw-pixls-3502.dng
```

Validation generates a genuine small uncompressed CFA DNG to exercise all eight
TIFF orientations and preview half-size, compares bytes with LibRaw's official
output, rejects unsupported input, and checks cancellation removes partial
files. The optional real DNG argument also tests full dimensions and exact
RGB16LE byte count/output. `spektra_raw_probe [input-raw [output-rgb16]]` reports
the linked version and runtime A7CR camera-list support, and optionally inspects
and develops a real file. These host checks exercise native core logic; device
JNI/SAF/UI behavior still needs Android execution.

Verified on 2026-11-06: NDK 27.2.12479018 / Clang 18 arm64 Android API 26
builds `spektra_raw`, the existing JPEG bridge, and diagnostic targets. The
WSL/GCC 13 build reports `LibRaw 0.22.3-Release` and runtime support for
`Sony ILCE-7CR (A7CR)`. The eight orientation checks and half-size check match
official LibRaw output exactly. The CC0 Pixel 4 XL DNG supplied in the workspace
develops to 3700 × 2774 and 61,582,800 RGB16LE bytes, also byte-for-byte identical
to official LibRaw output. No connected Android device was available during
these checks.

## Sources and licenses

Official API documentation consulted through Context7 `/libraw/libraw`:

- https://www.libraw.org/docs/API-CXX.html — `adjust_sizes_info_only`,
  `dcraw_process`, `get_mem_image_format`, `set_progress_handler`.
- https://www.libraw.org/docs/API-datastruct.html — WB, highlight, gamma,
  half-size and output-color parameters.
- Vendored `src/postprocessing/mem_image.cpp` and `src/write/file_write.cpp` —
  output transfer and eight-way orientation.

LibRaw is dual-licensed under LGPL-2.1 or CDDL-1.0; this integration selects the
LGPL-2.1 option for the GPL-3.0 application. The vendored sources, `third_party/libraw/COPYRIGHT`,
`LICENSE.CDDL`, and `LICENSE.LGPL` are preserved unchanged. Retain those notices
and provide the corresponding vendored LibRaw source, bridge source and CMake
build files with binary distributions so recipients can modify and rebuild the
linked application under the applicable licenses. No broader "or later" grant
is inferred from the dual-license summary. Existing libjpeg-turbo notices remain in
`third_party/libjpeg-turbo/LICENSE.md` and `README.ijg`.
