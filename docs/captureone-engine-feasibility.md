# Capture One Windows 真实引擎接入可行性

核查日期：2026-11-06。范围：官方公开文档、本机安装资源和 Windows 文件关联的只读检查。没有启动 Capture One，没有执行导入或导出，没有修改 Session、Catalog、首选项或生产代码，没有加载、注入、抽取或复制其闭源引擎模块。

## 结论

**本机有 Capture One 16.8.6.3784，但目前没有证据支持把它直接接成“Windows 后台 CLI/API：输入任意照片 + `.costyle` → 输出成片”的受支持引擎。** 能确认的是打开文档、导入文件的 Windows 入口，以及应用内应用 Style、按 Export Recipe 真正渲染的工作流。若接受运行已安装并有有效许可的 Capture One GUI，可以做桥接原型；这需要单独验证窗口状态、Style、导出完成信号和错误恢复，不能称为已可用的无界面 SDK。[S1–S7]

不能笼统说“SDK 仅支持插件或相机联机”：**Phase One 另有真正能转换并导出图像的 ImageSDK**，但其官方输入范围为 Phase One IIQ，公开文档没有 `.costyle` 应用接口，也没有承诺与 Capture One 全部工具或成片一致。因此它不适用于用户的 Sony ARW，也不能作为本项目通用照片处理的 Capture One 替代入口。[S8–S12]

## 已确认能力与边界

| 路线 | 已有证据 | 对本项目的判断 |
| --- | --- | --- |
| Windows 文档打开 | 本机 Session/Catalog 文件关联调用 `CaptureOne.exe "%1"` | 可作为启动/打开入口；本次未运行验证 |
| Windows 导入 | 本机文件关联注册了 `CaptureOne.exe /IMPORT %1` | 能确认注册的导入入口；不含 Style、Recipe 或输出参数 |
| Windows 完整渲染 CLI | 官方帮助中心未检索到该 CLI 的参数契约；本机未发现面向开发者的 CLI 帮助手册 | 不能虚构 `/style`、`/export`、`--headless` 等参数，也不能断言所有未公开参数都不存在 |
| Capture One 插件 SDK | 官方开发页提供 SDK、API 文档、macOS/Windows sample；用户手册描述发布和外部编辑插件 | 确认的是扩展 Capture One 的插件体系；尚未证明可从外部程序调用任意内置调节、Style 和 Export |
| macOS AppleScript/JXA | 官方明确写作 “Capture One for macOS supports AppleScript” | 是另一系统的有效自动化路线，不能当成本机 Windows 能力 |
| Studio/Enterprise Actions | 应用内通过批准的 Connector 把图像交给外部服务，再带回 Session | 不是公开的 Capture One 本地渲染服务 API；需要特定方案及 Actions 授权 |
| Phase One CameraSDK | 控制相机属性、触发拍摄、接收图像和 Live View | 不提供通用 C1 Style 渲染 |
| Phase One ImageSDK | Windows C++/C#，IIQ → Convert → Bitmap → TIFF/JPEG 等 | 是真实处理 SDK，但输入/工具/Style 范围不符合通用 Capture One 引擎需求 |

## 本机安装证据

| 项目 | 只读检查结果 |
| --- | --- |
| 安装入口 | `C:\Program Files\Capture One\Capture One\CaptureOne.exe` |
| EXE FileVersion | `16.8.6.3784` |
| ProductName / CompanyName | `Capture One` / `Capture One` |
| EXE SHA-256 | `3C4BB1346E3C70BD75B93EEA0551DD44FA01A41441105AE7ED1C40EBCD0064A1` |
| 本机插件清单 | `C:\Program Files\Capture One\Capture One\Plugins\OpenWith\manifest.xml` |
| 本机插件说明 | `Allows to select and use applications installed on the computer in order to open files from Capture One` |
| 核心致谢文件 | `C:\Program Files\Capture One\Capture One\ICSDK_Credits.txt`，开头标为 `Capture One Image Core SDK by Capture One A/S.` |
| 已见内部程序 | `ImgCoreProcess.exe`、`PluginHost\P1.C1.PluginHostProcess.exe` 等，仅记录存在，未执行 |

已安装程序中的核心 DLL、内部 helper 和 `ICSDK_Credits.txt` 不能证明对第三方开放了可重分发的 SDK，也不能证明公开 Phase One ImageSDK 与该核心具有相同 API 或输出。安装目录包含 `Enterprise`、`CulturalHeritage` 工作区同样不能证明当前账号获得相应许可。**本次没有核查或宣称本机已激活哪种产品方案。**

安装树没有检出 `.chm`、`.pdf` 开发者手册；检出的 HTML 是 CapturePilotWeb/ContactSheetWeb 页面。未找到本机公开开发包不能证明官方没有另行提供的开发包。[S3]

## Windows 可复核的调用路径

以下是读取本机注册表得到的原值，属于文件关联证据，尚不是运行成功证据：

```text
HKLM\SOFTWARE\Classes\CaptureOneCatalog\shell\open\command
"C:\Program Files\Capture One\Capture One\CaptureOne.exe" "%1"

HKLM\SOFTWARE\Classes\CaptureOneSession\shell\open\command
"C:\Program Files\Capture One\Capture One\CaptureOne.exe" "%1"

HKLM\SOFTWARE\Classes\CaptureOne.CaptureOne16\shell\import\command
C:\Program Files\Capture One\Capture One\CaptureOne.exe /IMPORT %1

HKLM\SOFTWARE\Classes\captureone\shell\open\command
"C:\Program Files\Capture One\Capture One\CaptureOne.exe" /CustomProtocol "%1"
```

这足以确定 `/IMPORT` 是本机正式注册的入口，且打开 Session/Catalog 不需要猜测参数；`/CustomProtocol` 仅证明注册了 URL handler，不能推导其 URL 语法、处理权限或具有导出能力。

未来如要验证导入，可按这个参数形状调用；下列是**未执行的示意**，输入路径需替换成专用测试文件：

```powershell
& 'C:\Program Files\Capture One\Capture One\CaptureOne.exe' '/IMPORT' 'D:\C1-Bridge-Test\input.nef'
```

本机注册值没有接受 Style、导出路径、Recipe 或完成回调的参数。官方帮助中心的精确检索 `"command line"` / `"command-line"` 只返回驱动删除与网络地址查询文章，未返回 Capture One 渲染 CLI 说明。这是本次搜索的边界，不能把“未找到文档”升级为“所有版本绝对不支持任何其他命令行功能”。[S13]

## 真正能应用 Style 并渲染的现有路径

官方文档给出下列应用内流程，两平台的图像处理工具均可用：[S1、S4–S7]

1. 在专用 Session 中导入/定位原图。Import 的 Adjustments 工具可选择 Styles/Presets，也可选择是否带入已有调整。
2. 在 Styles and Presets 工具应用 Style，或为常用 Style 绑定自定义键盘快捷键。
3. 选择 Export Recipe，确定文件格式、尺寸、ICC profile、输出位置及命名。
4. 通过 Exporter 导出；已配置时，Windows `Ctrl+D` 对选中照片使用上一次的 Export Recipes，跳过 Exporter 窗口。
5. Capture One 按保存的调整生成新的输出图像，应用其真实处理引擎。

其中 `Open With` 会把原文件交给外部应用，**不包含 Capture One 调整**；`Edit With` 才会先在 Capture One 中处理出 JPEG/TIFF/PSD，再交给目标应用。不能把 `Open With` 的原文件传递误记为真实 C1 成片。[S5、S6]

此路径可支持“外部程序准备任务 → Capture One GUI 应用 Style/导出 → 外部程序接收导出文件”的原型。它仍需真实验收：专用 Session 是否正确打开、选中照片是否唯一、Style 是否重复叠加、Recipe/ICC 是否准确、何时算导出完成、弹窗和授权失败如何报告。**这项研究没有执行该闭环，也没有提交 C1 后端实现。**

## 三类 SDK / 自动化入口不可混同

### Capture One 插件 SDK

官方开发者入口是 [Capture One Developer Portal][S3]，列出 Tutorials、API documentation、macOS/Windows sample projects，并导向 Developer signup。官方用户手册把插件分成发布到图库/社交服务与外部编辑/打开两类；后者由应用内 `Image → Edit With → Plugin` 或 `Open With → Plugin` 触发。[S2、S3]

因此，有插件 SDK 不等于有一个可嵌入 SpektraFilm、在程序外调用的 Capture One RAW 渲染 SDK。当前可公开读取的页面没有提供本项目所需的 `applyStyle(input, style)` / `export(recipe, output)` 外部调用契约。Developer signup 页本次被站点 JavaScript/cookie 验证拦截，未进入账号、注册或获取受限开发包；不能替未读的 SDK 文档下绝对结论。

若未来由官方提供插件开发包，应首先核对它是否真的允许创建/控制 Variant、应用指定 Style、触发 Export 并可靠取得完成事件，以及 Windows 和产品方案要求。取得这些证据以前，不应围绕推测的方法名实现适配器。

### Phase One CameraSDK 与 ImageSDK

Phase One 官方明确把两者分开且允许独立使用：CameraSDK 控制相机；ImageSDK 读取已拍摄图像，进行解码、转换、裁剪、缩放及写入 TIFF 等。[S8]

ImageSDK 的有效 Windows 路线确实存在。官方 C# 示例先设置 SensorProfiles 目录，然后：

```text
P1.ImageSdk.RawImage("input-file.iiq")
  → ConvertConfig
  → RawImage.Convert(config)
  → RawImage.WriteAsTiff("output-file.tiff", bitmap, tiffConfig)
```

该示例要求独立下载的正式 SDK，引用 `ImageSdkCs.dll`，并配套 `ImageSdkCBindingsForCs.dll` 等官方 SDK 依赖，不是从 Capture One 安装目录复制内部 DLL。官方 Windows 文档写明 .NET Standard 2.0、Windows x64 和相应 MSVC runtime；C++ 也有官方示例。下载页在本次核查时列出 CameraSDK 3.2.5、ImageSDK 4.1。[S9、S12]

其硬限制是：[S10、S11]

- `Open Image` 明确：`The ImageSDK accepts images in the IIQ format`。没有公开证据支持将 JPEG、普通 TIFF、NEF、CR3、ARW 等当作它的通用输入。
- Convert 依赖 Phase One 传感器 SensorProfiles；找不到对应 profile 会报 `Unsupported sensor`。
- 可以配置曝光、曲线、白平衡、锐化、降噪等，不代表覆盖 Capture One 的全部工具、图层、蒙版和 Style；本次阅读的公开文档没有 `.costyle` 应用接口。
- 输出 JPEG、JPEG 2000、TIFF/GeoTIFF 和 PGM 是真实可用的 SDK 能力；它不证明这些输出与 C1 GUI 像素一致。
- 本次没有下载 SDK 压缩包、接受其许可、核实商业重分发条款或编译运行示例。网站公开下载链接不能替代对 SDK 许可的核实。

### macOS AppleScript/JXA 与 Studio/Enterprise

官方 AppleScript 指南开头限定 macOS，也支持 JXA，脚本可从外部执行。macOS 应用内的 Scripting Dictionary 才是该路线的命令依据。16.8.x 文档仍在增加 Color Editor 和 Masking 等脚本能力；这些都不能搬到 Windows 当作 COM、PowerShell 或跨平台 JavaScript API。[S1]

旧 Capture One Enterprise 自 2024-05-14 起不再销售，官方改推 Studio/Studio for Enterprise。旧 Enterprise 文档提及的增强 AppleScript 同样明确限定 Mac。[S14]

当前 Actions 在 16.8 引入，是从 Capture One 应用内发送图像至批准的外部服务并将结果带回 Session。官方列举 Pixelz、Photoroom、Gemini 等 Connector。设置要求 Studio for Teams 或 Studio for Enterprise 的管理员权限、账号已启用 Actions upgrade，以及外部服务的凭据。文档说管理门户用于配置，Actions 从 Capture One 内部触发；没有公布一个让 SpektraFilm 远程提交任意照片/Style 并由 C1 本地渲染的 Enterprise API。[S15、S16]

这不能证明商业合作中绝无私有 SDK/API；它意味着不能声称“升级 Enterprise 就能在 Windows 调用全套引擎”。若路线必须无界面、无人值守或随本产品分发，需要官方给出适用于该用途的 Windows API、许可与样例证据。

## 可复核的只读检查

```powershell
(Get-Item -LiteralPath 'C:\Program Files\Capture One\Capture One\CaptureOne.exe').VersionInfo |
  Format-List FileVersion,ProductVersion,ProductName,CompanyName

Get-FileHash -LiteralPath 'C:\Program Files\Capture One\Capture One\CaptureOne.exe' -Algorithm SHA256

Get-Content -LiteralPath 'C:\Program Files\Capture One\Capture One\Plugins\OpenWith\manifest.xml'

(Get-Item -LiteralPath 'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Classes\CaptureOne.CaptureOne16\shell\import\command').GetValue('')

(Get-Item -LiteralPath 'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Classes\CaptureOneSession\shell\open\command').GetValue('')
```

## 一手来源

以下页面均在 2026-11-06 读取。帮助中心正文通过 Capture One 官方 Zendesk article API 读取，依据的是文章正文而非用户评论。公开 API 的读取形式为 `https://support.captureone.com/api/v2/help_center/en-us/articles/<article-id>.json`。

- **S1**：[Capture One Workflow Automation with AppleScript](https://support.captureone.com/hc/en-us/articles/360002681418-Capture-One-Workflow-Automation-with-AppleScript)；[macOS / Windows 差异](https://support.captureone.com/hc/en-us/articles/360013473237-What-are-the-differences-between-Capture-One-for-macOS-and-Capture-One-for-Windows)。
- **S2**：[Plugins for publishing images](https://support.captureone.com/hc/en-us/articles/360002659738-Plugins-for-publishing-images)；[Using plugins for external editing](https://support.captureone.com/hc/en-us/articles/360002638138-Using-plugins-for-external-editing)。
- **S3**：[Capture One Developer Portal](https://www.captureone.com/en/partnerships/developer)；其开发者注册链接为 [Developer signup](https://www.captureone.com/a/account/developer/developer-signup)。
- **S4**：[Applying a Style](https://support.captureone.com/hc/en-us/articles/360002611857-Applying-a-Style)；[How to add adjustments on import into a Session?](https://support.captureone.com/hc/en-us/articles/360003119237-How-to-add-adjustments-on-import-into-a-Session)。
- **S5**：[Opening images in an external editor](https://support.captureone.com/hc/en-us/articles/360002627737-Opening-images-in-an-external-editor)。
- **S6**：[Export overview](https://support.captureone.com/hc/en-us/articles/4403021653649-Export-overview)。
- **S7**：[Process Recipes and Export Recipes](https://support.captureone.com/hc/en-us/articles/360002633697-Process-Recipes-and-Export-Recipes)；[Adding Custom Shortcuts](https://support.captureone.com/hc/en-us/articles/10917697304733-Adding-Custom-Shortcuts)。
- **S8**：[Phase One SDK Introduction](https://developer.phaseone.com/sdk/docs/1_introduction/index.html)。
- **S9**：[ImageSDK : C# (Windows)](https://developer.phaseone.com/sdk/docs/getting_started/windows-imgSdk-cs.html)。
- **S10**：[ImageSDK Open Image](https://developer.phaseone.com/sdk/docs/7_imagesdk_features/open-image.html)。
- **S11**：[ImageSDK Convert Pipeline](https://developer.phaseone.com/sdk/docs/7_imagesdk_features/convert-pipeline.html)；[Export image](https://developer.phaseone.com/sdk/docs/7_imagesdk_features/export-image.html)。
- **S12**：[Phase One SDK Download](https://developer.phaseone.com/sdk/docs/appendices/download.html)。
- **S13**：[官方帮助中心精确搜索 command line](https://support.captureone.com/api/v2/help_center/articles/search.json?locale=en-us&query=%22command%20line%22)。搜索结果及未检出项仅用于说明本次检索范围。
- **S14**：[About Capture One Enterprise](https://support.captureone.com/hc/en-us/articles/360002671937-About-Capture-One-Enterprise)。
- **S15**：[Introduction to Actions (Studio for Teams & Studio for Enterprise)](https://support.captureone.com/hc/en-us/articles/36232790597149-Introduction-to-Actions-Studio-for-Teams-Studio-for-Enterprise)。
- **S16**：[Setting up Actions (Studio for Teams & Studio for Enterprise)](https://support.captureone.com/hc/en-us/articles/36039858656541-Setting-up-Actions-Studio-for-Teams-Studio-for-Enterprise)。

[S1]: https://support.captureone.com/hc/en-us/articles/360002681418-Capture-One-Workflow-Automation-with-AppleScript
[S2]: https://support.captureone.com/hc/en-us/articles/360002659738-Plugins-for-publishing-images
[S3]: https://www.captureone.com/en/partnerships/developer
