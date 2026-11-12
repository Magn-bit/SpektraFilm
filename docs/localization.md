# 四语言界面

设置 → 界面 → 语言提供 English、简体中文、繁體中文、日本語。选择即时生效，
不重启显影引擎、不重新加载照片、不改写当前编辑参数。首次启动按系统首个受支持
语言选择并记住；不支持的语言使用 English。之后保留用户明确选择。

实现采用 PySide6 `QTranslator`、QML `qsTr()` 与 `QQmlEngine.retranslate()`。
资源在 `desktop/translations/ui.json`，本地化入口在 `desktop/localization.py`。
`install_localization(app, engine, language=None, settings=None)` 在 QML 加载前安装，
并向 QML 暴露 `i18n`。`i18n.languages` 是 id/name 选项，`i18n.language` 是当前代码，
`i18n.setLanguage(code)` 切换。应用持有 translator，避免 Python 回收。

默认语言存储为 `QSettings('SpektraFilm','SpektraFilm')` 的 `interface/language`。
Windows 对应 HKCU\Software\SpektraFilm\SpektraFilm。验证使用临时 INI，
不覆盖真实偏好。打包需要包含 `desktop/translations` 和 `assets/qt`。

覆盖导入与筛选、编辑工具、显影与印相、曲线、蒙版、裁切、资料库、排版、
导出与输出配方、设置、主状态、常用失败原因、禁用原因与无障碍标签。
动态消息通过完整模板匹配，保留数量、路径和胶片名；系统或第三方返回的
未知错误原文保留。胶片/相纸档案名、ID、文件名、参数字段和用户输入不变。

仅一次关键 UI 验证：

```powershell
& .\.venv\Scripts\python.exe -X utf8 scripts/verify_localization.py
```

验证实际加载完整 Studio，依次切换四种语言，检查编辑和设置页面、动态状态、
文件选择对话框及验证错误、持久化、设置保持与中文文件名保持，保存同尺寸截图。
该验证不处理 RAW、不重新跑引擎测试、不做哈希检查。来源与许可见
`desktop/translations/README.md`。
