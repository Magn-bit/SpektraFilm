# SpektraFilm 验证记录

## Windows 0.7.0 · SpektraLab 2.2 功能整合

2026-11-09。本节与下方历史版本分开：四语言、真实图库变体、全窗任务页、物理片边与输出色管的关键整合已通过，最终冻结包运行结果随 `release/Evidence/Windows-0.7.0` 交付。确切0.7 GUI/CLI成品已通过实际运行：首帧1897.6ms（Python入口计时，不包含bootloader）、完整谱/编辑/历史/原尺寸TIFF、图库helper、HEIF/Adobe RGB、Cineon、同GUI开关；CLI原尺寸PNG及12项stdio MCP工具通过。正式发布与否以 `release/manifest.json` 为准，开发态证据不能代替成品验收。

- `output/parity-workspace/integrated-verification.json`：真实 Controller 同路径变体的设置、历史和 SDK 保存互不覆盖；导入入口与返回、已显影片看片台局部更新、1366×768 / 1440×900 / 1120×760 逻辑窗口的全窗任务页通过。QML 错误 0。当前系统 DPR 为1.5，1366×768逻辑窗口对应2049×1152原始截图，二者不混称。
- `output/localization/verification.json`：简中、繁中、英文、日文即时切换，831条精确文案与79种动态模板；标识符、文件名和用户数据不被翻译。`widget-font-verification.json`：仅修正 QWidget 对话框字体单位，认可的 QML 字体不变，Qt 消息0。
- 原生 C ABI 小图/中型检查覆盖物理扩画布、日期曝光、完整光学、全局随机场、独立半格印放、取消及有界精确 IIR。caller-owned RGBA16 memmap 不缩图，普通照片同尺寸保护仍生效。
- HEIF10 灰梯度输入保留1024级，Adobe RGB使用真实矩阵/TRC/ICC；显示器ICC/软打样在宽色域浮点结果上执行。Cineon TIFF16 使用原生负片密度与专用显示 LUT，不加不适用的RGB ICC。
- 图库 MIT helper、独立CLI/MCP与可选同GUI认证通道各自完成关键节点验证；正式 Windows 采用 GUI/console 双入口共用 `_internal`，最终成品再检查启动与代表性输入输出。

61MP真实源物理片边首次成功输出9924×9184 TIFF16/ICC，总155.724秒，源大小/mtime不变。该版本暴露中间平面IO与显存上传瓶颈。最终同shape合成输入在RTX3070Ti Laptop 8GiB走真实heap准入的整段resident路径：约91.14MP完整光学2.019秒，另有spk_open0.809秒，24个完整光学pass、12次Gaussian与0磁盘checkpoint。显存不足仍走精确完整行列执行。此profile没有重复RAW解码和编码，不能冒称最终全链测速。完整资源与性能口径见 [原生画布](native-bounded-film-canvas.md)。

本轮不执行哈希测试，不重复历史普通大RAW整链；Android仍为0.5.0/code23及其对应源码，没有新的真机或跨平台发布结论。

## Windows 0.6.0 历史验收

## 0.6.0 后续边框与排版修复

2026-11-08。排版弹窗曾只为电影片边绘制齿孔，拍立得、接触印样和半格样式虽然更新了状态，却缺少可见的结构装饰。共享 `decoration_spec` 现在为拍立得/接触印样/半格生成底部边带，为接触印样生成内框，为半格生成中线；QML 预览和完整源导出都消费同一份模型。`tests.test_composition` 的样式差异检查、`verify_composition.py` 的预览/取景/TIFF 导出、候选包 QML 检查均通过，QML 错误 0。

本轮仅更新 Windows，Android 0.5.0 APK 保持原包；Android 新增的色阶与创作源码尚未构建，不作为 Android 0.6 交付。完整成品范围以 release/manifest.json 为准。

- 新增色阶／HDR／亮度的 CPU–Vulkan 数值一致、默认旁路/headroom、设置往返、底片缓存复用、自动 WB/影调/色阶/拉直、重复自动幂等与过期结果隔离、分组撤销通过。实际蒙版 alpha 与旋转／透视／裁切后的原生覆盖对齐，均值差 <0.001、99分位 <0.006。
- 1366×768 小代理实际 QTest：画笔、柔边擦除、线性／径向首按拖动，局部曝光拖柄即时位移误差 0，调整曝光不重建选区；色阶精确值与历史、最窄 320px 侧栏的绿／蓝通道与五输入框可达、四个自动按钮真实点击、256 桶全图直方图，QML 错误 0。此处不从单次事件推断全程 60fps。
- 独立排版真实入口、首按取景、交换、异步图片已就绪后截图及 TIFF 导出通过；原始源 RGB16、ICC、超过 256 级精度、逐张独立编辑、原片大小/时间戳不变与取消无残留通过。A7CR 尺寸的纯几何检查证明单图添加边框不缩小照片；未重复大 RAW 导出测速。
- 最终候选 EXE 另验版本 0.6.0、完整光谱、色阶／亮度／HDR、历史、原尺寸 TIFF／ICC与正常退出；候选包内 QML 配合开发控制器的输入验收另列，不能混称整套最终 EXE 自动交互。

自动拉直和自动垂直/完整透视只在可靠、分布式直线一致时应用；弱场景保留手动调整。直方图来自当前显示结果的有界采样，非原始传感器值。边框／日期是图形装饰；排版源像素与缓存预览严格分开。证据见 release/Evidence/Windows-0.6.0。

## 0.5.0 历史关键节点

Windows 控件补丁：去除渐变滑轨附加黑线、修复零宽裁切菜单；稳定字段绑定、独立状态通知、连续输入合并和后台 QImage 准备。曝光指针处理中位 30.113→0.305ms，P95 57.853→0.560ms；当前候选实际菜单点击、精调／复位／历史和 EXE 工作流通过。详细计时口径、非零最坏帧间隔及测试边界见 [slider-input-fix.md](slider-input-fix.md)。Android APK 此次未修改。

2026-11-08。Windows/Android独立完整编辑与可选光谱暗房。仅在关键节点验证，不执行哈希测试。以下0.4.x记录保留历史范围，不视为本轮重复实测。

- Windows完整编辑与输出聚合8项通过：v4侧车与v<=3外观迁移、可选胶片、蒙版/几何与分组历史、源像素不可变、float裁切/TIFF16、批量轻量模型、分类同步逐张撤销、LCMS独立对照三色域、PNG16/宽色域TIFF及LibRaw重新解码线性DNG。
- 原生GPU基础/色彩/蒙版、八向EXIF镜头矫正、原位strip、RAW线程退出及内存生命周期已针对性验证。锐化与降噪置于胶片之前，跨strip/tile与分数预览尺度、headroom和默认0旁路通过。没有声称恢复商业私有算法。
- 桌面实际1366×768/1440×900：首按拖动、原位XPan裁切、缩放中心保持、任务区伸缩、曲线/校准/蒙版、配方保存与两张分类同步/撤销、90°真实转置/蒙版源坐标/QML无绑定错误。字体保留认可搭配及QtRendering。
- A7CR RAW256个独立路径（硬链接同一原片，共约29.95GiB逻辑输入）分批导入+当前预览5.85秒，峰值838.16MiB；仅当前照片解码，两个预览请求，其余未展开。它不是256张不同内容/机型的混合测试。
- 实际SonyA7CR 9564×6376→5219→TIFF16：WB6100K、阴影8、颗粒12、光晕5、锐化15、彩色降噪10，镜头矫正与去紫边开启；RTX3070Ti Laptop，源码新进程整链13.541秒，峰值3627.85MiB，RAW源所有权结束为0。阶段：读图3.276秒、光学准备4.337秒、完整处理3.285秒、编码/写入/同步发布2.643秒。产物保留原尺寸、RGB16和ICC，首条带超过256阶，原片大小/时间戳不变。不是手机耗时或所有硬件保证。
- Windows实际0.5.0EXE通过异步导入、原生完整谱、参数/撤销/重做、原尺寸TIFF/ICC及正常退出；资源版本0.5.0，原生RAW DLL和新增恢复shader已打包。
- Android0.5.0/code23 assembleDebug、lintDebug与测试源码编译通过；主机实际解码PNG8/16、TIFF16、DNG16样本准确，LibRaw可识别线性DNG，native三空间/线性光area缩放匹配共享参考。90°四方向/反变换/宽高与crop状态、细节nativeJSON通过；实际APK含共享shader、ICC、字体并通过v2签名检查。ADB无设备，真机UI/权限/触感/大RAW导出耗时尚未验证。

证据发布至release/Evidence，源码中完整边界见editor-native-research.md、editor-workspace-research.md、android-editor-integration.md。软打样/EDR、DI/片边/物理日期/双图、本地产品会话API与完整语言更新仍未接通，不以已有源码组件冒充完成。

## 0.4.3 历史增量验收

2026-11-08。本轮仅在关键节点检查受影响路径，未进行哈希测试、未重复历史RAW/大图全流程基准。最终发布范围见 release/manifest.json。

- Windows 0.4.3候选EXE实际完成异步导入、完整光谱预览、分组调参、撤销/重做、原尺寸TIFF导出和ICC；源文件大小/时间戳未变。版本资源为0.4.3。证据 windows-smoke.json。
- 裁切与产品边界10项通过，含真实Vulkan完整处理后精确取子矩形、TIFF16数值/尺寸、对比同构图、历史迁移、保存/撤销/重做，批量显影不覆盖单张裁切。旧综合编辑器的旋转/透视/蒙版仍不恢复；历史版本1/2侧车不突然激活旧裁切，版本3保存新裁切。
- 实际DSC09118.ARW完成桌面可拖动裁切、XPan65:24、1366×768/1440×900可达布局、菜单和撤销/重做。旧0.4.2与新0.4.3便携包取得相同2220×1368物理截图，清理闲置引擎标语。
- 字体保持朱雀仿宋中文/Noto Serif SC英文数字。实际150%六组渲染方式对照发现CurveRendering小字碎边，最终使用QtRendering/vertical hinting，不合成粗体；正文15px、辅助14px。在实际DPR1/1.25/1.5的产品文字组件截图复查。
- 同一新Python进程的controller导入由1.632s变0.361s；延迟SciPy及vendor公共科学导出，纸张目录查询不再载入Simulator。它不是完整EXE冷启动测速，未清空系统文件缓存。
- 四种原创密度域中性颗粒差异、通道噪声、原图坐标连续与CPU分块检查通过；详细范围和LR/C1静态证据见grain-texture-research.md。没有声称私有算法已完整还原。
- Android 0.4.3/code22 assembleDebug与lintDebug成功，0 errors/42 warnings；arm64原生库、50个SPIR-V、四型新shader、27胶片、字体、版本及v2签名验证。已编译照片显隐/多尺寸大字体/裁切聚合runner，当前ADB无设备，未运行真机UI检查，未重新测原尺寸导出耗时。
- 项目外SDK/Gradle/Maven依赖迁移后Gradle help成功；源码包保留可重建native/JNI/LibRaw/libjpeg/shader/数据和许可证，不含照片、外部工具或商业模块。

限制：Android新布局与触感需真机验收；大halo/低内存/150MP重复空间运算仍可能较慢；宽色域scene-linear RAW高光余量尚缺，当前自然RGB16不等于C1/LR私有显影。无macOS/iOS产物。

## 历史验收（范围与版本按原记录）

# SpektraFilm 0.4.0 验证记录

记录日期：2026-11-07。当前完成的是下列源码与原生路径验收；是否正式发布及最终成品哈希，以 `release/manifest.json`、`release/SHA256SUMS.txt` 和对应成品验证报告为准。历史 0.3.x 记录已归档至 `docs/history/before-native-0.4.0-validation.md`，不作为本轮重新测量结果。

## 当前范围

Windows 与 Android 保留完整胶片光谱显影，不恢复已撤下的通用编辑器。27 款胶片、曝光、颗粒及类型/大小、光晕、暗角、强度，以及本轮相纸、印相曝光/Y-M 滤色、模拟片幅、4 款黑白光谱材料和眩光进入统一参数合同。9 种相纸按胶片适配；正片直接扫描。

Windows 使用 Qt/Python 界面与 C++/Vulkan 完整光谱桥；原生输入 float32，输出真实 RGBA16，再以 float32 完成产品后处理。原生错误会明确失败，不静默换成 LUT 导出。原生可用时，640px 拖动预览和精细预览使用同一完整模型；显式 CPU 兼容路径仍可使用单独标注的交互 LUT，最终处理保持完整光谱。

Android 已接入同源 C++/Vulkan JNI；运行时移除 Python。APK 构建、资源与真机验收分别记录，不能把 Windows 或主机结果算成手机结果。

## 一次产品回归与必要修复

按用户要求减少冗余测试，仅统一运行当前产品相关的 131 个测试方法，耗时 11.792 秒，未跑历史 C1 研究或已撤下编辑器套件。范围包括图像/导出、控制器、拖入与粘贴、批量、产品白名单、RAW 路由/亮度/精度、缓存、颗粒物理尺度、窗口状态、胶片数据和发布资源校验。

首次 130 个方法通过；唯一失败方法有 8 个跨平台参数子场景失败，原因为 Android 保留 Python 参考桥仍启用默认眩光，而桌面新默认为 0。修复默认映射，并统一非零 Y/M 的 ±60 CC 标尺后，只重跑该方法的 8 个子场景，全部通过。没有为这一修复重复运行 131 项。

新增 3 个原生控制器交互检查通过：拖动最新值、松手最终值及撤销/重做使用相同完整光谱设置；迟到交互帧不能覆盖最终值或撤销；相纸/片幅/印相/眩光参数经过白名单与侧车文件后仍保留。历史记录迁移使用新增参数默认值，避免旧记录缺少相纸等字段时抛 KeyError。

证据：`output/cpu-product-regression.log` 保留首次运行和失败，`output/cpu-android-parity-regression.log` 为修复后定向结果，`output/cpu-product-regression-summary.json` 解释方法数与子场景数。

## RAW、16 位与文件完整性

Windows RAW 由 rawpy/LibRaw 以 RGB16 自然显影，相机白平衡、sRGB 曲线、Blend 与既有自动亮度策略保持；朝向后的完整尺寸在读图时保存。RGB8 仅供显示，导出处理直接使用 RGB16/float 源像素。普通 RGB16 文件经 OpenImageIO 读取，矩阵/TRC RGB ICC 在浮点变换；未实现的高位深 LUT/device-link ICC 明确拒绝，不经 RGB8 转换后冒充高精度。

4 个精度检查通过：合成 CFA DNG 与官方 LibRaw RGB16 逐样本相同；原尺寸 TIFF16 回读；超过 256 阶的梯度及复制/缩放；浮点矩阵 ICC 与重复调整时源像素不可变。原生整链小夹具从 DNG 到 TIFF16 保留 64×96，TIFF 与渲染结果的 16 位量化逐样本相同、含 9294 个不同数值，原片 SHA256 不变。见 `output/native-precision-acceptance.json` 与 `docs/windows-high-precision-pipeline.md`。

首次大图暴露 TIFF 迭代器契约错误：tifffile 把 ndarray 项当成整帧，原先小于 128 行的夹具未覆盖多条带。已改为逐条带预压缩 bytes，并把梯度扩为 263 行，覆盖 3 条带及最后 7 行，逐样本验证通过。此修复及后续编码优化只重跑关键多条带检查，见 `output/tiff-multistrip-regression.log`。

TIFF 为 RGB16、sRGB ICC、Deflate level1 无损压缩；最多 4 个有序 future，编码窗口约 48MiB，按宽度调整条带行数，不预提交全帧。48MiB 是编码额外窗口，整进程仍需源图和渲染帧。JPEG 最后量化为 RGB8；高品质质量 100 / 4:4:4，分享质量 85，均保持源尺寸。RAW 另存保持原始字节，不包含显影效果。原子发布及同名不覆盖规则保留。

## 0.4.2 增量验收范围

本轮完成 Windows 与 Android 的字体回退：界面正文、标题和控件重新统一到 bundled `Spektra Bilingual Serif`，其中中文为朱雀仿宋、英文与数字为 Noto Serif SC；保留 0.4.1 已验证的布局、精细滑块、双击当前项恢复、导出栏安全区和原尺寸导出逻辑。Windows 与 Android 重新构建，发布前由成品验证器检查实际字形、资源哈希、版本号、APK 签名和文件清单；本轮不重复大图 RAW/全谱手机计时，也不把历史 0.4.0 设备结果当作 0.4.2 测量。

## 0.4.1 增量验收范围

本轮 Windows 重点验证右侧分组、精确数值、键盘微调、双击当前项复位及当前照片历史；Android 重点验证安全区/导出栏结构、原尺寸裁切接线、实际精度及低灵敏度手势状态。Android `assembleDebug` / `lintDebug` 通过（0 errors / 41 warnings），当前包 SHA 与资源/签名由发布 Evidence 绑定。本轮尚未连接手机，没有新 Android 多尺寸截图、触感或整链耗时结果。

Windows 三项实际 QML 交互检查通过：数值输入/滚动可达，Shift/Alt 键盘实际步进及双击手柄复位，恢复默认的当前照片范围/撤销/无改动禁用。76px 数值框按实际 Microsoft YaHei UI 的最大符号数字测宽，避免较细精度被裁切。最终 EXE 已通过 Portra400 JPG、Agfa Vista100 TIFF16 与旧参数中性化流程，验证导入、完整谱、撤销重做、源尺寸/ICC/源完整性及实际正文/标题字形；另获取六个界面状态截图。对应 `output/release-0.4.1`，同照片1440×900前后截图位于 `output/ui-precision-0.4.1`，after 已绑定最终 EXE。APK资源与 v2 签名检查通过，当前包 `6bff506c…` 无绑定的新真机报告。

Android 导出优化的主机真实 JNI 编码检查保持解码像素、JPEG 量化表与 Q100 4:4:4；矩形分块/读回模型减少工作量，不是手机实测速率。150MP、大 halo 或低内存下仍有性能悬崖。详细报告在 `output/android-export-perf-20261108/report.json`。以下 0.4.0 大图计时作为历史参考保留，不视为当前包重复验收或加速结论。

## Windows 61MP 真实整链（0.4.0 历史基准）

硬件为真实 RTX 3070 Ti Laptop GPU。样片 Sony A7CR ARW，完整朝向尺寸 9564×6376。下列结果是当前源码每进程首次导出，包含 RAW、完整谱、TIFF 编码、写盘、fsync 与原子发布；不是成品 EXE 测速，也不是手机结果。

设置为 Portra 400、颗粒 18、classic / 大小 1、光晕 12、强度 100%、35mm、相纸 auto，其余暗房参数默认。没有为了测快关闭默认颗粒或光晕。

| 阶段 | 时间 | 范围 |
| --- | ---: | --- |
| RAW 读取/自然显影 | 2.189 秒 | 完整 RGB16 与显示表面 |
| render_pixels | 6.545 秒 | 浮点准备、首次引擎初始化、完整原生谱、读回及后处理 |
| TIFF 编码/写盘 | 4.293 秒 | 无损条带压缩、文件写入、fsync 与发布 |
| 整链合计 | 13.027 秒 | 上述三阶段 |

本次 C ABI 计算与读回 1.804 秒、原生 Python 桥 4.740 秒，属于 render_pixels 的内部子阶段，不能与表中阶段再次相加。进程峰值工作集 2869MiB。输出 346,087,816 字节、RGB16、sRGB ICC，首条带含 17,435 个不同数值；尺寸及源 SHA256 保持。

同口径此前串行 level6 条带整链为 20.695 秒；改为 level1 有界并发后缩短约 37%。独立 6.29MP 编码 helper 为 1.223→0.334 秒，只说明编码热点改善，不代表整链或通用机器表现。证据：`output/full-export-0.4.0-fast61/report.json`、`output/tiff-strip-encoding-benchmark.json`。

## 原生模型与数值边界

`output/native-spectral-0.4.0.json` 的独立原生检查保留 2039 阶灰度；改变印相曝光、切换相纸真实改变输出并复用底片；4 款黑白材料输出有限且中性，最大通道差低于 .00049。带状空间检查在关闭随机颗粒/眩光时与全帧输出最大差 0，颗粒大小与眩光另做参数进入像素的定向检查。独立桥基准中的 2.291 秒不含导出编码，也不是上表 13.027 秒的替代值。

Vulkan 探针通过不等于所有 shader 或所有公式已与 Python 逐像素对齐。报告明确保留 `full shader parity pending`；halation 面积、CAM16 数值和随机颗粒等实现存在模型差异。不能把原生完整模型、有限输出或尺寸一致称为全部数值等价。`contrast_mask` 在该 Vulkan 构建不支持，产品未暴露。

自然 RGB16 为 display-referred，有界 LibRaw 输出已可能裁切相机矩阵后的负值与超白。未实现无裁切 RAW headroom，也未完整恢复 Capture One/Lightroom 私有 RAW 显影。上游高光余量需原生 LibRaw 截取真实 pre_mul/out_cam，本轮 rawpy 公共 API 不提供该接口；线性 gamma 不能代替。

## 成品验收范围

Windows 0.4.0 实际 EXE 已通过完整光谱 JPG/TIFF16、原尺寸与 ICC、旧状态中性化迁移、撤销重做、字体及六个界面状态检查；DLL、shader、材料和许可逐文件绑定源码哈希。证据在 `output/release-0.4.0-final`，汇总在 `output/release-verification.json`。Android 最终 APK 的资源、签名和设备报告已刷新，Windows 二进制与资源未变，保留此前通过的流程，未重复整套测试。

正式发布由验证过的候选原子替换，成品、对应源码和证据统一列入 `release/manifest.json` 与 `release/SHA256SUMS.txt`。macOS/iOS 本轮没有成品。


## 150MP 中画幅有界处理验收

首次 IQ4 150MP 全帧原生执行触发 Windows commit 保护，保持保护阈值，不通过缩图或关闭光晕规避。最终对大于 80MP 的成品采用有界区域，float32 结果写入临时文件映射；保留全图像素尺度和随机采样全图坐标。空间 halo 组合光晕、DIR、颗粒及扫描上下文。含随机颗粒/光晕/眩光的区域与整图对照平均误差9.3e-8，99.9%误差不超过1/65535，少量随机离散采样最大差0.0078；有限halo不能宣称无限IIR数学逐像素等价。

实际 Phase One IQ4 原尺寸14204×10652，Portra400默认颗粒18/光晕12，TIFF16/ICC/source SHA检查通过。总64.878秒：RAW8.629、render41.176、编码写盘15.073；进程峰值4479.79MiB。20个区域，core3072、halo1616，最大区域39.74MP，原生阶段总22.357秒（属于render阶段）。成片847,283,909字节，首条带54,798个不同数值。报告output/full-export-0.4.0-150mp/report.json；与61MP合并发布证据为output/full-export-0.4.0/report.json。未重复跑已有大图；这里不是秒出承诺，也不是Android结果。

极宽空间PSF若无法装入有界预算会明确报错，不静默裁小halo、关闭效果或缩小导出尺寸。当前验收覆盖所列实际设置；没有宣称每个机型或所有极限参数均通过。

## Android 一加 15 实机验收

设备为一加 15 PLK110 / Adreno 840。生产原生目标使用 `-O3`，RAW OpenMP 最多六线程；运行不含 Python 解释器。实机通过原生 RGB16、小夹具 TIFF16、黑白材料、印相缓存，以及 Sony A7CR RAW 到完整尺寸高品质 JPG。没有在手机实测 100MP/150MP，TIFF16 设备验收是小夹具，不能套用 Windows 大图结论。

| 检查 | 结果与计时范围 |
| --- | --- |
| A7CR 冷 RAW 完整解码 | 8.603 秒，完整有效区 9564×6376 |
| RAW half-size 预览解码 | 3.638 秒，仅预览；没有用于最终输出 |
| 小夹具首次完整谱 / 缓存重印 | 3.399 秒 / 156 毫秒；不是 A7CR 全尺寸交互速度 |
| A7CR 完整谱 JPG100 导出 | 9564×6376，104,909,586 字节，源 SHA256 不变 |
| 导出墙钟 | 399.602 秒，包含设备 Doze/休眠；不代表纯活跃渲染时间，也未达到理想的大图速度 |
| 进度与取消 | 84 次进度更新到 100%，单调不回退；最终包取消后删除半成品 |
| 已观测原生内存 | GPU resident 峰值 727,428,608 字节；GPU/host/staging 记录合计峰值 1,070,384,344 字节，不是进程 RSS 峰值 |

完整大图在 APK `044f0c81603edc204c2ed8bc9fe0d71862b757053a40aee4601f9827340afa9c` 上成功。随后清理候选补 `writeJpeg` 异常删除半成品。最终 APK `941c91227c069c9bfe469776cfc0e18dced9e6df3e230ff274fa62b4ea23dd9c` 已安装，另将一行原生默认 `print_exposure_compensation=false` 对齐 Windows。仅谱库哈希改变，RAW/编码库和 49 个 SPIR-V 仍与全图包相同；零曝光小夹具 RGB16 与旧谱库逐字节相同。最终包定向曝光、缓存返回零、取消清理与 Bitmap-JPEG 通道检查通过，没有重复整张 61MP。

`output/android-device-0.4.0/report.json` 保留各个候选各自的验收范围和追溯信息；没有把前包全图结果伪称为最终包全图重测。拉取成片的缩图 `export-preview.jpg` 已视觉检查，未见黑图、错色或明显分块接缝；缩图不用于证明原像素细节。测试期间临时保持 USB 唤醒，原值 0 已恢复。历史 126.6 秒 RAW 轮次没有连续电源状态记录，不用它与 8.603 秒作严格算法加速比。

手机大图完整谱仍有明显成本，本轮解决原尺寸成功导出、内存有界、原生优化构建、进度和取消清理；不能称所有性能问题已解决。SAF 来源父目录能否直接定位依赖内容提供方授权，设备原生验收不等于覆盖所有提供方的文件选择流程。

## 发布前胶片亮度与 5219 核实

用户反馈胶片显影后变暗，追加小分辨率灰阶与当前 RAW 代理检查，没有重跑完整大图。18.4% 线性中灰经过编码后输入 .4661；Portra 400 输出线性 Y=.17935（−.037EV），Vision3 500T/2383 输出 .17668（−.059EV）。当前 RAW 768px 代理经直接 native 与产品处理结果最大差为 0，未发现重复 gamma 或整体固定减曝光。

该样片暗部占比较大，胶片趾部和肩部改变分布：源亮度中位 .0663，Portra 为 .03486、500T 为 .03081。没有强制全图提亮或打开自动测光来掩盖材料曲线；需要时用现有印相曝光小幅补偿。本模型负印相 EV 提亮，正值压暗。检查另外发现 Android 相机曝光仍启用自动印相补偿，已对齐 Windows 的关闭默认值。最终包 −1/0/+1 EV 小图平均编码值依次 .215256/.362460/.538290，返回零值缓存与修改前零曝光 SHA 一致；结果见设备报告。

5219 已在两端材料目录，界面名称为 `Vision3 500T`，材料 ID `kodak_vision3_500t`，包含谱敏感度、密度与染料数据，默认 `kodak_2383`，不是新增同名 LUT。Kodak 5219 为 35mm/65mm 编号，7219 为 16mm；物理模拟片幅由用户单独选择。采用公开谱模型不能称每一实拍/冲洗/扫描流程均完全复刻。数值报告 `output/exposure-diagnostic-0.4.0.json`；同源对照图 `output/exposure-current-raw-native.jpg`。
