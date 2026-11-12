# 构建 SpektraFilm

下载即用的成品在 [GitHub Releases](https://github.com/Magn-bit/SpektraFilm/releases)。以下工具只供开发，不是运行便携版的前提。

## Windows

- Windows x64、Python 3.12、PowerShell 7（`pwsh.exe`）。
- 支持 Vulkan 的显卡及驱动。
- 构建原生引擎需要 WSL / Ubuntu、CMake、Ninja、MinGW POSIX、Vulkan headers 和 glslang-tools；HDR 编码组件另需 NASM。

```powershell
git clone https://github.com/Magn-bit/SpektraFilm.git
cd SpektraFilm
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

按对应组件的说明准备工具链并生成运行时：

```powershell
./native/engine/build-windows.ps1
./native/library/build-windows.ps1
$colorBuild = (wsl.exe -d Ubuntu-24.04 -- wslpath -u "$PWD/native/color/build-windows.sh").Trim()
wsl.exe -d Ubuntu-24.04 -- bash $colorBuild
./native/hdr/build-windows.ps1
.venv/Scripts/python.exe scripts/install_metadata_runtime.py
```

`native/engine/build-windows.ps1` 同时构建光谱引擎和 LibRaw RAW 组件；色彩组件在 WSL 中生成 LittleCMS DLL。以上使用已配置的 Ubuntu-24.04，其他发行版请同步替换参数。依赖说明见 [原生引擎](../native/engine/README.md) 及相邻构建脚本。仓库保留源码与资源，DLL、EXE、编译缓存不进入 Git 历史。

源码运行与打包：

```powershell
./run.ps1
./scripts/build-windows.ps1 -Destination dist/windows -WorkDirectory build/windows
```

打包脚本会检查所需的原生运行时；缺少组件时先完成相应构建。发布时保留整个程序目录及 `_internal`，不能只复制启动 EXE。

## Android

使用 JDK 21、Gradle 8.13、Android SDK 35、NDK 27.2.12479018 和 CMake 3.22.1。设置 `JAVA_HOME` 后，向脚本提供本机工具路径：

```powershell
./android/build.ps1 -GradlePath <gradle.bat> -SdkPath <Android-SDK>
```

当前分支包含后续开发代码，不能保证其生成结果与已发布的 0.5.0 APK 完全相同。复现该 APK 请使用 Releases 中单独提供的 **0.5.0 对应源码包**，保留其构建输入和许可。正式分发需自行管理签名，不要将 keystore、密码或 `local.properties` 提交到仓库。

## 验证与资源

仅运行与改动直接相关的关键节点检查。UI 文档截图可用 `scripts/capture_product_screenshots.py --photo <已授权照片路径>` 重新生成；省略照片参数时下载公有领域备选照片。它运行当前真实界面，结果不能替代 RAW 压力或成品导出验收。

第三方来源与可重建输入位于 `licenses/`、`native/` 及 [THIRD-PARTY.md](../licenses/THIRD-PARTY.md)。macOS / iOS 当前无可验证产物，不应将 Windows 构建步骤视为 Apple 平台交付。
