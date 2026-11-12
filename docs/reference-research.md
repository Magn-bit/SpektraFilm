# Windows 胶片模拟开发参考

调查日期：2026-11-04。仅核对源码和上游已有验证记录；本文不代表本机已经完成引擎编译、色彩验收或性能测试。

## 取样与本地位置

| 参考 | 固定版本 | 本地目录 |
| --- | --- | --- |
| [andreavolpato/spektrafilm](https://github.com/andreavolpato/spektrafilm) | `3bb2c2d2801ff68b92019cf1dbcbb133d60832bc` | `.reference/spektrafilm` |
| [trouble123456/Film-Simulation](https://github.com/trouble123456/Film-Simulation) | `dc715d94efe75ce88df2e8b411d0c2f1b4479083` | `.reference/film-simulation` |

Windows 仓库顶层实际上只提交说明文件和 `Film-Simulation-src.zip`，README 中的 `engine/`、`windows_UI/` 链接在仓库顶层不存在。已将这份源码包展开至 `.reference/film-simulation/unpacked`，可以在那里查看完整 C++/Vulkan、Qt Quick 和历史 macOS 实现。引用包内文件时，应以[该版本的源码压缩包](https://github.com/trouble123456/Film-Simulation/blob/dc715d94efe75ce88df2e8b411d0c2f1b4479083/Film-Simulation-src.zip)为出处。

## 原项目：以物理模型为基准

Spektrafilm 是 Python 参考实现，处理顺序是输入线性 RGB、光谱重建、胶片曝光、染料密度/成色剂抑制、相纸曝光与显影、扫描。核心是可测量的光谱和密度模型；界面设计不应把它替换成几组随意的 RGB 滤镜。胶片颗粒、光晕、扩散、成色剂、放大机 Y/M 滤色、相纸预闪、扫描锐化等分别拥有明确阶段。[README](https://github.com/andreavolpato/spektrafilm/blob/3bb2c2d2801ff68b92019cf1dbcbb133d60832bc/README.md)、[pipeline.py](https://github.com/andreavolpato/spektrafilm/blob/3bb2c2d2801ff68b92019cf1dbcbb133d60832bc/src/spektrafilm/runtime/pipeline.py)、[params_schema.py](https://github.com/andreavolpato/spektrafilm/blob/3bb2c2d2801ff68b92019cf1dbcbb133d60832bc/src/spektrafilm/runtime/params_schema.py)。

当前三个包分层明确：`spektrafilm` 运行时、`spektrafilm_gui` Qt/napari GUI、`spektrafilm_lut_creator` LUT 工具。运行时不依赖 GUI。[pyproject.toml](https://github.com/andreavolpato/spektrafilm/blob/3bb2c2d2801ff68b92019cf1dbcbb133d60832bc/pyproject.toml)。

README 示例中的 `create_params` 与当前实际导出不一致；代码导出的是 `init_params`、`digest_params`、`simulate`、`simulate_preview`、`Simulator`。正确的当前调用如下，参数由 `simulate` 默认 digest：[__init__.py](https://github.com/andreavolpato/spektrafilm/blob/3bb2c2d2801ff68b92019cf1dbcbb133d60832bc/src/spektrafilm/__init__.py)、[process.py](https://github.com/andreavolpato/spektrafilm/blob/3bb2c2d2801ff68b92019cf1dbcbb133d60832bc/src/spektrafilm/runtime/process.py)。

```python
from spektrafilm import init_params, simulate

params = init_params(film_profile="kodak_portra_400", print_profile="kodak_portra_endura")
result = simulate(linear_rgb, params)
```

Python 项目版本 0.3.4，声明 `requires-python = "~=3.13"`；作者建议使用 3.13。依赖包括 NumPy 2.4、SciPy 1.17、colour-science 0.4.6、Numba 0.64、OpenImageIO 3.1、rawpy 0.26.1、PyFFTW；默认还安装 PySide6/napari 等 GUI 依赖。它适合算法 oracle 和资源烘焙，运行性能与部署体积不适合作为精致桌面首选。[pyproject.toml](https://github.com/andreavolpato/spektrafilm/blob/3bb2c2d2801ff68b92019cf1dbcbb133d60832bc/pyproject.toml)。

可复用数据：28 个 JSON 配置，含负片、反转片及相纸；`src/spektrafilm/data/profiles`、`data/filters/neutral_print_filters.json`、光谱重建数据和 `data/icc`。可复用算法参考：`runtime/stages/`、`model/grain.py`、`model/couplers.py`、`model/develop.py`、`model/diffusion.py`。应固定版本并保留原始数据，避免为了界面观感修改实测曲线。[源码树](https://github.com/andreavolpato/spektrafilm/tree/3bb2c2d2801ff68b92019cf1dbcbb133d60832bc/src/spektrafilm)。

## Windows 参考：可采用的工程基础

源码包 `engine/WINDOWS.md`、`engine/WINDOWS_FEATURE_COVERAGE.md` 和 `windows_UI/README.md` 对实现与限制有较准确的区分。它来自 SpektraLab C++20/Metal 移植链，将 GPU 后端改为 Vulkan，使用 LibRaw 0.22.2 读取 RAW，并提供 C ABI、Win32 最小查看器、Tauri 历史外壳及直接链接 native host 的 Qt Quick 编辑器。[README.zh-CN](https://github.com/trouble123456/Film-Simulation/blob/dc715d94efe75ce88df2e8b411d0c2f1b4479083/README.zh-CN.md)、[完整源码包](https://github.com/trouble123456/Film-Simulation/blob/dc715d94efe75ce88df2e8b411d0c2f1b4479083/Film-Simulation-src.zip)。

最有价值的复用边界：

| 模块 | 包内位置 | 用途 |
| --- | --- | --- |
| C++20 物理管线与 Vulkan kernels | `engine/src`、`engine/shaders`、`engine/include` | 保持真实胶片/相纸模型 |
| 预烘焙光谱常量与配置 | `engine/resources` | 构建时无需 Python |
| 桌面会话与 RAW host | `engine/src/desktop` | 单一 GPU 所有者、不可变结果、缓存重印 |
| Qt 控制器 | `windows_UI/src/PreviewController.*` | 文件队列、编辑、撤销、渲染合并、导出 |
| 编辑持久化 | `windows_UI/src/EditStore.*` | 本地 AppData 保存；不改原图 |
| 图像桥接与几何 | `windows_UI/src/FrameCanvas.*`、`FrameOutput.*` | QSG 纹理、物理 100%、裁剪/旋转/导出 |
| 可替换界面层 | `windows_UI/qml` | 重新设计 Apple 风格界面和动效 |
| 构建与依赖锁定 | `windows_UI/setup-qt.ps1`、`build.ps1`、`dependencies` | 固定官方 Qt 包和许可证校验 |

已有 Qt Quick 功能：多 RAW 导入与拖放、每图独立胶片/相纸/曝光/颗粒/光晕/画幅、导航器、缩略图条、裁剪比例与旋转/翻转/拉直、JPEG8/PNG8/PNG16/TIFF16 导出及批量导出、设置同步、每图 64 步撤销/重做、持久化。渲染用一个串行 worker，180 ms 合并参数更新，旧请求结果不能覆盖新状态；导出使用已经显示的不可变帧。反转片直接扫描，禁用不适用的相纸参数。以上依据包内 `windows_UI/README.md` 与实际 `PreviewController.hpp/.cpp`，不包含本机重新验收。

构建依赖：Windows x64、CMake >=3.22（Qt 层）、C++20、Qt >=6.8；作者固定验收 Qt 6.11.3 与 MinGW 13.1。Qt 官方 SDK 下载约 278 MB，不能混用之前后端 GCC 15.2 产物。还需 Vulkan headers、loader、`glslangValidator` 与 LibRaw 源码；驱动提供运行期 Vulkan。`windows_UI` 直接链接 `spk_desktop_host`，运行时不需 Python/Node/browser 或子进程渲染器。依据包内 `windows_UI/CMakeLists.txt`、`windows_UI/README.md`、`engine/WINDOWS.md`。

Windows C ABI 的 `spk_result.rgba16` 是独立拥有的 CPU RGBA16；`texture` 是所有权 handle，**不是可直接绘制的 VkImage**。必须遵守 stride 并调用 `spk_result_free`。目前每节点 flush 和显式同步是内存正确性的组成部分，不能为了动画帧率随意移除。依据包内 `engine/WINDOWS.md`。

## 前端建议

推荐 **Qt Quick/QML + C++20 + Vulkan 物理引擎**，UI 默认使用 Qt RHI 对 Windows 的 Direct3D 路线，计算后端仍用 Vulkan；界面与计算 API 不必绑定。理由是 Qt 已有直接 C++ 集成、成熟 scene graph、声明式状态/过渡、可定制控件与弹簧动画，并能直接复用正确的会话、导出和图像所有权边界。[Qt Quick Scene Graph 官方说明](https://doc.qt.io/qt-6/qtquick-visualcanvas-scenegraph.html)说明其 Windows Direct3D 11 threaded renderer 与原生图形整合方式。

Apple 是设计参考：克制层级、低饱和中性工作台、局部材质、明确操作、精确阴影、短而有因果的状态过渡。应保留 Windows 文件对话框、键盘和标题栏习惯，无需制作假的 macOS 交通灯。高频滑杆只动控件及数值，图像渲染异步合并；不可将 CPU/GPU 计算放在 UI 线程来“追求动画”。

若不用 C++ 工具链，PySide6/QML + 原 Python 引擎是算法一致性更直接的备选，但科学依赖、打包体积与全尺寸交互成本更高。Tauri/Electron 方便 Web UI，却增加浏览器边界和图像复制，现有 native host 可直接链接时收益较少。WinUI 3 有 Windows 原生能力，但需要重写引擎桥接/画布和现有会话边界；本任务没有证据表明这份额外工作比 Qt 更有价值。此段为基于本项目结构的工程判断。

## 必须准确表达的能力边界

Windows 上游记录 34 kernels、16 CTests、47 Python 工具测试，验收硬件 RTX 5070 Ti；这些不是本机测试结果。MSVC、其他 GPU、更多相机、全图 Metal/Python parity 尚未完成同等级验证。历史 32.95 MP 首次 871 ms、warm 229 ms、缓存重印 67 ms 仅为该机完整 render-call，排除了 RAW 解码/引擎创建/上传/写文件，不能照搬到宣传。依据包内 `engine/WINDOWS.md`。

Windows Qt 层导出固定 sRGB + ICC；校准显示器、HDR、多显示器验收未完成。LibRaw 对 Nikon HE/HE* 明确拒绝。片边、日期后背、contrast mask、scene latitude mapping 等后续 macOS 功能并未全部移植，不能因为中文 README 展示了它们就当作 Windows 可用。依据包内 `engine/WINDOWS_FEATURE_COVERAGE.md`。

胶片曝光补偿改变负片曲线位置，默认打印补偿会抵消中灰亮度变化；打印曝光才控制成片明暗。UI 必须区分“胶片曝光”和“印相亮度”。依据包内 `AGENTS.md` trap 30，以及原 Python `CameraParams`/`EnlargerParams`。

## 许可证与署名

原项目代码为 GPLv3，Windows 项目声明应用/引擎 GPL-3.0-or-later；采用其代码开发时应保留许可和作者说明，并将衍生应用按相容许可分发。配置与 LUT 为 CC BY-SA 4.0，需保留 Andrea Volpato、canonical repo、许可及修改说明。[上游 LICENSE](https://github.com/andreavolpato/spektrafilm/blob/3bb2c2d2801ff68b92019cf1dbcbb133d60832bc/LICENSE)、[资源许可证完整文本](https://github.com/andreavolpato/spektrafilm/blob/3bb2c2d2801ff68b92019cf1dbcbb133d60832bc/SPEKTRAFILM_LICENSE.txt)、[Windows README](https://github.com/trouble123456/Film-Simulation/blob/dc715d94efe75ce88df2e8b411d0c2f1b4479083/README.zh-CN.md)。

原 README 仍有一句旧的 LUT “no resale custom license” 描述，但当前完整资源许可证明确以 CC BY-SA 4.0 为法律许可，“不单独售卖 LUT 包”等列于额外倡议而非法律要求。实现时保留完整原文，不自行拼装新许可。商标和应用命名也应与事实署名区分；本项目可以使用独立产品名，并在 About 中写 “Film modeling powered by spektrafilm by Andrea Volpato”。
