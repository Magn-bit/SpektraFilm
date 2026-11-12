# Android Build and Verification Record

## 0.4.3 / versionCode 22 · 当前构建

2026-11-08，PowerShell 7 / JDK 21 / Gradle 8.13 / Android SDK 35 / NDK 27.2.12479018 环境，`assembleDebug lintDebug` 成功。Lint 为 0 errors / 42 warnings。产物 `android/app/build/outputs/apk/debug/app-debug.apk`，27,364,531 bytes；构建日志 `output/android-build-0.4.3-retry.log`。未执行哈希测试，也未重复历史 RAW 全图导出计时。

本次原生 Kotlin/View 编辑页面将照片预览与可滚动参数分离，支持单击照片及明确按钮收起/恢复参数；全屏裁切新增可定位矩形、四角和四边调整、自由/原图/标准比例、横竖切换及 XPan 65:24。裁切保存完整源坐标，继续使用原像素导出路径，保留已确认字体配对、精确输入和滑块微调。

`EditorUiInstrumentation` 随同 debug APK 编译成功；聚合覆盖多尺寸/字体、参数底部可达、照片显隐与实际触摸裁切，说明见 `android/EDITOR-UI.md`。ADB 本轮未发现设备，因此尚未执行此 runner、获取真实 Android 截图或验证手势帧率；编译和 Lint 通过不等于设备视觉验收通过。

## 0.4.2 / versionCode 21 · 历史构建

2026-11-08，`assembleDebug` 和 `lintDebug` 成功。本轮恢复已确认的 `Spektra Bilingual Serif` 字体配对（中文朱雀仿宋、英文与数字 Noto Serif SC），并重新验证 APK 中的字体、许可、ICC、原生库和光谱资源。APK 最终大小、SHA-256 与发布 Evidence 以 `release/manifest.json` 和 `release/SHA256SUMS.txt` 为准。由于本轮仅涉及字体与交付元数据，没有重复 0.4.0 的大图 RAW/全谱手机计时；历史设备报告不冒充本版本验收。

## 0.4.1 / versionCode 20 · 历史构建

2026-11-08，`assembleDebug` 和 `lintDebug` 成功，Lint 0 errors / 41 warnings（包括既有字符串资源与自定义 View 警告）。最终 APK 为 `android/app/build/outputs/apk/debug/app-debug.apk`，27,596,532 bytes，SHA-256 `6bff506ce6f8c076900fc386fd72cad243f1615dcff57f15c234629d6b35af7a`。本次未连接手机，未将历史 0.4.0 设备报告标记为当前 APK 验收。

界面继续使用原生 Kotlin View：固定导出栏与系统安全区、单一滚动正文、明确胶片/显影选中态、文件与源尺寸信息、裁切比例和统一数值布局。标题保留衬线，控件使用系统界面字。曝光和粒径实际精度为 .001，百分比 .01%，滤镜/眩光 .01；长按手柄后以当前值为锚进入 1/10 灵敏度，双击手柄恢复当前项，数值点击可精确输入。`FineSliderGestureChecks.kt` 的主机状态检查通过；这不能证明真机触感、系统字体放大或不同尺寸截图均已验收。

完整光谱导出改为按实际 halo 的矩形块规划、只读回所需连续行、RGB16 批量 JNI 与 libjpeg-turbo NEON。主机真实 JNI 检查确认 RGB16 批行与旧逐行路径字节相同，Huffman 策略变化前后解码像素与量化表相同，Q100 仍为 4:4:4。完整源尺寸不变，主动裁切除外；RAW 仍按原始字节保存。详细证据 `output/android-export-perf-20261108/report.json`。

61MP 默认参数的处理量模型由70块减少至30块，工作像素约减少39.1%、读回约减少73.9%；尚无本次手机墙钟测速，不将其作为耗时加速比。150MP、大 halo 与低内存组合仍会产生大量重复空间运算，需要后续按阶段分块优化。APK 资源、签名以发布 Evidence 的确切包哈希检查为准。

## 0.4.0 / versionCode 19 · 历史设备验收

2026-11-07，ARM64 / Android API 26+，个人 debug 签名。最终 APK 为 `android/app/build/outputs/apk/debug/app-debug.apk`，30,203,780 bytes，SHA-256 `941c91227c069c9bfe469776cfc0e18dced9e6df3e230ff274fa62b4ea23dd9c`。构建、APK 内原生资源哈希及字体/ICC/材料验证通过；本轮修改后的 Kotlin/NDK 编译通过，lintDebug 无错误。原生编译命令逐目标确认 `-O3`；LibRaw 静态 OpenMP 最多六线程，无 `libomp.so` 外部依赖，保留 LLVM OpenMP 许可。

运行时为 LibRaw RGB16 → 共享 C++ / Vulkan float32 光谱模型 → RGB16 行带，包含胶片、印相与扫描阶段；没有 Python、旧 LUT 或静默降低最终尺寸。实际材料为 27 胶片 / 9 印相材料。RAW 文件由原生区域读入，位图经原生像素锁定；仅完成的 RGB16 核心区域返回 Java。分块由真实光晕/DIR/颗粒云/印相/扫描参数计算六 sigma 邻域，固定完整画幅坐标与随机种子，复用同配方管线，整张结束释放导出 GPU 池。

真机为 OnePlus 15 PLK110 / Adreno 840。`output/android-device-0.4.0/report.json` 保留完整证据与精确包哈希，已验证：

- 真实 A7CR ARW 冷解码；半尺寸预览与完整像素缓存隔离。完整解码 8,603 ms，原尺寸高品质 JPG 为 9564 × 6376 / 104,909,586 bytes，84 次单调进度达到 100%，RAW 源 SHA-256 前后相同。缩图证据为 `output/android-device-0.4.0/export-preview.jpg`。
- 全图导出墙钟 399,602 ms，期间 headless 验收受手机 Doze 暂停影响；此数值不是纯 GPU 时间，也不等于正常前台交互导出性能。不声称达到亚秒导出。正常导出界面已有 `FLAG_KEEP_SCREEN_ON`，这是代码路径确认，不是本轮前台计时。
- 默认 61 MP / 35 mm 胶片参数的实际邻域为 1098 px。逐区域日志的 GPU resident 峰值为 727,428,608 bytes，GPU + host float + staging 的已报告缓冲峰值为 1,070,384,344 bytes；没有把它们当作完整进程 RSS。临时 USB 常亮设置已恢复原值 0。
- RGB16 非八位可表示细节、黑白/反转片/彩色材料、缓存底片重印、位图红蓝通道、原尺寸 JPG 扫描行、真实 TIFF16 / Deflate 无损逐像素还原及 ICC 均有专项证据。
- 完整 61 MP 导出在 `044f0c…` 包完成；`c7d077…` 候选补 `writeJpeg` 失败清理。最终 `941c912…` 候选另将一处原生默认 `print_exposure_compensation=false` 对齐 Windows，仅谱库哈希变化，RAW、编码器和 49 个 SPIR-V 与全图包一致。最终小图定向检查零曝光与旧谱库 RGB16 SHA 完全一致，−1/0/+1 EV 平均编码值依次 .215256/.362460/.538290；返回零曝光、取消清理和 Bitmap→JPEG 通道均通过。没有重复整图导出；详见报告分候选 acceptance cases 与 `exposure-native-default.patch`。

手机端 100 / 150 MP 运行、全部相机型号与不同 Android GPU 尚未逐机验收。有限邻域的 IIR 空间处理不声称与无限范围整帧数学逐像素相等。主机 Java TIFF16 编码器另有独立 tifffile 逐像素验证；历史记录不代表本版运行结果。

## 0.3.0 / versionCode 14 · 历史记录

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
