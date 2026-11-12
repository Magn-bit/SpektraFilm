# Interface translations

The four display languages are English (`en`), Simplified Chinese (`zh-Hans`),
Traditional Chinese (`zh-Hant`) and Japanese (`ja`). This matches the current
SpektraLab app's `LOCALIZATION.md`, rather than its older two-language desktop UI.

`ui.json` is a retained, UTF-8 runtime catalog. Simplified Chinese is the source;
other languages contain complete entries and anchored dynamic-message templates.
Unknown native/OS error details remain intact. Filenames, stock IDs, saved
parameters and user-entered recipe names/subfolders are never rewritten.

The initial 99 matching translations were adapted from
[SpektraLab](https://github.com/JamesQiu2005/SpektraLab), commit
`2201f5fa4d256b0c742b46b8e31f8176a12ca6ea` (2.2.0),
`app/SpektraLab/Resources/Localizable.xcstrings`, GPL-3.0.
Context-specific wording was reviewed and adjusted for SpektraFilm. The remaining
workflow, accessibility, validation and status entries were written for this
project. Traditional Chinese additions were seeded using OpenCC's `s2twp`
dictionary and retained as plain text. OpenCC is not a runtime dependency.

Qt's `qtbase_zh_CN.qm`, `qtbase_zh_TW.qm` and `qtbase_ja.qm` in `assets/qt` come
from the installed PySide6/Qt distribution. They cover the existing QFileDialog
browser and standard widgets; preserve the packaged Qt license notices.

QML translates only final presentation bindings with `qsTr(String(...))`.
`Localizer.setLanguage()` persists the explicit choice and calls
`QQmlEngine.retranslate()`, leaving current photographs and edits untouched.
Python dialogs call `desktop.localization.tr()` and handle `LanguageChange`.
For new strings add all three target translations, retain placeholders exactly,
and put interpolated messages in `templates`. Translate only known label/error
captures, never filename or stock-name captures.
