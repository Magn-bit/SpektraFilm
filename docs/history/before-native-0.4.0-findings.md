# 2026-11-07 RAW兼容与原片质量

Windows曾遗漏IIQ/3FR/FFF等RAW入口，已统一为shared/photo_formats.py；实测GFX100压缩16位RAF、X2D100C 16位3FR、IQ4 150MP IIQ L均完整解码，三者Android同源C++的full/half输出也逐字节匹配官方LibRaw。不能据此声称所有中画幅机型和压缩变种已验收。

Android过去打开RAW就先全尺寸显影，再从全尺寸磁盘缓存生成代理。现在明确使用native halfSize预览，full缓存键独立，完整导出重读原URI且拒绝缩小输出；内存准入仍按完整传感器估计，因为half不能省去全部RAW解包。完整分辨率不等于全程16位：现有两端胶片入口仍有RGB8/Bitmap转换。质量边界、样本来源、尺寸与实机限制见docs/raw-camera-compatibility.md。

C1研究新增CPU第二步、第三步标量子集、中性色彩前段和ICC融合节点独立比较。22项参考测试21通过、1已知失败；完整实际CPU第三步及ICC融合表生成仍有缺口，未接入产品。

# 2026-11-07 C1 RAW实际运行证据更新

取得受控原生RGB16 TIFF、真实CPU Bayer/GG参数及中间像素。曲线独立5324点逐float相同；A7CR噪声/阈值64次观测完全一致。GPU Bayer单段通过但四段级联有3严格失败；CPU公式与GPU有实际差异，隔离CPU scalar可复现捕获裁块。不能将这些局部结果称为完整C1显影或已迁入产品。

同片对照保留原尺寸差异，LibRaw共同区6376×9564裁取6336×9504，只平移无拉伸/色彩拟合。正常C1参考约2.33秒只计RAW ProcessToFile，非胶片光谱速度。总入口docs/captureone-raw-reconstruction.md。

---

# 2026-11-07 RAW 亮度与 C1 算法证据修正

Windows 原先使用 ReconstructDefault(5)；LibRaw `mem_image.cpp` 的 `!((highlight & ~2) || no_auto_bright)` 条件让该配置跳过 histogram 自动提亮。Android 另有固定 gamma white=65536 的逐行输出错误。现均改为 Blend(2)，Android 对齐官方 histogram/fuji/t_white/bright 曲线，并升级 RAW 缓存目录。

A7CR 同片旧解码均值约 .242、修正后 .5326、相机内嵌 JPEG 约 .546，证明此前整体偏暗存在实现原因。修正不是 Capture One 算法恢复；生产仍使用 LibRaw。Windows 修正后全尺寸完整光谱导出262.636秒、13057.9MiB，输出6376×9564，源hash未改；报告 `output/raw-film-0.3.4-a7cr-brightness-fixed/report.json`。并行静态分析/C1活动使其不适合作为与旧暗图的严格速度对照。

Capture One 16.8.6：已恢复 A7CR ICC 标准 mft2 数据路径及 FCRV 三块点表；ICC 属于去马赛克后的色彩环节，不能当成传感器 decoder。原生自动曝光/白平衡、曲线 parser 正在追函数体。报告 `docs/captureone-a7cr-camera-profile-analysis.md`。尚无独立完整 C1 RAW 引擎或逐像素同片等价证明。

---

# 2026-11-07 当前实现证据

Windows当前已接入受精确spec约束的Vulkan CAM16-UCS色域阶段；其余光谱阶段仍CPU。物理GPU是RTX3070Ti Laptop/device9376，Vulkan正确识别。默认临时GPU buffer按4M像素分带；系统14GiB级全链工作集并未因此消失。

M盘原片朝向后6376×9564，source hash未改，完整光谱JPG100/4:4:4/ICC131.778秒。此为源码全链含RAW/编码/写盘，不是Android或冻结EXE成绩。24MP最新58.570秒仅渲染含cold GPU setup。

发现preview_mode会关掉真实颗粒和DIR，故项目代理已改为运行完整模型；Android需区分wholeimageproxy与fullsource tile的film_format_mm。测试不能以全部关闭grain的速度作为颗粒滑杆已跟手的证据。

wgpu wheel官方PyInstaller hook收集DLL与combined_header.h，仍需冻结成品实际Vulkan smoke以排除CPU回退掩盖缺库。

---

# 开发发现

## 2026-11-07 跨平台 GPU 性能审计

### 本项目当前基线

- 当前 SpektraFilm Windows / Android 完整光谱路径仍运行 Python/NumPy/SciPy；Windows Numba 加速部分 CPU kernel，Android Chaquopy 使用 NumPy/SciPy 兼容层，不含 Numba/LLVM JIT。完整照片计算目前没有可用的 GPU backend。
- 24MP 固定合成输入在当前 CPU 路径实测 64.622 秒，峰值工作集 5983.9 MiB，输出尺寸 6000×4000。阶段：filming.expose 13.692 秒、filming.develop 28.651 秒、printing.expose 2.635 秒、printing.develop 0.207 秒、scanning.scan_print 18.728 秒。报告 `output/perf-baseline-20261107-current-host-cpu.json`。
- 用户确认真实显卡为 RTX 3070 Ti；本机枚举到 RTX 5090 与此不符。上述测量来自 CPU 光谱后端，GPU 没参与渲染，不能标注成 RTX 3070 Ti GPU 性能。
- 当前 profile 的主要流水线 tap 为 `rgb_in → rgb_pre → log_e_film → cmy_film → log_e_print → cmy_print → rgb_out`。可按阶段依赖复用中间结果；film stock、曝光、halation、grain 各自应有明确失效边界。使用 tap 不等于已实现持久缓存。
- Android 完整光谱 tile 仍逐块经 Kotlin/Bitmap/ByteArray 与 Python float64 转换；tile 降低单次整帧内存压力，但重复 Python 入口和数组分配仍在。原生 RAW RGB16 缓存已存在，主要差距是显影计算和搬运，不是再换 RAW 解码器。

### 对照实现能证明什么

- SpektraLab Windows Vulkan 的历史测量：32.95MP RTX 5070 Ti 首次 full render median 约 871ms、warm full 约 229ms、缓存 reprint 约 66.7ms；计时包含 CPU RGBA16 结果物化，但不含 RAW decode、engine creation、source upload、编码/导出。它证明原生 GPU + GPU resident negative + reprint cache 有可行性，不是本项目的 A/B 成绩。
- SpektraLab Android 社区移植 v1.5.0e 的 README 测量：SM8735/Adreno 825，16.5MP full render 约 8.2 秒、total 8.4 秒，2048 live 约 1 秒。它明确有设备/驱动/工作组和内存边界；不能用 Windows 成绩代表 Android。其默认导入会按内存预算与 8000px 长边限制缩小，不能照搬到要求原尺寸输出的流程。
- Android fork 的 512 行分带将一个 IIR kernel 单次 dispatch 从 616ms 降至 34ms，并记录逐字节相同结果。这主要解决单任务 watchdog 与设备丢失，不代表总光谱管线提升 18 倍。
- 上游 macOS README 的“45MP 不到一秒”是产品描述；源码服务记录另有 45.75MP full export 约 13.9 秒、GPU cache reprint 约 121.7ms、2560 preview reprint 约 13.7ms。其边界不同，不能混为一次完整 export 的证明。
- SpektraLab 使用自己的 C++/Vulkan/Metal 光谱实现。应复用经验证的 GPU 调度、资源池、阶段缓存和分带思想；不要把它的 shader/profile/印相模型冒充为当前 SpektraFilm 物理模型。
- SpektraLab Android 底层支持 negative cache，但该社区 UI 暴露的 `nativeRenderBegin` 每次调用 `spk_render` 强制重跑 film；UI 未调用 cached `spk_reprint`。所以“具备 GPU 缓存”与“产品参数交互命中缓存”是两个事实。

### 后端选择证据

- Context7 当前 `wgpu-native` 文档列出 Windows 10+ DX12/Vulkan、Linux/Android Vulkan/GL、macOS/iOS Metal/Vulkan portability；单套 WGSL compute shader可由 wgpu 映射到各平台原生 API。
- Context7 Dawn 文档虽有 C++ WebGPU API 与 D3D12/Metal/Vulkan，但其当前支持表把 Android Vulkan 标为 work in progress，不选作这项必须覆盖 Android 的共享后端。
- 每个平台独立维护 Vulkan、Metal、D3D12 shader 可获得更低层控制，但三份计算实现增加公式与边界语义分歧，验证成本最高，放弃作为首选。
- 选 `wgpu-native` + 固定版本作为原生 C ABI 边界，Windows 显式 D3D12、Android 显式 Vulkan、macOS 显式 Metal；WGSL 管线构建并在设备上缓存 pipeline。是否能达到目标帧时和具体设备兼容性仍须实测，当前没有 GPU prototype，也没有 Mac/Xcode。

### 原生化的验收底线

- GPU 实现必须调用同一份 SpektraFilm profile、物理公式和参数映射；不以 LUT 替代最终完整光谱。
- 输出宽高与源完整分辨率一致。大图按带执行时，空间滤波必须正确处理 halo/边界；相邻块拼合不能出现接缝，最终编码直接消费流式行/块。
- 先比较现有 CPU oracle 与 GPU 中间 tap 和成片。浮点精度、CAM16/色域压缩、颗粒随机数与跨设备一致性要逐项评估；未通过的 stage 不切换。RGB8 最终落盘并不意味着可在中间任意降低精度。
- 测量统一拆分 RAW decode、source upload、每个物理 stage、preview cache hit/miss、readback、JPEG/TIFF encode、write、PSS/working set 和 GPU allocation；记录真实设备与驱动，不比较不同设备/不同模型的“倍数”。
- 用户此前确认未来需要 macOS；同一引擎后端目标使用 Metal，但该 Windows 主机无 Mac/Xcode，故 macOS 构建和实机结果必须留作后续设备验收。

决策文档：`docs/gpu-performance-engine.md`。

## 2026-11-05 原片像素保留

- Android 列表缩略图使用 `decode(uri,160)`；编辑图调用 `decode(uri,2048)`，但 decoder 额外套用 `min(memory-budget,1.2MP)`；单张与批量 JPG/TIFF 导出也调用同一 decoder，因此 q=100 并未阻止输出像素尺寸下降。
- Android `FilmEngine.render()` 将完整 tile 整体打包成 ARGB byte array，再在 Python 创建 float64 全帧/光谱中间量；移除 1.2MP 上限后直接整图调用存在明显 OOM 风险。必须采用分块/区域显影或在超出设备容量时明确失败，不能静默缩尺寸。
- Windows `JPG_HIGH` 和 TIFF 预设为原片尺寸；export path 使用 `read_photo(path, max_edge=0)`。常规画布帧仍有代理尺寸，源路径仍保留，详情缩放通过独立完整尺寸加载。需要覆盖此合同的回归。

## 2026-11-05 导出速度与文件体积

- Windows/JPG_HIGH 为原尺寸、质量 100、4:4:4 且嵌入 sRGB；将普通 JPEG 转成该预设后比源文件大是正常情况，完整显影里的颗粒也会增加高频信息和文件熵。TIFF 通常远大于 JPG，RAW 应字节完全相同；JPG_SHARE 为质量 85、最长边 2048px，通常更小但不作绝对保证。
- 900×600 合成纹理的 Windows 实测：读取 6ms、镜头校正准备 450ms、完整光谱渲染 5.4s、JPEG 100/4:4:4 编码 14ms，总约 5.87s。上游 Simulator 阶段计时主要落在 `filming.expose`、`filming.develop` 与 `scanning.scan_print`。将 JPEG 质量降下来几乎不能缩短主要等待。
- 测试源 JPG quality 88 约 453,772 bytes，完整显影后的 quality 100 JPG 约 1,691,539 bytes（约 3.7 倍）；仅为高纹理合成图证据，真实增幅由照片内容、源格式与预设决定。
- Android 高品质 JPG 固定质量 100，重新解码 URI；最大处理像素受设备内存预算限制（代码上限 1.2MP），性能没有 Android 真机测量。当前没有用户原片/导出样本，不能对某对具体文件判定异常。

## 2026-11-05 预览优化与导出质量边界

- 预览限边只在 controller 生成编辑帧时使用；Windows `export_preset()` 独立调用 `export_photo()`，高品质 JPG 参数仍是 `edge=0, quality=100`，编码固定 `subsampling=0`；TIFF 为 `edge=0`、LZW，无 JPEG 压缩。
- Android 的编辑预览会使用独立小图，但 `saveTo()` 对非 RAW 通过 `decode(inputUri, preset.edge)` 重新从原 URI 解码；预设参数决定分享图尺寸与 JPEG 质量，其他 JPG/TIFF 不会借用预览 bitmap。需以原图尺寸的候选包实测高品质导出验证。
- 当前 `release/manifest.json` 不是可直接采信的发布证据：0.2.6 APK 缺失、Windows EXE 的实测哈希与记录不符，README 仍是 0.2.5。构建和 smoke 必须先使用隔离候选目录，验证后才切换 release。
- 默认 `python` 指向系统 Python 3.12，缺少 PySide6/部分上游依赖；桌面测试使用 `.venv/Scripts/python.exe`，并设 `PYTHONPATH=vendor` 才能代表项目环境。
- 旧 Windows smoke 调用 `export_to()` 的普通 JPG 默认质量 95，并将输出尺寸与已发布的 UI 预览 QImage 比较；这会把代理预览尺寸误当成原片尺寸。现在显式用 `JPG_HIGH` 或 `TIFF`，并使用源文件完整解码尺寸验证；首轮候选 JPG 实际已生成 900×600、带 ICC，失败在误判而非导出。
- Windows 实际候选高品质 JPG 实测 900×600、JPEG subsampling=0、所有量化项为 1（quality 100），含 ICC；TIFF 同尺寸、LZW tag=5、含 ICC。两种格式通过完整光谱 smoke 且源文件 hash 不变。
- Windows/Android 0.2.6 发布成功，SHA256SUMS 覆盖恰好 4,813 个 Windows、Android、README 与 manifest 文件，逐项无 hash 错误。`release/.windows-candidate` 是本轮首次候选生成的残留临时目录，不被清单包含；本机 PowerShell 执行策略拒绝递归删除，未另寻绕过方式。
- Android 导出 JPG 高品质预设仍 quality 100，并从原 URI 重新解码、运行完整光谱，不复用 640px 编辑预览；最大处理像素受设备运行时内存预算限制（当前上限 1.2MP），因此不能声称在所有手机上达到相机原始分辨率。没有真机/模拟器可验证设备上限与耗时。

## 2026-11-05 清晰度与预览响应

- Android 的照片列表缩略图是独立 160px 解码，只供列表使用；编辑照片和导出会从 URI 重新解码原图。但 `decode()` 的浮点光谱预算下限仅 160,000 像素，并额外把预览缩到 640px，因此导出和编辑显影都可能只有约 0.16MP。
- Android 原版光谱引擎使用 NumPy float64；不应直接改为整张 24MP 解码。应在保守像素上限内提升有效分辨率，并显示真实处理尺寸。RAW 原片仍逐字节复制。
- Windows 导入只将 1440px 代理缓存用于初始显影，缩略图另为 260px；高品质 JPG/TIFF 会从原文件重新解码至原尺寸显影，Windows 没有压缩或覆盖原片。
- Windows 导出按钮和所有预设最终确认受 `busy` 控制，而 `busy` 包含慢速完整光谱预览；导出还与显影共用单线程池，所以预览延迟也阻塞导出开始。目录选择应将选定目录作为根，并在其下保留格式子目录。
- Windows `selectStock()` 已更新当前照片设置并请求新一代渲染。`_changed()` 另有 640px LUT 交互预览，随后单线程完整光谱；需要回归验证两条结果的新胶片状态及显示顺序。

## 2026-11-05 源码目录整理

- `.tools/`（约 34.9 GB）、`.venv/`（约 1.17 GB）、`output/`（约 1.32 GB）、`dist/`（约 0.84 GB）、`build/`（约 0.21 GB）和 Android Gradle/Python 构建缓存均为可再生成内容；递归删除命令被执行环境策略拒绝，实际内容尚未删除。
- `.reference/` 保存两个上游参考仓库及研究文件；`personal-fonts/` 保存用户明确要求下载的字体与 Apple 来源/许可；`release/` 保存当前成品和先前发布归档。这三部分应保留。
- `release/manifest.json` 的旧 tests 字段引用 `output/` 临时报告，现改为指向源码项目验证说明。`release/SHA256SUMS.txt` 已对当前和历史发布文件重新计算，共 9,627 项。

## 2026-11-05 重新发布与 Apple 目标

- Windows 与 Android 0.2.4 已从当前工程分别重建并发布；Android 新包 SHA256 为 `7ce2f4d366d9789ca7c068c45a45156f99b15a063c00a3744a042e8d36c57768`。4,813 项 `release/SHA256SUMS.txt` 条目逐项核验通过，旧版在 `release/history/20261105-165711-republication`。
- `scripts/publish_local_release.py` 现在接收经校验的 Android APK，不再复制旧包；Windows 与 Android 成品、版本、QML、字体及 smoke/包内报告在切换前校验。空的 PowerShell 进程枚举被规范化为空列表。
- `android/tools/verify_apk.py` 原先断言已淘汰字体路径位于 DEX；现改为按当前双语组合字体资源和授权文件验证。发布 APK 包内含 288 个 Android 光谱 Python 文件、NumPy/SciPy/scikit-image 原生扩展、20 款交互 LUT 和四种导出实现，无照片样片。
- `scripts/build_macos.py --check` 只检查宿主，真实 `.app` 必须在 macOS 原生 Python / PyInstaller 环境构建。Swift 6.4.2 Windows 工具链已安装，但无 MSVC C++ 工具链、Xcode 或 Apple SDK。
- 仓库当前没有 `apple/ios`、`.xcodeproj` 或 `.xcworkspace`。Android Kotlin/Chaquopy 工程不能直接变成 iOS 工程；完整内核依赖 Python 科学计算及本机编译扩展，需单独选择并验证 iOS 移植路线。
- 用户授权重新发布到本地 `release/`，但未授权源码外传、云付费构建、Developer ID 或 iOS 代码签名。
- Swift 官方 Windows 工具链 6.4.2 已于 2026-10-29 发布；WinGet 包 `Swift.Toolchain` 的发布者为 swift.org，安装器 SHA256 为 `8fe5d31ca1153dfe6be3a76de0b93347fd42a27599671e9f9ade23a3648e7184`。它可供 Windows 上的 Swift 编译与静态验证，但不提供 Apple SDK/Xcode。来源：https://www.swift.org/install/windows/ 与 Swift 官方仓库 `docs/WindowsToolchain.md`。
- Windows SDK 自带 UCRT 头文件，但当前未发现 Visual Studio/MSVC `cl.exe`，Swift Windows 工具链尚不能完成标准库编译；无 Apple target SDK。
- 候选包烟雾测试已输出完整成功报告和非空导出/截图；首次 PowerShell 包装命令错误地将 GUI 进程空的 `$LASTEXITCODE` 当作非零值，不能作为应用失败证据。发布脚本改为以成品 JSON 报告的 `ok=true` 与光谱检查项作为判据。

- Windows: PySide6/QML，Python 科学内核。现有八款 33³ LUT，轻量近似与原版光谱模式。
- 当前目录 D:/Project/SpektraFilm，不是 Git checkout；无已发现的上级 AGENTS.md。
- 已安装「前端设计」Skill；本轮保持当前布局和字体，优先功能可靠性。
- Android 调试 APK 已构建，尚无真机/模拟器验证证据。
- WindowState.restore() 已补强无效 JSON、空屏幕、小屏与多屏处理；真实六项状态检查通过。
- apply_lut() 和全分辨率显影已使用 float32 分块，逐通道光晕降低峰值内存。
- export_photo() 已先校验格式/目标，临时文件编码完成后原子发布，不覆盖并发写入。
- README 已删除内置 AI 样片旧描述，正常启动为空状态。
- 打包启动故障已明确：PATH 中 Poppler 的 ICU 78 被收集为 icuuc.dll，缺少 Qt 依赖的 Windows 系统 ICU 无版本函数；移除生成副本后 exe 实际启动通过。永久构建使用隔离 PATH。
- Windows 原生 HWND Restore 可修复 Qt 无边框 showNormal 留在最大化的问题；实际六项窗口状态检查已通过。
- 分块显影和逐通道光晕将 24MP 默认轻量显影的进程峰值从约 1800MiB 降到约 769MiB；耗时约 35.5 秒（与构建并行，本机单次测量，不是通用速度结论）。
- 截图发现导出对话框自定义 header 只有 height 而没有 implicitHeight，导致背景高度少计并裁到按钮；已修复。
- 四种导出为高品质 JPG（100 / 原尺寸）、分享 JPG（85 / 2048px）、8bit 无损 TIFF、RAW 原片。RAW 必须逐字节复制，不能包含显影或伪装图片转换。
- JPEG quality 100 的随机宽幅图暴露 Pillow 优化/渐进编码缓冲失败；取消不必要的优化/渐进选项，保留质量 100 与 4:4:4 后回归通过。
- Android 用真正的逐行 TIFF 编码，主机 JVM 编码后由 Pillow 独立回读，像素/ICC 一致。RAW 在系统无法解码时仍可原片另存，不伪造预览。
- 原 ScrollView 的默认覆盖式滚动条与参数共用右侧空间。固定 20px gutter、12px 交互轨道，数值到轨道保留 8px；显示/隐藏不改变内容宽度。四档 Qt DPI、六种大小状态和两页参数通过。
- Qt offscreen 的 MultiEffect 圆角遮罩截图为空，因此 offscreen 仅作为几何/位置证据；视觉验收使用原生 Windows 与实际成品截图，未把黑图当作通过。


## 0.2.0 最终交付

2026-11-05T01:39:41+08:00：69 项回归、原生导入/批量 7 组与 DPI 52 组合通过。交互计算 27.91ms，事件到发布中位 67.36ms，非完整光谱速度。两端 0.2.0 发布到 release，主界面无粘贴按钮；Android 编译/资源/签名/Lint 通过，无设备运行。完整证据见 docs/validation.md、release/manifest.json。

## 0.2.1 完整光谱与界面发布

2026-11-05T11:52:10+08:00：两端完整光谱、真实汇文明朝体、统一弹窗、安卓重置与滑块端点修复。75 项回归、7 组原生流程、52 个布局组合、实际 EXE 光谱 JPG/TIFF、Android 构建/Lint/源码/依赖/签名检查及主机数学对照通过。0.2.1 发布至 release，旧版进入 history；Android 无设备运行，内存/触控/权限仍需真机验收。见 docs/validation.md。

## 2026-11-05 字体方向再次更新
用户随后明确要求 Apple 字体用于个人使用，0.2.2 个人版已接入从 Apple 官方安装包提取的原始 SF Pro Text / Display。来源与原始许可随个人目录保留；个人使用不改变原有字体授权。未找到苹方，真实 Windows glyph runs 为 Microsoft YaHei UI + SF Pro Text；Android 配置系统中文回退，未真机验收。霞鹜文楷仅为共享默认候选，并非个人版实际字体。
官方来源：https://developer.apple.com/fonts/ ，https://developer.apple.com/fonts/system-fonts/ ，https://developer.apple.com/documentation/technologyoverviews/fonts

## 0.2.2 个人使用版（2026-11-05）

早期个人字体实验曾在独立本地构建中使用 Apple 字体；该成品目录已不保留。当前共享字体与发布资产见 assets/fonts/ 和 release/。

正文接入 SF Pro Text，标题接入 SF Pro Display。没有苹方：Windows 中文实际字形来自 Microsoft YaHei UI，Android 使用设备系统中文回退。Windows 成品运行时已确认 SF Pro Text；Android 字体资源 hash 已核对，尚未真机验收。

Windows 增加会话移除与 Delete、适合/100%/200%、鼠标定点滚轮缩放、放大后拖动、双击适合/100%；保留原片与编辑记录。Android 照片列表支持点缩略图直接编辑、独立批量勾选和移除会话项。

80 项 Python 回归、7 项真实窗口导航检查、52 个 DPI/尺寸/页签组合与界面弹窗检查通过。发布副本的实际 EXE 完成完整光谱预览、撤销/重做、原尺寸 JPG 导出、sRGB ICC 和原片 hash 保护；编辑页与导出弹窗截图已检查。证据 output/personal-release、output/photo-navigation/report.json。

Android assembleDebug、assembleDebugAndroidTest、lintDebug 成功，Lint 0 errors / 20 warnings，字体资源和签名检查通过。APK 为 arm64-v8a、Android 8+、开发调试签名、versionCode 4。没有连接真机或模拟器，未完成触控、字体视觉、权限、内存和完整光谱性能的设备验收。

# 2026-11-06 导出性能与内存诊断续记

- 上一轮 6000×4000 完整光谱测量：优化前约 117.5 秒；CAM16 分块后约 88.6 秒、峰值工作集约 7,101 MiB；释放已消费的中间帧后约 89.5 秒、峰值约 6,465 MiB。全尺寸光谱导出依然不适合当作已解决。
- 当前最大单块数组风险位于 `interp_density_cmy_layers()`：将整张 `H×W×3×3` float64 图层堆在内存中，24MP 单数组约 1.61 GiB；插值复制与逐层随机颗粒还会制造更高峰值。
- Android `FullResolutionPhoto.SpectralRows` 会依据 heap 预算切片，但每个 tile 调用 `render_argb()`；桥接层每次把 ARGB tile 展开为 H×W×3 float64，并由完整光谱 Simulator 跑全部 stage。实机失败尚无设备日志，不能仅凭 APK 构建推断设备可用性。
- 导出质量与像素尺寸必须保持：Windows JPG_HIGH 质量100/原尺寸，TIFF原尺寸；Android 高品质 JPG 质量100/TIFF原尺寸。性能修复优先消除整帧临时数据、复用管线及缩小有边界的工作集。
# 2026-11-06 双端导出最终性能数据

- 24MP 完整光谱桌面渲染（6000×4000、默认颗粒/光晕）：起始 89.7 秒、峰值工作集 6.54 GiB；流式颗粒层与 Poisson thinning 后 68.0 秒、峰值基本不变；DIR 校正数组复用与扩散混合原位累加后 66.3 秒、峰值 5.84 GiB。
- 对照 24MP 最终阶段计时：曝光 13.9 秒、胶片显影 28.4 秒、放大 2.6 秒、扫描 20.5 秒。编码和磁盘 I/O 不包含在此数字内；渲染输出始终是 6000×4000。
- 将 Numba 线程数固定为 4 的 24MP 基准为 71.4 秒，慢于默认 20 线程的 66.3 秒，因此保留默认线程配置。
- 颗粒层按像素概率做 Poisson thinning，理论分布、期望和方差与原 Poisson-Binomial 混合完全相同；固定随机序列改变，但不再额外做一个逐像素 Binomial 抽样。
- Android 瓦片预算改为 Java heap 的 12% / 320 B-per-pixel，并对无旋转且完全落在图像内的区域直接返回解码 bitmap，省去额外整块像素复制。无设备/模拟器，无法验证用户手机的实际崩溃堆栈或持续运行性能。
# 2026-11-06 Android 进度条与 RAW 解码

- Android 当前 `FullResolutionPhoto` 使用 `BitmapRegionDecoder`，它不是相机 RAW 解码器；RAW 扩展名目前仅支持原片复制，打开 RAW 时常规位图解码失败，导出 RAW 到 JPG/TIFF 也会失败。
- Android 桌面端依赖 `rawpy`，但 Android 的 Chaquopy 构建没有 rawpy/libraw；rawpy 不能直接视为 Android 已具备 RAW 支持。
- 进度回调把每次值直接赋给 UI，未保护单张进度、批量总进度或导出任务代次。即使算法给出阶段性较低值，进度条也会原样回退。
- 上游 GitHub API 报告 LibRaw 最新版本为 0.22.3。Android 目标仅 arm64-v8a；完整分辨率 RAW 解码采用 LibRaw 原生处理，预览与导出需分离以控制工作集。
- Lightroom APK/设备不是当前可用输入，按用户最新指示跳过 REA；外部代码/许可证仍须核验并随源码保留。

# 2026-11-06 颗粒选项、Android 性能与 UI 重构

- Skill 指示保留现有 Qt/QML 桌面与 Kotlin 原生 Android 技术栈；局部 UI 重构不需要重新选型矩阵。
- 桌面主页面由照片工作区和编辑区组成，胶片选择与参数目前分属标签，部分控件/标题密度和照片导入、导出入口需要理顺；Android 目前是窄高画布下方再叠参数卡，控件区高度只按屏幕高度 20% 限制。
- 桌面 QML 与 Android 都在调节区显示“银盐颗粒”；当前颗粒只有连续强度值，桌面和移动端都须增加同一组可持久化类型。
- 颗粒类型不能停留在文案选项；通过上游光谱模型的粒径、空间模糊、均匀度与微结构映射形成可比较的物理风格，Classic 保持原结果作为兼容默认。
- Android 使用 Chaquopy 调用 Python/NumPy 科学引擎；ARGB tile 每次都跨 Kotlin/Python 边界重新打包，并初始化完整处理链。性能结论应由分段基线和可复现小图/中图用例支持；当前没有 Android 设备用于真机延迟/内存结论。
- 前端调整方向：保留现有字体、灰绿强调色、无衬线工具正文和照片优先工作流；桌面突出画布+常驻工具，手机用紧凑顶栏、可伸展画布和固定下部控制区，避免缩小桌面布局。
- 右侧多个参数（包括暗角）预览慢的主因尚未测量。待检查：桌面是否每个值都触发全尺寸光谱/重复 RAW 解码、交互预览是否先走低成本路径、过期结果是否覆盖、像素预算；Android 是否每次滑动仍等待整张照片的 Python 计算。
- 用户确认电脑上已装 Capture One 与 Lightroom Classic；REA 以确切安装目录/可执行文件为目标做静态分析，运行态或打开照片等实验需另行确认运行作用域，当前只读取静态实现。

# 2026-11-06 本机 Lightroom / Capture One 静态分析

- 本机安装项确认 `Capture One 16.8.6` 和 `Adobe Lightroom Classic 15.5`；目标 EXE / 模块由程序卸载项对应安装目录解析。
- Capture One `ImgCoreDll.dll`（SHA256 `ca02b6ac2786e9a100f63221df7340e5df210416eb0bd53a4bb1bfc2306a44a4`，完整导入目录）静态导入 OpenCV、ONNX Runtime、DXCore/DirectML、线程/同步和图像存储依赖。导入表不证明目标代码路径执行、具体功能由哪种技术实现或 GPU 实际使用。
- Capture One `CaptureOne.dll`（SHA256 `add69b3dfead8c0ddc96ab8a9cfcb983bc3ff2d5fc5a84a1473cbf317a81d45c`）为完整可枚举的现代 .NET CIL：版本 16.8.6.3784，45,109 个方法、5,876 个类型，无 ReadyToRun。仅做静态元数据检查，没有加载、解码 C# 或执行目标。
- Lightroom `CameraRaw.dll`（SHA256 `854f3275b64b8f3f47dc84ec0027f34662d39831c66f88ed17f86d54a9c822bf`，完整导入目录）静态依赖 Adobe 自有 `AgKernel.dll`/`substrate.dll`/`ui.dll`、并发同步、文件映射/虚拟内存、Direct3D 与色彩管理 API。导入表不能证明具体算法/功能或实际 GPU 调度。
- Lightroom `Develop.lrmodule` 无普通 PE 导入目录；不能据此推断无依赖或无显影功能。
- 当前从这些结果可用的工程方向是：预览/计算/文件 I/O 分工、控制内存映射和并发、GPU/CPU 加速要以本项目设备基准决定。无法通过静态导入表恢复 Lightroom/Capture One 的数值算法或性能行为。
- 用户扩展目标为个人完整照片编辑器。实现功能按公开色彩科学、许可证允许的开源算法和可互操作常规处理建立，不从商业模块复制实现代码。
# 2026-11-06 蒙版范围收敛

- Capture One 临时会话的可访问控件树可观察到“图层与遮罩”、单独“皮肤色调”选项卡，以及修饰模块入口；其导入模态窗焦点无法通过自动化稳定操作，故未完成样片视觉对照。
- Adobe 官方帮助页和 Capture One 官方支持页当前 HTTP 返回 403/404，不能将未读到的官方材料写成已核实事实。
- 用户最新收敛目标：避免软件杂乱，只保证有蒙版和基本调整。因此停止人像特化研究与脸部模型路线，改做上下文式单一蒙版工具入口。
- 当前两个图像引擎均无蒙版状态/路径；需新增每张图的灰度蒙版和局部调整参数，并将其串入交互和高品质输出渲染。
- 引擎无需更换；预览蒙版边缘应做软化，保存的 mask 保持源图坐标/尺寸映射，导出路径不可用预览缩略图蒙版替代。

# 2026-11-06 编辑工作流收敛

- 用户明确不需要评级或类似图库管理；偏好一次大量导入/拖入，减少额外的软件留存与占用。实现中不能复制/删除原片；导入清单与代理图应有界，预览缓存可淘汰。
- 用户澄清青橙色调应属于 Lightroom 风格“相机校准”，不是单独色彩分级。两端当前已有红/绿/蓝原色色相与饱和度，接入真实渲染；避免重复模块。
- 产品目标是先正常载入/查看照片，用户选择是否启用胶片显影；白平衡、曝光和基础色调在关闭胶片时仍有效。
- 兼容建议：旧 JSON 若缺 `film_enabled`，按既有行为保持显影；新导入明确写入关闭值，避免旧记录被意外改变。
- Lightroom/Capture One 的私有内部算法无法从本机静态导入表推定；只实现可观察到的工作流与独立色彩处理，不宣称私有算法复刻。

# 2026-11-07 最终发布0.3.2

- 纯胶片23款、Claude配色、紧凑颗粒菜单、常用参数不强制折叠、主界面无推导标签。
- Windows实际EXE及Android包验收通过，正式成品已替换；4848文件哈希一致。
- 旧临时 release/.windows-candidate 删除被工具自动审批以 blocked by policy 拒绝，未绕过；未影响新成品发布。
- Android未连接设备；61MP Windows源码完整谱JPG实测164.269秒/14624.9MiB，不能称大图性能已解决或手机已验收。
