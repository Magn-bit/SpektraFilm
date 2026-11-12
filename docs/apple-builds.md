# Apple 平台构建状态

2026-11-07 更新：用户重新要求后续 macOS。共享 GPU 计算选定 wgpu-native/WGSL，macOS 目标后端为 Metal；Windows 已验证并接入的仅是 CAM16-UCS 输出色域阶段，完整曝光、显影、颗粒、印相原生化仍在开发。打包脚本已准备 wgpu 的原生库与头文件收集，但当前不在 macOS 启用未经验证的 GPU。没有 Mac/Xcode，尚无 Metal 编译、Apple Silicon 测速或 macOS 发布物；iOS 保持暂停。

2026-11-05：当前开发主机为 Windows，用户确认暂时没有 Mac。Swift 6.4.2 Windows 工具链已安装，但它的目标为 `x86_64-unknown-windows-msvc`；当前没有 MSVC C++ 工具链、Xcode 或 Apple SDK。当前未生成或验证 macOS `.app`、iOS `.ipa`。Windows 版 Swift 不能替代 Apple SDK，也不能构建 Apple 二进制。

## macOS

现有桌面端为 Python / Qt Quick，完整光谱内核和共享资源可以作为 macOS 移植的基础。Windows 原生拖放、窗口还原和系统动画设置已有平台保护。新字体资源也不依赖 Windows 系统字体。

scripts/build_macos.py 提供原生 macOS 构建入口。--check 只检查环境，不编译；实际构建必须在 Mac 上使用原生 Python 3.12 环境，先安装 requirements.txt 与 PyInstaller。运行构建脚本后，在 dist/macos/实际架构/SpektraFilm.app 生成候选，并默认执行隔离的完整光谱预览检查。

脚本只生成宿主原生架构，不声称 universal2。当前没有在 Mac 执行，Python 原生依赖、Qt 包资源、圆角、窗口记忆、照片拖放和完整光谱速度仍需在 Mac 上验证。没有 Developer ID 签名或公证，不作为已验收的 macOS 发布包。

下一步需要一台 Mac，或用户明确授权的 macOS 构建服务。之后可使用现有脚本从共享桌面代码构建并验收；本轮没有上传源码或触发外部付费构建。

## iOS

当前仓库没有 iOS/Xcode 工程。Android 的 Kotlin/Chaquopy 程序不能直接转换成 iOS 软件；现有 Python 科学内核的 NumPy、SciPy、scikit-image 等原生依赖，也不能使用 macOS 动态库替代 iOS 依赖。需先选择 iOS 可维护的完整光谱内核移植方案，再实现原生照片导入、显影交互和导出界面。

iOS 尚需完成原生界面、照片与文件授权、原版完整光谱内核及依赖的设备端移植，再建立 Xcode 工程，做模拟器与真机验收。不得用 LUT 替身或无功能界面声称已经移植完整光谱。

中文朱雀仿宋 / 英文与数字 Noto Serif SC 的组合字形、色彩、字阶和交互规范可共享；尚无可安装的 iOS 成品。后续 iOS 工程还需要在 Mac 上使用 Xcode 编译，并为真机安装配置签名和设备。
