# 2026-11-07 原片质量与中画幅优先

- [completed] 统一 Windows 导入/拖入/元数据/RAW另存的26种RAW格式路由，与Android清单对齐。
- [completed] Android新增显式半尺寸RAW预览；full/preview缓存隔离，完整导出继续从原URI解码并严格校验原尺寸。
- [completed] Sony、Canon、手机DNG及GFX100、X2D100C、IQ4 150MP实际完整解码和源hash验证。
- [completed] 三款中画幅的Android同源C++全尺寸/半尺寸RGB16与官方LibRaw逐字节对照。
- [completed] 81项相关生产回归；独立C1参考22项为21通过、1项已知expectedFailure。
- [completed] Android主/测试APK与Lint（零错误）完成；Windows开发候选重新构建。
- [pending] Android真实设备执行新增CFA预览→完整缓存→JPEG集成测试与高像素性能验证；没有设备，不能称实机完成。
- [pending] 更多机型/压缩与颜色质量对照、完整16位生产输入管线；完整C1显影仍未独立还原。

详见 docs/raw-camera-compatibility.md。正式release仍为0.3.3，本轮未发布。

# 2026-11-07 C1 完整RAW重建：实际中间值与输出

- [completed] 使用原版wrapper在隔离进程取得受控A7CR原尺寸RGB16 sRGB TIFF；约2.33秒仅ProcessToFile，不含完整光谱胶片，也不代表独立实现。
- [completed] 正常运行只读插桩：Bayer/GG参数64条；A7CR ISO噪声表及阈值公式重算逐float一致。
- [completed] 实际CPU Bayer输入/输出裁块采集；确认红蓝原CFA×4、黑偏置保留、单块顶部镜像边界；同片LibRaw/C1比较只平移不拉伸。
- [completed] 独立曲线5324点完全一致；高光90036像素人工参数对照通过；GPU Bayer76单段对照通过。
- [completed] CPU第一/第二步已验证范围独立对照通过；第三步两个标量工作器通过，实际优化整阶段未完成。
- [in_progress] 中性色彩链顺序和前段已取得运行对照；独立ICC融合节点仍有最大9个16位码值误差；GPU四阶段严格级联仍有3场景失败，未提高容差。
- [pending] 完整RAW独立端到端等价、更多原片/ISO、原生生产迁移和Windows/Android验收。当前未完整还原，生产未换C1。

状态总入口：docs/captureone-raw-reconstruction.md。0.3.4候选构建/成品验收完成但正式发布仍0.3.3。

---

# 2026-11-07 当前优先项：Capture One RAW 算法与基础亮度

- [in_progress] 对本机 Capture One 16.8.6 的 RAW 管线做函数级分析与实际输出对照；恢复入口不等于恢复算法，不宣称已完成 C1 引擎移植。
- [completed] 确认两端 RAW 偏暗根因：LibRaw highlight>=3 跳过 histogram 自动亮度；Windows 改 Blend，Android 同时恢复官方 histogram-derived 输出 white，并失效旧缓存。
- [completed] Android 同源主机测试：A7CR 6376×9564 RGB16LE 与官方 LibRaw 全字节一致；原片 hash 不变。不是 Android 真机成绩。
- [completed] Windows 修正后 A7CR 完整光谱 JPG 原尺寸导出成功，262.636 秒、peak 13057.9 MiB。该次伴随 C1/静态分析工作，不能与旧暗图 131.778 秒作严格性能比较。
- [completed] A7CR ICC/FCRV 资源结构和局部数值变换恢复；去马赛克、黑电平、高光重建及完整曲线算子仍待恢复。
- [pending] RAW 回归、C1 对照及现有版本验收完成后再构建发布；0.3.4 尚未发布，0.3.3 仍为正式成品。

以下是此前阶段记录，旧暗图成绩不能作当前画质验收依据。

# 0.3.4 当前收尾：真实原片与阶段性能优化

- [completed] Windows默认CAM16-UCS/sRGB色域阶段Vulkan，数值、黑场与分带验证；CPU同公式回退。
- [completed] CPU曝光/输出色彩分块、等价filter短路及同源Poisson采样器；同步Android科学内核。
- [completed] 两端预览曝光tap缓存；修复上游预览关闭颗粒、Android代理物理尺度错误。
- [completed] M盘α7CR原片6376×9564完整光谱JPG导出131.778秒，源hash不变，peak14628MiB；24MP当前渲染58.570秒。
- [in_progress] 0.3.4全量回归、实际冻结包Vulkan与JPG/TIFF、Android构建/资源/签名验收、发布。
- [pending] 完整GPU曝光/显影/颗粒/印相驻留管线及Android JNI移植；当前不是原生全链路，也未达到秒级导出。
- [pending] 未来Mac Metal编译和实机验收，当前无Mac。

以下为各阶段历史记录；Windows当前选择Vulkan而非最初D3D12。

---

# 2026-11-07 跨平台完整光谱性能工程

- [completed] 审计 SpektraLab Windows / macOS / Android 执行链与公开计时口径；拆分 GPU 计算、预览、缓存重印、RAW 和编码边界。
- [completed] 在当前主机重跑 SpektraFilm 24MP CPU 完整光谱基线：64.622 秒、峰值工作集 5983.9 MiB；filming.develop 28.651 秒、scanning.scan_print 18.728 秒。该路径不调用 GPU；用户确认实际显卡为 RTX 3070 Ti，系统枚举的 RTX 5090 不作为硬件依据。
- [completed] 选定 wgpu-native / WGSL 为共享原生计算接口：Windows D3D12、Android Vulkan、macOS Metal。Dawn 的 Android Vulkan 当前文档状态为进行中；分别维护三套原生 shader 则增加公式漂移和验证成本。
- [in_progress] 设计并实现原生 GPU 光谱纵切片，保持当前 SpektraFilm profile、公式、颗粒物理和源图像素尺寸；不将 SpektraLab 不同模型的性能数值当作本项目保证。
- [pending] 用固定样片逐阶段比对 Python CPU oracle 与 GPU：曝光/光谱上采样、显影/DIR/颗粒、印相、扫描/色域；校验最终颜色误差、颗粒统计、分块接缝与确定性。
- [pending] 让高分辨率管线使用有界 GPU 工作集、可复用设备缓冲和流式输出；实现依赖键控阶段缓存，确保只重算被参数改变影响的阶段。
- [pending] 集成 Windows 原生库并在实际 RTX 3070 Ti 上测 24MP、61MP 与中画幅；完成交互预览延迟、全分辨率渲染、编码和峰值内存分段记录。
- [pending] 集成 Android NDK JNI 原生库，去除全光谱热路径中的 Chaquopy / Bitmap-ByteArray 往返；完成 Gradle、ABI、内存边界与真机验证。
- [pending] 在 macOS 构建同一 WGSL 管线的 Metal 后端并做 Apple Silicon 性能、色差、内存和 UI 体验验收；当前没有 Mac/Xcode，不能将未编译状态记作完成。

决策边界：Python CPU 保留为测试参考；GPU 结果未通过精度与图像回归前不替换正式输出。预览允许使用明确标记的低分辨率源代理，最终 JPG/TIFF 始终从完整源分辨率计算。GPU 不可用时不得静默改用 LUT 或缩小最终图；运行态是否提供显式 CPU 模式待完成硬件兼容验证后决定。

---

# 2026-11-07 配色回退 0.3.3

- 用户否定新配色：恢复此前灰绿、冷白与深灰，覆盖两端主界面/菜单/滑杆/弹窗/系统主题；恢复Windows原14px正文。
- 保留现有布局、字体家族、23款胶片与全部显影/RAW功能，避免把外观回退变成功能回退。
- [completed] 两端0.3.3已发布至release/Windows与release/Android；16项相关回归、Windows实际成品导出/截图、APK资源/签名验证通过，4848个发布文件哈希一致。Android code17，无真机运行验收。

---

# 2026-11-07 当前收尾：纯胶片 0.3.2

- 产品仅完整胶片光谱显影；旧编辑字段中性化，保留23款胶片及7类显影调整。
- Claude暖白/陶土配色、紧凑颗粒菜单；常用参数直接呈现，不强制折叠。主界面不显示推导标签，来源/拟合边界留在文档与元数据。
- 新增Velvia50、Vista100、Natura1600；完整谱与交互LUT共用数据，MIT/原有CC BY-SA分别保留。
- Android严格校验RAW元数据完整朝向尺寸和RGB16字节数；已完成最终构建及包校验，无设备实测。
- [completed] 两端0.3.2构建与发布：Windows实际EXE Portra JPG、Vista100 TIFF及纯胶片迁移通过；五个界面状态截图已检查；4848个发布文件SHA256一致。209项回归（202通过、7归档skip），Android lint 0错误/38警告，无设备验收。
- [limited] 旧临时目录 release/.windows-candidate 删除被自动审批以策略限制拒绝；当前Windows/Android正式成品替换成功。
- 历史记录在下方，仅说明当时状态；当前范围与证据以README、docs/validation.md为准。

---

# SpektraFilm 当前工作（2026-11-07）

## 0.3.2：收回完整光谱胶片显影与 Android RAW 分析

- [in_progress] Windows / Android 仅保留胶片显影、曝光、颗粒及类型/大小、光晕、暗角和强度；导出固定完整光谱。
- [in_progress] 所有产品入口重建白名单参数，旧基础调整、HSL、曲线、色轮、蒙版、几何、风格记录停止生效。
- [in_progress] 使用 REA 分析用户提供的手机版 Lightroom 11.4.3 APK，明确原生解码链路、全尺寸/预览、离线依赖与证据限制。
- [pending] 依据实际证据落地可独立离线实现的 RAW 改进，不把 LR 符号或字符串称为算法恢复，不打包未授权的 LR 库。
- [pending] 两端构建与成品验收；实际 RAW 原尺寸、源文件保护、批量参数与输出后缀验证；无 Android 设备时标明限制。
- [pending] 仅将最新 Windows / APK / 对应原生组件源码发布至 release。

当前保留 Qt/Kotlin、灰绿设计与已认可字体，保留完整 LibRaw/RGB16 缓存与原尺寸区域导出修复。以下为历史记录，不能视为当前产品功能。

# SpektraFilm 开发收尾

## 当前请求：独立离线 RAW 与色彩引擎（2026-11-06）

- [completed] 用户否定自制人像/风光参数预设的效果，要求改用 LR 或 C1 引擎；不再把调整预设名称或微小参数作为解决方案。
- [completed] 只读确认本机 Lightroom Classic15.5 与 Capture One16.8.6.3784 均安装；未启动应用、未改其配置或用户catalog。
- [completed] 已核实两者公开接口需要商业宿主，用户明确 Windows / Android 都必须独立离线；取消宿主插件、电脑代处理路线。
- [completed] 选择可嵌入 LibRaw 解码模块与共享色彩处理；Android 接入真正 RAW 解码、RGB16 私有缓存与原尺寸分区读取，补系统内存准入与unpack预算；Windows 保留 rawpy / LibRaw。
- [completed] 八色 HSL 共享核心、跨端控件/会话/预设、24 项 XMP HSL 字段转换；Adobe Look 配置依赖明确提示，不能称原版效果。原创风格加入分色设置。
- [completed] 公开 DNG 全尺寸/八方向/缓存/取消验证，A7CR同源native主机全尺寸解码与Windows实际EXE原尺寸JPG导出、189项回归、Android构建/资源/签名检查。最终成品证据 output/release-0.3.1-final。
- [completed] 发布 0.3.1 至 release，附 LGPL 原生组件对应源码；Windows/Android 已替换最新版本，校验清单4835项。

约束：LibRaw 是 RAW 读取/基础显影模块，LittleCMS 是 ICC 模块，不能混称商业修图引擎。当前编辑输出为 RGB8，不因内部 RGB16 缓存宣称全链路 16-bit。没有 Android 设备时如实标明实机未验收。

## 当前收尾：0.3.0 实用编辑器与用途风格（2026-11-06）

- [completed] 两端可选胶片、基础编辑、相机校准、画笔/线性/径向蒙版、五通道曲线、三区色轮、手动几何及原像素裁切。
- [completed] 宽松层级与渐进展开、直接操控、独立会话编辑与撤销、预览缓存复用/过期结果保护。
- [completed] 按用户最新纠正撤下重复胶片和实验CLUT；默认改为4人像、6风光原创参数预设，用途筛选、批量与XMP审阅导入。
- [completed] 实用人像/风光样片、179项回归、两端重建和Windows成品实际导出检查；Android仅包/签名/编译验收。
- [completed] 当前EXE/APK已发布release，4831项SHA256核对通过；前端设计Skill与D:/Tool/Skills备份一致且两份结构校验通过。
- [blocked] 旧release/.windows-candidate临时目录的递归删除此前被自动审批拒绝（blocked by policy），未清除；本版候选已由发布脚本正常收尾。

边界：Android尚无独立完整相机RAW解码器，且无设备实测；不能声称用户RAW问题/手机大图导出已解决。macOS/iOS按用户决定暂停。商业参考私有算法未恢复；作者XMP如核心HSL/profile不兼容则不以原名冒充原版内置。早期记录以下视为开发历史，以本节及docs/validation.md为准。


## 当前任务：跨端局部蒙版与连续参数交互（2026-11-06）

- [completed] 定义共享矢量笔触、局部调整、柔边/流量/擦除、多层状态及原图坐标约定，Windows/Android 画笔实现及构建初验。
- [in_progress] 用户追加径向/椭圆与线性渐变蒙版、柔和选区轮廓与直接操控，保持一次操作一次撤销。
- [in_progress] 五通道曲线（RGB 总线/红/绿/蓝/独立亮度）、三向色轮及平衡/混合；共享核心已接后处理，两端控件实施中。
- [in_progress] 旋转、垂直/水平透视、比例、缩放、翻转、自动填满几何；原尺寸处理与分块导出，已有蒙版时锁定几何防止错位。
- [in_progress] 依前端设计 Skill 重排宽松层级/渐进展开/字号，检查真实 Windows 主视图和复杂工具。
- [in_progress] 验证软边/线性光混合、分块一致、预览与导出、旧记录兼容及性能边界。
- [completed] 更新前端设计 Skill 的连续滑杆、宽松工具布局、画布/曲线/色轮交互规则并同步 D:/Tool/Skills 备份；UTF-8 校验通过。
- [pending] 构建并核对两端当前候选与真实 Windows 界面，记录 Android 无设备验证边界。

决策：蒙版在全局显影后按线性光混合局部调整，保存归一化矢量笔触；两端使用同一 NumPy 核心，导出按块计算而非缩略图放大或整帧 alpha。以现有灰绿/组合字体和原生栈扩展上下文工具，不添加人像识别或图库管理。

追加决策：用户确认“镜像”指径向/椭圆渐变。曲线采用形状保持 PCHIP，独立亮度曲线作用于 OKLab 明度；三区调色使用本项目定义的平滑分区和色域压缩。几何使用共享投影矩阵，自动填满改变视野而非降低输出像素。REA 证据为 C1 参数/包装代码/原生边界，不等于恢复其私有像素算法；样片商业软件运行对照尚未完成。0.3.0 画笔版候选构建成功但因追加范围尚未发布，必须按最终源码重建。

## 当前任务：照片编辑工作流整合（2026-11-06）

- [in_progress] 按“不做评级/图库、不复制源照片、批量导入优先”明确产品工作流；相机校准沿用 LR 式 RGB 原色色相/饱和度，不新增青橙分级模块。
- [pending] 新增独立胶片显影开关：新导入照片默认普通照片编辑；开关关闭时跳过胶片 LUT/光谱、胶片颗粒、光晕与暗角，白平衡、曝光、曲线/色调和相机校准继续工作。
- [pending] 在 Windows 与 Android 的紧凑编辑区接入同一开关、状态反馈、每张照片编辑状态和批量预设行为；旧编辑记录保留原显影行为。
- [pending] 补充参数迁移与渲染回归，验证开关开闭、基础调整独立生效、快速预览和原尺寸导出的调用语义；运行 Android 构建与可用的 Windows 检查。
- [pending] 评估蒙版和批量文件会话的下一步边界；不伪称与 Lightroom/Capture One 内部算法等价，也不复制其私有实现。

决策：不新建评级或图库管理；导入路径引用原文件，源照片不会被软件复制或删除。当前编辑状态只在工作会话/已有编辑记录中保存。青橙风格使用相机校准原色控制。首轮实现优先修正可选显影与基本调整的渲染语义，蒙版继续保留为独立功能阶段。

## 当前追加：简洁的局部蒙版与基础调整（2026-11-06）

- [in_progress] 统一采用“单一蒙版入口 + 基础参数”的轻量范围；不扩展人像专属工具组或重量级识别模型。
- [pending] 检查 Windows/Android 画布的指针/触控坐标映射、编辑会话持久化与全分辨率渲染入口。
- [pending] 实现可创建、绘制、软边、擦除、选择和删除的画笔蒙版；提供少量基础局部曝光/色温/色调/饱和度调整。
- [pending] 将蒙版以图层/蒙版形式保存到每张照片编辑状态，快速预览与最终导出共用相同蒙版且不降低源像素尺寸。
- [pending] 运行跨平台参数/掩膜像素回归、Windows UI 检查和 Android 编译；设备不可用时标明未完成实机触控验收。

决策：保留 Python 光谱核心与 Android Kotlin/Chaquopy 接入层；蒙版是后处理图层，不替换底层引擎。桌面工具区保持简洁，控件只在“蒙版”上下文出现。

## 当前新增请求：Android 进度条与相机 RAW 解码（2026-11-06）

- [in_progress] 修复导出进度回退：任务代次隔离旧回调，并在单张与总进度两层做单调保护。
- [pending] 为 Android 接入 LibRaw 原生解码；RAW 预览使用有界小图，JPG/TIFF 导出仍走原尺寸分块管线，RAW 原片导出继续逐字节复制。
- [in_progress] Windows/Android 将“银盐颗粒”统一为“颗粒”，新增有物理参数映射的多种颗粒风格。
- [in_progress] 分析 Android 完整光谱性能瓶颈，只优化有基线支持的热点，不缩小最终输出或退回 LUT。
- [in_progress] 修复右侧参数调节（含暗角等）预览迟滞：先检查桌面/Android 调度和像素预算，保证有即时且可辨识的当前结果。
- [in_progress] 按前端设计 Skill 重排两端核心编辑界面，保留 Qt/Kotlin、现有字体与灰绿品牌方向。
- [pending] 用 REA 只读分析本机已安装的 Capture One 与 Lightroom，提取可验证的颗粒/预览/渲染架构线索。
- [pending] 覆盖 RAW、颗粒、普通照片与批量导出，运行两端视觉/功能检查，构建并更新发布物。
- [pending] 更新发布物与校验记录；无可用设备时明确保留真机验证限制。

## 当前产品范围扩展：个人照片编辑器核心工具（2026-11-06）

- [in_progress] 只读 REA 检查本机 Lightroom Classic / Capture One 图像模块、公开功能结构与安装资源，记录观察证据与未知。
- [pending] 建立跨端共享编辑状态：白平衡色温/色调、曝光/阴影/高光/白场/黑场、色阶/曲线、相机校准和基础色彩微调。
- [pending] 把新模块接入 Windows/Android 完整光谱显影与快速预览；数值输入有即时反馈，曲线/选择控件能直观操作。
- [pending] 完成普通照片与 RAW 的导入、编辑预览和原尺寸导出；保留原片分辨率和输出质量。
- [pending] 重构两端编辑面板的信息层级和手机触控布局，保留现有技术栈、字体与视觉方向。
- [pending] 用单元/主机样例和可用设备执行颜色数值、性能、无障碍、完整流程及构建验收；无真机时注明边界。

决策：优先用开源 LibRaw；用户已确认目标应用已安装，可只读分析本机 Capture One 与 Lightroom，不运行目标中发现的命令/脚本，不把推断伪装成已观察行为。

## 当前任务：双端导出性能与内存不足（2026-11-06）

- [completed] 定位完整光谱流程中的峰值内存与单张导出时延，并保留原片尺寸/导出质量。
- [completed] 将颗粒层插值与采样按层/通道分解，并合并为分布等价的 Poisson thinning。
- [completed] 运行全量 Python 回归及 24MP 时间/峰值内存基准，确认改善未改变显影/导出规格。
- [in_progress] 同步 Android 光谱源码、重建主/测试 APK、运行包资源和主机数值验证。
- [pending] 更新验证记录与发布物；设备未连接时明确标注 Android 真机导出仍未实测。

约束：Windows 与 Android 导入/导出保持源像素尺寸；预览可降采样；不得以降低最终导出画质、跳过完整光谱显影或静默缩图掩盖问题。

## 当前追加迭代：清晰度、导出响应与胶片预览（2026-11-05）

- [completed] Windows/Android 编辑预览使用有界缓存与独立交互通道；Android 编辑位图与高品质导出重新解码路径分开。
- [completed] Windows 预览期间可进入导出；导出使用独立队列，单张/批量均可选目标文件夹。
- [completed] 胶片切换先发布对应快速结果，过期交互帧不会覆盖新结果。
- [completed] 回归并确认导出质量预设未降低；发布 Windows/Android 0.2.7，生成新的发布清单与 SHA256 校验。
- [pending] 本机没有 Android 设备或模拟器；实机触控、内存与速度仍需设备验证。Android 高品质 JPG 维持质量 100，处理像素依设备内存适配。

## 新增反馈：导出耗时与文件体积（2026-11-05）

- [completed] 核对 Windows/Android 四种导出预设的质量、尺寸和 RAW 原字节行为。
- [completed] 分段测量 Windows 完整光谱显影与 JPEG 编码，确认主要延迟在全光谱流程。
- [pending] 尚未收到用户遇到的原片/成片文件，具体体积差只能按其预设和源格式判断。

## 当前请求：两端导入与导出保持源分辨率（2026-11-05）

- [completed] Android 编辑态支持查看原片像素，列表和适屏预览可以使用代理图。
- [completed] Android 高品质 JPG/TIFF 从原片尺寸开始分块显影并以原尺寸写出；逐行编码避免整张输出位图。
- [completed] 核验 Windows 导入源像素访问与全尺寸导出不受预览限边影响。
- [completed] 运行回归、Android 构建和包检查；记录并说明真机高分辨率内存边界。

## 当前请求：整理源码目录（2026-11-05）

- [completed] 识别并保留源码、共享资源、上游参考源码、个人字体和当前/历史发布物。
- [completed] 更新 README 与 release manifest，避免依赖临时输出路径；重新生成发布 SHA256 清单。
- [pending] 清理可重建的本地依赖、构建缓存、测试输出和机器本地配置。执行环境拒绝了递归删除命令，尚未删除目录。

## 当前追加迭代：重新发布与 Apple 平台开发（2026-11-05）

- [completed] 重新构建 Windows 候选并通过完整光谱桌面 smoke；Android APK 从当前源码重建，包内资源与引擎检查通过。
- [completed] 发布 Windows 与 Android 至 release/，4,813 项 SHA256 核验通过并归档上一版。
- [completed] 更新 Android 与 Apple 构建说明、发布记录和本轮验证证据。
- [pending] macOS 原生构建、iOS 工程和完整光谱内核移植；当前没有 Mac、Xcode 或 Apple SDK，不能在 Windows 上生成 Apple 成品。

限制：用户已授权本地重新发布，但没有授权上传源码、付费云构建或签名服务。当前主机为 Windows；Swift 6.4.2 可用，但没有 Xcode 或 Apple SDK，macOS/iOS 原生构建无法在此主机完成。

## 当前迭代：双语字体与 Apple 平台（2026-11-05）

- [completed] 按最后确认统一为中文朱雀仿宋、英文及数字 Noto Serif SC，覆盖正文、标题、按钮、参数与弹窗。
- [completed] 构建可复现的跨平台字体资源；13009 个编码字形的轮廓与水平度量逐字核验。
- [completed] Windows 实际界面、最小窗口弹窗与文件窗口核验；Android 主/测试 APK 与 Lint 编译通过。
- [completed] Windows 退出时释放 Qt 的 Python 日志回调，重新构建并验收本地启动和退出。
- [completed] 发布 0.2.4 至个人兼容路径及默认 release/Windows、release/Android，保留旧版。
- [completed] macOS 原生构建入口与只读环境检查；Windows 没有生成 .app。
- [pending] macOS 原生依赖、打包与界面验收，需可用 Mac 或获得授权的 macOS 构建服务。
- [pending] iOS 工程和完整光谱内核移植、Xcode 构建与设备验收；用户确认暂时没有 Mac，尚无 IPA。

## 目标
2026-11-05 界面精修：移除编辑区胶片宣传短句，收紧标题与参数留白，统一数值排版，明确当前照片与多选范围，并完善胶片搜索反馈。保留明朝体、照片工作区与现有 Qt 技术栈。

## 本轮界面精修
1. [completed] 检查实际界面，保留认可方向。
2. [completed] 去文案、真实明朝字体、统一弹窗、数值与照片选择层级。
3. [completed] 75 项回归、7 组原生流程、52 个 DPI/布局组合与界面截图检查。
4. [completed] 两端只保留完整光谱；Android 原版模型移植并完成主机数学对照、APK 源码与依赖检查。
5. [completed] Android 重置宽度与滑块端点修复；测试 APK 已编译，真机验收仍待设备。
6. [completed] 0.2.1 两端构建、签名/成品验证及本地发布，旧版保留；通用 Skill 与备份一致。

## 上轮目标
2026-11-05 追加需求：圆点/焦点对齐、快速交互预览、扩充真实胶片、自动镜头校正/去紫边、精简原片对比。

## 当前追加阶段
1. [completed] 修复窗口圆点与图外对比控件，固定精简缩放操作。
2. [completed] 独立快速预览、精算质量优先与有界缓存，实测延迟并覆盖旧结果竞态。
3. [completed] 扩充 20 款上游实际胶片配置，分类搜索与资源验证。
4. [completed] 接入严格本机 LCP 匹配、镜头校正和保守去紫边；20 项模块检查。
5. [completed] 修复 Windows 文件拖放及 Ctrl+V 文件/图片导入；主界面不显示粘贴按钮。
6. [completed] Windows 多选/批量预设/参数/导出；Android 多张会话、批量与预览调度，设备边界明确。
7. [completed] 更新“前端设计” Skill 及 D:/Tool/Skills 备份，验证结构与内容一致。
8. [completed] 重建两端、核对成品，发布到 release/Windows 与 release/Android，保留历史与校验清单。

## 前轮目标
完成可交付的 Windows 应用和 Android 初版，保留用户认可的界面、右上角圆点、可读导出按钮与圆角。当前优先修复真实功能与验证缺口，不再重做视觉方向。

## 阶段
1. [completed] 修复分块 LUT、状态、后台导入与安全导出，35 项回归检查通过。
2. [completed] 完成键盘与可读禁用态，修复导出对话框高度；原生窗口六项检查通过。
3. [completed] 隔离 PATH 中错误 ICU，最新 EXE 的轻量 JPG 与完整光谱 TIFF 实际导入/导出验证通过。
4. [completed] Android 主/测试 APK 均构建成功，资源与签名验证通过；没有设备，未声称实机通过。
5. [completed] 更新使用、选型、许可与验证记录，整理 EXE/APK、四种导出预设及已知限制。
6. [completed] 修复缩放后的滚动条遮挡：固定独立 gutter、两页参数与底部滚动同步；四档 Qt DPI 和原生窗口截图通过，已同步成品 QML。

本轮收尾已完成，不代表全部参考功能已经实现。后续功能及设备验收边界见 docs/validation.md。

## 约束
- 照片来自用户导入，不加入 AI 样片。
- 原版科学管线与 LUT 近似明确区分，不虚构支持或性能。
- 不覆盖原片，不发布过期渲染结果。
- 项目当前没有 .git，不执行清理、重置或删除用户内容。
- 普通本地开发已获得授权；未经用户授权不发布或向外部发送信息。

## 已知错误
| 问题 | 证据 | 处理 |
| --- | --- | --- |
| 窗口 roundtrip 测试失败 | offscreen 屏幕 800px 宽却期望 1180px 原尺寸 | 保留真实可见区域保护，修正测试并扩展边界验证 |
| README 存在 AI 样片旧描述 | 正常启动已改为空状态 | 收尾时更新文档 |
| 打包 exe 无法导入 QtCore | 实际运行报 DLL 找不到指定程序 | 排查打包进来的第三方 DLL 版本冲突，不要求用户反复安装运行库 |
| 真窗口最大化重开后还原尺寸错误 | verify_window.py 复现 | 显式保留并恢复正常几何，继续真实窗口验证 |
| Android ScrollView.LayoutParams 无法解析 | compileDebugKotlin | 使用 FrameLayout.LayoutParams 后重建 |


## 2026-11-05 照片管理、细节缩放和字体适配
- [completed] Windows 会话移除、原始像素倍率/定点缩放；Android 缩略图直达编辑与独立批选。
- [completed] 使用适合工具阅读的平台字体；更新前端设计 Skill 并同步备份。
- [completed] 80 项回归、Windows 真窗口截图、双端构建与 0.2.2 个人版本地发布；Android 真机验收仍需设备。

字体方向更新：用户否定系统无衬线，改为查找官方授权的屏幕阅读字体并做实图验证；不强制明朝体。

早期个人构建实验过 Apple 字体；当前交付统一使用共享字体资源，不含 Apple 字体，也不保留个人构建目录。
