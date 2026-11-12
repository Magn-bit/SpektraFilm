# RAW 引擎与实现语言评估

日期：2026-11-12  
范围：当前 Windows RAW 导入、预览和全尺寸输出；兼顾 Android 离线复用与后续 Apple 构建。

## 结论

- **不把 `CIRAWFilter` 换进 Windows。** Apple 官方 API 可提供 RAW 显影、EDR、降噪、细节和镜头校正，但可用平台是 macOS 12+、iOS/iPadOS 15+、macCatalyst 15+、tvOS 15+、visionOS 1+，没有 Windows 支持。它只适合未来作为 Apple 专属 RAW 前端。
- **现在也不直接把 Windows/Android 全部改成 darktable 或 RawTherapee。** 官方资料证明二者是成熟的独立 RAW 显影软件，但没有证明它们在 SpektraFilm 的目标相机、色彩契约、滑块延迟、峰值内存和全尺寸输出上胜过当前组合。未有同一批 RAW 的实测，就不能把“更好”当作事实。
- **实现语言继续采用分层方案：Python/PySide6 管理桌面 UI 与任务；C++ 管理 RAW/native 图像核心；Android 继续经 JNI 调用 C++。** RAW 核心已有 C++/LibRaw 和跨端 native 能力，重写成 Rust、C# 或 Swift 会增加 FFI/数据复制，且不会自动得到更好的 demosaic 或色彩科学。
- **LibRaw 保留为文件解包/元数据层候选，而不是最终显影质量的默认背书。** LibRaw 自己说明它的基础 RAW 转换是为次要用途保留的 dcraw 衍生功能，不以 production-quality rendering 为目标。后续优先实测 RawTherapee 显影管线；其未胜出前维持现状。

## 候选矩阵

| 候选 | 语言与交付形态 | RAW 能力与控制 | 平台、离线及集成 | 许可证与维护 | 当前判断 |
|---|---|---|---|---|---|
| **当前 LibRaw** | C++ 库；SpektraFilm Windows 静态链接，Android 经 C++/JNI；`rawpy` 是 Python 绑定而非另一套引擎 | 擅长解析相机 RAW、像素和显影所需元数据；带基础 dcraw 派生转换与若干 demosaic 参数，但上游不定位为高质量完整显影软件 | Windows/Android 可离线打包；当前调用边界和输出合同已存在，集成成本最低 | LGPL-2.1 或 CDDL 1.0 二选一；升级可控，需保留相应源码/告知 | **保留解包层**；逐项评估浮点、白平衡、高光和 demosaic 路径，不以 `postprocess` 等同完整商业显影 |
| **Apple `CIRAWFilter`** | Apple Core Image Objective-C/Swift API，产物是 `CIImage` / Core Image 图形管线 | 官方公开 baseline exposure、曝光、局部/全局色调、EDR、色温/色调、降噪、moire、锐度、细节、镜头校正和 draft mode 等控制 | 仅 Apple 平台；可用 Apple 系统栈离线工作。不能编译进 Windows 或 Android；作为 macOS/iOS 特定后端时须统一输出色彩空间和高位深接口 | Apple 系统框架，无独立可移植库或跨端维护入口 | **Windows 淘汰**；未来可作为 Apple 专属后端与同一 C++ film pipeline 对接，再单独验证渲染一致性 |
| **RawTherapee** | 以 C++ 为主、GTK 前端的完整应用；含 `rtengine` 显影实现 | 官方强调多种 demosaic 与显影控制，并有自有 RAW 读取实现；是最值得拿来与现有 RAW 预处理作同片比较的开源候选 | 官方称跨平台；可以作为离线完整程序验证输出。现有证据不足以确认稳定、受支持的独立嵌入 ABI；直接进实时桌面工作流需要评估引擎抽取/维护或独立进程开销 | GPL-3.0；SpektraFilm 主程序也标记 GPL-3.0，但仍需随发布保留依赖许可、源码和修改说明 | **质量基准优先候选**；先比较它的真实全尺寸输出，不直接假定一定更准或更快 |
| **darktable** | C 实现的完整非破坏 RAW 工作流软件；Windows 10+、Linux、BSD、macOS | 完整开发与导出管线，适合高质量参考图、功能和参数行为对照 | 可离线完整运行；目前评估未发现受支持的独立稳定 RAW 引擎 ABI。以独立程序/CLI 作逐张对照较现实，嵌入桌面实时预览需要承担管线、资源和状态同步成本 | GPL-3.0；主程序同为 GPL-3.0，发行仍需满足许可证和源代码义务 | **高质量对照候选**；不作为实时引擎直接替换，除非 benchmark 与嵌入原型证明值得 |
| **RawSpeed** | C++ RAW 解码组件 | 官方说明其面向快速 RAW 数据解包，输出未修改 sensor RAW；明确不做去马赛克、白平衡和颜色校正，因此不提供可直接观看的成片 | 可成为解码阶段候选；离线/嵌入需按锁定版本验证。速度不能代表完整图像效果 | 当前上游 README 声明 LGPL v2；发布前应按选定 commit 重新核对完整许可证 | **仅作为速度/格式解包实验候选**，不能替代完整 RAW developer |
| **重写成 Rust / C# / Swift** | 需要重建解包、demosaic、颜色、线程和格式适配，或通过 FFI 调用现成 C/C++ 核心 | 语言本身不给出 demosaic、相机矩阵或高光还原优势 | Swift/CIRAWFilter 限 Apple；Rust/C# 若继续调用 LibRaw/RT 仍需 FFI，跨大图缓冲区还要约定所有权和像素布局 | 需要自建 RAW 技术栈与维护团队 | **不采纳**；对当前风险没有可证实的图像/性能收益 |

## 语言决策

| 层 | 选择 | 依据 |
|---|---|---|
| 桌面界面、流程与文件任务 | Python + PySide6 | 已与现有工作区、缩略图队列、异步控制器和工具生态接通；避免将核心像素循环留在 Python。 |
| RAW 解包、demosaic 接口、色彩与显影核心 | C++ | LibRaw 和两个开源完整显影候选都以 C/C++ 原生代码为主；可直接控制线程、内存预算、浮点像素和 Windows/Android ABI，并已存在 C ABI/JNI 集成。 |
| Android 桥接 | Kotlin UI + JNI/C++ 核心 | 保持系统 UI 语言与共用高成本像素实现分层；离线交付不需要解释器或远程服务。 |
| Apple 专属 RAW 解码 | Swift/Objective-C + Core Image（未来选项） | `CIRAWFilter` 不能跨平台，但可以通过平台适配层提供 Apple native 解码，再传入共用胶片处理合同。它与 Windows/Android 的输入显影可能不同，需保留来源/引擎标识并做观感校准。 |

不建议为“语言更新”迁移整个桌面应用。此处最重要的是明确 C++ 层返回什么：方向正确、全尺寸、线性高位深、相机/镜头/曝光/白平衡元信息明确，带取消和进度；上层不应依赖某一供应商的 gamma 编码预览。

## 下一步验证门槛

1. 以相同的 Sony A7CR RAW、至少一张可用中画幅 RAW 和一张高 ISO RAW，对照当前 C++ LibRaw、RawTherapee、darktable。相机样片、版本、参数和色彩空间固定；不以嵌入 JPEG 代表 RAW 显影。
2. 分开记录解包、demosaic、色彩变换、预览、完整输出的耗时与峰值内存；报告设备（当前 RTX 3070 Ti/CPU）、冷/热运行和并发数。没有测量时不宣称“更快”。
3. 对比中性区曝光/白平衡、肤色、饱和高光、暗部噪声、细节/摩尔纹、镜头校正和输出尺寸；按固定显示变换看图，同时检查浮点范围和 16-bit 输出。
4. 若 RawTherapee 在目标画质上稳定胜出，再做最小 C++ 纵切片：一次 RAW → 线性工作像素 → 原有 SpektraFilm 光谱运算 → 原尺寸 TIFF/JPEG；验证连续预览延迟、峰值内存、离线打包、相机支持和 GPL 交付义务。darktable 同理只在用户体验与打包成本可接受时推进。
5. 若候选只胜在一项 demosaic 或降噪阶段，优先评估移植/独立集成该阶段，而非整个 GUI 应用；必须保留来源与许可证，并以可复现 RAW 对照证明改进。

在完成这些同片实测前，当前正确决策是保持 Windows 现状，不做未经验证的全量换引擎。Apple 后端与 Windows 的质量、性能结论必须分开验收。

## 本机环境复核 · 2026-11-12

- 当前 Windows 成品 `release/Windows/SpektraFilm` 已含 SpektraFilm 0.8.0 和 `spektrafilm_raw.dll`；上一份成品验收记录为 [`windows-0.8-release-verification.md`](windows-0.8-release-verification.md)。本轮没有引擎代码变更，因此不生成一个仅版本号不同的新包。
- raw.pixls.us 当前目录确认有 Sony ILCE-7CR 无损压缩 4:3 RAW（约 75.91 MB，CC0）及 Fujifilm GFX100S 16-bit 无损压缩 RAW（约 129.34 MB，CC0）；同一目录还列出 Hasselblad X2D 100C 和 Phase One IQ4 150MP 样片。这使目标覆盖可取得，但不代表文件已经下载或完成比较。
- 官方 RawTherapee 5.13 x86-64 Windows release zip 已从 GitHub Release API 确认存在（约 121.5 MB）。本轮对 raw.pixls.us 的直接传输约 15–35 KB/s，短时只得到不到 0.5 MB；GitHub release zip 传输也未开始有效下载。为避免数十分钟空等，已中止这些下载。未留下可用于解码或对比的完整样片，也未运行 RawTherapee 对照。
- 因此本轮交付的是引擎/API/语言和部署选型，不是画质或速度竞赛。现有六类相机记录仅证明当前 LibRaw 路径能解码指定样片并保留其解码尺寸；不证明其观感胜过 RawTherapee/darktable 或 C1/LR。
- 当前组合结论：Windows 继续使用 C++/LibRaw 负责 RAW 兼容解包与相机元数据，既有 C++ 原生影像管线接收线性高位深像素并执行 SpektraFilm 自己的光谱算法，Python/PySide6 负责界面和任务编排。`rawpy` 是相同 LibRaw 家族的 Python 封装，不应被误计成更好的独立成像引擎；未来可收敛两条不同参数/版本路径，但须先在真实同片和 CPU 模式关键工作流验证。
- 继续替换的选型门槛是取得完整 A7CR 与至少一种中画幅样片、可运行的候选版本及完整输出，并在相同输入上检查颜色/高光/细节、原尺寸、耗时和峰值内存。否则保留已发布 0.8.0，不冒称“最佳算法”或“已还原 C1”。

## 一手资料

- Apple `CIRAWFilter` 官方 API 与平台可用版本：<https://developer.apple.com/documentation/coreimage/cirawfilter.md>
- LibRaw 官方定位、支持范围及自述的转换质量边界：<https://github.com/LibRaw/LibRaw/blob/master/README.md>
- LibRaw 官方 C++ API：<https://www.libraw.org/docs/API-CXX.html>
- LibRaw 官方双许可证声明：<https://github.com/LibRaw/LibRaw/blob/master/COPYRIGHT>
- rawpy 官方 README（明确说明它是 LibRaw 的 Python wrapper）：<https://github.com/letmaik/rawpy/blob/main/README.md>
- RawTherapee 官方 README（C++、GTK、GPL-3.0、RAW 读取/显影能力）：<https://github.com/RawTherapee/RawTherapee/blob/dev/README.md>
- RawTherapee 官方许可证：<https://github.com/RawTherapee/RawTherapee/blob/dev/LICENSE>
- RawTherapee 官方处理引擎源代码目录：<https://github.com/RawTherapee/RawTherapee/tree/dev/rtengine>
- darktable 官方 README（完整非破坏 RAW 工作流和 Windows 支持）：<https://github.com/darktable-org/darktable/blob/master/README.md>
- darktable 官方许可证：<https://github.com/darktable-org/darktable/blob/master/LICENSE>
- RawSpeed 官方说明（输出未修改 RAW、无 demosaic/WB/颜色校正，并标明 LGPL v2）：<https://github.com/darktable-org/rawspeed/blob/master/README.md>
- 当前 Windows native RAW 解码合同、限制与打包方式：[`native/engine/upstream/engine/WINDOWS_NATIVE_RAW.md`](../native/engine/upstream/engine/WINDOWS_NATIVE_RAW.md)
- 当前 C++ RAW 入口与线程限制：[`native/engine/upstream/engine/src/io/raw_decoder.cpp`](../native/engine/upstream/engine/src/io/raw_decoder.cpp)
