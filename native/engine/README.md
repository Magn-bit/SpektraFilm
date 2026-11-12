# 原生完整光谱引擎

SpektraFilm 的 Windows 完整光谱模式使用本目录 C++20 / Vulkan 引擎；输入 float32，显影输出实际 RGBA16，Python 桥接不经过 RGB8。最终尺寸校验失败会停止导出。原生失败不会在桥接内改用 LUT。显式 CPU 兼容模式仍由应用选择。

来源固定为 [JamesQiu2005/SpektraLab](https://github.com/JamesQiu2005/SpektraLab)，commit `2ca735ad60a998e925bf346f57d80012bdb5c6bf`（`windows-v1.3.4-beta.2`）。来源记录在 `UPSTREAM.json`。原始引擎、shader、生成资源及所需第三方源码保存在 `upstream/`；GPL-3.0 文本在 `upstream/license/LICENSE`。Andrea Volpato 的 spektrafilm 光谱材料、常数与直接衍生数据保留 CC BY-SA 4.0 及 `SPEKTRAFILM_LICENSE.txt` 署名。产品黑白资料和数据假设保留 `resources_product/NOTICE.md` 及 profile metadata；不能称为胶卷制造商提供的完整实测模型。

## 重建

在 Windows PowerShell 运行 `./native/engine/build-windows.ps1`。默认 WSL 发行版为 Ubuntu-24.04，需要 `cmake ninja-build g++-mingw-w64-x86-64-posix glslang-tools libvulkan-dev`。可用 `-Distribution` 指定另一个已配置的发行版。Windows 安装程序不依赖 WSL；WSL 仅负责可重建交叉编译。

输出为 `runtime/spektrafilm_engine.dll` 和 `runtime/resources/`。DLL 静态链接 MinGW C++/线程运行时，仅动态加载系统显卡的 Vulkan loader。CMake 预编译全部 GLSL 成 SPIR-V。资源先复制原版，再叠加产品黑白、相纸、neutral-filter 数据和当前 vendor 扩展 profile；不改写保存的原版数据。`runtime` 必须整体进入成品，源码及各自许可随项目保留。

本地补丁仅包括：外层 CMake/MinGW 工具链与静态运行时链接；参数 wire 开放颗粒面积、均匀度、模糊、数据库滤色开关和眩光百分比；Android Vulkan loader 的无版本后缀分支。参数新增的 Shoot/Print 分类同时决定负片缓存失效，未绕开科学计算。

## 调用与缓存

ABI 见 `include/spektrafilm/spk_engine.h`，应用约定见 `contract.json`。Windows 入口为 `desktop.native_spectral.render_spectral`，共享引擎调用串行，session 按稳定源标识保存。负片可用于重印；相纸/印相变化调用 `spk_reprint`，只有负片缺失或 Shoot 参数失效时开发。`spk_render` 的语义是强制重新开发，不能用于每次滑块更新。

预览和成品的源标识分开，完整导出始终 `full`。大图启用引擎带状阶段执行；空间算子的 halo 在连续阶段相加，完整帧统计节点与颗粒按原图上下文保留。带状执行仍保存原图/负片完整平面，不能当作手机有界 IO 的替代。

`cancel_active()` 可从别的线程取消节点边界上的工作；不保证能中断已经提交的单个 GPU kernel。需要在上层继续丢弃过期 generation，防止旧预览覆盖新参数。

## 证据与边界

`verify_native.py` 是单次定向检查，结果存于 `output/native-spectral-0.4.0.json`。真实 RTX 3070 Ti Laptop 上，Sony A7CR 9564×6376 的原尺寸 float32 输入，完整谱和读回 C ABI 1.676 秒，桥接处理 2.291 秒，RAW 解码 2.169 秒。以上不含 JPEG/TIFF 编码与写盘；不是手机时间，也不是通用“不到一秒”承诺。源 SHA256 前后相同。

渐变保留 2039 级，排除了 RGB8 中间量化；印相变化和显式换纸真实生效且复用负片。4 款黑白材料输出有限且中性，最大通道差低于 .00049。精度验证不等于所有光谱公式已与 Python 逐像素对齐；上游 halation 面积、CAM16 数值和随机颗粒等部分有模型差异。当前报告的 Vulkan 数学模式也明确标注 full shader parity pending。

定向空间检查在含边缘高光的画面上对照全帧与 64 行带状执行（多于 3 条带），颗粒/眩光关闭以排除随机变量；结果最大差为 0。眩光 5% 的输出平均变化 .0838，细小颗粒与粗大颗粒的灰场标准差分别 .00990/.02506，确认控制参数真实进入模型。没有另跑大图来重复证明这些字段。

当前源显影为 LibRaw 自然 RGB16。float32 边界不代表已经保留 RAW 未裁切高光、原生负值或广色域 headroom；此项不能包装为 Capture One/Lightroom 算法复原。上游 `contrast_mask` 在此 Vulkan 构建不支持且会明确拒绝。Android 使用同源核心但需其独立 JNI/资源与实机验收；Windows 测速不能替代它。
