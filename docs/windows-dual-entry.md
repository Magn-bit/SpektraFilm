# Windows GUI / console 共享打包

正式发布使用 `scripts/windows.spec`，已接入 GUI / CLI 双入口。
`scripts/windows-dual.spec` 仅保留为最初的可审查模板与历史参考，不用于正式发布。
一次 `Analysis` 与 `PYZ` 构建两个 `EXE`，一次 `COLLECT` 放在同一个目录，共享
`_internal`。GUI 入口 `console=False`，CLI 入口 `console=True`；不能把 windowed
EXE 的 stdin/stdout 当作 MCP stdio，双入口也无需复制整个依赖树。

`desktop/main.py` 已在 PySide6 / Controller imports **之前**按可执行文件名分流：

```python
if Path(sys.executable).stem.casefold() == 'spektrafilmcli':
    from desktop.automation import main as automation_main
    raise SystemExit(automation_main())
```

先设置已有 ROOT / vendor sys.path，再执行上述分流；GUI 的其余初始化顺序保持。
CLI `automation.main` 明确把控制台和 MCP 管道设为 UTF-8，避免 Windows 旧代码页
产生不可解析的中文 JSON。console 的 `--help` 不应创建 QApplication 或显示窗口。

使用 PowerShell 7 和项目虚拟环境按正式 `scripts/windows.spec` 运行 PyInstaller，最终 Windows 目录同时包含
`SpektraFilm.exe`、`SpektraFilmCLI.exe` 与共享 `_internal`。原生库 helper、引擎
runtime、QML 和许可证均在该 spec 数据清单中。发布前只需在最终成品检查一次：
GUI 启动、CLI `--help` / 结构化 status、显式 MCP initialize / tools/list，以及已授权
同窗口小图流程。不重新执行已经通过的全量资料库或大 RAW 验证。
