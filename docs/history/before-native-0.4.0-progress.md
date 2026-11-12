# 2026-11-07 中画幅RAW与预览/导出隔离

已实现26种RAW后缀的统一路由、Android原始URI/代理/完整缓存隔离。六张多品牌实片Windows完整解码和源hash检查通过；其中GFX100、X2D100C、IQ4 150MP的同源Android C++全/半尺寸RGB16与官方LibRaw逐字节相同。未连接Android设备，新增真实微型DNG缓存/导出集成测试仅编译。

生产相关回归81项通过，C1独立参考22项为21通过+1已知expectedFailure。Android assembleDebug/assembleDebugAndroidTest/lintDebug完成，0错误38警告；APK资源与签名检查完成。Windows开发候选重新打包到dist/SpektraFilm，正式release未变。入口docs/raw-camera-compatibility.md，完整C1仍未还原。

新Windows EXE已实际通过微型CFA RAW的异步导入/预览/完整光谱JPEG导出、原尺寸、ICC和源完整性烟测。该样片更改为IIQ后缀只检验路由；三款中画幅的真实编码验证另由真实RAW测试覆盖。

# 2026-11-07 C1 RAW算法继续重建

原版wrapper/ABI隔离运行取得A7CR完整RGB16 sRGB TIFF；真实Frida只读观测64条Bayer/GG参数与CPU首块输入输出，均留REA证据并已detach/close。A7CR噪声表、码值×4、黑偏置、单块镜像边界和CPU/GPU区别均取得实际证据。新增独立高光算子与12组参数90036像素对照；11项recovered测试为10通过+1明确已知失败，绝不称全通过。

同片研究比较及图像已生成并查看，源hash不变。CPU参考和ICC/FCRV实际链继续；完整RAW未独立复现，生产没有加入C1资源。状态和缺口集中docs/captureone-raw-reconstruction.md。候选0.3.4已build/verify，但仍未发布，正式0.3.3。

---

# 2026-11-07 RAW 基础亮度修复与 C1 还原研究

用户指出全图偏暗。实片及 LibRaw 源码证明不是只因原片曝光：ReconstructDefault 跳过自动亮度，Android 逐行输出还固定了 gamma white。两端已修复，Android 旧缓存失效。同源主机对 Pixel4XL、暗曝光合成 DNG、A7CR 原尺寸逐字节对照通过；Windows 增补真实 DNG 回归中。

修正后 Windows A7CR 6376×9564 原尺寸 JPG 完整光谱导出成功，262.636秒，peak13057.9MiB，源hash不变。该轮与 C1 和反汇编同时进行，不作为严格速度对照。原131.778秒来自旧暗图，保留作历史，不能作当前最终画质证据。

C1 正常启动；正在专用对照会话准备同片导出。A7CR ICC/FCRV 已数值解析，原生函数级分析继续。完整RAW显影算法未恢复，未将专有DLL/profile加入生产。0.3.4发布暂缓。

---

# 2026-11-07 0.3.4 实片性能验证

使用用户授权M盘真实A7CR DSC06823.ARW，6376×9564完整光谱高品质JPG导出131.778秒；源SHA256 c0d80fc67e79e84ee5c4d6ba71c11c8407af13356f47ac2fec53176b73cae56e不变，RAW另存byte-identical。总peak14628MiB。报告output/raw-film-0.3.4-a7cr/report.json。

24MP同机串行CPU76.572秒、GPU色域67.695秒，进一步CPU色彩分块后58.570秒；有系统/温度和少量测试负载波动，不作为严格速度倍数。当前显影28.36秒、曝光14.15秒、扫描12.27秒，主要热点仍在CPU。独立CAM16 GPU345ms与整链不是同一口径。

预览发现upstream preview_mode将grain.active设False，已改成小代理运行真实完整模型；Android whole-proxy使用35mm全画幅物理尺寸，export tile保留原片pitch。新的像素/尺度测试通过。定向测试初次混入未同步Android包导致异常，统一port与导入顺序后修复；grain恢复后Numba glare不受np.random.seed影响，确定性cache测试仅停用paper glare，生产保留。

CPU同色域matrix保留，不能直接删矩阵只调用CCTF。Poisson同原SciPy RandomState/Generator采样器，shape和RNG状态测试通过。GPU density/blur往返并无充分收益，保留为原型，不接生产。

新版尚在构建/冻结包验收；Android无真机、Mac无编译环境，完整GPU管线未完成。

---

# 2026-11-07 跨平台完整光谱性能优化

- 完成 SpektraLab Windows/macOS/Android 渲染链路边界核对，并结合 SpektraFilm 的源码、阶段 profiler 与 Android native 桥接检查定位瓶颈。
- 当前 24MP CPU 完整谱重测：64.622 秒、5983.9 MiB；filming.develop 28.651 秒，scanning.scan_print 18.728 秒。报告保存在 `output/perf-baseline-20261107-current-host-cpu.json`。
- 用户纠正显卡：实际 RTX 3070 Ti。系统枚举给出的 RTX 5090 是错误信息；该基线为 CPU 路径，不依赖任何显卡。
- 依据用户授权自选后端，选择 wgpu-native/WGSL：Windows D3D12、Android Vulkan、macOS Metal。Dawn 当前 Android Vulkan 状态为 work in progress；上下游不同设备的 SpektraLab 速度不作为 SpektraFilm 的承诺。
- 新增后端决策和验收要求至 `docs/gpu-performance-engine.md`。本轮尚未替换生产渲染路径；仍需实现 GPU 纵切片、逐阶段精度/颗粒/接缝对照，并在真实 RTX 3070 Ti、Android 真机与 Mac 上验收。

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

# 进度

## 2026-11-06 当前收尾进度

- 完成共享蒙版/曲线/色轮/几何裁切，两端原生UI及单张/批量状态接入；用户样片1280×1920导出与TIFF像素回读通过。
- 第一批胶片型号CLUT与第二批实验创意风格被用户否定，均撤出默认与打包资产。当前10款原创以人像/风光实际用途组织，不用知名作者名称包装。
- 外部作者XMP已找到可分发原文，但关键HSL/Adobe配置尚未等价，保留研究，不伪称已移植。Links仅保留准确官方来源。
- 最终179项全量回归及55项相关Qt分组测试通过。两端最终重建完成；Android lint0错误/34警告，APK资源与签名通过但无设备。Windows实际EXE光谱JPG/TIFF、蒙版、曲线/几何裁切及实用风格导出通过。
- 0.3.0已替换release/Windows与release/Android，4831文件校验通过；Skill新增按常用任务筛选扩展内容的规则并同步备份，两份校验通过。旧release/.windows-candidate删除曾被自动审批拒绝而保留。


## 2026-11-06 蒙版、曲线与几何追加

- 用户风向袋照片的原片、基础调整、局部调整对照及 100% 裁切保存至 output/mask-sample；原图 SHA256 未变，1280×1920 JPG/TIFF 尺寸保留，TIFF 像素回读一致。
- 初版画笔蒙版主机核心 7 项通过，两端画笔 UI 实施完成；Android 主/测试 APK 与 Lint 首轮通过，但未连接设备。Windows 130 项回归暴露 retry 新缓存失效问题，正修正。
- 用户追加径向/线性渐变、RGB 和独立亮度曲线、三区色轮、几何校正及宽松 UI；共享核心与两端界面继续实施，上一轮候选不作为最终成品发布。
- C1 本机 REA 得到画笔字段、线性/径向几何、曲线及三区色彩字段、部分真实包装方法体；记录见 docs/mask-reference-evidence.md。没有完成 C1/LR 样片导出对照，也没有恢复其内部像素公式。
- 前端设计 Skill 已加入连续参数拖动、图形控制器、宽松层级与渐进展开规则，已备份至 D:/Tool/Skills/software-frontend-craft，安装及备份两份 quick_validate 通过。

## 2026-11-05 双端源分辨率要求

- 用户明确要求 Windows 与 Android 导入/导出像素尺寸不得下降，缩小仅限预览。
- 已确认 Android 的 `openPhoto()` 与 JPG/TIFF `saveTo()` 都复用 `decode()`，而该函数把源图硬上限限制在 1.2MP；列表另有 160px 缩略图。故编辑图和导出输出确实会降采样。
- Windows 高品质 JPG/TIFF 导出独立从原片重新解码，使用 `edge=0`；导入状态保留源路径和完整 `source_size`，预览走代理图。需加验证确认查看像素不会被代理边长限制。

## 2026-11-05 导出速度与文件体积诊断

- 按完整应用路径分段测量 900×600 测试 JPG：读取 6ms、校正准备 450ms、完整光谱渲染 5,400ms、JPEG quality 100/4:4:4 编码 14ms，总计约 5.87s。显影与校正远慢于编码。
- 同一纹理测试图源 JPG quality 88 约 454KB；光谱显影后质量 100 / 4:4:4 JPG 约 1.69MB。颗粒与色调变换提高图像熵，原有有损 JPG 重新编码到最高质量也可能明显变大。
- 未改任何最终导出质量参数。Windows 质量 100 JPG、TIFF 全尺寸；Android 高品质 JPG 仍 100，分享 JPG 85；RAW 逐字节复制。

## 2026-11-05 预览性能与原画质导出复核

- 用户强调最终导出不要因预览性能优化而压缩画质。Windows `JPG_HIGH` 仍为原尺寸、quality 100、4:4:4；`TIFF` 原尺寸 LZW；Android 非 RAW 导出从原始 URI 使用所选预设尺寸解码，预览位图没有接入导出路径。
- 发现 `release/manifest.json` 已写 0.2.6，但清单所列 Android APK 不存在、Windows EXE 哈希与清单不匹配，`release/README.md` 仍写 0.2.5。本轮会从候选包重验再发布。
- 第一次全量测试误用系统 Python，缺 PySide6 且未设置 `PYTHONPATH=vendor`，不能作为项目测试结果；改用 `.venv/Scripts/python.exe` 与正确导入路径。
- 项目环境全量回归 88 项通过；Android `assembleDebug`、`assembleDebugAndroidTest`、`lintDebug` 均通过，APK 元数据为 0.2.6 / versionCode 8。
- 首次候选包 smoke 的检查代码将导出尺寸与预览缓存比较，导致 JPG 已成功生成仍超时。已改为按后缀实际使用 `JPG_HIGH`/`TIFF`，并从源文件读取完整尺寸后校验；需重新打包并重跑 smoke。
- 修订后的 Windows 候选 smoke 通过：完整光谱 JPG/TIFF、原片尺寸、ICC、源文件 SHA、撤销/重做及三张非空界面截图；完整光谱预览测试图耗时约 1.24–1.26 秒（900×600，本机候选包）。
- Android APK 0.2.6 / versionCode 8 构建、测试 APK 编译、Lint、288 个光谱源码/依赖及 20 款 LUT 校验、debug APK v2 签名通过；没有设备/模拟器，未做运行态速度或导出实测。
- 已发布至 `release/`：Windows SHA256 `01a427a20e84a8746ee4a5233e583179f5d68c871fec49d783dbc0375528d9fb`；APK SHA256 `6a1a2c6839352b23516ee68373dfb9d4515e442589c2054ecb15658837d1f382`；正式成品及发布文档共 4,813 个 SHA256 条目无误。
- 删除本轮第一次失败验证的 `release/.windows-candidate` 时，PowerShell 执行策略拦截递归删除。未尝试绕过；该隐藏临时目录不在发布包或 SHA256 清单里，仍待手动清理。

## 2026-11-05 整理源码目录

- 已分类源码、共享资源、上游参考源码、用户下载字体以及当前/历史发布物；计划保留这些内容。
- 已修正文档中的临时输出路径引用，并更新 `release/manifest.json` 与 `release/SHA256SUMS.txt`。
- `.tools/`、`.venv/`、`build/`、`dist/`、`output/` 与 Android 构建缓存尚未清理：执行环境拒绝了递归删除操作，未改用其他途径绕过。

## 2026-11-05 重新发布与 Apple 平台开发

- 用户要求重新发布，并继续 macOS/iOS 开发。
- 最新 Windows 源码通过 82 项 Python 回归与 9 项 Qt 实际窗口流程；当前 Windows 候选 EXE 的完整光谱 smoke 通过，包含导入、预览、撤销/重做、全尺寸导出、sRGB 和原片保护。
- Android 0.2.4 / versionCode 6 从当前源码重建成功，`assembleDebug`、`assembleDebugAndroidTest`、`lintDebug` 均通过；APK v2 debug 签名有效。包内检查核对 288 个 Python 源文件、科学计算原生库、20 款胶片、字体/授权、四种导出和无样片。ADB 当前没有连接设备。
- Windows 与 Android 已重新发布至 `release/`，旧目录及元数据归档在 `release/history/20261105-165711-republication`。新 APK SHA256 为 `7ce2f4d366d9789ca7c068c45a45156f99b15a063c00a3744a042e8d36c57768`；4,813 项发布文件校验通过。摘要保存在 `release/manifest.json`。
- Android 包校验脚本先暴露旧字体资源名断言，已改为校验当前组合字体和许可；修订后的实际 APK 验证通过。
- Swift 6.4.2 Windows 工具链可用，目标为 `x86_64-unknown-windows-msvc`；本机没有 Xcode、Apple SDK 或 MSVC C++ 工具链。macOS/iOS 仍不能在此主机原生编译。
- 仓库没有 iOS/Xcode 工程；本轮没有上传源码或使用付费构建服务，也没有生成 macOS `.app` / iOS `.ipa`。具体构建前置条件见 `docs/apple-builds.md`。

## Earlier Typography Experiment (2026-11-05)

The earlier personal SF Pro / PingFang experiment was superseded by the current shared font asset and is not included in the current release. Historical UI and export behavior is documented in `docs/validation.md`; generated screenshots and logs have been removed.

Android assembleDebug、assembleDebugAndroidTest、lintDebug 成功，Lint 0 errors / 20 warnings，字体资源和签名检查通过。APK 为 arm64-v8a、Android 8+、开发调试签名、versionCode 4。没有连接真机或模拟器，未完成触控、字体视觉、权限、内存和完整光谱性能的设备验收。


## 2026-11-05 当前迭代完成

- 修复用户截图中的 QtCore DLL 启动故障，隔离打包 PATH 后重新生成 Windows 便携版本，系统目录 PATH 下启动/导入/显影/导出实际通过。
- 最新 EXE 轻量 JPG 与完整光谱 TIFF 两条主流程通过，原片 hash 不变，包含 sRGB ICC；当前摘要保存在 release/manifest.json。
- 按追加要求将导出整理为高品质 JPG、分享 JPG、无损 TIFF、RAW 原片。明确 RAW 无显影效果、不得由 JPG 转换，TIFF 当前 RGB 8bit。
- 35 项回归通过。Android 真实 Java TIFF 编码器另经 JVM + Pillow 像素与 ICC 回读通过。
- Android 主 APK/测试 APK 更新并核验签名、八个 LUT、字体、许可、ICC 与无内置照片。无连接设备，设备测试未运行。
- 修复窗口缩放时右侧滚动条压住参数数值：预留固定布局区域，自定义轻量轨道，保持内容宽度稳定。100%/125%/150%/200% Qt 缩放、大小切换、两页参数、底部位置同步通过，并检查原生 Windows 真实截图。
- 修复已同步到发布便携目录；运行中的旧窗口需要正常重开以加载新 QML。保留整个便携目录。
- docs/validation.md、README 和 Android 记录已说明证据及未完成项，没有宣称全部参考功能等价、Android 实机验收或稳定 60fps。

## 2026-11-04 继续软件开发

- 已从此前的 UI 调整和 Skill 制作返回实际应用开发。
- 已检查窗口状态、图像处理、打包脚本与 README，建立当前收尾计划。
- 开始修复与补充回归验证，尚未声称 Windows 产物或 Android 实机验收完成。
- 已通过 25 项回归检查：窗口恢复/损坏配置、多屏、分块 LUT、原片保护、失败与重名导出、异步导入、独立参数、撤销重做、持久化、原尺寸查看、过期渲染与真实导出。
- 原版光谱路径实际运行 Portra 400 与 Velvia 100 小图，均通过。源码桌面已完成导入、调节、撤销重做与原尺寸 PNG 导出验证。
- Windows PyInstaller 构建已开始，结果仍需运行产物验证。
- 实际打包启动暴露 ICU DLL 冲突，已通过隔离错误的生成 DLL 验证启动恢复；永久修正构建 PATH 并重新构建。
- 原生 Windows 窗口验证暴露 Qt 无边框还原行为问题，改为 Windows 原生 Restore 后通过六项窗口状态检查；27 项单元回归通过。
- Android 静态检查发现混合强度零值语义和防过期时机问题，已修正，并补齐可读导出禁用态与系统减少动画偏好；下一步实际编译。


## 0.2.0 最终交付

2026-11-05T01:39:41+08:00：69 项回归、原生导入/批量 7 组与 DPI 52 组合通过。交互计算 27.91ms，事件到发布中位 67.36ms，非完整光谱速度。两端 0.2.0 发布到 release，主界面无粘贴按钮；Android 编译/资源/签名/Lint 通过，无设备运行。完整证据见 docs/validation.md、release/manifest.json。

## 0.2.1 完整光谱与界面发布

2026-11-05T11:52:10+08:00：两端完整光谱、真实汇文明朝体、统一弹窗、安卓重置与滑块端点修复。75 项回归、7 组原生流程、52 个布局组合、实际 EXE 光谱 JPG/TIFF、Android 构建/Lint/源码/依赖/签名检查及主机数学对照通过。0.2.1 发布至 release，旧版进入 history；Android 无设备运行，内存/触控/权限仍需真机验收。见 docs/validation.md。

## 0.2.4 字体组合与平台构建状态

- 全部应用文字统一以中文朱雀仿宋、英文及数字 Noto Serif SC 呈现；标题、正文、按钮、参数和弹窗均用相同组合字体。
- 组合字体构建脚本逐字核验 13,009 个编码字形的轮廓与水平度量；保留两份源字体和 OFL 许可。
- 80 项回归、Windows 原生界面与字体核验、Android 主/测试 APK 构建及零错误 Lint 均通过。
- 0.2.4 已发布至个人兼容路径、通用 release/Windows 和 release/Android。Windows EXE 完整光谱预览、JPG 导出、sRGB ICC、源片完整性与退出验证通过；4,813 个文件校验项全部通过。
- Android 签名、版本 0.2.4/versionCode 6 与字体资源校验通过。没有连接设备。
- macOS 构建入口已经准备，Windows 主机检查确认没有 Apple 构建工具，也没有生成 macOS 应用。iOS 工程与完整光谱内核尚未移植；用户当前没有 Mac。
# 2026-11-05 清晰度与预览响应

- 用户反馈 Android 照片和导出模糊，追加 Windows 导入原片质量、导出按钮响应/目录选择，以及胶片切换视觉反馈和处理速度问题。
- 已确认 Android 的 160px 解码仅用于照片列表；主编辑/导出均从源 URI 读取，但被约 160K 像素预算限制。
- 已确认 Windows 源文件未压缩；初始编辑代理为 1440px，原尺寸缩放模式和高品质导出重新读原片。导出按钮受预览 `busy` 禁用，预览和导出共用线程池。
- 接下来提升 Android 处理尺寸并加入画布缩放；分离 Windows 导出队列并提供可选导出目录；补回归后重新构建。

## 2026-11-05 Android 内存诊断与 0.2.7 发布

- JPG 的压缩体积远小于显影工作集：24 MP 图像约需 96 MB 的 RGBA 位图；单份 float64 RGB 数组约 576 MB，尚未计入光谱内核临时数组和输入/输出副本。
- Android 源码采用区域解码、带重叠的分块显影、逐行编码，保持导出像素尺寸；无法分配缓冲区时会停止，不会静默降尺寸。实际设备内存受 Java heap 与 native NumPy 分配共同影响，本机没有 Android 设备/模拟器，未做设备峰值测试。
- 88 项 Python 回归通过；Windows 0.2.7 候选通过完整光谱 JPG/TIFF 原尺寸导出、ICC 与源片 hash 烟测。Android `assembleDebug`、`assembleDebugAndroidTest`、`lintDebug`、APK 资源及签名检查通过；主机光谱数值对照最大绝对误差低于 1.6e-13。
- Windows/Android 0.2.7 已发布至 `release/`。APK versionCode 9；SHA256 清单 4,814 项全部通过。成品清单见 `release/manifest.json`。
# 2026-11-06 双端导出性能与内存修复

- 接续已有内存优化：CAM16 输出色域压缩分块并行；拓扑节点在读取完成后释放整帧输入。源端科学流程的数值对照和拓扑释放测试已加入。
- 开始审查颗粒模型时确认：`interp_density_cmy_layers()` 创建全尺寸四维 float64 layer tensor；Android全分辨率块显影重复走同一完整 Simulator 管线。接下来先按固定随机种子对比改造前后的像素结果，再决定是否接受优化实现。
# 2026-11-06 导出性能与内存完成候选

- 96 项改动前回归通过；新增颗粒流式路径和分布检验后，全量测试通过 97 项。DIR 扩散及混合过滤对旧公式逐像素相同。
- 24MP 完整光谱从 89.7 秒降至 66.3 秒，峰值从约 6.54 GiB 降至 5.84 GiB；输出尺寸仍为 6000×4000。JPEG 文件编码时延未包含在该独立内核基准中，应用导出还包含读取、校正、编码与写盘。
- Android 已调整全尺寸瓦片内存预算及常见 EXIF orientation=1 的无复制区域读取。Android 主机数学对照、APK 包含性与签名通过；没有实机/模拟器，未能复现用户手机失败。
- 当前准备发布 0.2.8 / Android versionCode 10，待最终两端构建、Windows 成品 smoke、APK 校验及发布清单校验完成。
# 2026-11-06 Android 进度条与 RAW 解码

- 开始排查用户反馈：Android 导出进度条回退，以及相机 RAW 无法查看/转 JPG。
- 发现 Android 现有 `BitmapRegionDecoder` 不支持通用相机 RAW，当前 RAW 功能只做原件复制；不依赖 Android 缩略图解码来冒充原片解码。
- 进度 UI 缺少单调保护与任务代次隔离；计划在写入界面之前先保证单张值和总值不会下降。
- 选定评估 LibRaw 0.22.3 原生接入；Lightroom 目标缺失时按用户指示不运行 REA。
- 尚未修改实现；后续记录真实设备是否可用、构建与 RAW 样本回归结果。

# 2026-11-06 追加：颗粒、性能与界面

- 用户追加 Windows/Android 术语与颗粒风格，并要求核实 Android 完整光谱是否受引擎性能拖慢，同时按“前端设计”Skill 重构布局。
- 已读取 Skill 全文和项目设计规范；本项目已有合适的 Qt/QML + Android 原生栈，不做技术栈更换。
- 确认现有两端只有颗粒强度，桌面 `Settings` 和 Android `Adjustments` 是需扩展的状态入口；Android 每次 tile 都经 Chaquopy 调用 `studio_spectral`。
- 方向：Classic 作为向后兼容默认；另加细颗粒、粗颗粒、团簇三种物理参数组合；UI 保留字体与灰绿配色，按桌面/手机分别重组。
- 尚未改动 UI 或颗粒业务逻辑；即将检查持久化、上下游引擎参数及实际控件尺寸。
- 用户补充右侧暗角等参数预览迟缓、缺少状态反馈；当前新增按相同图像测试参数预览延迟并梳理交互/精算通道，不能仅归因于像素高。
- 已在卸载注册表和进程路径发现 Capture One、Lightroom Classic，REA 服务为 6.8.0 且本机 Windows 可用；用户授权分析两款指定应用，下一步确认具体 EXE 后只读检查。
- 用户明确扩展到个人照片编辑器，不局限胶片模拟：需求纳入 Lightroom 风格的白平衡、相机校准、色阶/曲线与 Capture One 风格色彩/质感微调。
- REA 已静态检查 Capture One 图像核心及 .NET 主程序集、Lightroom CameraRaw 模块导入证据；未执行目标，也未宣称恢复专有算法。
- 下一步把跨端编辑数据结构、显影桥接、持久化、快速预览和核心控件连起来；RAW 解码使用 LibRaw，不依赖 Android Gallery 缩略图或商业软件。
# 2026-11-06 蒙版实现范围

- 用户新增并收敛要求：不希望功能堆叠；优先保证有蒙版和基本调整，界面需维持简约美观。
- 之前被询问的专有引擎替换不需要；蒙版可作为本地像素处理层接到现有完整光谱/LUT 渲染之后。
- Lightroom 原用户图库未访问。Capture One 当前仅观察到工具名称/分组，没有加载图像或完成实际效果比较；官方帮助抓取被 403/404 拦截。
- 计划实施单一上下文蒙版入口，先支持可编辑画笔与基础局部调节，不做脸部检测/自动修肤。
- 具体改动前检查 QML/Android 画布交互、每张照片的会话持久化、交互与导出渲染调用。
- 测试重点为蒙版像素坐标/软边/强度归一、状态序列化、两端渲染一致接入和构建；未连接 Android 设备时不声称触控通过。
# 2026-11-06 编辑工作流整合开始

- 根据最新反馈收敛范围：无评级/图库管理，批量直接导入；源照片保持原位；相机校准承担青橙色彩控制，不添加重复的色彩分级面板。
- 已确认 Windows `Settings` 已有温度/色调、基础色调和 RGB 三原色色相/饱和度；Android `Adjustments` 与 `studio_spectral.py` 也已有对应参数，旧记录需兼容。
- 发现桌面强制完整光谱，但没有独立“胶片启用”状态；Android `strength == 0` 直接返回原图，可能会一并跳过基础调整。本轮将先建立显影启用状态并确保基础编辑分层有效。
- 本轮未改源代码；下一步定位两端各渲染分支的准确管线，并为新开关补测试。
# 2026-11-06 跨端蒙版实施

- 已检查现有 Qt/QML、Android View、逐张状态和分块导出；当前没有局部蒙版实现。
- 并行分工：Windows controller/QML、Android Kotlin/UI、通用 Skill；主线程实现共享 NumPy 核心、桥接及数值/分块回归。
- 使用归一化原片坐标、短边相对半径和矢量笔触；局部编辑不重新进入完整光谱内核。
- 用户新增连续参数滑杆顺滑要求，同步纳入功能验证与通用 Skill 备份。

