# 引擎选型

Windows 使用 Qt Quick/QML + PySide6，科学计算采用上游 Python 内核；Android 使用原生 Kotlin 和专用 Canvas 照片视图。当前不更换架构。

| 候选 | 交付与系统集成 | 动效原语 | 体积/启动与响应 | SSR/水合 | 维护与科学管线 |
| --- | --- | --- | --- | --- | --- |
| Qt Quick/QML | Windows 原生窗口，独立可执行目录 | 状态、Transition、Behavior、场景图合成 | 需附带 Qt 与 Python 科学依赖；以实际构建测量为准 | 不适用 | 可直接复用上游 Python；QML 与后台任务接口清楚 |
| WinUI 3 | Windows 桌面，系统集成强 | Composition、Storyboard | UI 运行时与科学子进程体积均需计入，待测 | 不适用 | 需额外维护 .NET/C++ 与 Python 的跨进程科学边界 |
| Flutter | 桌面/移动二进制，自绘控件 | AnimationController、Tween、合成层 | 引擎与独立科学运行时均需打包，待测 | 原生不适用 | 同一 UI 可共享，但原版 Python 集成和桌面窗口仍需桥接 |
| React + Electron | Chromium + Node 桌面容器 | CSS/Web Animations，可配动效库 | Chromium 与科学运行时同时存在，待测 | 本地暗房没有首屏 SEO 需要，水合收益有限 | 可复用 Web 组件，但引入 DOM/IPC/Python 三层运行时 |
| Android 原生 Kotlin | 手机 APK、SAF 文件和系统返回集成 | ViewPropertyAnimator、系统属性动画 | 共享 LUT，无完整 Python 科学运行时；APK 见构建记录 | 不适用 | 原生文件与内存控制直接；两端 UI 各自适配 |

Qt Quick 让照片画布、精密控件与自定义窗口用同一场景图实现，并直接复用实际科学代码，减少跨运行时传图和参数协议。动效使用 QML 原生属性动画，数值处理使用单线程后台任务，界面合并高频更新并拒绝过期结果。

没有选择流行的 React/Electron，原因是当前本地照片暗房没有 Web 内容与 SSR 的主要需求，叠加 Chromium 和科学进程会增加运行时、数据传递和打包边界。WinUI 与 Flutter 可行，但都需额外适配现有 Python 科学管线；当前收益不足以抵消重做成本。

Android 使用共享来源的 LUT，不能宣传为桌面完整光谱运行时。界面颜色、字体角色和参数语义统一，布局与系统交互分开实现。

实际安装体积、启动、预览与导出验证以 docs/validation.md 和 output 下的测量记录为准；表格没有推测性能数字。
