"""Load the approved bundled bilingual interface typeface throughout."""
from pathlib import Path
import json
from PySide6.QtCore import QTranslator
from PySide6.QtGui import QFont, QFontDatabase


def load_mincho(app, root: Path) -> str:
    translator = QTranslator(app)
    if translator.load(str(root / 'assets/qt/qtbase_zh_CN.qm')):
        app.installTranslator(translator)
        app._studio_translator = translator
    record = json.loads((root / 'assets/fonts/interface-font.json').read_text(encoding='utf-8'))
    path = root / 'assets/fonts' / record['file']
    ident = QFontDatabase.addApplicationFont(str(path))
    families = QFontDatabase.applicationFontFamilies(ident) if ident >= 0 else []
    family = record['family']
    if family not in families:
        raise RuntimeError('界面字体加载失败：' + str(path))
    app._interface_font_selection = dict(
        primary=family, display=family, editorial=family, cjk=family,
        body_weight=400, display_weight=400,
        script_fonts=record['scripts'], font_file=record['file'],
        personal_families=[], apple_primary_active=False,
    )
    font = QFont(family)
    font.setPixelSize(15)
    font.setWeight(QFont.Normal)
    # Vertical hinting improves small serif stems without changing glyph widths.
    font.setHintingPreference(QFont.PreferVerticalHinting)
    font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(font)
    return family
