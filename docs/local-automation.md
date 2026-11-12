# 本地脚本与参数剪贴板

`desktop/automation.py` 使用应用现有的 RAW 解码、原生显影和导出配方。CLI 与 MCP 都离线运行，不监听网络；导入只登记原片路径与尺寸，导出按顺序处理，默认配方不缩小尺寸。MCP 需要显式启动，关闭进程后不留服务。

`--session` 使用明确指定的 JSON sidecar，与当前 GUI 窗口独立。`--gui` 则连接设置中已显式开启的同窗口接口，操作同一编辑状态、参数剪贴板、撤销记录和导出 worker。两个入口互斥，不会在连接失败时静默退回 sidecar。裁切、旋转和显式输出配方仍可改变输出尺寸。

在源码目录运行（PowerShell 7）：

```powershell
& .\.venv\Scripts\python.exe -X utf8 scripts/spektrafilm.py --session D:\Work\film-session.json open D:\Photos\a.ARW D:\Photos\b.ARW
& .\.venv\Scripts\python.exe -X utf8 scripts/spektrafilm.py --session D:\Work\film-session.json status
& .\.venv\Scripts\python.exe -X utf8 scripts/spektrafilm.py --session D:\Work\film-session.json catalog --stock kodak_portra_400
```

`open` 返回每张照片的 id。以下命令中的 `<id>` 换成返回值，也可传入会话中已打开照片的绝对路径。

```powershell
& .\.venv\Scripts\python.exe -X utf8 scripts/spektrafilm.py --session D:\Work\film-session.json set '<id>' --settings '{"film_enabled":true,"stock":"kodak_portra_400","exposure":0.2}'
& .\.venv\Scripts\python.exe -X utf8 scripts/spektrafilm.py --session D:\Work\film-session.json get '<id>'
& .\.venv\Scripts\python.exe -X utf8 scripts/spektrafilm.py --session D:\Work\film-session.json copy '<id>' --categories film paper color
& .\.venv\Scripts\python.exe -X utf8 scripts/spektrafilm.py --session D:\Work\film-session.json paste --photos '<other-id>'
& .\.venv\Scripts\python.exe -X utf8 scripts/spektrafilm.py --session D:\Work\film-session.json undo '<other-id>'
& .\.venv\Scripts\python.exe -X utf8 scripts/spektrafilm.py --session D:\Work\film-session.json redo '<other-id>'
& .\.venv\Scripts\python.exe -X utf8 scripts/spektrafilm.py --session D:\Work\film-session.json export --photos '<id>' --recipe tiff --destination D:\Exports
```

`set --settings @D:\Work\settings.json` 可读取 JSON 参数对象。配方支持 `jpg-high`、`jpg-share`、`tiff`、`png`、`dng`、`raw`，或 `--recipe @D:\Work\recipe.json`。输出沿用应用的文件命名、类型文件夹和冲突编号规则，原片不被覆盖。`raw` 复制原始相机文件；`dng` 是处理后的线性 RGB DNG。导出错误不会偷偷改用缩略图。

`export-clip D:\Work\look.json` 导出已复制的分类；`import-clip D:\Work\look.json` 导入。剪贴板默认不复制蒙版和几何；只应用在复制时实际捕获的字段。每张照片保留最多 32 步撤销/重做；sidecar 最多 32 MiB、4096 张，可按拍摄批次拆分。并行写同一个会话会立即报错，避免静默覆盖。

MCP 客户端配置示例（目录按本机安装位置调整）：

```json
{
  "mcpServers": {
    "spektrafilm-local": {
      "command": "D:\\Project\\SpektraFilm\\.venv\\Scripts\\python.exe",
      "args": [
        "-X", "utf8", "D:\\Project\\SpektraFilm\\scripts\\spektrafilm.py",
        "--session", "D:\\Work\\film-session.json", "mcp", "--enable-local"
      ]
    }
  }
}
```

MCP 使用 newline-delimited JSON-RPC stdio，提供 `initialize`、`ping`、`tools/list` 与 `tools/call`。12 个工具为 `spektra_status/catalog/open/get/set/copy/paste/undo/redo/export/import_clip/export_clip`。图片/参数读取与导出是同步调用；调用中退出进程可停止后续批次，完整输出通过原子发布，已经完成的文件会保留。接口不提供网络服务、LLM、生图、任意脚本执行或 GUI 自动控制。

已验证的 sidecar 边界见 `output/automation/verification.json`。

## 同窗口模式

设置中的“本机会话接口”默认关闭。开启后，`GuiAutomation(controller)` 建立
`QLocalServer.UserAccessOption` 限制的本地 socket / Windows named pipe，另外以
随机 token 认证每个请求。凭据只存入应用数据下专用 `automation` 目录，Windows
先设置仅当前用户可访问的继承 DACL；关闭时移除凭据和 listener。token 不出现在
日志、CLI 参数或设置界面；不开 HTTP / TCP 服务。多个窗口并行开启时用
`--gui-session <id>` 选择，便携数据目录可用 `--gui-directory <目录>` 指定。

```powershell
./SpektraFilmCLI.exe --gui status
./SpektraFilmCLI.exe --gui open D:\Photos\a.ARW
./SpektraFilmCLI.exe --gui get current
./SpektraFilmCLI.exe --gui set current --settings '{"exposure":0.25}'
./SpektraFilmCLI.exe --gui copy current --categories film exposure
./SpektraFilmCLI.exe --gui paste --photos D:\Photos\b.ARW
./SpektraFilmCLI.exe --gui export --recipe tiff --destination D:\Exports
./SpektraFilmCLI.exe --gui job '<返回的任务id>'
./SpektraFilmCLI.exe --gui cancel-export '<尚在运行的导出任务id>'
./SpektraFilmCLI.exe --gui mcp --enable-local
```

源码入口相同，只需把 EXE 换为 `python -X utf8 scripts/spektrafilm.py`。
`photo` 使用 `current` 或当前窗口已打开照片的绝对路径；open 每次最多 256 张，
可分批提交。open/export 立即返回任务 ID；用 job 查看完成、错误和最终输出路径。
参数操作通过排队调用进入控制器的 Qt 线程，导入、显影和导出沿用既有 worker，
不会在界面线程等待大图。导出期间或正在手动拖动时拒绝冲突的自动化写操作。
超时后先查询 GUI 状态，不自动重放可能已经提交的写操作。

MCP 同窗口模式提供 19 个工具，增加 `spektra_job` 与 `spektra_cancel_export`及下述5项分析/预览工具，
initialize 明确报告 live GUI scope。`--session` 的原 12 个同步工具仍保持原契约。
默认分享配方的压缩质量与显式缩放设置照常生效，未指定缩放的导出走原片尺寸。

接线接口：controller 创建 `GuiAutomation(self)`，设置开关调用 `setEnabled(bool)`，
界面读取 `enabled` / `status`，订阅 `changed` / `error(str)`；控制器关闭前调用
`close()`。对象本身不会保存开启偏好，开关持久化由应用设置负责；重启是否重开
必须依据明确的已保存设置。`sessionId` 可供多窗口选择，始终不暴露 token。

同窗口关键节点见 `output/gui-automation/verification.json`：一张 64×48 小图、
实际 Controller、token/方法拒绝、同 GUI 复制粘贴与撤销重做、异步原生 PNG 导出、
CLI 和 MCP 均通过。接口只复用现有引擎，没有宣称还原竞品私有会话接口。

## 当前窗口的分析与视觉迭代

这5项仅用于`--gui`，没有连接窗口时不会转到sidecar：

```powershell
./SpektraFilmCLI.exe --gui describe
./SpektraFilmCLI.exe --gui preview-image --long-edge 1280
./SpektraFilmCLI.exe --gui auto-meter --target both --method protect_highlights
./SpektraFilmCLI.exe --gui latitude
./SpektraFilmCLI.exe --gui place
```

`describe`返回当前照片尺寸、胶片/相纸配对、参数和真实预览/处理状态；也接受当前窗口已打开照片的路径。`auto-meter`调用同一Controller的`autoMeter`，可选目标`exposure/filter_pack/both`，测光方式`balanced/center/protect_highlights/protect_shadows`。`latitude`调用`measureLatitude`，只测量；`place`先测量，并且只有引擎建议的fit有效且照片/参数仍当前时才调用`applyLatitude`。三者立即返回job ID，用`job`查询真实原生计算结果与是否应用；失败或已过期的结果分别报告`failed/discarded`，不会假报完成。自动配光和应用置位沿用GUI撤销记录。

`preview-image`只读取当前窗口已完成的照片预览，不触发原尺寸重渲染。预览落后于当前参数时返回`state=rendering`与重试间隔；就绪时返回64–2048上限边长的JPEG。MCP的`spektra_preview_image`返回真正的`type=image`内容块与不含图像数据的文字元信息；CLI JSON中包含base64 image字段。图像域明确为`monitor-managed-display`，用于查看当前屏幕效果，不冒充最终sRGB输出或原尺寸文件，也不改变源图/导出的分辨率。

剪贴板导入通过Controller的`setSettingsClipboard`保存规范字段子集；导出保留真实来源和复制时所选分类，不根据别名重复推断film/paper分类。

本次工具聚合节点：`scripts/verify_gui_analysis_tools.py`，结果在`output/gui-analysis-tools/verification.json`。127×79小图、实际Controller和认证本地socket、CLI分析job、原生有效fit应用、64×39 MCP JPEG解码以及分类/来源保真均通过，事件循环603次心跳。本节点没有重复原有CLI复制/粘贴/导出或大RAW测试。最终成品可通过`SPEKTRAFILM_PROBE_TOOLS_ONLY=1`的workspace probe复用新工具验收。
