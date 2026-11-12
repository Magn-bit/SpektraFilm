# 跨平台完整光谱 GPU 引擎决策

日期：2026-11-07

## 目标

将现有 SpektraFilm 完整光谱模型迁入编译的原生 GPU 管线，覆盖 Windows、Android 和后续 macOS。性能优化不能改成 LUT 最终输出，不能减少原片像素，也不能以输出变模糊换速度。界面只消费代理图和结果帧；图像计算、资源驻留和高分辨率编码在原生层完成。

## 选型

| 候选 | Windows | Android | macOS | 主要优点 | 主要代价 | 结论 |
|---|---|---|---|---|---|---|
| wgpu-native + WGSL | D3D12 或 Vulkan | Vulkan | Metal | 一套 compute shader 与 C ABI，映射到各平台原生 GPU；适合从现有 Python / Kotlin 热路径接入 | Rust/wgpu 构建链、WGSL 能力边界、GPU 读回和分带设计仍需工程化；性能必须逐机验证 | 选用 |
| Dawn + WGSL | D3D12 或 Vulkan | Vulkan | Metal | C++ WebGPU API，浏览器生态和 C++ 接入直接 | Dawn 当前支持文档把 Android Vulkan 标为 work in progress，给移动主目标增加风险 | 不选 |
| 手写 D3D12 + Vulkan + Metal | D3D12 | Vulkan | Metal | 每个平台最直接的 API 控制与最低抽象成本 | 三套 shader/同步/资源管理，长期容易出现物理公式和边界行为漂移，验证成本最高 | 不作为首选 |

依据 wgpu-native 当前文档的支持矩阵，Windows 10+ 支持 DX12/Vulkan，Android 支持 Vulkan，macOS/iOS 支持 Metal。Windows 本机对照后显式选择 Vulkan；Android Vulkan、macOS Metal 仍为计划，不能把库的支持矩阵等同于本项目已完成移植。单一 WGSL 维护科学算法，设备 API 由 wgpu-native 执行。

这一选型优先控制跨平台公式一致性和维护成本。当前已有 Windows 密度插值与 CAM16-UCS 色域阶段的 wgpu 实测，不能据此宣称整个应用快于每个平台的手写 API。CAM16 fixture 中 Vulkan 数值误差小于 D3D12，24MP 阶段中位数约 345ms 对 375ms；这包含上传、派发、读回，不含其他光谱阶段、RAW 与编码。完整边界、数值和打包记录见 [GPU 阶段验收](../native/docs/gpu-stage-validation.md)。如果 GPU API/驱动不满足正确性或稳定性门槛，应以证据修正后端选择。

## 现状基线

本机 SpektraFilm 24MP CPU 全光谱基线为 6000×4000、64.622 秒、峰值工作集 5983.9 MiB；filming exposure 13.692 秒、film develop 28.651 秒、print exposure 2.635 秒、print develop 0.207 秒、scan print 18.728 秒。报告：[`perf-baseline-20261107-current-host-cpu.json`](../output/perf-baseline-20261107-current-host-cpu.json)。这条路径不调用 GPU。用户确认真实显卡为 RTX 3070 Ti；OS 枚举到的 RTX 5090 不准确，不能作硬件凭证。

SpektraLab 的不同硬件、不同胶片模型与不同计时范围只作为架构证据。其 Windows Vulkan 在 RTX 5070 Ti 的 32.95MP 记录：首次完整渲染 871ms、warm full 229ms、cached reprint 66.7ms；不含 RAW、建引擎、source upload 和编码。Android 社区移植在 SM8735/Adreno 825 的 16.5MP full render 记录约 8.2 秒。macOS 的 45MP 宣传值与源码里 full export、cache reprint 不同口径，不能拼成一个速度结论。

## 处理边界

同一套 GPU pipeline 继续使用当前 SpektraFilm 的曝光、光谱上采样、显影/DIR、胶片颗粒、相纸印相、扫描和色域转换。当前阶段 tap 可用于缓存与重算：`rgb_pre`、`log_e_film`、`cmy_film`、`log_e_print`、`cmy_print`、`rgb_out`。缓存必须依据输入版本与参数依赖失效，不能仅用胶片名称做 key。

全分辨率输入不要求同时将整张图的每个中间面常驻显存。对大图采用有界行带、复用 GPU scratch、支持 halo 的空间滤波，并把最终像素流送入 JPEG/TIFF encoder。预览可使用明确尺寸的代理图；最终尺寸始终等于源像素尺寸。Android 移除全光谱路径中的 Bitmap/ByteArray/Python 往返；Windows 与 macOS 通过进程内原生 ABI 传入解码后像素。

## 迁移顺序

1. 冻结 CPU reference 与黄金样片，分别计量 RAW、每个 tap、encoder、磁盘和 peak memory。
2. 用 wgpu-native 建立最小 GPU device / buffer / WGSL pipeline，验证 Windows D3D12 和纹理/存储 buffer 尺寸限制。
3. 先迁移曝光及 density curve interpolation 等逐像素阶段，验证 shader 与 CPU 输出，再处理空间滤波、DIR、颗粒和 spectral scan。
4. 让负片和可复用中间状态留在 GPU；参数变化按依赖关系重跑最短阶段，最新任务覆盖旧任务，不让拖动队列堆积。
5. 增加有 halo 的行带调度与直接块编码；对图像各分辨率测时、显存、系统内存和接缝误差。
6. 共享 WGSL 与 C ABI 接入 Android JNI，单独测真实设备和热降频；相同核心接入 macOS Metal，在 Apple Silicon 上编译和实测。

## 正确性与性能门槛

- 不降源尺寸；JPG/TIFF 解码回读尺寸完全等于源尺寸，RAW 原片复制 hash 不变。
- 将 Python CPU 作为阶段参考。逐阶段检查最大/均值绝对误差和最终 ΔE00；最终 RGB8 不能掩盖中间高光、暗部或高饱和误差。
- 对颗粒固定种子回归均值、RMS、频谱功率与空间相关性；如果需要改变随机实现，按版本记录，不以一张随机图主观判定通过。
- 行带边界与整幅参考结果比较；对空间滤波严查 halo、递归长尾和首末行处理。接缝错误、内存越界或未定义的精度退化均阻止发布。
- 预览延迟、完整光谱计算、阶段缓存命中、RAW decode、GPU readback、编码、写盘分别计时。用真实 RTX 3070 Ti、各目标 Android 设备和 Apple Silicon 分平台记录硬件、驱动、图像、参数、像素尺寸、GPU/CPU峰值与持续负载。
- 第一阶段不承诺某个普适毫秒值。GPU 原型通过数值与稳定性门槛后，再以同机真实测量设定交互与全分辨率发布目标。

## 未完成项

Windows 开发代码已为默认 linear sRGB / CAM16-UCS 输出色域阶段接入可选 Vulkan 计算，保留其他规格与不可用设备的 CPU reference。密度插值等原型尚不等于完整原生光谱管线；最终性能需要整条应用路径实测和冻结包验收。Android 没有连接真机，macOS 没有 Mac/Xcode；尚无移动 GPU 实测、Metal 编译、Apple Silicon 验收，也没有全分辨率全管线不到一秒的承诺。大图临时 GPU buffer 已按条带限制。61MP A7CR 修正 RAW 亮度后的全链导出实测262.636秒、peak13057.9MiB（伴随C1和反汇编活动，不作严格速度对照）；100MP与空间滤波halo验收仍未完成。报告：`output/raw-film-0.3.4-a7cr-brightness-fixed/report.json`。
