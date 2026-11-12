# SpektraLab 全量功能审计 · 2026-11-12

本文件核对参考软件的实际消费者与 SpektraFilm Windows 实现，不把字段、资源文件或旧版 `complete` 标签等同于可用功能。Windows 0.8.0 已完成冻结成品关键验收并发布，确切范围见 [成品验收记录](windows-0.8-release-verification.md) 和 `release/Evidence/Windows-0.8.0/review.json`。下方母表保留源码专项完成当时的状态标签；“包待验”是历史阶段状态，不表示整版未发布。它也不代表每项组合都已在成品中逐项穷举验收。当前差异以本节的成品状态说明、末尾收尾结论和 [简明功能对照](spektralab-feature-comparison.md) 为准。上游增量另外记录，不覆写 2.2.0 固定基线；已列真实差异继续保留。

## 基线与证据边界

- `R`：`output/reference-spektralab-latest/SpektraLab-2201f5fa4d256b0c742b46b8e31f8176a12ca6ea`，2026-11-08 主源码，发布标签 2.2.0。
- `R2`：`output/reference-spektralab-update-20261111/SpektraLab-1952c63537ec576d24422f1065b12495631346a5`，2026-11-10主提交及2.3.2发布；增量审计另记，下面母表仍明确保留R固定基线。新增Decode真实场景直方图见`docs/scene-histogram.md`，native与HDR film-session专项已过，最终包关键节点亦已通过，范围单列在成品验收记录。
- `H`：`R/app/SpektraLab/Sources`，当前 Swift/Catalyst host；`M`：`R/modern_UI/Spektrafilm/Spektrafilm`，**本 checkout 只保留 Localization / Resources / icon，旧 Mac 业务源码已不在此目录**；`T`：`R/desktop`，Windows/Tauri 分支。下文“旧 M”只表示 T/PARITY 对历史 Mac 的描述，不能算已读旧 Mac 源码。
- `W`：`output/reference-spektralab-latest/windows-portable/SpektraLab-Windows-x64-portable-spektralab-windows-v1.3.4-beta.2`。`BUILD-MANIFEST.json` 标记提交 `2ca735ad60a998e925bf346f57d80012bdb5c6bf`。这是旧 Windows 成品，不等同于最新 Mac 2.2.0。
- `L`：`output/reference-spektralab-latest/SpektraLab_library-f236e03b4c8eea622fd7360c4d6277ada48b180c`，MIT 图库 SDK。
- 官网本地资料：`output/editor-0.6-research/spektralab.txt`，主要对应 1.3.7 文案；不能用它证明 2.2.0 每个细节。
- 方法：逐组阅读 feature/settings/model/engine/service 的入口、调用方与编码链，并核对本项目 QML → Controller → shared/native/output。此次审计不重复大 RAW 性能测试，不计算哈希。
- **已核实**表示静态入口和真实消费者已核对，动态验证只引用写明范围的既有证据。**部分**表示至少一环缺失、行为不同或正在集成。**缺失**表示未找到对等可用入口/处理链。**未运行平台**单独标识 Apple 平台专属能力，不能称本机动态验证。

## 2.3.2 增量状态（R2，不改写旧基线身份）

完整差分见 `docs/spektralab-update-2026-11-11.md`，本地13提交/149文件；图库SDK未变，材料目录没有新增。最新官方Windows仍1.3.4-beta.2，不能用Mac新版本号冒充Windows产物能力。

| 增量 | 本地消费者与证据 | 当前范围 |
| --- | --- | --- |
| Decode后场景直方图 | SceneHistogram → 256px pre-scene → native实际scene_latitude/scene_curve节点 → curved RGB128bins，EditorTools曲线旁同轴图 | 源码专项覆盖真实照片、连续更新、过期隔离和空/禁用/隐藏状态；Windows 0.8.0 收录该组件并有专项记录，但没有把每种曲线、明暗主题和所有尺寸组合列为成品穷举验收 |
| 数字中间片作为印相选择 | EditorTools DI → digital_intermediate设置/native → Cineon专用view，保留独立DI原log输出配方 | 源码专项确认专用view与原log导出的分离；Windows 0.8.0 的实际运行检查覆盖 Cineon DI、专用 LUT 与 TIFF/JPEG路径；物理片边 DI 明确拒绝，未声明所有材料组合等价 |
| 画布色域 | Settings colorDisplay.canvasSpace → 新native浮点CAM16/CCTF桥 → 预览/细节消费者 | sRGB/DisplayP3/AdobeRGB/ProPhoto 源码对照通过；Windows 0.8.0 包含 Adobe RGB/HEIF 与颜色管理运行证据，但没有在本机验证 macOS CAM16 显示链或每种显示器 |
| 真HDR/峰值亮度 | native每介质gain曲线、正片独立光谱HDR扫描 → 图像rendition/文件gain map | Windows 0.8.0 当前构建通过兼容配方、1200×800 原尺寸 JPEG gain-map 写出和独立解码；Qt画布仍为SDR，不代表 HDR 显示器预览、排版 HDR、物理片边 HDR 或 61MP 速度保证 |
| 放大机四项与预闪范围 | 新minilab按真实光学常量比率/预闪中灰域修正，旧neutral外观精确复原 | 有 native 差异与中性恢复专项，Windows 0.8.0 对支持的材料组合有成品路径；校准只覆盖已验证配对材料，不宣称 SpektraLab 全部放大机模型等价 |
| 上游平台修复 | Finder drag/drop、Intel Metal math启动自检 | Windows已有独立拖放与Vulkan数学路线，不照搬Apple API；未运行macOS，不声称复刻其平台行为 |

### Windows 0.8.0 成品状态对照

以下状态用于解释历史专项标签，不把“源码验证”“资源在包内”和“运行成品验证”混为一谈。精确成品检查项见 `release/Evidence/Windows-0.8.0/review.json`。

| 对照范围 | 当前结论 | 可支持的说法 | 不支持的外推 |
| --- | --- | --- | --- |
| SpektraFilm Windows 0.8.0 发布物 | 成品审查 `ok=true`；GUI、CLI、引擎、素材和 QML 资源随包，冻结工作流通过 | 0.8.0 已发布；审查覆盖光谱选择、基础显影、异步导入、预览、撤销/重做、原尺寸单张导出、ICC、CLI/MCP、首张照片自动显示等记录项 | 不代表 253 行母表的每个参数组合均经过独立成品测试 |
| SpektraLab 2.3.2 增量中有明确运行证据的交集 | Cineon DI、色彩输出路径、HDR gain-map 有 0.8.0 对应成品检查 | 可称相应功能进入 0.8.0，且限定在报告记录的容器、配方、尺寸和材料范围 | 不称 macOS Swift/Metal 与 Windows C++/Qt 代码或结果逐项等价 |
| 上游源码专项、Windows 包内能力 | 曲线 / 色轮 / 通道混合、缓存、图库分面、来源信息、材料试阅、几何引导、排版等按各自专项证据记载；成品冻结也核对对应 QML / 运行路径 | 可说功能已随 0.8.0 发布并有范围受限的源码或运行证据，逐项边界保留在母表 | 不把资源存在、单一夹具通过、或源码节点通过说成全面稳定性/性能验证 |
| 未重新验证或明确差异 | 多图批量导出、全机型 RAW、极端内存、冷启动普遍表现、自动透视全场景、完整 Apple Catalog 迁移仍有边界 | 保留为已知风险 / 功能差异；按简表标 P1/P2 或平台边界 | 不将单张导出、单一机型或目录级重新定位扩大成全覆盖 |

## 首批 P0 / P1 缺口闭环记录

| 优先级 | 发现 | 参考实际链路 | 当前缺口 / 处理归属 |
| --- | --- | --- | --- |
| 源码已定向验 / 包待验 | 输出配方必须真正改变打样，批量逐张使用原图 | `H/Features/Export`、`H/Mac/Export/MacExportCheck.swift`、`H/Engine/ExportWriter.swift` | `output_proof.py` / `OutputProofView.qml` 实际 render → encode → readback、同编码件发布、取消和上一有效图保留；`output/output-proof-review/report.json`，384×256真实代理，非大RAW测速 |
| 源码已定向验 / 包待验 | 同 GUI CLI/MCP 必须作用于当前窗口 | `H/Mac/MacDriver.swift`、`T/agents` 与运行控制契约 | 默认关闭的认证QLocalServer接实际Controller；19个GUI工具含真实预览/原生分析；`output/gui-analysis-tools/verification.json`，独立session仍为12工具且不能冒充同窗 |
| 源码已定向验 / 包待验 | 导出源 EXIF / GPS / IPTC | `H/Engine/ExportWriter.swift` 的 `metadataFrom` → `metadata(from:)` → ImageIO | `export_pixels(metadata_source)` → `export_metadata.py` → ExifTool UTF-8参数流；中文路径/真实相机EXIF与尺寸方向ICC清理通过，未逐类穷举所有GPS/IPTC标签 |
| 源码已定向验 / 包待验 | 可命名的完整暗房预设 | `H/Services/PresetStore.swift` → `H/Features/Develop/PresetSheet.swift` | `FilmLibrary` 分类保存/重命名/删除恢复/重开/未知字段/坏文件只读；两目标应用均可撤销并保留crop，`output/film-library-review/report.json` |
| 源码已定向验 / 包待验 | 用当前照片试阅胶片 / 相纸缩略图 | `H/Services/StockPreviews.swift` / `StockPreviewRules.swift` → `StockPreviewPanel.swift` / `StockCards.swift` | 真实当前照片≤640px源、可见优先串行、前台busy让路、≤12张/12MiB；同上证据，选择与试阅设置一致 |
| 已接 / 包待验 | 负片无相纸 / 扫描底片模式 | `H/Model/FilmParams.swift` 的 `scanFilm` 与印相选择消费者 | `EditorTools` → `scan_film` → CPU/native与缓存身份；扫描关闭不适用的Minilab/EDR；半格原生gate已有定向验 |
| 源码已定向验 / 包待验 | EDR 渲染选项 | `H/Model/FilmParams.swift` → engine `params.cpp` 的 `print_render.edr_enabled` | 8彩色纸材各自256点标定/native finite且有差异，黑白无标定禁用；`edr-materials.json`及`output-proof-review/report.json`，不代表Apple显示器EDR |
| 已接 / 包待验 | 分层颗粒 / 印相效果 gate 的模型差异 | `H/Model/FilmParams.swift` 的 `grainLayered` / print effects gate | 状态/CPU/native/缓存键均接，保留量；最新宽屏H隐藏旧入口，T有真实入口，不把H字段当现有可见UI |
| 源码已定向验 / 包待验 | 分类剪贴板需按版本准确映射 | `H/Model/SettingsClipboard.swift` 当前11组；旧官网/截图不同 | `settings_sync.py` canonical分类/摘要/来源及重启持久，逐图历史；默认保留每图crop/调色/片边；`refinement-integration/report.json`与FilmLibrary节点 |
| 源码已定向验 / 包待验 | 完整渲染持久缓存与独立预算 | `H/Services/AppSettings.swift` / `StorageTidy.swift` / `Engine/FullRender.swift` | `disk_cache.py` / `full_detail.py` 三类5/10/8GiB有界LRU、pin/安全清理、源stat/Settings/颜色域身份；同颜色域跨格式原像素float32复用，异域依原链重建；见`docs/full-detail-cache.md` |


## 功能矩阵

后续段落按实际功能组补全，包含已有能力与缺口；旧 `docs/spektralab-2.2-parity.md` 只作为历史声明，不作为验收证据。

### 设置与产品级状态（入口 / 消费者已读）

| 功能 | 参考位置与实际消费者 | 本项目位置 | 状态 | 缺口 / 边界 |
| --- | --- | --- | --- | --- |
| 新照片默认胶片 / 相纸 / Last used | `H/Services/AppSettings.swift:newFrameStocks` → `Mac/Settings/MacSettingsDevelop.swift` 的两个选择器 | `preferences.py` / `SettingsPanel.qml` → `Controller._settings_for_import` | 已接 / 包待验 | 胶片与相纸各自saved/last/明确材料；不兼容纸回auto，已有照片不覆盖。实现链已核对，独立新图默认组合尚待聚合验。 |
| 预览长边 | 同上 `previewLongEdge` → 原图代理调度 | `SettingsPanel.qml` / Controller preview edge | 已核实 | 1080/1920/2560/3840；是预览而非最终输出 |
| 自动镜头校正偏好 | `AppSettings.lensCorrection` → `AppServices.holdLensCorrection` → `FrameDecoder` 的 `CIRAWFilter` | `SettingsPanel.qml`、`desktop/lens.py` / RAW development | 已核实 | 独立 Lensfun/RAW 路线，覆盖受相机/镜头数据限制，不冒称 Apple/C1 同算法 |
| 裁切重映射物理片幅 | `AppSettings.cropRemapsFrame` → 物理格式解析 | `FilmFormatControl.qml`、Settings 的 `crop_remaps_frame` | 已核实 | 用户原位裁切与物理片幅是独立控制，默认不擅自改变颗粒尺度 |
| 随机相机机身 / Another | `MacSettingsDevelop.swift:filmEdge` → `AppSettings.anotherBody` → FilmEdge journey | SettingsPanel片边机身 → preferences.frame_body_seed → Composition新打开初始值 | 部分（进行中） | 已接按照片区分/固定/更换机身与真实全局默认消费者，seed进入native片边；source-workspace新增节点验证新打开默认/已有排版不覆盖及按照片确定性。不声称所有Mac机身旅程等价，成品待验 |
| 界面 80–150% 缩放 | `Features/Settings/AppearancePage.swift` → `DesignSystem/InterfaceScale.swift` | `SettingsPanel.qml` / `desktop/preferences.py` | 已核实 | 独立于照片缩放；已有四语言/缩放旧证据，当前整合 UI 尚待统一验收 |
| System / Light / Dark 模式 | `AppearancePage.swift` → `AppAppearance` / Theme | `components/Theme.qml` / SettingsPanel → preferences.appearance | 部分（已定向验） | 单窗明暗往返、主按钮/selected/hover文本均≥4.5:1、RGB曲线/色阶≥3:1、纯黑SVG真实tint与Canvas重绘通过；output/dark-theme-review/verification.json，1366×768/QML0。成品和所有DPI未泛化。 |
| 明暗模式独立背景色 / HEX / 复位 | `AppearancePage.swift:BackgroundPicker` → `AppBackground` | `Theme.qml` / SettingsPanel → light_background/dark_background | 部分（已定向验） | 分别保存六位HEX与复位，真实主题消费者；默认暖纸白/石灰画布保留，明暗关键组件实际截图/对比度已验。最终包待验。 |
| 工作副本 / 预览副本 / 完整渲染三预算 | `MacSettingsStorage.swift` → `AppSettings` 5/10/8GB → `StorageTidy` / `FullRender` | SettingsPanel资源页 → fullDetail.configureBudgets → DiskCache | 部分（已定向验） | 5/10/8GiB独立预算0–65536MiB、持久LRU、工作/代理/最终域身份和使用中pin已验。保存float32完整最终图，不是上游pre-Layer2的16位tile；跨进程写锁未实现。 |
| 存储分类占用 / 安全清理 | `MacSettingsStorage.swift:parts` 区分 copied-in originals / working / previews / full | SettingsPanel资源页 → fullDetail.storageUsage/clearCategory → DiskCache | 部分（已定向验） | working/preview/full真实占用与分类清理已接并验证；生产中clear延后到映射释放。只清自己生成的平面缓存，不删原片；本项目无同语义copied-in originals第四类。 |
| 完成后台导出开关 | `FeatureFlags.backgroundFinish=false`，设置行隐藏 | Windows 后台任务线程 | 未运行平台 | 上游自身未启用 Apple continued-processing，不计本项目功能差距 |
| Pro-control 基础/高级密度 | `AppSettings.proControl` → Develop panels | 现有按任务的折叠工具组 | 部分 | 没有同名双级模式；用户要完整模式且布局简洁，不应机械加开关 |
| 四语言 | `Model/Localization.swift` / Settings | `desktop/localization.py` / QML qsTr / translations/ui.json | 已核实 | 当前1049静态词条/96锚定模板，22本轮组件缺口0，en/zh-Hant/ja占位完整；四语言切换节点通过。保留16条QFont点大小警告的已知记录，不以此声称所有DPI字形已验。 |
| 减少动效 | SwiftUI 系统 accessibility reduce motion | Theme / preferences reduceMotion | 已核实 | 自有统一动效 token，保留用户认可风格 |
| 日志保留 / ZIP / 查看目录 | `MacSettingsDiagnostics.swift` → `Diagnostics/LogBundle` | SettingsPanel / `desktop/diagnostics.py` | 已核实 | 本地诊断，未见自动上传；本轮不重复生成 ZIP |
| 参考更新 / 许可 | 上游官网与支持者/版本入口 | `desktop/update_check.py`、Settings about/license | 部分 | 能手动检查参考版本，本项目没有托管的自动升级服务；支持者页面不属于编辑功能 |

### 导出模型已确认的版本差异

最新 H 的 ExportRecipe 容器只提供 JPEG8 / HEIF8 / PNG8 / TIFF16，四空间；支持 full、12MP、任意 longEdge、任意 shortEdge 和离线 preview。旧 M 还含命名模板、DI 等桌面扩展。本项目 PNG/TIFF 可选 8/16bit、DI、处理后 DNG 和 RAW 原样副本是额外能力，应保留。H 的 full 受设备 cap 限制；本项目最终输出必须遵守用户原像素要求，不能照抄其减尺寸策略。

最新宽屏源码的另一重要边界：`DevelopInspectorParts.swift` 把 Edit 固定为 Adjust；原 EngineRouter、Enlarger、Pre-flash 页入口退休，已有值继续渲染并被 Reset 清除。`DecodeSection.swift` 明确 Scene Placement 不再有控制，保留历史帧 wire，以 Decode curve 代替。功能审计须同时核入口和调用方，不能把旧 View 定义当作当前界面能力。

相反，`T/src/panels/LeftRail.tsx:296–316` 确有 No Print Profile / DI / Print Effects / EDR 的实际 UI 与 setter，`RightRail.tsx:299` 菜单确有 grainLayered。它们可作为 Windows 分支对照，但不能套成最新 H 界面截图。旧 `T/PARITY.md` 的 feature gate / unsupported 说明须与消费者同时读取，文档的 ported 不自动等于原生成品支持。

### 暗房、解码、格式、材料与光学

| 功能 | 参考位置与实际消费者 | 本项目位置 | 状态 | 缺口 / 边界 |
| --- | --- | --- | --- | --- |
| 可关闭胶片显影、自然原片 | `H/StockPreviewPanel.swift:filmSwitch` → FrameEdit.appliesFilm → EngineRouter | `EditorTools.qml:filmEnabledButton` → `Controller.setFilmEnabled` / Settings.film_enabled | 已核实 | 原片不是预先套胶片，保留独立编辑器功能 |
| 彩色负片 / 黑白 / 正片 / Still-Cine 分类 | `H/Model/Stock.swift`、`StockPreviewRules.swift`；`T/StockList.tsx` | `shared/film_profiles.py`、Studio 胶片档案、native runtime profile | 已核实 | 目录数与真实性由片边/相纸专项逐数据核对，不以封面数量当材料数 |
| 当前照片胶片与相纸试阅条带 | `H/Services/StockPreviews.swift` → scheduler.stockPreview → `StockPreviewPanel/StockCards` | FilmLibrary.qml → desktop/film_library.py → current-photo native auditions | 部分（已定向验） | 可见优先串行、前台busy让路、关闭/切源过期隔离；≤640px单源、≤12图/12MiB；真实照片16张滚动后12缓存、4.15MB，选择与卡片一致。不是上游相同32MB磁盘策略。 |
| 相纸兼容约束 / 正片直接扫描 | `StockPreviewRules.paperShelf` / StockCatalog.isSlide → strip 禁用 | `shared/darkroom.py:resolve_paper,paper_choices` → `native_spectral.params_for` | 已核实 | 黑白只匹配黑白纸；正片禁用相纸 |
| 负片 No Print Profile | `T/LeftRail.tsx:PrintProfile` → params.scanFilm → wire `scan_film` | `EditorTools` 相纸列表scan → `Settings.scan_film` → `native_spectral.params_for` | 部分（进行中） | 主线程本轮接线并关闭扫描时不适用的Minilab/EDR；正片仍自动直接扫描。模式与最终成品待集成验 |
| 印相 EDR | `T/LeftRail.tsx` → effectiveExtendedDynamicRange → `print_render.edr_enabled` | `EditorTools` → `Settings.extended_dynamic_range` → CPU/native；`ctrl.edrSupported` | 部分（进行中） | 8纸材真实EDR资源和native有限输出专项已验；当前GUI选材/扫描/正片禁用状态与最终包待验，不是显示器HDR |
| RAW As shot、色温 / 色调 | `H/DevelopPanels.swift:ScenePanel` → changeDecode → FrameDecoder；`T/RightRail.tsx` → redecode | 原片/基础 WB、`raw_development.py` / `raw_source.py` | 已核实 | 本项目允许普通图色调调整，但真实 RAW 解码与编码后 WB 的范围应区分 |
| RAW 镜头自动矫正 | `H/FrameDecoder.swift` 使用系统支持的 Lens Correction | `desktop/lens.py` / native LibRaw / Lensfun | 已核实 | 开源数据和本地可用依据；不从商业模块复制二进制算法 |
| 去紫边 | 上游不见对等独立主控 | `EditorTools.qml:defringe` → imaging preparation | 已核实 | 本项目额外能力，应保留 |
| RAW 解码路线 / 场景高光余量 | `H/FrameDecoder.swift` CIRAWFilter；`T` LibRaw host | `raw_source.py` / `raw_development.py` / native | 已核实 | 非同一解码器；已有 Bayer 余量和兼容 RGB16 路由，不能声称还原 C1 私有显影 |
| 胶片曝光 | `H/DecodeSection.swift` Film Exposure ±8EV → shoot wire | `EditorTools.qml` / Settings.exposure → native 2^EV pre stage | 部分（进行中） | 基础曝光UI/归一化限值为±8EV，沿真实2^EV处理链；局部蒙版仍±3EV。source-workspace/refinements新增真实native端点有限响应已过，成品与完整RAW耗时不由此证明 |
| 自动配光：均衡 / 中央 / 保高光 / 保阴影 | `Model/FilmParams.swift:ExposureMethod` → meter / SceneLatitude | `autoMeter` + `native_optics.py` → native solve | 已核实 | 曝光/滤色/两者三作用域，源stat/参数迟到隔离；127×79同GUI真实原生job通过，HDR时延证据另述，不能当任意RAW耗时。 |
| 源曝光与旧中心重点兼容 | `ExposureSource` custom/metered/legacy | 本项目四种测光方式和手动曝光 | 部分 | 无对等独立 legacy/custom 来源选择；保持手动可控，不回退旧公式 |
| 宽容度直方图 / 介质范围 / 分离度 | `SceneLatitude.swift` / latitude UI / fit | LatitudePanel.qml → Controller.measureLatitude/applyLatitude | 已核实 | 原始/拟合分布、材料范围、超白/过期状态；同GUI latitude只测量，place仅有效fit应用且有历史，603事件心跳节点通过。 |
| 旧 Scene Placement | H 当前 UI 退休；旧 M/T 有左右放置或 gate | Settings 场景置位 / Latitude fit | 已核实 | 我们保留可用调节，是增益；不能误说当前 H 仍有其入口 |
| Decode 场景曲线 | `DecodeSection.swift` → FilmParams.sceneCurve → `scene_curve` 129×5 samples | `CurveEditor.qml:scene` → scene_curve_samples → native wire | 已核实 | 在胶片曝光前线性场景 gain；不等同于输出 RGB 曲线 |
| 物理片幅预设 Still / Cine | `Model/FilmParams.swift:FilmFrame` / format UI | `FilmFormatControl.qml` / `shared/darkroom.py:FILM_FORMATS` | 已核实 | 135/半格/XPan/中画幅/大画幅/Cine，真实毫米长度 |
| 长边/短边与自定义 4–200mm | 同上 FilmSide / sideLength | FilmFormatControl / native geometry | 已核实 | 不是仅改裁切比例；原始物理尺度参与颗粒与光学 |
| mm / cm / inch 显示单位 | `Model/FilmParams.swift:FrameUnit` / `T/RightRail` | FilmFormatControl → preferences.format_unit → mm内部值换算 | 已接 / 包待验 | mm/cm/in切换仅显示/输入换算，存储与native始终毫米；不改变物理尺度语义。 |
| 四种颗粒形态 / 独立大小 | 上游通常单 stock 模型 + multiplier | `GrainSelector.qml`、`grain_texture.py` / native grain_type/size | 已核实 | 本项目额外能力；当前形态差异与细腻度仍由视觉反馈持续验收 |
| 分层颗粒开关 | T RightRail 菜单 → wire；H最新宽屏隐藏 | `EditorTools` → `grain_layered` → `grain_sublayers_active` | 部分（进行中） | 已由固定True改为状态、CPU/native消费者与缓存键；新GUI状态和切换出图待本轮集成 |
| 颗粒 / 光晕独立启停并保留强度 | H FilmParams grainActive/halationActive；T ToggleRow | EditorTools → grain_enabled/halation_enabled → CPU/native/缓存键 | 部分（已定向验） | 独立布尔旁路保留原强度，整合9项节点开关/恢复通过，不再靠强度归零伪装相同语义；最终包待验。 |
| 散射独立强度 / 尺度 | H/T effects scatter → native halation scatter | EditorTools 光学 / params_for | 已核实 | 可跟随光晕或独立，关闭时尺度禁用 |
| 防光晕层移除 | H Format / T RightRail → antihalation_removed | 光学控制 / runtime capability | 已核实 | 依真实模型支持，正反射类材料约束不以标签替代 |
| 高光 boost / protect / headroom | 参考 engine schema 与旧 M Format | EditorTools 光学 / native_spectral | 已核实 | 支持能力/强度有依赖禁用；全图峰值已有专门一致性证据 |
| DIR 层间耦合强度 | FilmParams.effects.couplers → engine | EditorTools / native_spectral | 已核实 | 黑白和不支持材料禁用；并非所有 material 可有同效果 |
| 印相曝光 / 黄与品红滤色 | H旧 Enlarger、T LeftRail → print wire | EditorTools 印相 / print_exposure,y,m | 已核实 | H brightness采用 2^-stops；本项目“印相曝光”采用2^EV是有意不同语义，不应盲目反号 |
| 相纸预闪 | H FilmParams.preflashExposure / 旧Enlarger | EditorTools / native_spectral preflash_exposure | 已核实 | R旧基线范围0–0.03；R2消费上游0–1归一化显示对应实际0–0.2，不重缩旧保存值。半格逐孔预闪专项与2.3.2 native节点均有证据，成品待验 |
| 眩光 | H effects.glare / T ToggleRow → print engine | EditorTools / glare_active percent | 已核实 | 独立0–30%，材料/直接扫描约束应按实际支持表现 |
| 相纸效果总旁路 | T LeftRail.printEffects → glare/preflash gate | `EditorTools` → `print_effects` → preflash/glare gates | 部分（进行中） | 主线程本轮已接保留数值的总开关、CPU/native与缓存键；扫描等依赖条件待集成验。最新H保留字段/退休入口，WindowsT入口可达 |
| 快速 Minilab 标定 LUT | H EngineWire + reference calibration resources | `setMinilab` / native params | 已核实 | 仅标定组合可用，完整谱是默认；不是任意胶片的通用快算法 |
| DI 替代相纸 / 蓝通道补偿 | H FilmParams / engine DI；T gate拒绝则禁用 | digital_intermediate.py / Settings.digital_intermediate + OutputRecipe.di_blue_compensation → native wire | 部分（已定向验） | DI印相选择、普通view与四画布域均经lab-232-desktop真实照片节点；原Cineon代码与显示view明确分开。source-workspace蓝补偿delta0.0545968；物理片边拒绝DI而非静默改用相纸。成品待验 |

## 检索纠正记录

源码路径以 `rg --files` 为准：早期猜测的 SettingsDialog.qml、output_recipe.py、desktop/settings.py 与旧 M Panels 路径不存在，已改为 SettingsPanel.qml、shared/output_recipes.py、desktop/imaging.py。一次在参考 Sources 工作目录搜索本项目 desktop 路径失败，随后切回项目根读取。宽泛输出被截断的搜索不作为已核实依据，改按具体功能/消费者读取。

再次逐目录核实：M 当前只保留三组资源，旧 M Export/Agent/Canvas 代码不能在本 checkout 动态或静态验证；T/PARITY 中对它们的名字仅是历史说明。所有最新 H 能力以实际 Sources 为准，T以 TS 消费者/gate 为准。

### 输出、配方、色彩管理与交付

| 功能 | 参考位置与实际消费者 | 本项目位置 | 状态 | 缺口 / 边界 |
| --- | --- | --- | --- | --- |
| 配方新建 / 命名 / 保存 / 删除 | `H/Services/ExportRecipeStore.swift`、Settings RecipePages；T export recipes | `OutputRecipeDialog.qml` / Controller.outputRecipes / JSON 持久化 | 已核实 | 不是仅固定几种格式按钮；配方完整参数可保存 |
| JPEG8 / HEIF8 / PNG / TIFF | H ExportRecipe.Format → ExportWriter；T write_image | `shared/output_recipes.py` / `desktop/output.py` | 已核实 | 本项目 PNG/TIFF8/16，JPEG默认100/4:4:4，HEIF8；格式能力不退化成 H固定深度 |
| RAW 原样副本 / 处理后 DNG16 | H/T 无同等完整对照 | output recipe raw/dng | 已核实 | RAW为原文件复制，不可冒称处理后的专有 RAW；DNG是处理后线性sRGB RGB16 |
| Cineon DI 与显示LUT | H FilmParams DI / engine；T DI门控取决于host支持 | digital_intermediate.py → DI TIFF16 + companion LUT；普通照片专用view | 部分（已定向验） | lab-232-desktop实图确认view只应用一次、post→geometry、JPEG/TIFF一致；原Cineon输出精确代码/无RGB ICC/不受显示后期影响。蓝补偿source-workspace有真实差异；相纸密度cube不能套Cineon，物理片边DI显式拒绝。成品待验 |
| 四输出空间 / ICC | H OutputTransform → CAM16 compress → ExportWriter | `color_management.py` / output.py ICC / native outputspace | 已核实 | sRGB/AdobeRGB/P3/ProPhoto均真实变换；成品色域与显示器变换分开 |
| 软打样 / 显示器ICC / gamut warning | 旧 M color management；T仅sRGB，无profile awareness | `color_display.py` / Settings proof controls | 已核实 | 本项目显示链优于旧Win；有浮点LCMS对照旧证据，不能把它代替配方编码打样 |
| 配方编码后回读打样 | H MacExportCheck逐项调度/尺寸深度验证；T仅1400px画布proof | output_proof.py / OutputProofView.qml → encode/readback/tile | 部分（已定向验） | 384×256真实照片代理、JPEG实际编码回读、中文EXIF、1:1有界tile、相同artifact发布、取消隔离/上一有效图及导出后恢复通过；非大RAW输出测速。 |
| Full / 长边 / 短边 / MP尺寸 | H `Features/Export/SizePage.swift` → recipe.outputSize | OutputRecipeDialog → OutputRecipe/recipe_dimensions → proof/export | 部分（已定向验） | 三种互斥任意精确尺寸与归一化消费者共用，默认原尺寸/不放大、raw/DI清缩放；源码节点实测original/short-edge，未把其余每个尺寸组合写成已运行。 |
| 离线 preview 明确降级 | H ExportRecipe.Size.preview / Original missing状态 | 代理存在但原文件失效 | 部分 | 未找到明确“导出预览副本”选项；当前原源失败应报错，绝不静默代理冒原图 |
| 文件名模板 / 示例 | 旧 M ExportRecipe；T exporter token map | OutputRecipeDialog自定义 → output token planner / metadata header batch | 部分（已定向验） | 支持{name,film,paper,index,date,year,month,day}；默认原文件名_胶片名称。日期仅用模板才每64头读取，缺EXIF明确无拍摄日期、不用mtime代替；整合命名规划通过。 |
| 目标文件夹 / 子文件夹 | H Files destination；T location | Controller选目录、recipe.subfolder、原导入文件夹默认 | 已核实 | 用户要求默认导入路径下类型子夹仍保留，可显式改位置 |
| 文件冲突：编号 / 跳过 | T existing-file policy | OutputRecipe.conflict / batch planner | 已核实 | 不给覆盖原片的危险默认；参考覆盖策略不是本项目必须照搬的优点 |
| 批量串行 / 失败记录 / 取消 | H ExportService/ExportPlan / MacExportRun；T Stop between frames | Controller.export_recipe_batch / batch / atomic publish | 已核实 | 一张原源处理后释放，不缓存整批完整帧；取消清理与单调进度已有旧证据，本轮proof复用须再验 |
| 每张输出网格 / job log | H MacExportPage/Run；旧 M详细页；T明确skipped | ExportResults.qml → ctrl.exportItems / retryFailedExports，复用两导出页 | 部分（已定向验） | 实际一成功一失败、原因可见、按钮仅重试失败且沿用原参数快照、原尺寸与两窗口布局通过；导出结束打样自动恢复，最终包待集成 |
| 导出后指定应用 Open With | 仅旧 M 历史说明；T PARITY明确skipped，最新H未找到对等入口 | recipe.open_after只打开文件夹 | 历史差异 / 待确认 | 不能把打开文件夹称外部编辑器Open With，也不能把历史文档当最新H必有功能 |
| 源EXIF / 相机 / 镜头 / GPS / IPTC | H ExportWriter.metadataFrom → metadata(from:)过滤复制 | export_metadata.py → ExifTool UTF-8 stdin / output.metadata_source | 部分（已定向验） | 中文目标、SONY/ILCE-7CR/日期/ISO真实写回且最终尺寸/方向/ICC正确；代码选择复制捕获EXIF/GPS/IPTC但未穷举每类tag，拒旧尺寸/MakerNote污染。 |
| 原子发布 / 尺寸深度回读 | H ExportWriter.partial → readback → move | imaging `_publish_export` / output | 已核实 | 失败不得留下最终名半成品；无需逐文件哈希，关键节点回读足够 |
| 相纸 .cube输出 | T实际export菜单 → `exportCube(printStock)` → `spk_print_lut_table` | EditorTools印相入口 → Controller.paperLutInfo/exportPaperLut → paper_lut.py → 现有Job/export_pool | 部分（已定向验） | 8种真实33³表、红轴最快/float32逐样本回读、中文路径/原子发布/失败释放/Ilford禁用/QML0通过。输入为配对负片归一化染料密度，输出Display P3+CCTF；不能直接套普通RGB或当前Cineon DI，不含当前调节/空间效果。最终包待集成，见docs/paper-lut-export.md |
| 系统 Share / Photos | H ExportRecipe.files/share；iOS Share sheet | Windows保存/打开目录 | 未运行平台 | Windows可另加分享但不要求复制iOS系统Photos；不把平台专属计作编辑器故障 |

### 导入、图库、会话、目录与大量照片

| 功能 | 参考位置与实际消费者 | 本项目位置 | 状态 | 缺口 / 边界 |
| --- | --- | --- | --- | --- |
| 文件 / 文件夹 / 拖入导入 | `H/Mac/Import/MacImportFlow.swift` / Drop / Scan；T files.rs | `import_workspace.py` / `import_bridge.py` / Studio DropArea | 已核实 | 保留用户大量直接拖入路径，不强迫建catalog |
| 递归扫描 / 选择候选 / 全选 / 取消 | H MacImportScan / MacImportSession | ImportWorkspace/QML，分批扫描/单线程预览 | 已核实 | 元数据/缩图渐进，不全量解码所有 RAW |
| 粘贴文件 / 剪贴板图片 | H MacImportDrop；T平台open | Controller.paste / import bridge | 已核实 | 快捷键可用但不在主界面加用户反感的粘贴提示文案 |
| 系统 Open With / 单实例转交 | T platform/files.rs/lib.rs | main.py位置路径/--open → SingleInstance → 当前window/controller.add_paths | 部分（已定向验） | 两真实进程/两小图交给同一窗口、最小化恢复、导出时排队、Qt FileOpen和CLI自动化关闭通过；截图/验收实例独立。未自动抢占系统文件关联，最终包待验 |
| 导入时默认外观 | H AppSettings.newFrameStocks → import jobs | Controller._settings_for_import → preferences.default_stock/default_paper | 已接 / 包待验 | 独立saved/last/指定材料入口及消费者已接，纸材兼容回auto；保存材料/特效默认不覆盖已有图，各组合新导入待末节点。 |
| 原文件只读 / 移除不删除原片 | H RemovalWords / Originals / import references | SessionBrowser.removeSelected / Controller | 已核实 | Delete移除软件列表；不会擅自删除源照片 |
| 唯一图库入口 / 返回编辑 | H Mac shared browser / MainWindowLayout | Studio / SessionBrowser / LibraryWorkspace | 部分（已定向验） | 按用户要求移除旧三导航与看片台，仅图库入口与编辑返回；当前多个真实1366/1440专项截图可用，确切成品仍待最终验收。 |
| 直接快速会话 | H Mac folder source / session | LibraryWorkspace.quickSession + 直接编辑列表 | 已核实 | 不强制永久收藏/评级，符合本项目任务 |
| Catalog / Session新建打开 | `H/Mac/Library/LibraryAPI` → L host；MacSettingsSources | LibraryWorkspace.chooseOpen/create → native/library helper | 已核实 | 真 SQLite/helper，非仅JSON模拟；已有Unicode/会话旧证据 |
| 相册新增 / 重命名 / 删除 / 加入移除 | H MacLibrarySidebar/Actions → library data | QML相册菜单 → createAlbum/renameCollection/remove | 已核实 | 真SDK mutations，C1只读来源限制正确保留 |
| 变体新建 / 切换 / 独立设置历史 | H LibraryAPI variants / frame linkage | QML variant row → createVariant/activate / edit cache | 已核实 | 同路径不同变体不能互相覆盖；已有同路径验证旧证据 |
| 编辑持久化 / revision冲突 | H LookTransactions/library helper | LibraryWorkspace保存队列 / reload / SaveAsNewVariant | 已核实 | 异步顺序写入；冲突可重载或另存，不盲覆外部状态 |
| 留用 / 不留用 | H gallery filtering / library flags | setSelectedRetained | 已核实 | 本项目采用用户所需简单二态选片 |
| 星级 / 彩色标签 | H MacMetadataPicker → helper override | 无主流程入口 | 有意不加 | 用户明确不需要评级；保留C1元数据读兼容不等于要加UI |
| 文件名检索 | H Mac query / filters | LibraryWorkspace.query → filter.text | 已核实 | 原生SDK text真实范围是文件名/display name，不冒称相机/关键词全文搜索；相机/关键词用独立精确分面 |
| 日期 / 机身 / 镜头 / 类型 / 关键词分面 | `H/Mac/LibraryUI/MacLibrarySidebar.swift:facetGroups` → MacImageQuery | LibraryFilters.qml → activeFilters → images.list + images.facets | 部分（已定向验） | 全库计数保留其他分面条件，维度内OR/维度间AND；日期半开范围、C1导入关键词、空/清除、按库持久、实际点击/QML0通过。单线程每批64只读文件头补EXIF，不RAW解码；不加评级/强制入库 |
| 已显影 / 已打开显影过滤 | H sidebar developedOnly + facets | LibraryFilters → LibraryWorkspace saved-edit filter/facets | 部分（已定向验） | 已有显影调整按实际已保存参数过滤，节点已验；不是上游developed-cache/已打开状态的同义复现，标签明确避免误导。 |
| 拍摄/文件名/添加时间排序与方向 | H MacSharedControls → query.sort | QML三项排序 → setSort | 部分 | 有三类固定方向，未有独立升降序；不能把backend descending布尔当完整UI |
| 大图库分页 / 虚拟化缩略图 | H MacLibraryGrid / helper query | QML GridView + LibraryWorkspace bounded page | 已核实 | 当前页注册/移除缩图，避免N个完整图驻留 |
| 照片元数据 Info面板 | H MacLibrarySidebar.infoPane/InfoSheet | LibraryInfo.qml → LibraryWorkspace.photoInfo | 部分（已定向验） | 单选真实相机/镜头/拍摄时间/尺寸/格式/ISO/光圈/快门/焦距/曝光补偿/源路径，多选相同/多种/未知摘要；信息独立可滚，实际EXIF与1366布局/QML0通过，最终包待验 |
| 多目录 Sources 列表 / 在线状态 | H MacSettingsSources列all sources/open/remove/re-read | LibrarySources.qml → folders/locations/C1 origin | 部分（已定向验） | 本库多监视文件夹、状态/计数/上次刷新、逐项/全部刷新、取消监视与重新定位均接消费者，避免重复列同一路径；当前C1来源可同步。仍非跨多个资料库同时挂载的持久多源导航 |
| C1只读链接 / 独立复制 / 更新快照 | H CaptureOneSource / LibraryAPI → L | QML更多菜单 / syncCaptureOne | 已核实 | mirror/复制，不运行C1显影引擎、不写原C1库；busy/WAL/revision旧证据范围保留 |
| 监视文件夹 / 自动更新 / 手动刷新 | H MacSettingsSources watchedFolders | QFileSystemWatcher + poll / watchFolder/syncFolders | 已核实 | bounded增量；串行helper不并发回放写操作 |
| 移除监视文件夹 UI | H MacSettingsSources watched actions | LibrarySources确认 → unwatchFolder → folders.remove | 部分（已定向验） | 说明仅停止刷新，真实按钮验证照片/持久调整/原片全部保留，未监视目录新增文件不再导入；仍监视目录正常增加。最终包待验 |
| 原文件丢失 / 文件夹重新定位 | H LocateSheet / MacLibraryAPI.relink | QML原片位置 → chooseRelinkLocation | 部分 | 目录级relink已接，单文件定位与离线preview差异尚缺完整入口 |
| Session Capture/Selects/Output/Trash搬移与还原 | H/L Session设计 | QML只Selects与restore / moveSelected(role) | 部分 | 后端支持角色，GUI未提供全部；是否加Trash需符合用户只留用/移除偏好 |
| 旧应用库迁移到catalog | H Mac/Migration/MacLibraryMove | 现有session JSON迁移与打开资料库 | 部分 | 无参考旧Apple应用库导入迁移；本项目不必伪装兼容不同格式 |
| 自定义照片排序 / 拖动重排 | H LibraryOrdering/FrameOrder；T明确未实现 | 当前直接列表/时间排序 | 缺失 | 若需复现图库交互，应明确拖动操作与原片路径不变 |

### 基础编辑、画布、曲线与几何

| 功能 | 参考位置与实际消费者 | 本项目位置 | 状态 | 缺口 / 边界 |
| --- | --- | --- | --- | --- |
| 亮度 / 曝光 / 对比 / 饱和 / 自然饱和 | H EditTool.controls → Adjustments → Layer2Renderer；T GLSL + CPU twin | EditorTools → imaging.Settings → native pre/post | 已核实 | 有真实处理；HDR/缓存与跟手性能本轮仍在修，不等于效果已达到C1私有算法 |
| 高光 / 阴影 / 白 / 黑独立控制 | H tone controls → Layer2Kernel | EditorTools / shared.levels / native editor detail base | 部分（已定向验） | 9点稀疏双边log-luma细节/边缘保护与48px halo分带，CPU/native关键节点过；真实61MP源640px交互代理热路径median33.706ms，不是C1私有算法像素等价或屏幕60fps。 |
| 自动白平衡 / 自动影调 / 自动色阶 | H 未见相同全部自动按钮；有测光配光 | autoAdjust工作线程 / auto_adjust.py | 已核实 | 本项目额外能力，可信度与幂等/迟到隔离保留 |
| RGB+亮度色阶 / 输入黑中白 / 输出黑白 | 上游H Adjustments与直方图非完整色阶 | `LevelsEditor.qml` / `shared/levels.py` | 已核实 | C1风格已有独立实现优势，不因对齐Lab删除 |
| 8色 HSL | H HSLPanel/Adjustments → Layer2Kernel | ColorToolsPanel / shared.hsl / native | 已核实 | 选色状态、按色复位；当前HSL轨道未像参考每色分别表达变化方向，UI可精修 |
| 3×3通道混合器 | `H/Features/Develop/Edit/HSLPanel.swift:ChannelTool` → Adjustments.channelMixer → Layer2Kernel | ChannelMixerPanel → Settings.channel_mixer → CPU/native/输出 | 部分（已定向验） | I+百分比偏移的3×3编码RGB，位于HSL后/曲线前，独立于原色校准。6项颜色节点及整合精确值/undo/redo通过；最终包待验。 |
| LR式原色校准与阴影色调 | 上游H未见同完整控制 | CalibrationPanel / native pre | 已核实 | 本项目额外能力，应保留可视色带 |
| master+三区色轮 | H Adjustments.ColorBalance master/shadows/midtones/highlights → ColourPads | ColorToolsPanel四轮 → ColorGrading.master/三区 → CPU/native | 部分（已定向验） | 全局+三区已接，现有OKLab/色域保护与混合平衡保留；不是上游cosine RGB逐像素公式。整合全局轮真实指针/细步键盘单历史通过。 |
| 精细低饱和色轮输入 | H ColourPad 11×11网格、饱和ring²；MacColourWheel | ColorWheel local draft/16ms合并 → 单手势历史 | 部分（已定向验） | 指针即时draft、Shift细步.1、Esc/双击reset与单次历史已接；保留圆盘输入而非上游11×11网格/ring²，不宣称逐手势完全等价。 |
| 成品曲线 RGB / luma / R/G/B | H CurvePanel → Adjustments.curves；T CurveEditor | CurveEditor / color_tools / native | 已核实 | 图像亮度曲线独立于RGB曲线，保持已实现优势 |
| 点曲线增点/拖动/删点/输入输出精调 | H CurvePanel / CurveMath | CurveEditor → curveInputSamples / 曲线模型 → CPU/native | 部分（已定向验） | 端点x已可移动、域外常量；parametric输入逆映射保证组合曲线首拖命中无跳。首拖单历史/undo/redo整合通过；拖出删除旧节点复用。 |
| 参数曲线四区模式 | `H/CurvePanel.swift:CurveMode.parametric` | ParametricCurvePanel → CurveSet.parametric → point(parametric(x)) | 部分（已定向验） | RGB/R/G/B/luma五通道四区与可移分界(.05最小间隔)，FC单调插值/旧点PCHIP保真；Settings/CPU/native/同步/最终链已接，6项颜色+整合首拖通过。 |
| 各曲线背景直方图 / 编辑标记 / 持久mode | H CurvePanel / DevelopPanelPrefs | 当前图与Ctrl histogram | 部分 | 有曲线和直方图但不是参考每通道背景/状态全部；持久选中/折叠未全接 |
| 暗角量 / 中点 | H EditTool.vignette / vignetteMidpoint → Layer2Kernel | EditorTools vignette单量 | 部分 | 可用暗角，但缺midpoint独立控制；“强度0”与旁路保留量不同 |
| 纹理 / 清晰度 / 去雾 / 锐化 / 明度彩色降噪 | 上游H未见同等完整主控 | EditorTools / native editor | 已核实 | 本项目额外功能；不因对齐Lab删除，也不冒称商业算法 |
| 独立pre/post调整阶段 | H Decode + Layer2为不同阶段；T pre/post controls | scene曲线、WB/校准/pre + film后曲线/蒙版 | 部分 | 当前未见相同参数任意pre/post切换，语义是固定分工；不得只凭多stage函数宣称全等 |
| RGB/亮度全图直方图 | H HistogramPanel → Layer2Live 640px histogram；T canvas输出histogram | HistogramPanel → ctrl.levelHistogram | 已核实 | 有RGB线+亮度，当前计算/显示与实际预览一致性由集成核对 |
| C1/Lab旧双直方图样式与曝光信息footer | 旧H HistogramStyle；R2 HistogramPanel已固定captureOne样式并退休旧style key | 当前单样式/无EXIF footer | 旧版差异 / 部分 | 最新R2不再有双样式要求，不能继续把缺style开关算新缺口；折叠有，跨launch折叠/ISO快门光圈footer仍非完全对等。 |
| 原图对比拖杆 | H DevelopCanvas/ViewerPane；T compare line | PhotoViewport/PhotoCompare | 已核实 | 实际触摸/鼠标命中、状态可见，原图与最终照片不能错位 |
| fit / 100% / 200% / 任意缩放 / pan | H CanvasZoom/MacScrollZoom；T viewstate | PhotoViewport / Studio zoom | 已核实 | 真实源像素与逻辑DPI分开，有滚轮锚点/拖拽/双击 |
| Navigator小图与视口框拖动 | T LeftRail Navigator → output mini render / visible rect | 新Navigator.qml → PhotoViewport.navigatorRect/centerOnNormalized | 部分（已定向验） | 本轮真实点击/拖动/fit与DPI矩形通过；仅放大显示，不用底部照片列表冒充导航。最终包待主线程集成 |
| 编辑实时 / 停止后清晰帧 / 全分辨率detail | H FullDetail/FullRender / Layer2Live；T live+idle400ms full | Controller interactive/final → FullDetail → PhotoViewport/PhotoCompare tiles | 部分（已定向验） | 160ms settled视口请求、原源完整float32缓存、至多约4MP可见patch及同坐标自然对比；源stat/参数过期撤图，整合真实tile通过。不是把1920px放大称源细节。 |
| 鼠标在图内始终可见 / 工具指针 | H canvas tools / T pointer modes | PhotoViewport本轮去BlankCursor、brush ring+cross | 部分（已定向验） | 真实QML专项通过，成品最终集成未做；事件dispatch不等于稳定60fps |
| 原位自由/固定比例裁切 / 拖位置 | H CropStage/CropScreen / T CropOverlay | CropOverlay/CropToolbar/PhotoViewport | 已核实 | 用户要求原画布框而非另开界面；自由/固定/横竖/XPan已实现，当前通用验证未重跑 |
| 90°旋转 / 翻转 / 拉直 / 透视 / aspect / scale | H Geometry/Keystone/CropStage | GeometryPanel / shared.geometry / native float mapping | 已核实 | 裁切/旋转映射保持源空间一致，非成品JPEG二次裁切 |
| 自动拉直 / 自动垂直 / 自动完整透视 | H CropGuides明确没有自动图像检测；本项目额外 | GeometryPanel → auto_adjust | 已核实 | 本项目独立图像分析，低置信度不乱应用 |
| 手工引导水平 / 垂直 / 四角矩形透视 | `H/Model/CropGuides.swift` → Features/Frame/CropStage Apply最小二乘求解 | GeometryPanel → GuidedGeometryOverlay → applyGuidedGeometry → shared.geometry.solve_guided_geometry | 部分（已定向验） | 本轮三模式、局部拖点/Esc、真实应用、单次undo/redo、原源float尺寸通过；参考线真实源坐标投影，最终包待集成。不是用auto算法冒充手工引导 |
| 自动填满避免空角 | H Geometry/Crop fitting | GeometryPanel.auto_crop / native geometry | 已核实 | 显式可开关，不静默裁切最终像素 |
| brush / linear / radial局部蒙版 | H/T均禁用或退出产品的masks；非同virtual contrast mask | MaskPanel / local_masks / native masks | 已核实 | 本项目明显优势，完整源坐标、羽化/擦除/反转/多层保留 |
| 删除笔画 / 局部可撤销 | 参考C1结构证据而非Lab | MaskPanel / Controller / history | 已核实 | 本轮已有小代理真实交互证据，不复跑大RAW |
| 三线线性渐变 / 法向羽化 / 旋转 / Esc取消 | C1 ViewModels静态结构；Lab无对等已启用面板 | PhotoViewport本轮渐变修复 | 部分（已定向验） | 局部draft/16ms合并、单撤销；最后全窗显示待主线程集成，算法不冒称C1私有实现 |
| 调整蒙版时临时隐藏overlay | 用户任务优于机械复制 | MaskPanel.suppressOverlay/restoreOverlay | 已核实 | 真alpha与轻量guide分离，不能用淡出掩盖未更新照片 |
| 撤销/重做/各项双击默认/全图reset | H EditHistory / pertool reset | Controller.history / FineParameter / reset | 已核实 | 各职责独立；reset可撤销；新预设/同步/渐变须同历史契约 |

### 调度、资源、缓存与引擎边界

| 功能 | 参考位置与实际消费者 | 本项目位置 | 状态 | 缺口 / 边界 |
| --- | --- | --- | --- | --- |
| 原生完整光谱执行 | H SpkEngine → C++/Metal；T native host/Vulkan | native/engine + desktop/native_spectral | 已核实 | Windows C++/Vulkan，不能把Apple Metal timings视作3070Ti实测 |
| 81波长数据 / profile真实性 | R/engine/resources、H StockCatalog | native runtime profiles / vendor profiles | 已核实 | 有真实光谱密度/感色数据，不用普通风格LUT冒充完整谱 |
| 印相只重印缓存底片 | H PrintLayers、spk_reprint；T print deltas | native session/checkpoint / native_spectral cache stages | 已核实 | 底片/准备/HDR detail base缓存实际复用已证；缓存身份含独立特效与输出域，DI补偿source-workspace与DI普通view节点均已过，成品待验。 |
| 单飞、最新输入覆盖、取消过期帧 | H RenderQueue / Planner；T session scheduler | Controller tokens/worker pools + native stage cache | 部分（已定向验） | 61MP源640px代理40输入发布31交互帧，输入→worker publication27.453–57.300ms/median42.476；final精算618ms。不是屏幕FPS或完整RAW导出耗时，现包仍待验。 |
| 全局优先级与作业成本预算 | H Scheduler JobKind/CostModel/MemoryBudget/Planner | 分离import/preview/export pools + native memorybudget | 部分 | 有有界资源与前台优先，但未见参考同一JobKind全局成本队列/统一可抢占预算；新增试阅不能另起无界池 |
| 全图/分带/region选择 | H Planner.ladder whole/bands + memorywait | native optical planner / tiled/memmap | 已核实 | 本项目大像素可region完整效果；不抄H“超过设备cap降尺寸”，不削弱commit保护 |
| 内存压力取消 / 等待原因 | H MemoryProbe / budget/watch / DevelopStatus | native guard / errors / bounded sourcecache | 部分 | 有准入保护，缺参考实时压力观察→作业状态的完整统一链路；不会因此声称全部性能完成 |
| 全尺寸分块磁盘缓存供放大与导出复用 | H FullRender256tile + half level → FullDetail / EngineHost.cached | disk_cache.py/full_detail.py → Float32 mmap / viewport patch / output | 部分（已定向验） | 同颜色域原尺寸float32跨JPEG/TIFF/尺寸配方复用一次render，6项及生命周期2+2项已验；不是上游16位tile/pre-Layer2检查点，跨域CAM16必须按原链重建。 |
| RAW代理的持久缓存 | H RawProxy → WorkingCopies / FrameDecoder | Controller._source → DiskCache working/preview → exact source identity | 部分（已定向验） | 精确解码工作副本和指定边长高精度代理分别持久、lossless mmap/元信息，不混用embedded JPEG；源stat/采样尺寸/颜色域身份和预算验证通过，不能声称跨所有RAW机型已验。 |
| 当前照片材料试阅预算 | H StockPreviews 12MB memory /32MBdisk /800px /onecard | FilmLibrary scheduler/native auditions → bounded cache | 部分（已定向验） | 单个≤640px源、可见优先串行、前台busy让路、≤12卡/12MiB，关闭/切源隔离；实测12卡4.15MB，不照搬上游simulator时延。 |
| 邻片预取 / 最近完整渲染LRU | H MacRenderCache / FullRenderJobs | 轻量缩图 / 当前sourcecache | 部分 | 有缓存和当前预览，没有对等按最近查看完整tile预取/磁盘预算 |
| 批量异步不阻塞GUI / 不全解码 | H import/export services / queues | ImportWorkspace分批 / export串行 / photo model | 已核实 | 保留本项目优势，所有新增图库/试阅任务必须共享预算 |
| 取消与进度单调 | H JobDiagnostics / cancellation / ExportService | Controller cancel / batch / native progress | 已核实 | 已有旧关键检查；本轮新增proof与元数据收尾仍需集成定向检查 |
| 首次启动 / lazy import /首帧 | H bundlednativehost；T WebView2 | desktop/main lazyController / PyInstaller | 部分 | 旧源码first-frame日志不是全冷启动；当前无新冷启动EXE时间，不称“启动已极致” |
| 低层schema和unsupported gates | R/engine/core/params.cpp、T gate.ts | capability flags / materialSupported | 已核实 | schema字段包括scanner、lensblur等不一定有参考GUI，不应逐字段堆控件 |
| virtual contrast mask / Tone Mask | H FilmParams.wire恒false；T gate toneMask false | 不照搬未启用功能 | 有意不加 | 不能把上游disabled功能列为可用差距；不影响本项目真正局部mask |
| Apple EDR显示 / Metal显示链 | H CoreImage/Metal / window platform | Windows SDR ICC | 未运行平台 | 单独技术平台能力，不等于可用EDR印相参数已接 |

### 分类同步、预设、CLI / MCP 与 GUI 状态

| 功能 | 参考位置与实际消费者 | 本项目位置 | 状态 | 缺口 / 边界 |
| --- | --- | --- | --- | --- |
| Copy时选择类别 / Paste / 同步选中 | H SettingsClipboard → CopySettingsDialog / AppServices；T clipboard | SyncSettingsDialog → shared.settings_sync canonical分类 → Controller | 部分（已定向验） | 材料/曝光/WB/胶片效果/相纸效果/scene分开，按选中目标校验后逐图提交单独历史；FilmLibrary两目标/crop保持与整合重启clipboard通过。 |
| 类别范围 / 默认选项 / 版本迁移 | H当前11 canonical leaves，默认除片边全选；旧Win六类 | settings_sync CLIP_VERSION2 / v1迁移 / Controller持久剪贴板 | 部分（已定向验） | 用户方向默认前五组、各图crop/调色/片边保持；复制实际类别/规范字段保真并重启恢复，不等同最新H默认11叶全选。 |
| 每目标单独撤销 / seed与裁切不传播 | H clipboard.applied → LookTransactions | Controller.pasteSettings / perphoto history | 已核实 | 既有逐张撤销证据保留；新类别须本轮定向再验 |
| Copy种类记忆 / 内容摘要 | H ClipboardGroup.remembered / summary | Controller.clipboardInfo/setClipboardCategories → settings-clipboard.json | 部分（已定向验） | 保存source_name/categories/selected_categories/字段摘要，≤1MiB规范子集原子写入，重启恢复通过；不会偷偷将crop加入默认。 |
| Clip文件导入 / 导出 | H PresetStore/SettingsClip；W agent settings patches | 本项目CLI import_clip/export_clip | 已核实 | 传参数而非整图或源路径；有尺寸上限/分类校验 |
| 保存当前完整暗房预设 / 分类保存 | H PresetSheet.SavePreset → PresetStore | FilmLibrary → film_library.py PresetStore → applySettingsClip | 部分（已定向验） | GUI命名/分类保存、应用两目标逐图undo/crop保持、重开恢复通过，不再仅CLI clip导出。 |
| 预设重命名 / 删除 / Undo Delete | H PresetSheet / PresetStore | FilmLibrary.qml → rename/delete/restore preset store | 部分（已定向验） | 真实JSON持久CRUD/删除恢复/重开节点已验，非按钮toast；坏文件只读并提示。 |
| 预设原子保存 / 未知字段保留 | H PresetStore versioned file | film_library.py versioned JSON / preset canonical settings | 部分（已定向验） | 未知JSON字段往返、原子保存、坏文件不覆盖、重开恢复已验；用户预设名与路径不作翻译替换。 |
| 原创 / 社区Hald / XMP部分转换预设 | 上游不是相同预设目录 | StyleLibrary / style_presets / look LUT | 已核实 | 本项目额外功能；XMP不完整转换明确提示，不冒充Adobe配置全还原 |
| 独立离线CLI / stdio MCP | W agents/agent.mjs Workspace + spektralab-cli.cmd | desktop/automation.py / spektrafilm-cli | 已核实 | 无网络服务默认，12标准参数工具旧成品通过；新分类schema需同GUI聚合检查 |
| 同GUI当前窗口入口 / 默认关闭 | 用户截图要求；H MacDriver是debug驱动，不是公开stdio MCP；W agent未见同窗口client | SettingsPanel.guiAutomationToggle → gui_automation.py QLocalServer | 部分（已定向验） | 本用户ACL/随机认证/会话ID、实际Controller与GUI job，源码同窗分析/真实MCP图像603心跳节点过；最终EXE尚未验。 |
| GUI异步导入导出job / query / cancel | W agent nativehost longrequest；H scheduler ownjobs | GUI_TOOL_SCHEMAS / controller workers / job/cancel_export | 部分（已定向验） | 14原工具与5分析/预览工具共19；原同GUI导入导出、参数历史节点及新分析job已有源码证据，独立session不冒同窗，成品待验。 |
| Describe/get schema/材料配对信息 | W agent tool schemas + StockCatalog | automation schemas/catalog + gui describe → real Controller state | 部分（已定向验） | describe返回当前尺寸/材料配对/参数/处理状态，规范参数校验；小图实际GUI socket/CLI节点通过，不伪造未知材料能力。 |
| 模型查看预览图 / MCP image content | W mcp builds image/jpeg content from preview file | GUI preview_image → current published display preview → MCP image/jpeg | 部分（已定向验） | 64–2048有界JPEG、rendering状态不回过期图；实际64×39 JPEG内容块可解码，显示域为monitor-managed-display，不冒充最终sRGB/原像素。 |
| 自动配光/场景置位脚本工具 | W agent usage process/latitude/place | gui auto_meter/latitude/place → Controller/native jobs | 部分（已定向验） | 真实原生求解job，latitude只测量，place仅有效fit应用；discard/failed区分且迟到源stat保护。127×79/603心跳节点已验，未重复大RAW。 |
| 重置 / Undo / Redo脚本与GUI一致 | W reset/export；H EditHistory | gui_automation → real Controller history / independent automation | 部分（已定向验） | 当前窗口调用统一历史，曲线/混合/轮整合撤销重做及既有同GUI参数节点已过，独立session契约不变；最终包待验。 |

## Windows 1.3.4 成品与源码的不一致

`W/agents/agent.mjs` 是可读的 shipped JavaScript，包含 `desktop/agent/workspace.ts`、CLI/MCP 与 exporter 源片段。实际 exporter 已使用 `export_frame` / `export_cineon`、pair参数、no-film、TIFF LZW/preview-page 选项，并按 `hello` 能力决定是否调用。相比之下，`R/desktop/PARITY.md` 仍描述 write_image 和部分早期不支持状态。因此 **不使用 PARITY 的 skipped/refused 文字判断 W nativehost 当天运行能力**；这需要独立hello/runtime证据。

已核实 W 包含：`spektralab.exe`、`spektralab-host.exe`、WebView2Loader、Node24.19.0运行时与 `agents/agent.mjs`/StockCatalog、engine profiles/产品材料/neutral filter/grades/print LUT/constants、两张DI view LUT、Lensfun XML、GLSL/SPIR-V和许可证。存在 Lensfun/DI/pair字段不证明GUI已经支持。此次只读取manifest既有信息，未计算或运行哈希检查。其 `BUILD-NOTES.txt` 明确102MP报告属于historical beta.1，不是beta.2新测速。

### 片边、日期、半格、纸面排版与材料资源

| 功能 | 参考位置与实际消费者 | 本项目位置 | 状态 | 缺口 / 边界 |
| --- | --- | --- | --- | --- |
| 物理片边在显影前曝光 | H FilmEdgeResolver/FilmLayout → Engine canvas → `overscan.cpp` | `film_canvas.render_film_edge` → `native_overscan_options` → `render_film_canvas` | 已核实 | 胶片片门、边字与日期进入完整谱/颗粒/光晕；不是在最终JPEG上画棕色边框 |
| 135 / 120 / XPan等物理片幅和真实毫米尺寸 | H FilmEdgeStock/FilmLayout → supported layouts | `shared/composition_edge.py:FORMATS` / FilmFormatControl / CompositionDialog | 已核实 | 物理格式和照片裁切分别建模；不可用普通正方画布冒充120片边 |
| 一键物理样式及真实当前照片缩略图 | H FilmEdgeJourney四步/FilmEdgeSnapshots | CompositionDialog六种physical presets → `requestFrameTemplates` 串行native | 部分（已定向验） | 本轮135、120 6×6、开窗片夹、XPan、120 6×7、半格已接真实渲染；只是六个入口，不是全部原生片门形态。见专项证据，最终包待集成 |
| 片门 auto / square / rounded / eared / kicked / shouldered | H FilmEdgeSteps.GateShape → FilmEdgeResolver → overscan | CompositionDialog的gateShape字段 → native options | 已核实 | 可组合参数而非六张静态贴图；材料/片幅约束与最终源密度仍需最终UI核对 |
| 片孔透光 / 遮黑及格式依赖 | H FilmEdgeSteps.holesPanel → FilmEdgeSettings.holes | CompositionDialog holes → native overscan | 已核实 | 两者UI均按片幅决定是否可用；孔的大小/落点来自原生格式和机身几何，没有把原生内部字段虚构成独立UI控制 |
| 片基底雾 / 漏光 / 散射 / 机身差异 | H Edge light/body → fog/leak/carrier/camera seed | CompositionDialog light/body → `native_overscan_options` | 部分（已定向验） | 底雾/漏光/散射/seed真实消费者已有专项；本轮新增全局frame_body_seed默认、按照片区分/固定/更换入口，source-workspace验证新打开生效/现有排版不覆盖/确定性，成品待验 |
| 片边 stock字 / 格号 / DX条码 | H FilmEdgeStock/FilmEdgeResolver → native artwork | `shared/composition_edge.py` / `native/engine/upstream/engine/src/pipeline/overscan.cpp` | 已核实 | 按stock与片幅资源输出；未发现对应stock数据时不能凭空伪造实测原卷边字 |
| 扫描窗口 full strip / tight crop / 片夹 | H FilmEdgeSettings scan/gate/crop rules | CompositionDialog `edge_view` / native geometry | 已核实 | 返回有效gate几何供取景映射；片边扩出的像素是画布，不应误报原图降尺寸 |
| 日期LCD / Dots / Data、角落 / 大小 / 亮度 | H FilmEdgeSteps.DateStepPanel → DateBackSettings → FilmEdgeResolver.dateText | CompositionDialog date controls → shared.date_back.imprint_options → native imprint | 部分（已定向验） | 135/半格LCD·Dots·Data、645仅Data、XPan等禁用；裸双图不能Data/片边打印；US/Japan、真实快门光圈Data、日期+Data、半格Data字号上限1及native像素变化通过。仍是共用后背；native无第二孔独立Data字段，不宣称所有Mac逐孔行为等价；最终包待集成 |
| 日期来自EXIF / 自定义文字 | H date resolver uses frame date + face format | `_date_options` 取placement metadata.date，显式输入优先 | 已核实 | 规范EXIF YYYY:MM:DD，不把冒号日期误当时间；缺日期时不得制造拍摄日期 |
| 半格两张独立原片 / 各自取景 / 交换 / 旋转 | H HalfFramePair/PairFlow/PairPieceView → PairDevelop/PiecePlacer | CompositionWorkspace.open_selection/swap/rotate/position → `film_canvas._prepare` | 已核实 | 两张独立曝光源共用同一底片/相纸链，不是两张成品JPEG贴图；用户原图只读 |
| 半格逐孔曝光 / 黄品红滤色 / 预闪 | H PrintLayers对每个不同孔重印缓存底片 | `film_canvas.render_film_edge` left/right print wire | 部分（已定向验） | 每孔preflash真实差异已验；新增scan/positive忽略独立印相、printEffects关闭跳过预闪的native像素比较通过。物理半格不支持DI并明确拒绝，不能把Apple DI物理半格行为称已还原；最终包待集成 |
| 半格横/纵、条带取向、组取景 | H HalfFramePair turned/onStrip/origin/spacing | pair_axis / group_turn / linkFrames / pair_on_strip / pair_spacing_mm | 部分（已定向验） | 裸双图0.5–2mm实际改变原源线性画布与2个native gate，带片条固定1mm；横纵尺寸互换通过。原源1257×800 TIFF16/ICC导出证实未用240px代理；Mac全部取向origin行为未逐项等价验证 |
| `.spektrapair`持久文件与hole replace/remove | H HalfFramePair schema1 + PairKeeping / PairFlow | shared.film_pair schema1 → Composition openPair/savePair/replaceHole/removeHole | 部分（已定向验） | 本项目完整Settings命名空间往返、便携孔字段/未知JSON/取景/移除空孔/替换通过，失联引用保留且可换图。上游独立look与自动测光未逐项映射，最大缩放5与上游4有差异，不宣称跨软件外观或所有Mac旅程完全一致 |
| 纸面/即时相纸/接触印样/图形拼图 | H Frame/LightTable纸张导出；非所有皆为光谱相纸 | CompositionDialog paper category + `shared/composition.py` / `_decorate` | 已核实 | 图形纸面排版和物理胶片分类分开，不能将暖白纸色当新光谱相纸数据 |
| 纸面画布尺寸 / 边距 / 间隔 / 文案 / 颜色 | H Frame/LightTable尺寸与装饰 | CompositionDialog → CompositionWorkspace options →原源串行render | 已核实 | 可预览、换图、逐格取景与最终导出；排版有明确独立输出尺寸，不冒称保留每张整幅所有像素 |
| 最后一项不被footer遮挡 / 黑预览重试 | 参考用户最新截图；H独立stage和controls | CompositionDialog bounded ScrollView + opaque独立footer / sourceproxy / retry | 部分（已定向验） | 专项1366×768、1440×900滚到底可达，QML0；真实native样式截图与layout代理截图分开，最终包仍待集成 |
| LightTable自由摆放 / 角度 / mm纸张 / 存储 / 全源输出 | H LightTable20文件 → Renderer/FullRead/Export/Store | 原LightTable.qml及后端；本轮唯一图库移除其导航 | 有意不恢复入口 | 用户明确说看片台多余、改图库；不得为了机械复现强行加回。其自由摆片能力与当前图形网格不是全等，准确保留差异 |
| 九种真实印相材料 | H StockCatalog + engine profiles | runtime profiles / vendor / `shared/darkroom.py` / MaterialSelector | 部分（已定向验） | 8彩色+1黑白，真实数据与有限输出，公用输入最小RGB8均差1.968；黑白用真银盐胶片非彩色去饱和。材料选择最终包待集成 |
| 每种彩色纸独立EDR标定 | H profile.data.edr_tone_map → native print render | 8个匹配profile各256点追加，无改原6核心数组 | 部分（已定向验） | 同名数据核对后才追加；黑白无标定禁用。8种均有限且delta .00418–.01678，不将SDR印相映射称显示器HDR |
| 30胶片目录 / 新Pro160S、Pro160C、Reala | H catalog与开放光谱资料，不仅增加名字 | film_catalog / runtime/vendor/profile_extensions / neutral packs | 部分（已定向验） | JanLohse MIT a15043f6数字资料，81波长/256密度；三个独立neutral CMY实际消费、相互均差2.15–5.37。密度分量是拟合，未实测DIR禁用，不声称精确复刻实物全部化学 |
| 数据/源码许可证和转换来源 | R各LICENSE/资源notice；L MIT | `licenses/additional-spectral-data/source-20261109`、vendor sidecars、source包 | 已核实 | CC BY-SA4.0与MIT来源分别保留；是否进入确切发布源码包须主线程发布联检，目录存在不等于包已携带 |

片边/相纸运行证据来自 `docs/lab-frames-papers-refinement.md` 和 `output/lab-frames-papers-review/{materials-and-frames,layout-boundaries,edr-materials,additional-materials}.json`。半格/日期新增证据为 `docs/half-frame-date-workflow.md`、`output/half-frame-review/report.json`；相纸cube为 `docs/paper-lut-export.md`、`output/paper-lut-review/report.json`。均为本轮实际源码/native关键节点，不替代最终成品或未验证Mac行为，不另跑大RAW或哈希。

## 页面、状态与真实处理契约

下表是验收的可观察契约和当前证据，不是新运行测试。每一行的“待”必须在主线程关键集成节点关闭或明确保留，不能由静态已接线升级为已验收。

| 页面 / 状态 | 入口与前置条件 | 状态 / 归一化 → 处理边界 | 必须可观察的结果 / 失败 | 当前证据 |
| --- | --- | --- | --- | --- |
| 编辑空态 | Studio唯一选择照片；允许浏览材料 | import workspace / DropArea → 分批metadata与缩图 | 对比/缩放/裁切/排版/导出按实际可用性禁用；拖入高亮；无营销标语 | 源码`Studio.qml`及`output/current-ui/empty-after.png`；最终包待验 |
| 导入扫描 / 导入失败 | 文件/目录/粘贴，不能要求先建catalog | ImportWorkspace单扫描worker → lightweight rows → Controller选择当前 | 渐进显示文件名/原尺寸/失败；取消不继续全批解码；坏文件不使整批丢失 | 既有导入节点，新增导航最终待验 |
| 自然原图 / 胶片开关 | 当前照片可打开；film_enabled可关闭 | EditorTools → Settings.normalized → pre/film/post消费者 | 关闭显影能独立编辑；开关需有效图；代理不能被当成最终原源 | 静态完整链及旧纵向切片证据 |
| 胶片 / 相纸 / 扫描模式 | 材料目录可访问；黑白/正片/负片约束 | MaterialSelector → setPaper/setFilmOption → params_for → native | 当前材料名与结果一致；不兼容纸或无EDR标定禁用；扫描不继续印相 | 新字段/8纸native专项；当前GUI组合和包待验 |
| 参数首次拖动 / 精确输入 | 可编辑当前图；有有效范围和单位 | FineParameter本地值 → 合并输入 → preview最新令牌 → idle精细帧 | 不需先点再拖；数值立即移动，图像持续呈现，末值精确；双击回默认单次可撤销 | 曲线/色轮首拖单历史整合通过；HDR 640px代理实际事件→worker发布27.453–57.300ms，非显示FPS，最终包待验 |
| 裁切 / 取景 / 缩放 | 当前图有效，打开原位crop | CropToolbar / CropOverlay → normalized geometry → float map | 自由/比例/XPan与拖框生效；Esc取消；apply一次历史；缩放不能改变输出像素 | 旧真实QML节点；当前布局最终待验 |
| 对比 / 原图 | 当前frame存在，裁切时禁用 | Studio.compareToggle → PhotoViewport/PhotoCompare同坐标base及原尺寸detail | 左右/开关状态明确，照片不位移；图上指针可见，源细节与自然对比patch对应 | 本轮指针专项、缓存生命周期和refinement实际tile/对比整合通过；最终包待验 |
| 蒙版线性 / 画笔 / 径向 | 当前图有效、选中相应层 | PhotoViewport局部draft → 16ms合并 → Controller history → native alpha | 三线/方向/法向羽化/旋转吻合真实alpha；Esc还原；临时隐藏overlay；一个手势一个undo | `docs/gradient-cursor-refinement.md`与verification.json；局部事件不是照片帧率证明 |
| 撤销 / 重做 / 重置 | 当前历史实际可用 | Controller perphoto/variant history，reset是可撤销新事务 | 不可用按钮禁用；reset范围明确；同步/裁切/渐变不串其他照片 | 分类预设两目标undo/crop保留、曲线/混合/全局轮单手势历史与undo/redo整合通过；最终包待验 |
| 图库 / 直接会话 / catalog | Studio唯一图库；双击或返回继续当前编辑 | SessionBrowser或LibraryWorkspace → SDK/helper → 当前Controller | 删除只移除引用；切换不丢参数；C1只读快照不写源库；多图不完整解码 | 导航静态+空态；SDK旧节点；最终包待验 |
| 排版物理 / 纸面 / 处理中 | 当前选择有效；半格保留两孔且至少一孔有源 | CompositionDialog → workspace normalized options → original source → native canvas或graphic renderer | 选择即改变真实样式；保留上一有效图；报错可重试；只活动卡加载；最后参数不进footer | 本轮6物理/9纸材/2尺寸及半格scan/positive/效果门控/工程/原源TIFF16关键节点通过，确切成品待整合 |
| 输出配方 / 代理打样 | 当前照片与配方有效 | normalize_recipe → render/encode/readback → color display | 空态有动作；品质/空间/位深/尺寸变更可见；DI不用普通RGB软打样 | 真实384×256照片JPEG编码回读/尺寸/上一有效图已验；DI蓝补偿新增末节点待验，最终包待验 |
| 原像素打样 / 最终发布 | 原源仍可访问、full proof完成 | 原源完整render → encoded artifact身份 → 有界tile → 原子publish | 1照片像素/1物理屏幕像素；settings/source/recipe变更不得复用旧件；失败不静默代理替代 | output-proof 1:1 tile、同artifact发布、EXIF/取消隔离通过；full缓存131×97原尺寸float32逐像素一致；非大RAW新测速 |
| 批量 / 失败 / 取消 | 选中N张，不能只看当前frame | 各source/settings/recipe快照 → 串行完整原源 → 每件publish | 分项成功/失败记录；取消进度不回退、临时清理；无整批完整像素驻留 | 真实两源一成功一缺失→仅失败重试→480×320原参数快照及proof恢复通过，1366/1440布局已看；旧batch证据复用，最终包待验 |
| 设置 / 能力不支持 | 设置可进；自动化默认关闭 | preferences → startup/apply / capability flags | 缩放与照片zoom分开；日志/缓存能关闭；无效材料功能禁用，错误可理解 | 三预算/独立开关/clipboard重启及四语言新增节点过；暗色实际视觉和新图材料/机身默认组合仍待相应末节点 |
| 同GUI CLI / MCP | 设置显式开启、当前用户认证通道 | QLocalServer sessionID →真实Controller →异步job/query/cancel | get/set/film/paper/undo/export反映同一窗口；关闭后不可连接；独立session不得冒充GUI | 现有同GUI流程与新增127×79真实原生分析、64×39 MCP image/jpeg/603心跳节点通过；确切成品待验 |

## 源目录覆盖与未验证边界

以下是本次基线的源码清点，不是按文件数估算完成率。Swift数量是当前checkout的物理文件数；一个文件可包含多个功能，也可能只是测试harness或退休页面。

| 源分组 | 文件清点 / 已追踪主题 | 审计结果落点 |
| --- | --- | --- |
| H/Features：64 Swift | Develop33（含Edit8）、Export3、FilmEdge4、Frame2、Import3、Library6、Pair8、Settings5 | 当前可达面板及上下文消费者；旧EffectsPanel/Enlarger定义不等于现有入口 |
| H/Mac：72 Swift | root11、Export3、Import6、Library13、LibraryUI16、LightTable7、Migration3、Render2、Settings11 | Mac宽屏入口、导出/图库、预算/渲染；不冒充Windows或Mac运行验收 |
| H/Model：20 Swift | FilmParams、Adjustments、SettingsClipboard、ExportRecipe、HalfFramePair、FilmEdge/DateBack、Geometry/CropGuides、Stock等 | 参数范围、迁移、兼容/门控、序列化与入口差异 |
| H/Services：24 Swift | Settings/WorkingCopies/StorageTidy/StockPreviews/PresetStore/Originals/PairKeeping/Library/Export等 | 入口后的持久性、缓存、原源/错误/清理契约 |
| H/Engine：28 Swift | Decode/RawProxy/Exposure、Wire/Router、SceneLatitude、PairDevelop/PrintLayers、FullRender/Detail、Layer2/ExportPlan/Writer等 | 光谱和后处理边界、输出空间/尺寸、全分辨率缓存与逐孔重印 |
| H/Scheduler：12 Swift | Queue/Planner/CostModel/MemoryBudget/Probe/DevicePolicy/SpkEngine | 不只核单kernel；同一预算、优先级/取消、设备cap与本项目保原像素策略差异 |
| H/DesignSystem：21 Swift | Theme/Appearance/Background/InterfaceScale、ValueSlider/TickRuler/CoexistingDrag/InputFeedbackRules等 | 控件交互、手势共存、状态/可访问性；平台原语不直接复制到Qt |
| H/LightTable：19 Swift | Model/Store/Touch/Gestures/Renderer/FullRead/Export/Share/Textures等 | A4/A5/A6、99图、mm自由位置/角度、吸附/放大镜；导航按用户要求不恢复 |
| H/Diagnostics：7 Swift | local logs、performance、job status、bundle | 保留真实可比时序；日志存在不证明UI帧率 |
| H/App、FilmEdge、Support | AppServices/Router/Routes/WindowLayout/MenuCommands、geometry/resolver/stock/layout、C桥头 | 路由和实际present调用；Snapshot/DesignGallery/Tour/probe只作开发工具，非消费者功能 |
| T desktop | 左右rail/Canvas/Crop/Curve/Color、export、platform、agent与gate | Windows实际控件与host门控；不把PARITY历史描述直接当成品能力 |
| W shipped Windows | exe/host、agent.mjs、Node、profiles/Lensfun/shader/DI LUT/notice | 本轮仅读库存/可读JS；未运行hello/nativehost或执行新性能测试。其beta.1历史102MP报告不能证明beta.2 |
| L library SDK | catalog/session/album/variant/query/edit/revision/relocation/C1 mirror | 本项目真实helper与QML消费者分别核对；backend支持不等于已暴露UI |
| 本项目Qt/Python/C++ | Studio与组件 → Controller/Workspace → shared models → native/output/resource | Windows 0.8.0 已发布；包内与成品关键路径按上方状态表限定，原始照片只读，Android 本轮不变 |

未知/受限：未在Mac运行H，未运行W的nativehost能力hello；SpektraFilm Windows 0.8.0 的候选整合和冻结成品审查已完成，但不覆盖普通相机、特殊RAW、HEIF系统编码器、极端低内存设备、所有DPI与冷启动时间。材料试阅和三类持久原源/完整缓存有源码专项及限定范围的成品证据；同上游的缓存阶段/颜色域/跨进程锁等差异仍明确保留，不把源码结果替代全机型或全部组合验收。未找到的历史Open With只留待确认，不混入确定最新功能缺口。

## 当前收尾与保留差异

1. **确切成品节点已完成**：Windows 0.8.0 GUI/CLI/helper候选、导入、原尺寸输出、完整光谱和同 GUI CLI/MCP 关键检查通过；首图自动显示另用真实 ImportWorkspace + Studio QML 路径确认。证据为 `release/Evidence/Windows-0.8.0/review.json` 和 `source-milestones/photo-navigation.json`。
2. **状态与首图反馈已发布**：二态控件文案和选中外观统一表达当前值；导入不再在首张预览到达前返回编辑页。导入后画布 `hasImage`、首项路径与 1:1 细节瓦片均通过，无需点击缩略图。
3. **已实现并进入 Windows 0.8.0**：真实材料试阅/命名预设、三类缓存及源细节、通道混合/色轮/曲线、引导透视/Navigator、输出回读/EXIF/失败快照重试、图库分面/来源Info、单实例和同GUI工具。每项具体证据仍按表内范围引用，不扩大成逐项算法等价。
4. **有意不同**：唯一图库、无评级/独立看片台、每图保留裁切与编辑、原尺寸输出不照搬设备 cap 缩小；保留本项目局部蒙版/校准/色阶等能力。色轮、缓存、显影公式均不假称内部实现与上游相同。
5. **仍有真实差异**：自定义照片拖排、独立排序方向、单文件 relink、明确离线预览输出、旧 Apple 库迁移、任意 pre/post 切换、暗角 midpoint、部分曲线直方图偏好和外部应用 Open With 未完全对应；详细状态见功能矩阵及 `docs/spektralab-feature-comparison.md`。
6. **半格/相纸边界**：物理片边 DI、排版 HDR 明确拒绝；Minilab校准表仅适用已验证配对材料；第二孔独立 Data 和全部 Mac pair journey 未宣称等价。相纸 cube 是配对负片归一化密度→Display P3+CCTF，不是通用 RGB 滤镜或 Cineon LUT。
7. **未验证平台 / 风险**：未在 Mac 运行 H，未运行 SpektraLab Windows nativehost hello，Android 本轮不变。所有 RAW 机型、极端内存与冷启动时间没有普遍结论；批量导出此前有 `0xC0000374` 堆损坏记录，本轮没有重跑，不标记通过。
8. **上游边界**：主源码仍为 2.3.2，Windows 包参考仍为 1.3.4-beta.2；Apple-only 代码不计入 Windows 上游包能力。旧 2.2.0 固定基线和 2.3.2 增量分别保留在对应章节，不覆盖证据身份。

补充检索纠正：DateBack模型实际位于 `H/Model/FilmEdge.swift`，不是DateBack.swift；本项目native源码在 `native/engine/upstream/engine/src/pipeline`，不是`native/engine/core`。已通过rg文件库存定位，不重复失败路径；被截断的宽泛输出不作为叶功能核实依据。






