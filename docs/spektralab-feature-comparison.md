# SpektraLab 与 SpektraFilm Windows 功能对照

更新：2026-11-12。本文把 SpektraLab 最新源码、SpektraLab Windows 已出货包和 SpektraFilm Windows 当前发布包分开比较，不把一个平台的代码当作另一平台已发布能力。

## 对照基线

| 产品 / 平台 | 版本与证据 | 边界 |
| --- | --- | --- |
| SpektraLab 最新源码 | `main` / `spektralab-v2.3.2`，`1952c63537ec576d24422f1065b12495631346a5` | 本轮远端核对未发现更新；2.3.2 主界面和显影实现主要是 Apple Swift / Metal 源码，未在本机运行 macOS |
| SpektraLab Windows | `spektralab-windows-v1.3.4-beta.2`，`2ca735ad60a998e925bf346f57d80012bdb5c6bf` | 是单独的较旧 Windows 发行基线；有 shipped `agent.mjs`、native host、材料资源和 exporter。不能由 2.3.2 Mac 源码推定这个包有相同 UI / 功能 |
| SpektraFilm Windows | `0.8.0`，本轮 QML 修订 `2026-11-11-first-photo` | Windows 独立发布；首图自动显示修复及状态开关语义已进入本次发布 |
| SpektraFilm Android | `0.5.0` / `versionCode 23` | 本轮未更新 Android；以下功能状态与 Windows 0.8.0 对照，不表示 APK 有相同 UI 或性能 |

状态含义：**已覆盖**表示有可用入口和实际处理链；**部分**表示存在具体功能或平台边界；**差异**表示两边做法不同，不代表算法等价；**有意不做**表示按用户的产品方向不增加。源码专项、包内资源和成品关键路径是不同证据等级：完整审计中早期“包待验”标签保留其历史语境，当前发布状态以 0.8.0 成品记录和本表边界为准；未逐项做过的组合不视为全部验收。

## 功能矩阵

| 能力 | SpektraLab 2.3.2 最新源码 | SpektraFilm Windows 0.8.0 | 差异与边界 |
| --- | --- | --- | --- |
| 导入与照片工作流 | 文件 / 文件夹导入、拖入、图库 / 会话、批处理；Apple Finder 修复属于 macOS | 文件、文件夹、拖入、粘贴、批量扫描；导入完成自动选中并显示首张 | 两边都能直入照片；SpektraFilm 不要求先建永久图库。首图问题经候选包实测已修 |
| RAW 解码 | macOS 使用系统 `CIRAWFilter`；Windows beta 使用自己的 native host 路线 | LibRaw 原生解码、相机白平衡 / 曝光、兼容 Bayer 高光余量与 RGB16 路由 | 解码器和处理模型不同；不声称还原 Capture One / Lightroom 私有 RAW 算法，也未证明覆盖每种相机和压缩 RAW |
| 镜头与基础校正 | 曝光、WB、镜头数据依平台路线；有真实产品 UI 的功能按源码 / host 分开判断 | 曝光、色温 / 色调、镜头矫正、去紫边、拉直与自动影调 | 镜头结果受机身、镜头和公开配置文件覆盖限制；不保证与商业软件完全一致 |
| 基础影调 | 亮度、曝光、对比、高光 / 阴影等显影控制；另有真实胶片 / 相纸处理 | 曝光、亮度、对比、饱和度、自然饱和度、高光、阴影、白、黑、色阶与自动调整 | 基础功能覆盖充分；各参数曲线、局部对比和 RAW 基线并非同一实现 |
| HSL / 校准 / 色彩 | HSL、曲线、颜色平衡 / 色轮；色轮算法与交互有自己的实现 | 8 色 HSL、可视色带式原色校准、3×3 通道混合器、全局 / 阴影 / 中间调 / 高光色轮 | SpektraFilm 的校准与通道混合是额外能力；色轮使用 OKLab / 色域保护，不是上游逐像素公式复刻 |
| 曲线与直方图 | RGB / 亮度曲线；2.3.2 加入 Decode 曲线后按真实处理像素重算的 RGB 直方图 | RGB / R / G / B / 亮度点曲线与参数曲线、可移动点和删除、RGB / 亮度直方图、输入 / 输出色阶 | 主要工具均覆盖；曲线背景分布、折叠偏好等小交互仍有差异 |
| 几何与裁切 | 裁切、旋转 / 翻转、透视与引导式几何；当前源码没有证据证明自动视觉识别透视 | 图片原位裁切、自由 / 固定比例 / XPan、旋转 / 翻转、透视、自动拉直 / 自动几何和四点引导 | 都有几何流程；SpektraFilm 的自动分析属于本地实现，低置信度不应用；不是 Capture One 私有自动透视算法 |
| 局部蒙版 | 当前 Lab 产品入口未启用等价的 brush / linear / radial 编辑器；virtual contrast mask 在 gate 中关闭 | 画笔、线性渐变、径向 / 椭圆，多层、擦除、羽化、反转、源坐标、撤销删除；调参数时可隐藏覆盖层 | SpektraFilm 在局部蒙版上覆盖更广；连续手势和算法外观仍不应宣称与 C1 完全相同 |
| 颗粒与光学 | 胶片颗粒、分层颗粒字段 / Windows 分支开关、halation、DIR 等，按材料 / 平台约束 | 4 种颗粒纹理、强度和大小、物理片幅缩放，以及独立光晕 / 散射 / DIR / 防光晕等 | 功能面较全；通用颗粒类型不等于每卷真实颗粒测量，尚未做到逐胶片的 C1 颗粒匹配 |
| 光谱材料 | 原生光谱胶片 / 相纸目录、扫描和印相处理；2.3.2 相比 2.2 没有新增材料目录 | 30 种胶片、9 种实际相纸，完整光谱计算，可选择关闭胶片显影；支持黑白、负片、正片及多种片幅 | 核心胶片光谱是产品重点。部分扩展胶片密度资料为拟合数据；原生 Minilab 校准表目前只覆盖 Portra 400 / Portra Endura |
| No Print Profile / DI / 印相 EDR | Windows beta 分支有 No Print Profile、DI、Print Effects、EDR 控件；Mac 2.3.2 新增 DI 试阅路径，二者不能混为一谈 | 扫描底片模式、Cineon DI TIFF16 + view LUT、相纸印相和 8 种彩色纸 EDR；无效组合明确禁用 | DI 原始 Cineon 输出与普通照片 view 分离；物理片边 DI 目前明确拒绝。EDR 印相不等于 HDR 显示器输出 |
| HDR | 2.3.2 增加真实 HDR session / gain-map 路径，当前公开文件能力以可用容器和 Apple 平台路径为界 | 活跃光谱 session 生成原尺寸 JPEG HDR gain map，限 sRGB / Display P3 与受支持模式 | SpektraFilm Qt 编辑画布仍为 SDR；排版 HDR、DI HDR、部分介质组合明确不支持，不把 HDR 文件能力说成 HDR 屏幕预览 |
| 物理片边、日期与半格 | 有物理 film edge、日期后背、半格双曝光和 pair 工程；Windows beta 包与最新 Mac 源码能力不同 | 原生物理片边、片孔、机身几何、日期 / Data、半格工程和原片逐孔重印 | 真实功能已接通，但入口预设不穷举所有 Lab 片门；日期与 Data 共用后背，native 没有每个孔单独 Data 字段；半格 DI 不支持 |
| 拼版 / 纸面排版 | Light Table 支持自由摆放、角度、纸张尺寸、间距、存储与分享 | 独立排版与拼图：网格、横 / 纵布局、主图、逐格取景、交换和真实原源导出 | SpektraFilm 没有独立 Light Table 工作区，这是用户确认的产品选择；自由摆片 / 角度与 Lab 并非全等 |
| 导出 | JPG / HEIF / PNG / TIFF、配方、DI、HDR、尺寸和元数据策略按平台版本 | JPEG、HEIF、PNG8/16、TIFF8/16、RAW 原片副本、处理后 DNG16、Cineon DI、色域 / ICC、尺寸 / 命名 / 目标文件夹 / 批量 | SpektraFilm 输出选项更宽；RAW 是原文件副本，不是处理后的专有 RAW。外部编辑器 Open With、系统 Photos / Share 未对等提供 |
| 图库与资料管理 | Catalog / Session、相册、变体、筛选 / 元数据、排序、来源和只读 C1 快照 | 唯一图库入口、会话 / Catalog、来源文件夹、C1 只读同步、元数据分面、监视目录、留用 / 移除 | 用户不需要评级，故不提供星级 / 彩色标签，也不单设 Light Table。尚缺自定义拖动排序、独立升降序、单文件原片重新定位和旧 Apple 库迁移 |
| 命名预设与材料试阅 | 预设保存 / 分类及当前照片上的材料试览，具体入口随平台版本不同 | 可命名、分类、重命名和删除预设；用当前照片生成胶片 / 相纸试阅 | Windows 0.8.0 有对应入口与有界工作流证据；不意味着所有上游 preset 字段逐项同构 |
| 参数复制 / 同步 | 按上游版本的参数组复制 / 粘贴及选片同步 | 按类别复制、粘贴和同步，默认保留每张图自己的裁切、调色与片边 | 覆盖常用批量编辑路径；字段集合及默认同步规则并非完全相同 |
| 单实例与系统打开 | Windows 包有 agent/native host；macOS 有不同的系统文档打开旅程 | CLI 的路径打开可转交当前应用窗口；系统文件关联和外部编辑器 Open With 未全对等 | 当前窗口转交有包内证据；不能由此推断系统已注册关联，或导出后可直接交给外部修图软件 |
| 缓存与大量照片 | 有任务队列 / 设备预算、RAW proxy、FullRender tile 与预取策略 | 异步分批导入、分开的预览 / 工作 / 完整渲染磁盘预算，完整 float32 源像素缓存、局部细节瓦片与逐张导出 | 都有缓存与异步策略但内部格式不同；SpektraFilm 未实现同一全局成本队列、实时内存压力状态、邻片完整瓦片预取和跨进程缓存写锁 |
| 自动化与设置 | Windows beta 有 agent CLI / MCP；macOS 源另有驱动 / 设置能力 | 独立 CLI / stdio MCP；明确开启后，可经同一窗口本地认证服务操作 GUI 当前会话；四语言、色彩管理、缓存与主题设置 | SpektraFilm 同 GUI 自动化是额外工作流；不将 macOS 专属 Metal / EDR / 分享表单当作 Windows 的缺失功能 |

## SpektraLab Windows 成品边界

上面的主矩阵描述 SpektraLab 2.3.2 当前源码的功能面；Windows 可交付能力还要以 `spektralab-windows-v1.3.4-beta.2` 单独判断。该包有 GUI/native host、Node agent、材料与镜头资源、DI view LUT、shader 和 exporter，但资源或 exporter 字符串本身不能证明某项功能已有可见 UI 或 native host 当次运行支持。

| Windows beta.2 可确认项 | 核实结果 | 比较时的限制 |
| --- | --- | --- |
| 发布结构 | GUI、`spektralab-host.exe`、WebView2、Node 24 和 `agents/agent.mjs` 均在便携包中 | 没有把 Apple 2.3.2 的 Swift/Metal 页面和交互记入 Windows 已发布能力 |
| CLI / MCP 与导出协议 | 包内 agent 暴露 CLI/MCP；exporter 源使用 `export_frame` / `export_cineon`，并包含 pair、no-film、TIFF 选项 | 调用受 native host `hello` 能力门控；本次没有运行 beta.2 native host，故不把所有协议分支标为成品实测 |
| 附带材料和平台资源 | 有产品材料、neutral filter、grades、print LUT/constants、DI view LUT、Lensfun、GLSL/SPIR-V 和许可文件 | 资源存在不等于 GUI 有对应入口、每个配置生效或与 2.3.2 源码同步 |
| 性能与相机覆盖 | beta.1 的 102MP 记录属于历史数据 | 不用作 beta.2 新性能结论，也不推断全机型 RAW 覆盖 |

因此，功能差距表中标记的“上游有而本软件不同”，指向最新 2.3.2 源码合同；如果只问 Windows beta.2 成品是否具有对应功能，应以完整审计中的 Windows 包清点和明确的 host/runtime 证据为准。

## 目前确认的差距

| 优先级 | 差距 | 影响 / 当前边界 |
| --- | --- | --- |
| P1 | RAW 相机与压缩格式覆盖不是全机型实测；没有 C1 / LR 私有解码算法 | 需按真实机型样片逐项验证，不能从一张 A7CR 或 16-bit 输出推断通用兼容 |
| P1 | 批量导出确切发布包仍未通过本轮专项复验 | 既往综合路径曾出现 Windows 堆损坏 `0xC0000374`；0.8.0 成品记录证明单张原尺寸导出与 CLI 路径，不证明多图批量全链无故障 |
| P1 | HDR 编辑预览仍是 SDR，排版 HDR 不支持 | 当前只对支持的照片 JPEG 输出 gain map；不包括 HDR 显示器链 |
| P2 | 图库没有自定义拖排和独立升降序；原片修复以目录级重新定位为主 | 影响大批照片人工排序、单张源文件迁移与旧 Apple 资料库迁移，不影响直接拖入编辑和快速会话 |
| P2 | 全局作业成本模型 / 实时内存压力反馈 / 邻片完整细节预取未与 Lab 等价 | 现有池和存储预算有界，但还不能声称完整复刻其调度器或对任意批量无内存压力 |
| P2 | 部分胶片、片边和材料行为不是逐项物理标定 / 逐入口复刻 | 新扩展光谱数据包含拟合成分；Minilab 只对已校准配对材料启用；半格独立第二孔 Data / DI 片边未支持 |
| P3 | 色轮、曲线、颗粒和部分控件的交互模型 / 算法不同 | 有对应工具但不等于视觉输出或内部公式与 SpektraLab / C1 相同；继续以真实照片验证质感 |
| 有意不做 | 星级 / 彩色评级、独立 Light Table 页面、强制入库 | 用户要求只留用 / 移除，且认为独立看片台多余；排版拼图保留为照片编辑工作区内的可选工具 |
| 平台边界 | Apple Metal、macOS EDR 窗口 / iOS Photos Share、CIRAWFilter | 不是 Windows 可直接移植的调用；本项目 Windows 用 Vulkan / LibRaw 的独立实现。Mac / iOS 未构建，也未声称等价 |

## Windows 发行核验

SpektraLab Windows 1.3.4-beta.2 的实际包清单、agent 与 exporter 证据见完整审计中的“Windows 1.3.4 成品与源码的不一致”。SpektraFilm 0.8.0 确切包、HDR / 原尺寸输出、GUI / CLI / MCP 和 UI 导入验收见[Windows 成品记录](windows-0.8-release-verification.md)及发布包 `release/Evidence/Windows-0.8.0/review.json`。本轮未运行 macOS 程序，未运行 SpektraLab Windows nativehost hello，也没有重跑历史大 RAW 或哈希测试。

逐项的参考消费者、入口、状态和证据见[完整功能审计](spektralab-complete-audit.md)；2.2.0 到 2.3.2 的具体源码增量见[上游更新记录](spektralab-update-2026-11-11.md)。
