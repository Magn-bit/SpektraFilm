# Lightroom Classic 真实显影引擎可行性核查

核查日期：2026-11-06。范围仅为本机 Lightroom Classic 与其公开 Lua SDK；没有启动 Lightroom、登录 Adobe、加载插件、读取或修改任何用户 catalog，也没有执行显影验证。

## 结论

可行的官方集成形态是 **运行 Lightroom Classic 宿主，通过 Lua 插件应用 Lightroom 已识别的原生显影预设，再用 `LrExportSession` 导出**。Adobe 的 SDK Guide 明确说明导出请求最终交给 Lightroom Classic 的 built-in rendering engine，而且插件可以不打开 Export 对话框直接开始导出。[S1，印刷页 49–52]

这是一条依赖本机 Lightroom 应用的引擎路线，不能描述成可嵌入 SpektraFilm 的 Adobe engine SDK。所核查的公开 SDK 中没有独立 raw→render/headless 可执行接口、外部进程直接执行 Lua 插件的 CLI、或可重新分发的显影运行时。安装目录出现 `LightroomSDK.dll` 并不能证明它提供以上能力；本研究没有复制或调用该 DLL。[S1，Preface、页 10–11；S2]

**任意原 XMP 预设的完整自动导入尚未实现，也没有核查到公开的 `LrApplication.importDevelopPreset(path)` API。** 不能把解析若干 XMP 标量后调用 `applyDevelopSettings` 宣称为原生完整 XMP 支持。最可信的首次验证方案是先用 Lightroom 的原生导入流程准备预设及其依赖，然后插件按原生 preset UUID 获取 `LrDevelopPreset` 并应用。[S3、S4、S5]

## 本机安装证据

只读 Windows 卸载注册表与 EXE 文件版本得到：

| 项目 | 结果 |
| --- | --- |
| 产品 | Adobe Lightroom Classic |
| 注册表 DisplayVersion | `15.5` |
| 主程序 | `C:\Program Files\Adobe\Adobe Lightroom Classic\Lightroom.exe` |
| EXE ProductVersion | `15.5 (202607291506-b8869fa7)` |

没有检查登录、许可证、首次启动或导出功能是否可用；“已安装”不等于“宿主已验证可运行”。没有在安装目录找到 SDK HTML Reference 或 SDK Guide，因此另取文档。

## 已核实 API 与边界

下列精确签名来自 Adobe 编写、第三方原样托管的 API Reference（页面版权 2007–2025）。这不是已运行的 15.5 API 探针；存在版本差异的可能，首次插件试验仍应记录 `LrApplication.versionString()` / `versionTable()`。[S3–S9]

| 公开 API | 输入、返回与限制 |
| --- | --- |
| `LrApplication.activeCatalog()` | 返回当前已打开的 `LrCatalog`，不是打开任意 catalog 的构造器。[S3] |
| `LrApplication.developPresetFolders()` | 返回 `LrDevelopPresetFolder[]`。[S3] |
| `folder:getDevelopPresets()` | 返回文件夹中的 `LrDevelopPreset[]`。[S5] |
| `LrApplication.developPresetByUuid(uuid)` | 用 UUID 获取原生 `LrDevelopPreset`；不获取 `addDevelopPresetForPlugin` 产生的隐藏插件预设。[S3] |
| `preset:getUuid()` / `getName()` / `getFile()` | 用于核对预设身份、名称与路径。[S4] |
| `LrApplication.addDevelopPresetForPlugin(plugin, presetName, presetValue)` | `presetValue` 为 Lua settings **table**；返回 `LrDevelopPreset`。存储在隐藏的 `Plugin Develop Presets`，不显示在 Develop 预设面板中。[S3] |
| `LrApplication.getDevelopPresetsForPlugin(plugin, uuid)` | 获取指定或全部关联插件预设；不是从 XMP 文件导入，也不是枚举普通用户预设的主入口。[S3] |
| `photo:applyDevelopPreset(preset, plugin, presetAmount, updateAISettings)` | `preset` 为 `LrDevelopPreset` 对象，须在 `catalog:withWriteAccessDo` 或 `withProlongedWriteAccessDo` 内调用。`plugin` 为可选；与隐藏插件预设相关。当前参考中 amount 范围 0–200，AI 更新默认 false。首次支持 SDK 3.0 不代表后两个可选参数也在 3.0 中存在。[S6] |
| `photo:applyDevelopSettings(settings, optHistoryName, optFlattenAutoNow)` | 接受 Lua table；照片必须存在且为图像。可选历史名称、同步展开 Auto 设置。它不接受 XMP 路径或 XML 字符串。[S6] |
| `photo:getDevelopSettings()` | 返回当前显影 settings，须在 `LrTasks` task 中调用。文档明确将 settings table 标为 experimental，跨版本兼容性不受保证。[S6] |
| `catalog:addPhoto(path, stackWithPhoto, position, metadataPresetUUID, developPresetUUID)` | 相当于 Add photo without moving；须在 catalog 写门内调用，会修改活动 catalog。[S7] |
| `LrExportSession{ photosToExport = photos, exportSettings = settings }` | 传入 `LrPhoto[]` 和导出设置；不是只传文件路径即可脱离 catalog 使用的 renderer。[S8] |
| `exportSession:doExportOnCurrentTask()` | 须在异步 task 中调用；等待 renditions 创建完成。[S8] |
| `exportSession:doExportOnNewTask()` | 自建异步 task，立即返回，不能把返回当成导出已完成。[S8] |
| `exportRendition:waitForRender()` | 等到 rendition 完成并写入目标路径；返回成功状态与路径或失败信息。应检查真实文件存在和失败状态。[S9] |

注意参考文档中的历史交叉链接存在不一致：`addDevelopPresetForPlugin` 段落提到 `applyDevelopPresetFromPlugin`，而 `LrPhoto` 的实际公开方法清单和签名为 `applyDevelopPreset`；`LrDevelopPresetFolder` 引言提到 `getDevelopPresetFolders`，而 `LrApplication` 方法清单为 `developPresetFolders()`。原型应使用实际声明的后者，不能照抄旧交叉链接。[S3、S5、S6]

## XMP、HSL 与 Adobe profile 的实际含义

1. **原生对象路线**：由 Lightroom 原生导入目标 XMP，核对它在 Lightroom 中的效果及依赖，再用 `developPresetFolders()` → `getDevelopPresets()` 找到对象，记录 UUID，之后用 `developPresetByUuid(uuid)` + `applyDevelopPreset`。插件无需自行展开预设内部结构，导出仍走 Adobe 引擎。[S3–S6；导出引擎见 S1]
2. **Lua settings 路线**：`getDevelopSettings` 的公开表列有 `CameraProfile`、`ProcessVersion`、HSL 的 `HueAdjustment*` / `SaturationAdjustment*` / `LuminanceAdjustment*`、曲线及校准等，证明 SDK 可以接触这些显影设置。但这是参数设置能力，不能推导出任意 XMP、所有嵌套 `Look` 或 profile 内容都被完整解释。`LrDevelopController` 也列出 HSL 和 `ProfileAmount` 控件参数，依然不是 XMP 文件导入 API。[S6、S10]
3. **完整保真仍需验证**：公开 API 没有保证“XMP XML 到 Lua settings 的通用无损映射”，文档也没有把 `Look` 的完整嵌套数据结构定义为稳定交换规范。只设置 `CameraProfile = "某名称"` 不足以证明 XMP 中引用/内嵌的创意 profile、Look table 或依赖已加载。优先保留原生 preset 对象；缺失 profile、文件类型不兼容、AI 设置等应由原生导入与样片验证暴露，不能静默降级成近似效果。

其中第 3 点是基于公开接口边界的工程判断，不是已在本机 15.5 上测出的失败结果。特别是原 XMP 在当前宿主中能否显示、能否枚举、能否应用到项目实际 JPEG/RAW 输入，仍须逐项试验。

## 独立 catalog 与 Windows 启动限制

**可以把工作约束在应用已打开的独立 catalog，但所核查 SDK 没有创建、打开或切换 `.lrcat` 的公开方法。** `LrCatalog` 对象来自 `activeCatalog()` 或 catalog 内对象；`createCollection` 只是创建 collection。不能把它当成新建 catalog。[S3、S7]

建议在后续用户选定此路线后，先通过 Lightroom 原生界面建立专用 worker catalog，将样片复制到专用输入目录，在打开 worker catalog 后再启用显影任务。插件必须首先比较 `catalog:getPath()` 与事先配置的绝对 worker 路径，不相符则终止；不能自动对“最后打开的 catalog”执行 `addPhoto` 或显影写入。专用 catalog 的新建/打开操作尚未在本机执行；Adobe 的 create-catalogs 帮助页面本次请求被服务器拒绝，因此这里没有声称验证了任何 CLI catalog 参数。

Catalog 隔离也不等于 Adobe 用户配置隔离：SDK Guide 说明插件标准自动发现目录是 Windows 用户级路径；将插件放在那里会影响该 Windows 用户的 Lightroom 插件列表。首次试验适合把 `.lrplugin` 留在项目目录，通过 Plug-in Manager 的 Add 加载。[S1，页 29–30]

官方文档确认的加载方式：

- 将 `Info.lua` 和 Lua 文件打包在 `Something.lrplugin` 文件夹中，通过 Plug-in Manager 的 Add 加载、启用、重载或移除。[S1，页 29]
- Windows 自动发现目录：`C:\Users\<username>\AppData\Roaming\Adobe\Lightroom\Modules`。[S1，页 30]
- `Info.lua` 中的 `LrInitPlugin = 'Init.lua'` 在插件加载或重载时运行；`LrLibraryMenuItems` 可注册菜单命令。[S1，页 23、32、34]
- 没有核查到官方 Windows `Lightroom.exe --run-plugin …`、`--headless` 或脱离 GUI 会话的宿主启动契约。`LrInitPlugin` 是宿主内加载回调，不能等同为外部命令执行 API。

若要让 SpektraFilm 提交任务，可在已加载插件中轮询本地任务文件，或用 SDK `LrSocket` / `LrHttp` 与本地 helper 通讯；这属于需实现的应用桥接方案，并非 Adobe 已提供的 headless 服务。插件生命周期、宿主是否打开、当前 catalog、错误回报与导出完成判断都须由桥接层管理。当前不应宣称可启动后台服务或同时维持独立无 UI Lightroom 实例。

## 最小原型建议（仅设计，未生成或安装插件）

### A. 先验证真实渲染，避免主动修改 catalog 内容

`Info.lua` 声明插件身份和一个 Library 菜单项。菜单脚本使用 `LrTasks.startAsyncTask`，读取 `activeCatalog():getTargetPhotos()`，仅对明确的当前选择构造 `LrExportSession`，导出到新建的项目输出目录；**不**调用 `addPhoto`、`applyDevelopSettings`、`applyDevelopPreset`、`createVirtualCopies` 或 catalog 写门。这样先验证“插件成功请求 Adobe 内置渲染、结果文件可回到项目”，不能据此证明目标 XMP 已应用。

采用 `specificFolder` 目标、`LR_reimportExportedPhoto = false`、`LR_collisionHandling = 'rename'`；固定 JPEG/TIFF、颜色空间、尺寸和质量并记录输出。相应 export 属性和取值均由 Guide 页 61、65–67 定义。不要使用 `ORIGINAL` 格式做显影 proof，因为目标是得到渲染后的像素。[S1；S8、S9]

“不主动修改 catalog 内容”只描述插件行为，不承诺 Lightroom 宿主运行期间完全不写缓存、偏好或 catalog 文件。此阶段也应在用户已选择并打开的测试环境中执行。

### B. 在独立 worker catalog 验证原生 XMP 预设

1. 在 Lightroom 原生流程导入测试 XMP 及所需 profile，核对 UI 中实际效果；保持任务范围为少量复制样片。
2. 插件先检查 `catalog:getPath()`，只接受专用 worker catalog；枚举原生 preset 并记录 UUID、名称、文件路径。
3. 在 catalog 写门中 `addPhoto` 或定位已导入样片，然后 `photo:applyDevelopPreset(nativePreset)`；完成写门后再导出。
4. 使用固定 export settings 渲染，逐一检查 rendition 状态、文件存在及可解码；同时保存宿主版本、预设 UUID、输入类型、输出设置与错误。
5. 将插件输出与相同 Lightroom、相同源照片、相同原生 preset 和相同 export settings 的 UI 手动导出对比。只有这项通过后，才能说此路线在目标预设上实现真实引擎效果；目前没有运行结果。

## 来源与证据位置

- **S1，Adobe 官方 SDK Guide（原始 PDF，2007–2022）**：[Adobe Developer Console CDN](https://ioconsolerykerprodcdn.azureedge.net/static/installers/lr/sdk/2022/cross_platform/v13/doc/Lightroom%20Classic%20SDK%20Guide_1655133965.pdf)。已下载至 `output/engine-research/lightroom/Lightroom-Classic-SDK-Guide-2022.pdf`，并用 `pdftotext -layout` 提取同名 TXT；PDF SHA-256：`BFA23A9D5898EC71D16C3BAD4A7EEB6D05484CE679E2942E7FD40866C210B8CE`。URL 路径中的 `v13` 不被当成该 PDF 适用 Lightroom 版本的证明。
- **S2，官方产品/SDK 入口**：[Adobe Lightroom Classic developer page](https://developer.adobe.com/lightroom-classic/)，以及其链接的 [SDK downloads](https://developer.adobe.com/console/downloads)。本次未登录，不把 Console SDK ZIP 的最新版获取视为已完成。
- **S3，Adobe 编写的 API Reference，第三方托管**：[LrApplication](https://lrc.mcor.dev/modules/LrApplication.html)。
- **S4，同上**：[LrDevelopPreset](https://lrc.mcor.dev/modules/LrDevelopPreset.html)。
- **S5，同上**：[LrDevelopPresetFolder](https://lrc.mcor.dev/modules/LrDevelopPresetFolder.html)。
- **S6，同上**：[LrPhoto](https://lrc.mcor.dev/modules/LrPhoto.html)。
- **S7，同上**：[LrCatalog](https://lrc.mcor.dev/modules/LrCatalog.html)。
- **S8，同上**：[LrExportSession](https://lrc.mcor.dev/modules/LrExportSession.html)。
- **S9，同上**：[LrExportRendition](https://lrc.mcor.dev/modules/LrExportRendition.html)。
- **S10，同上**：[LrDevelopController](https://lrc.mcor.dev/modules/LrDevelopController.html)。

API Reference HTML 与纯文本快照位于 `output/engine-research/lightroom/api-mirror/`，明确标为 mirror；并非 Adobe 官方站点当前发布包的认证副本。官方 Guide 能确认宿主内 Lua、安装位置、加载回调和真实导出引擎路径；较新的精确可选参数来自上述 API 镜像，未在本机执行验证。本研究没有完成最新版 SDK 包的一手来源交叉核验，也没有将社区示例代码当作已验证的官方接口。
