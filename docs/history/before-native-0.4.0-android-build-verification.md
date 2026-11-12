# Android Build and Verification Record

## 0.3.0 / versionCode 14 · 当前版本

Windows 主机完成 assembleDebug、assembleDebugAndroidTest 和 lintDebug（0错误/34警告）；实际APK资源逐文件校验及v2签名通过，已发布release/Android/SpektraFilm-0.3.0-debug.apk。包含可选胶片显影、普通照片基础调整、画笔/线性/径向蒙版、五通道曲线、三区色轮、手动几何与原像素裁切、4人像/6风光原创参数风格与用途筛选、批量风格及XMP转换审阅。最终源码包由 tools/verify_apk.py 核对共享内核、目录、原生依赖、字体、许可、sRGB及未内置样片；最终签名与成品导出证据见 output/release-0.3.0。

测试APK编译成功但未执行；无已连接Android设备或模拟器。手机触控、全尺寸导出成功率、native峰值内存与帧率未验收。Android完整相机RAW解码器尚未接入，不能声称ARW可正常预览或显影为JPEG。当前PNG/JPEG/TIFF区域读取不能代替RAW解码。旧记录仅作历史构建说明，实际当前状态以本节与docs/validation.md为准。


## 0.2.11 / versionCode 13

Built on Windows with JDK 21, Gradle 8.13, Android SDK 35, NDK 27.2.12479018, and CMake 3.22.1. Artifact: `release/Android/SpektraFilm-0.2.11-debug.apk`, arm64-v8a, Android API 26+, debug-signed.

- Export offers a remembered full spectral mode and an explicitly labeled vectorized LUT approximation. Both preserve source pixel dimensions; RAW is copied unchanged and receives no film processing.
- LUT processing uses bounded non-overlapping source regions, NumPy trilinear interpolation, exposure adjustment, globally seeded grain, and a local halation approximation. It is not equivalent to the upstream full spatial model.
- `assembleDebug`, `assembleDebugAndroidTest`, `lintDebug`, and `testDebugUnitTest` succeeded. APK source/resource/hash checks passed, including the bundled LUT export implementation and upstream film resources.
- Host checks confirmed the LUT path transforms pixels, preserves identity at zero strength, and produces identical pixels across a horizontal tile boundary (512 x 384 test image). A 693 x 692 (0.48 MP) LUT tile took 0.194 s on this Windows host; this is not an Android performance estimate.
- No Android device or emulator was connected. Instrumentation was compiled but not executed; phone export timing, memory, image appearance, and completion remain unverified on device.

## 0.2.10 / versionCode 12

Built on Windows with JDK 21, Gradle 8.13, Android SDK 35, NDK 27.2.12479018, and CMake 3.22.1. Artifact: `release/Android/SpektraFilm-0.2.10-debug.apk`, arm64-v8a, Android API 26+, debug-signed.

- The full-resolution exporter now budgets smaller spectral tiles, avoids copying the decoded pixel region for common unrotated images, streams emulsion layers, and uses exact Poisson thinning for grain.
- The tile planner covers Sony A7CR 61 MP (9504x6336), 100 MP medium format (11648x8736), and 150 MP medium format (14204x10652) under a 256 MiB Java-heap planning budget. These are planning checks; no connected Android device was available for full-resolution runtime measurements.
- Export remains source-resolution JPG/TIFF. The high-quality JPG remains quality 100; no preview proxy is used for export.
- `assembleDebug`, `assembleDebugAndroidTest`, and `lintDebug` succeeded. APK contents and v2 debug signature were verified.
- Host parity passed with maximum absolute error below `1.6e-13` for the covered deterministic model stages. This does not represent Android device performance.
- No Android device or emulator was available. Device-side export, peak memory, and large-photo completion remain unverified.

The 0.2.9, 0.2.8, and 0.2.7 records are retained below for their original build evidence.

## 0.2.9 / versionCode 11

The previous packaged build compiled the full-resolution A7CR and medium-format tile planner, but did not include the additional 100 MP and 150 MP instrumentation assertions added in 0.2.10. This version record is retained to distinguish installed packages from the current release.

## 0.2.8 / versionCode 10

Built on Windows with JDK 21, Gradle 8.13, Android SDK 35, NDK 27.2.12479018, and CMake 3.22.1. The earlier artifact was `release/Android/SpektraFilm-0.2.8-debug.apk`, arm64-v8a, Android API 26+, debug-signed.

- `assembleDebug`, `assembleDebugAndroidTest`, and `lintDebug` succeeded.
- Full-resolution JPG/TIFF export used source-resolution tiles and scanline encoding; no Android device or emulator was available for device-side memory and performance validation.

## 0.2.7 / versionCode 9

Built on Windows with JDK 21, Gradle 8.13, Android SDK 35, NDK 27.2.12479018, and CMake 3.22.1. Artifact: `release/Android/SpektraFilm-0.2.7-debug.apk`, arm64-v8a, Android API 26+, debug-signed.

- `assembleDebug`, `assembleDebugAndroidTest`, and `lintDebug` succeeded. Gradle reports deprecated APIs that will need attention before Gradle 9.
- `tools/verify_apk.py` verified the actual APK's bundled source, native scanline JPEG library, TIFF writer, 20 film LUTs, NumPy/SciPy/scikit-image extensions, font and licenses, sRGB profile, four export presets, and absence of sample photos.
- JPG/TIFF export reads original pixel regions, processes overlapped tiles through the full spectral model, and writes rows to JPEG/TIFF encoders. It preserves EXIF-oriented source dimensions and does not substitute the preview proxy or lower output dimensions to avoid memory pressure.
- `scripts/verify_mobile_spectral.py` host parity checks passed with maximum absolute error below `1.6e-13` for the covered deterministic model stages. `scripts/verify_android_tiff.py` passed a host JVM/Pillow pixel and ICC roundtrip.
- No Android device or emulator was connected. Instrumentation tests compiled but were not executed; device-side large-image peak memory, performance, permissions, and visual behavior remain unmeasured.
- A compressed file expands substantially in memory. A 24 MP ARGB bitmap is about 96 MB, and one float64 RGB array is about 576 MB, before other spectral intermediates. Android's Java heap limit alone does not describe all native NumPy allocations; low-memory devices may still reject a tile allocation. Failure must remain explicit rather than silently reducing output dimensions.
