# SpektraFilm Android 0.4.2

独立离线的 Kotlin / Android Canvas 胶片暗房。ARM64、Android 8.0（API 26）及以上；版本代码 21。灰绿、冷白与石墨层级，标题和正文恢复使用 bundled `Spektra Bilingual Serif`（中文朱雀仿宋，英文与数字 Noto Serif SC）。颗粒类型、模拟片幅、强度和大小位于同组，印相设置按需展开。固定导出栏不覆盖滚动内容；长按圆点微调，双击恢复当前项，点击数值精确输入。

## 图像与性能路径

- LibRaw 0.22.3 JNI 解码真实 RAW，有相机白平衡、有效完整像素及朝向保护。RAW 的编辑预览可半尺寸解码，完整导出单独完整解码，缓存键、尺寸校验和生命周期隔离。个人交付虽使用 debug 签名，全部生产原生目标仍以 `-O3` 编译；RAW 保留 AHD 显影算法，静态 OpenMP 最多六线程，不降低输出分辨率或解码质量。
- RAW 显影缓存为 sRGB RGB16LE；原尺寸输出直接按区域读到 float32，经过共享 C++ / Vulkan 完整光谱胶片、相纸和扫描模型，得到 RGB16 行带。不会经过预览 Bitmap8 或内嵌 JPEG。
- JPEG/PNG 等系统位图格式按 EXIF 方向重新读取原始区域；输入原来只有八位时不会虚构更高的源精度。JPEG 最终编码才量化八位。TIFF 是真实无符号每通道十六位和无损 Deflate，嵌入 sRGB ICC，使用有界行缓冲与临时编码文件。
- 交互和精细预览都运行同一原生光谱模型、当前印相材料；没有旧 LUT 预览造成松手换色。每执行通道只保留最新请求，过期任务不可覆盖新照片或新参数；原生负片和重印缓存有像素及字节预算。
- 相机曝光不再被自动印相补偿抵消，与 Windows 保持同一默认。小图实机验证正负曝光和返回零值；胶片本身的趾部、肩部及暗部反差保留，不强制匹配原片直方图。
- 运行时不再包含 Python、Chaquopy、NumPy 或 SciPy。科学 Python 参考源码只保留在源码包中。GPU 不可用时明确报错，不静默换成 LUT、CPU或缩小最终输出。
- 高像素导出使用带 halo 的有界区域和 RGB16 行带，按完整源长边保持实际胶片像素间距。邻域由实际胶片与参数计算，包含光晕、DIR 扩散、颗粒云、印相眩光及扫描滤波，保留六 sigma 邻域。RAW 由 C++ 直接读取磁盘 RGB16 区域；位图原生锁定像素，只有完成的 RGB16 核心区域跨 JNI，避免整块 FloatArray 占用 Java 堆。同配方分块复用原生管线，整张完成或取消后释放负片与闲置 GPU 池。
- 颗粒和眩光使用统一种子与完整图像坐标，重叠像素共享随机场；空间滤波的有限 halo 仍不等于无限范围整帧逐像素相同。分块预算同时受系统可用内存、GPU 单缓冲范围与 Java 行带预算约束，不裁短邻域来凑内存。RAW 解码本身仍需要完整传感器缓冲，设备内存不足明确停止，绝不缩小成片。

## 材料与导出

27 种胶片（含四种黑白材料）、9 种真实印相材料；胶片默认采用自己的目标相纸，反转片直接扫描，黑白使用 Multigrade IV RC。模拟片幅影响颗粒及光晕物理尺度；印相曝光、黄色/品红滤镜和眩光提供暗房控制。保留照片选择/移除、收藏、批量应用、独立每张参数、对比和缩放。旧通用修图、曲线、蒙版、校准和外部风格入口已撤下。

导出选项为原尺寸高品质 JPG（质量100 / 4:4:4）、原尺寸分享 JPG（质量85）、原尺寸 TIFF16 和逐字节 RAW 原片备份。RAW 原片不含显影效果。文件名为 `原名_胶片名称.扩展名`，同名编号，不覆盖原片。支持批量、进度及取消，失败清理未完成文件。Android SAF授权允许时定位导入目录，也可选择其他目标目录；系统内容提供方不保证提供原文件夹路径。

## 构建与验证

JDK 21、Gradle 8.13、Android SDK 35、NDK 27.2.12479018、CMake 3.22.1。先按 `native/engine/README.md` 准备共享原生引擎资源及 SPIR-V，再运行：

```powershell
.tools/gradle-8.13/bin/gradle.bat -p android assembleDebug assembleDebugAndroidTest lintDebug
.venv/Scripts/python.exe android/tools/verify_apk.py
.venv/Scripts/python.exe scripts/verify_android_tiff.py
```

APK校验核对JNI库、真实SPIR-V及27胶片/9印相材料/字体/ICC资源哈希，并确认没有 Python 运行时。主机 Java TIFF16 编码器由独立 tifffile 逐像素验证；这不等于手机运行验收。个人 debug 主包提供无界面 ADB 验收入口：`adb shell am instrument -w -e raw_path <应用私有路径> com.spektra.film/com.spektra.film.NativeReleaseInstrumentation`，无需另外安装测试 APK。0.4.2 本轮构建、资源与签名通过，未重复真机大图计时；0.4.0 的历史设备报告不作为本次验收。清理后当前发布证据位于 `release/Evidence`。当前为debug签名个人本地交付。

共享GPL引擎、LibRaw、libjpeg-turbo、公开胶片数据及字体的完整许可和可重建源码随Source包保留，没有商业照片软件的私有二进制。
