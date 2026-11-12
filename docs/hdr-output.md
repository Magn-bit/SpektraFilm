# Windows HDR JPEG 输出

本轮对应 SpektraLab 2.3.2 / `1952c63537ec576d24422f1065b12495631346a5` 的 HDR 显影机制。本项目使用独立、原生编译的 libultrahdr 2.0.2 写出实际双图 JPEG，同时携带 ISO 21496-1 与 Adobe `hdrgm` 声明。既有 SDR JPEG 的熵编码扫描不被重编码，普通 SDR 阅读器仍可读取照片。它并非只添加 HDR 标签。

## 开关与支持范围

- 编辑参数：`hdr_enabled`，默认关闭；`hdr_peak_stops` 为 0.5–4 EV，即目标 H 为 `2**EV`。
- 本轮支持普通照片配方的 JPEG，sRGB 或 Display P3；使用配方的质量参数、ICC、原有命名与拍摄信息保留逻辑。
- 只有用户明确指定配方缩放时才改变输出尺寸。未缩放导出为原图经裁切后的完整尺寸，增益图与最终 JPEG 基图逐边相等，不用预览代理替代最终源。
- 彩色印相及反转片可用；胶片关闭、底片扫描、数字中间片、黑白胶片、印相 EDR 明确拒绝。PNG、TIFF、HEIF、RAW 与其他色域也不进入该 HDR 编码器。旧存档或 CLI 直接传入参数仍受同一检查。
- 排版/拼图画布的 HDR 当前未实现，由上层阻止，不把普通 SDR 排版输出称为 HDR。
- 当前 Qt 编辑画布及编码打样显示 SDR 基图。HDR 显示器呈现、系统 HDR 开关与第三方阅读器兼容属于另外的显示链，未以本节点宣称通过。

## 实际显影与增益来源

负片印相从本次显影的真实介质参数向 native `spk_session_hdr_curve` 请求曲线，返回 256 点 `log2_gain`、`ks`、`rho` 及 H/域/恢复参数。没有捆绑通用提亮表或遇错替代曲线。参数与来源身份在准备前后核对。

在完成后期、几何与配方缩放的最终 SDR 浮点像素上，用对应色域的线性 Y 求 `own=log2Y`。颗粒残差的中心裁片自相关只用于估计 Gaussian 宽度；增益本身仍逐个最终像素计算。局部亮度 `L=own-clamp(own-Gaussian(own),±tau)`，增益为 `clamp(Ks(L)+kappa*clamp(rho(L),0,rho_max)*(own-L),0,log2H)`。中间浮点工作区按 256 行及滤波 halo 分条；保留全尺寸 mono8 最终图。

未做 Layer 2 后期的正片使用两次真正的光谱显影：SDR 开启 `scan_hdr_stretch`；HDR 关闭 stretch、开启 H 及 `1/H` 输出缩放。两次及基图使用相同非零 `grain_seed=743`。按 ProPhoto 传递函数解码、D50 Y 求亮度比，低于 `1e-4` 的 SDR Y 不放大噪声；实际最大增益限定于 H×1.05 的量化保护范围。映射至与基图相同的旋转、裁切、透视与明确缩放后写入增益 JPEG。RGB 显影先后转换成亮度并释放，避免仅为算比值同时持有两张全尺寸 RGB。

正片若已有亮度、对比、色彩、曲线、蒙版等 Layer 2 调整，使用最终 SDR 图片和其会话曲线，不用调整前的比值重新抬起用户压暗的区域。

## 编码与拍摄信息

`desktop/output.py` 在最终像素渲染/明确缩放之后调用 `prepare_rendition`。返回的 `HDRRendition` 保留同一 SDR 像素，并附带相同尺寸的 mono8 图、H、色域与来源/参数身份；JPEG 分支调用 `encode_jpeg`。编码阶段拒绝丢失的图或尺寸/色域不一致。

原生 C 边界将已经编码的普通基图和 mono JPEG 交给 libultrahdr；gamma=1、offsets=0、capacity min=1/max=H、使用基图色域。零偏移保持胶片黑位。输出分段写入现有原子发布路径，拍摄元数据随后写入临时文件。本轮验证 ExifTool 写 EXIF 后，MPF/增益声明、增益尺寸与独立 HDR 解码结果保持有效。取消与失败不发布半成品。

## 性能边界

这项功能不降低最终分辨率。负片/编辑正片额外取得介质曲线、做全尺寸灰度增益和第二张 JPEG 编码；当前实现重新准备该曲线所需源数据。未编辑正片额外进行两次 native 显影；尚未实现复用刚导出的同一 native 会话完成配对，因此不能称为一次显影或全分辨率亚秒。

增益计算的浮点 scratch 按行带有界，但原图、显影输出、正片亮度平面和编码器仍消耗与尺寸成正比的内存。官方独立解码会分配完整半精度 RGBA，仅供明确验证使用，不在每张大照片常规导出后自动回解码。

## 构建与许可

- `native/hdr/upstream/libultrahdr-2.0.2`：官方 Google libultrahdr v2.0.2 源码；本轮不修改其代码。
- 复用项目既有 libjpeg-turbo 3.1.3 源码。
- `native/hdr/bridge.cpp`：本项目的 owned-memory C ABI；独立 DLL 静态链接运行库及编码依赖。
- PowerShell 7 执行 `native/hdr/build-windows.ps1`，调用 WSL Ubuntu-24.04 的 CMake/Ninja/MinGW/NASM。默认中间目录为 WSL `/var/tmp/spektra-hdr-win`。
- JPEG 维度上限显式设为 65500，移除 libultrahdr 默认 8192 边界；不为 A7CR 或中画幅照片自动缩小。
- 打包必须包含整个 `native/hdr/runtime`：DLL、`UPSTREAM.json` 及 libultrahdr/libjpeg-turbo/image_io/Adobe notice。来源与许可保持在交付源码及运行物中。

## 已执行的关键节点

1. `scripts/verify_hdr_container.py` → `output/hdr-container-review/report.json`：明确标为合成编码 fixture，sRGB/P3 的 ISO+Adobe 双声明、真实增益尺寸、普通基图熵扫描/ICC不变、官方独立 HDR 读回、显示 headroom 响应、EXIF后保持；9564×8 边界证明不受8192宽度截断。它不证明照片光谱效果或大 RAW 性能。
2. `scripts/verify_hdr_session_export.py` → `output/hdr-session-review/report.json`：同一张实际照片的320×213明确小样本，真实Windows Vulkan负片/正片显影、介质变化、正片同seed配对、Layer 2路径、旋转/裁切/透视/配方缩放、P3、EXIF/ICC、官方独立HDR读回、源文件不变、显式代理隔离与取消。全节点7.692秒；新增模式门控后另作仅边界检查，无重复native显影。

以上是源码节点。最终冻结 Windows 发布包的启动与运行组件可用性由发布报告另行记录，不能把本报告自动当作该包完成，也未据此宣称所有第三方 HDR 阅读器、Android 或 Apple 平台均验证。
