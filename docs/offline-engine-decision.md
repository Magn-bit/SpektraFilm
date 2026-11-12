# Windows / Android 独立离线影像引擎选型

核查：2026-11-06。目标是两端均在本机完成解码、编辑和导出，不调用 Lightroom / Capture One，不上传照片。本文仅研究与取证，未修改生产源码、界面或预设目录。

## 结论

本项目优先采用 **LibRaw 解码 + 本项目共享原生色彩处理 + LittleCMS ICC 转换**。这是可控制依赖和内存的组件组合，不应称作“LibRaw 完整编辑引擎”或“Adobe 兼容引擎”。LibRaw 处理 RAW 读取、去马赛克、基础白平衡/矩阵和 dcraw 风格后处理；LittleCMS 是 ICC CMM；分色相 HSL、色调、局部工具、显影调度与导出仍需本项目实现。[L1–L4][C1]

三条路线都能合法获得源码，但**本次没有核实到可直接嵌入 Windows 与 Android、同时完整复现 Adobe PV15.4 / Adobe Color / XMP 的现成 SDK**。完整 RawTherapee / darktable 是成熟桌面应用，不能因其开源、支持 ARM 桌面或含内部 library，就承诺无改造地用于 Android。Adobe Color 名称也不是 ICC 或 DCP 文件。[R1–R4][D1–D4]

### 0.3.1 实际实现状态

上述为选型与演进方向。当前已落地 Windows rawpy/LibRaw、Android LibRaw JNI 与 RGB16LE 私有区域缓存，以及跨端同源 NumPy 八色 HSL；Windows 普通图像已有 Pillow/LittleCMS ICC 转换。**Android 普通图像 LittleCMS 转换、外部 DCP/Adobe Look 尚未实现**，不把该矩阵写成全部集成完成。编辑/导出仍为 RGB8，内部 RGB16 缓存仅保留 RAW 显影中间精度。真实 DNG/A7CR native 主机验证及限制见 output/offline-engine。

## 决策矩阵

体积、启动、峰值内存和手机耗时尚未作同条件三方 benchmark，以下成本是根据接口与构建依赖作出的工程判断。

| 候选 | 可嵌入范围及 RAW 能力 | HSL / ICC / DCP 实际边界 | Windows / Android ARM | 内存与维护成本 | 本项目决策 |
| --- | --- | --- | --- | --- | --- |
| **LibRaw + LittleCMS + 自有处理核心** | LibRaw 有 C/C++ API，可读取 RAW、预览、元数据及执行 dcraw 风格显影；LittleCMS 提供 ICC 转换；编辑管线需另建。[L1–L4][C1] | LibRaw 的 `camera_profile` / `output_profile` 走 LCMS 的 ICC API，需启用 LCMS。没有核实到接受任意外部 `.dcp` 并应用完整 LookTable 等的接口。HSL 和 Adobe PV 算法不由这两库提供。DNG 内嵌矩阵可被解码器利用，不等于外部 Adobe DCP / Look 被还原。 | 官方 LibRaw 安装文档列出 Unix/Linux/Android，且提供 Windows 构建。LittleCMS 为 C 库，官方 CMake 支持 toolchain 交叉编译；Android NDK 集成仍须本项目编译与运行验证。桌面现有 rawpy 可复用，手机使用 JNI/NDK，不依赖不存在的 rawpy Android wheel。[L2][C2][P1] | 依赖最可控；可统一两端接口、线程和缓存。但高质量编辑、ICC 接入、内存预算与回归由本项目负责，不能将工程工作量说成“接上库就完整”。 | **选择。** 保留现有光谱显影，逐项补原生色彩工具与 ICC。先明确支持范围，再拓展外部 DCP。 |
| **RawTherapee 全 rtengine；或 LibRaw + librtprocess** | 全 RT 有成熟 RAW / 色彩管线。`librtprocess` 则只导出部分去马赛克、色差与高光恢复算法，不读取 RAW 容器，也不是完整 RT 核心。[R1][R2] | 全 RT 的 `dcp.cc` 确有双光源、HueSatMap、LookTable、tone curve、baseline exposure 等处理；ICC 由 LCMS 支撑，另有 HSV 曲线。**这些不在 librtprocess 公共接口中**，也不能因此声称支持 Adobe 所有处理版本/XMP。[R2–R4] | Windows 有官方构建说明；librtprocess 的小型 C++/CMake 接口适合按需移植。全 RT 当前 `rtengine` 静态目标仍链接 GTKMM、GLIBMM、CAIROMM、Exiv2、Lensfun、FFTW、LCMS、图像编解码库；不能直接把它当纯 NDK 库。未核实官方 Android SDK/发行包。 | 全 RT 嵌入需拆解桌面依赖，成本高。librtprocess 较窄，但需提供 float 单通道输入与三个 float 输出平面，自建元数据/色彩/IO；有额外内存与算法适配成本。 | 不作为本轮整体替换。以后有实测瓶颈或去马赛克质量需求，可单独评估 librtprocess；DCP 可研究抽出相关模块，但必须保留 GPL 与测试。 |
| **darktable 内部库 / CLI** | 成熟桌面 RAW 显影与编辑，CLI 可无人值守导出；源码确实构建 `lib_darktable`，但其为应用内部库。[D1–D3] | 有输入/工作/输出 ICC 与颜色分区工具；官方输入文档明确描述相机矩阵、嵌入 ICC、自定义 ICC。其公开接口/本次核查未证明能直接应用完整外部 Adobe `.dcp`，更不等于支持 Adobe XMP。[D3][D4] | Windows 官方支持；ARM macOS / Linux 能运行不代表 Android。当前必需依赖含 GTK3、GLib、Exiv2、SQLite、Lensfun、LCMS、Pugixml 等，CLI 仍初始化应用配置、数据库/模块系统。未核实官方 Android SDK。 | 桌面作为完整独立应用比抽取内部管线容易；双端嵌入依赖重、维护范围大。官方桌面最低 RAM 4GB / 建议 8GB，不能直接当手机内存承诺。[D1] | 不选为双端共同内核；可作为本地质量参考，不能变成对用户已安装宿主的依赖。 |

## 分发与离线 profiles

| 组件 / 数据 | 本次核实的许可与处理方式 |
| --- | --- |
| LibRaw | 官方双许可 LGPL-2.1 / CDDL-1.0，应用可择一；源码含第三方算法通知，应保留对应许可与实际构建配置，不能只复制一个二进制。[L1] |
| LittleCMS | MIT；保留版权与许可。其是 ICC 渲染器，不自带所有相机厂商/Adobe 配置文件的分发权。[C1][C3] |
| librtprocess / RawTherapee / darktable | GPL-3.0 系列，嵌入或修改须履行对应源码/许可义务。本项目现有 GPL-3.0 方向可容纳，但仍需记录实际版本、修改与依赖许可。[R1][R2][D1] |
| 相机基线 | 首先采用所选 LibRaw 版本的内建相机矩阵、合法 DNG 内嵌矩阵/白平衡及已核实的数据；库支持表列有 Sony ILCE-7CR，但这不是本轮 A7CR 所有压缩模式的实测证明。[L5] |
| 工作/输出 ICC | 可用 LittleCMS 标准 sRGB profile 或项目明确生成/许可的工作空间；不要从商业宿主目录搬出配置文件再随包发布。已存在的标准 sRGB 输出 ICC 可保留。需要在应用层实际调用转换，而不是仅给输出贴上 profile 标签。 |
| 自定义 ICC / DCP / Look | 用户本地导入与产品内置是两件事。逐文件记录类型、SHA256、来源、许可、适用相机、白点/工作空间与渲染方式。RT 源码能解析 DCP，并不意味着任意 RT/Adobe 相机 profile 都已取得独立打包许可。没有合法且兼容文件时，明确使用项目基线，不显示“Adobe Color 已加载”。 |

建议先固定处理契约：RAW 解码为明确白平衡/矩阵和传递函数的高精度 RGB；JPEG/TIFF 有 ICC 时将像素**转换**到工作空间；无标记图像采用已说明的默认规则；编辑完成再转显示/输出空间，并嵌入相匹配 ICC。需要保留相机空间做 DCP 时，应在正确阶段应用，不能先压成显示 sRGB8 再用 DCP 补回。ICC 与 DCP 也不能互换扩展名。[L3][C1][R3][D4]

当前本机运行探测：rawpy **0.26.1 / LibRaw 0.22.0**，`rawpy.flags['LCMS'] == True`；Pillow 的 LittleCMS **2.19** 可用。此处比“上游旧 Windows makefile 默认不含 LCMS”更能反映本机实际构建。Android 当前观察到 LibRaw CMake 使用 `NO_LCMS`，故不能凭 Windows 成功声称手机 RAW 已应用 ICC；独立 native LCMS 的编译、16-bit/float 转换和真机显示仍需验证。证据：`output/offline-engine/fixture-decode-report.json`、本地 `android/app/src/main/cpp/CMakeLists.txt`。[L2][P1]

## 内存与执行边界

LibRaw 的 `max_raw_memory_mb` 文档定义为 **raw buffer** 上限，默认 2048MB，不是整个进程峰值内存限制。`half_size` 可降低显影输出，但不能把它描述成所有 RAW 格式的完整分块解码保证。[L3]

以 61MP 为例，仅 uint16 单通道约 **122MB**，RGB16 约 **366MB**，RGB float32 约 **732MB**；实际还可能同时保留解码缓冲、LibRaw 四通道图像、中间平面、预览及输出。这些是数组大小计算，非实测峰值。librtprocess 的标准接口需 float 原始平面与 R/G/B 三个 float 平面，61MP 对应约 **976MB** 主数组，尚未算 scratch 和输入副本。[R2]

手机端应限制并发解码与完整处理任务，复用缓冲，在读取前估计像素和工作集，预览与全尺寸导出分别设预算；失败时准确报告，不静默缩小全尺寸导出。共享 native 接口和规范化参数用于两端一致性，不能只因算法名字相同就假设浮点、ICC、边界处理和线程调度一致。完整去马赛克并非天然 tile-safe，不能只给后处理加分块就声称 RAW 全链路恒定内存。

## 六款作者 XMP 的真实 HSL 需求

原文件为 `peva3/EmulsionPresets` 固定 commit **`0cdb71c60603867a046bc92c63617feec7894dd1`**，MIT；仍仅保留在 `output/preset-research/practical-xmp-source/` 研究，不改本版 10 款原创目录。下表来自 XML 逐字段提取，完整原值、hash 与嵌套 Look XML 保存于 `output/offline-engine/practical-xmp-fields.json`。[X1]

H = `HueAdjustment*`，S = `SaturationAdjustment*`，L = `LuminanceAdjustment*`。只列文件明确提供的非零项；空项表示该文件未写，不能把它误认成已测得的作者隐藏默认。字段数值是 Adobe 控件值，**不是直接色相角度、百分比乘数或通用 HSL 公式**。

| 作者原名 | H | S | L | 关键用途 |
| --- | --- | --- | --- | --- |
| Natural Skin | — | Orange −10；Red −8；Green −10 | Orange +12；Red +5 | 橙红提亮/降饱和是肤色主体；忽略这些只留总对比就偏离主要意图。 |
| Bright & Airy Wedding | Green +20 | Blue −20；Green −30；Yellow −10 | Aqua +35；Orange +10 | 青色明显提亮、草木降饱和、绿色偏移，与柔亮色调共同起效。 |
| Golden Hour Selfie | — | Orange +5；Yellow +5；Blue −15；Green −15 | Orange +18；Red +10 | 肤色提亮与暖色保留，不能仅靠暖色轮代替。 |
| Epic Landscape | Green +15 | Aqua +5；Blue +15；Green −15；Yellow +10 | — | 蓝青增强、绿色收敛与偏移；细节增强还依赖 Clarity/Dehaze。 |
| Grass Natural Exterior | Green −10；Yellow −10 | Blue −5；Green −20；Yellow +10 | — | 草木色相及黄绿关系是关键。 |
| Byron Bay Surf | — | Aqua +15；Blue +10；Orange +5；Green −15 | Aqua +15；Orange +12 | 水色增强/提亮，橙色提亮与背景绿色收敛。 |

本批共 **33 个非零 HSL 字段**；H 范围 **−10…+20**、S **−30…+15**、L **+5…+35**；未出现 Purple / Magenta 项。实现公共八色通道时仍需覆盖 Red / Orange / Yellow / Green / Aqua / Blue / Purple / Magenta，不能只为这六个文件硬编码颜色。

### HSL 以外不能遗漏的依赖

- **全部指定 `ProcessVersion="15.4"`**。全部有嵌套 `crs:Look/rdf:Description`，其 `crs:Name="Adobe Color"`、`Amount="1.000000"`，以及 UUID / 支持标记；这些文件没有提供 ICC / DCP / 3D LUT 的实际二进制数据。六文件根层未提供可直接加载的 `CameraProfile` 文件。嵌套 `Look.Name` 不能误当预设展示名或已存在的 profile。作者 MIT 许可覆盖其文件，不会随引用产生 Adobe 渲染器。[X1]
- 曝光范围 **+0.10…+0.60 EV**；Highlights **−45…−25**、Shadows **+15…+40**、Whites **+5…+25**、Blacks **−10…+15**。白黑场是渲染控件，不应直接套为“输入黑点裁切/输出白点”并声称等价；曝光策略仍须尊重本项目“风格是否覆盖逐图曝光”的明确规则，不能因为解析到字段就偷偷改变操作范围。
- Clarity 范围 **−10…+15**，Texture 出现 **−5**，Dehaze **−8…+10**。这些涉及空间/局部处理，不能用全局 HSL、总饱和或一条曲线冒充。Natural Skin 的这些字段是 0；全局兼容警告应区别“非零未支持”与“零值未处理”。
- 色彩分级包含阴影/高光 hue、saturation 与 blending；Wedding / Epic / Grass 还写出 midtone、global 和 balance（其中多项为 0）。Golden 指定 Custom WB / **6000K**，Surf 指定 **5700K**。这属于 Adobe RAW 白平衡语义，对已渲染 JPEG 不能仅按 K 数值复制。曝光、WB 若按本项目风格作用范围保留，必须在转换说明中明示。

### 可实施的兼容契约

1. 先完整保留八色 H/S/L 的数值、作者来源和未支持字段，给导入结果明确标记“本项目算法转换”；支持 24 个参数不代表 Adobe PV15.4 像素一致。
2. HSL 混合使用连续、有重叠的色相权重并处理红色环绕、低饱和及黑白稳定性；明确所有通道权重是否基于同一原始色相，避免多个色相修改相互改变下一通道的命中范围。具体曲线属于本项目设计，需要色卡、肤色、渐变和两端一致性回归，不冒称 Adobe 私有公式。
3. 分开记录 `profile_status`、`process_compatibility` 与逐字段映射；缺失 Adobe Color 时提供明确的项目基线选项，不静默显示原版已加载。DCP 的 matrix / HueSatMap / LookTable / tone curve / exposure offset 是独立能力，也不能用任意 ICC 替代。
4. 对八色渐变、红色边界、灰阶、无色高光/暗部、极值及全零参数进行验证；全零应为恒等，数值有限，预览与导出共用参数语义。最后用匹配用途的实片验收，不能只以 XML 成功或 RGB 差异证明视觉还原。

## 公开 RAW 测试素材与本机验证

已下载 **raw.pixls.us 条目 3502：Google Pixel 4 XL DNG**，目录明确标为 **CC0-1.0**。源站说明上传者须持有权利并将文件置于公有领域；此文件仅作本地测试，不内置应用。[F1]

- 文件：`output/offline-engine/pixel4xl-raw-pixls-3502.dng`，**11,402,436 bytes**，低于 30MB。
- SHA256：`0c03a6c93b4b8593cd0e4426166e6389710007238b82eb23861ef191322f0c54`，与公开 catalog checksum 一致。
- 元数据的 RAW SubIFD 为 **Color Filter Array、2×2 CFA、JPEG 压缩 DNG**；另有嵌入 JPEG 预览。解码器实际读到了 uint16 单通道 CFA 和 `[[0,1],[3,2]]` Bayer pattern，未把 JPEG 缩略图当 RAW。[F1]
- 本机 rawpy/LibRaw 以 camera WB、关闭 auto bright、`gamma=(1,1)`、RGB16 实际完成显影，输出 **3700×2774×3 uint16**，RGB 数组 **61,582,800 bytes**；源 hash 未变。单次 open/unpack **429.55ms**，postprocess **732.44ms**；仅此次本机调用计时，不含 UI、导出编码、HSL 或 Android，亦非多次 benchmark。
- 来源、许可、URL：`fixture-manifest.json`；本机解码证据：`fixture-decode-report.json`；站点元数据：`pixel4xl-3502-exif.txt`，均在 `output/offline-engine/`。

raw.pixls.us 的 A7CR 条目最小为 **30.41MB**（APS-C compressed）；其余 **35.62…126.38MB**。本次按小于 30MB 优先选择上述 DNG，**没有用 Pixel DNG 成功代替 A7CR 或 Android 的运行验证**。完整 catalog 快照已留存，不下载更大的 ARW。[F1]

## 一手来源与固定版本

官方源码下载快照与逐文件 URL / SHA256 位于 `output/offline-engine/source-evidence.json`、`source-repositories.json`；Context7 文档查询返回 fetch failed，因此以项目自己维护的源码/文档取证。下列链接固定到本次 commit，非第三方教程。

- [L1] [LibRaw README / 双许可](https://github.com/LibRaw/LibRaw/blob/0b87f5c907d7ee0e7641dd1b6a6c9140b9451922/README.md)。
- [L2] [LibRaw 安装及 Android / Windows / LCMS 开关](https://github.com/LibRaw/LibRaw/blob/0b87f5c907d7ee0e7641dd1b6a6c9140b9451922/doc/Install-LibRaw.html)。
- [L3] [LibRaw 参数与内存限制](https://github.com/LibRaw/LibRaw/blob/0b87f5c907d7ee0e7641dd1b6a6c9140b9451922/doc/API-datastruct.html)。
- [L4] [LibRaw ICC apply_profile 实现](https://github.com/LibRaw/LibRaw/blob/0b87f5c907d7ee0e7641dd1b6a6c9140b9451922/src/write/apply_profile.cpp)、[C++ API](https://github.com/LibRaw/LibRaw/blob/0b87f5c907d7ee0e7641dd1b6a6c9140b9451922/doc/API-CXX.html)。
- [L5] [LibRaw 相机列表](https://github.com/LibRaw/LibRaw/blob/0b87f5c907d7ee0e7641dd1b6a6c9140b9451922/src/tables/cameralist.cpp)，包含 `Sony ILCE-7CR (A7CR)`。
- [C1] [LittleCMS README / ICC V2/V4](https://github.com/mm2/Little-CMS/blob/689a84bcae6dc0173f3f45b55ffb8dea721c3d6b/README.md)。
- [C2] [LittleCMS BUILDING / toolchain 交叉编译](https://github.com/mm2/Little-CMS/blob/689a84bcae6dc0173f3f45b55ffb8dea721c3d6b/BUILDING.md)。
- [C3] [LittleCMS MIT LICENSE](https://github.com/mm2/Little-CMS/blob/689a84bcae6dc0173f3f45b55ffb8dea721c3d6b/LICENSE)。
- [R1] [RawTherapee README](https://github.com/RawTherapee/RawTherapee/blob/b2ee504c47e5e6d5e054395aa12bf1fe43bd1c3c/README.md)。
- [R2] [librtprocess README / 输入输出缓冲](https://github.com/CarVac/librtprocess/blob/9a858270acb2096e2e403d932760ee688fcac425/README.md)、[完整公共头](https://github.com/CarVac/librtprocess/blob/9a858270acb2096e2e403d932760ee688fcac425/src/include/librtprocess.h)。该快照 README 自称 0.12.0，CMake project 标 0.11.0，故以 commit 标识。
- [R3] [RT DCP 实现](https://github.com/RawTherapee/RawTherapee/blob/b2ee504c47e5e6d5e054395aa12bf1fe43bd1c3c/rtengine/dcp.cc)、[ICC store](https://github.com/RawTherapee/RawTherapee/blob/b2ee504c47e5e6d5e054395aa12bf1fe43bd1c3c/rtengine/iccstore.cc)、[参数模型](https://github.com/RawTherapee/RawTherapee/blob/b2ee504c47e5e6d5e054395aa12bf1fe43bd1c3c/rtengine/procparams.h)。
- [R4] [RT 构建依赖](https://github.com/RawTherapee/RawTherapee/blob/b2ee504c47e5e6d5e054395aa12bf1fe43bd1c3c/cmake/Dependencies.cmake)、[rtengine 实际链接](https://github.com/RawTherapee/RawTherapee/blob/b2ee504c47e5e6d5e054395aa12bf1fe43bd1c3c/rtengine/CMakeLists.txt)。
- [D1] [darktable 平台、内存与 GPL](https://github.com/darktable-org/darktable/blob/205f9a55ca345a842ff350bc1b361ad3ac53f2e0/README.md)。
- [D2] [darktable 内部库及依赖](https://github.com/darktable-org/darktable/blob/205f9a55ca345a842ff350bc1b361ad3ac53f2e0/src/CMakeLists.txt)。
- [D3] [darktable CLI 初始化](https://github.com/darktable-org/darktable/blob/205f9a55ca345a842ff350bc1b361ad3ac53f2e0/src/cli/main.c)、[color zones](https://github.com/darktable-org/darktable/blob/205f9a55ca345a842ff350bc1b361ad3ac53f2e0/src/iop/colorzones.c)。
- [D4] [darktable 官方输入 color profile 文档](https://docs.darktable.org/usermanual/development/en/module-reference/processing-modules/input-color-profile/)、[colorin 实现](https://github.com/darktable-org/darktable/blob/205f9a55ca345a842ff350bc1b361ad3ac53f2e0/src/iop/colorin.c)。
- [P1] [rawpy 官方平台 wheels / 构建功能表](https://github.com/letmaik/rawpy/blob/2705f5b223c162c3cbc48474fe1a01c3cf09fa4f/README.md)。
- [X1] [peva3 MIT 原文件与 catalog](https://github.com/peva3/EmulsionPresets/tree/0cdb71c60603867a046bc92c63617feec7894dd1)，每款固定 URL 与 hash 见本地 `output/preset-research/practical-xmp-source/manifest.json`。
- [F1] [raw.pixls.us 项目与上传权利声明](https://raw.pixls.us/)、[公开 catalog](https://raw.pixls.us/json/getrepository.php)、[Pixel 4 XL 3502 DNG](https://raw.pixls.us/getfile.php/3502/nice/Google%20-%20Pixel%204%20XL%20-%2016bit%20%284:3%29.dng)、[源站 EXIF](https://raw.pixls.us/getfile.php/3502/exif/IMG_20191023_125156.dng.exif.txt)、[CC0 正文](https://creativecommons.org/publicdomain/zero/1.0/)。
