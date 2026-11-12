"""Four-language display translation, without changing model IDs or saved recipes.

The source language stays Simplified Chinese. QML translates at the presentation
boundary using qsTr(), and Python dialogs use tr(). Dynamic statuses use anchored
message templates rather than replacing arbitrary words inside file names.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from PySide6.QtCore import (QObject, Property, QCoreApplication, QLibraryInfo,
                            QLocale, QSettings, QTranslator, Signal, Slot)


LANGUAGES = ('en', 'zh-Hans', 'zh-Hant', 'ja')
LANGUAGE_CHOICES = [
    {'id': 'en', 'name': 'English'},
    {'id': 'zh-Hans', 'name': '简体中文'},
    {'id': 'zh-Hant', 'name': '繁體中文'},
    {'id': 'ja', 'name': '日本語'},
]
_CATALOG = Path(__file__).with_name('translations') / 'ui.json'
_TOKEN = re.compile(r'\{([a-z_]+)\}')
_NUMBER_NAMES = {'count', 'done', 'total', 'current', 'failed', 'radius', 'softness'}
_TRANSLATE_CAPTURE = {'label', 'reason', 'phase', 'state', 'status'}


def normalize_language(language: str) -> str:
    """Normalize known locales; unsupported languages use English."""
    value = str(language or '').replace('_', '-').lower()
    if value.startswith(('zh-hant', 'zh-tw', 'zh-hk', 'zh-mo', 'yue')):
        return 'zh-Hant'
    if value.startswith('zh'):
        return 'zh-Hans'
    if value.startswith('ja'):
        return 'ja'
    return 'en'


def preferred_language(preferred=None) -> str:
    """Choose once from the first supported system preference."""
    for value in (QLocale.system().uiLanguages() if preferred is None else preferred):
        if str(value).lower().startswith(('en', 'zh', 'ja', 'yue')):
            return normalize_language(value)
    return 'en'


class CatalogTranslator(QTranslator):
    def __init__(self, language='zh-Hans', parent=None):
        super().__init__(parent)
        record = json.loads(_CATALOG.read_text(encoding='utf-8'))
        self.entries = record['entries']
        self.language = normalize_language(language)
        self.templates = []
        for source, targets in record['templates'].items():
            parts, cursor = [], 0
            for match in _TOKEN.finditer(source):
                parts.append(re.escape(source[cursor:match.start()]))
                name = match.group(1)
                body = r'[0-9]+(?:\.[0-9]+)?' if name in _NUMBER_NAMES else r'.+?'
                parts.append('(?P<' + name + '>' + body + ')')
                cursor = match.end()
            parts.append(re.escape(source[cursor:]))
            self.templates.append((re.compile(''.join(parts), re.DOTALL), targets))

    def isEmpty(self):
        # A Python translator has no .qm bytes; Qt must still register it.
        return False

    def text(self, source: str, depth=0) -> str:
        source = str(source)
        if self.language == 'zh-Hans' or not source:
            return source
        targets = self.entries.get(source)
        if targets:
            return targets.get(self.language, source)
        if depth >= 4 or len(source) > 16384:
            return source
        for pattern, targets in self.templates:
            match = pattern.fullmatch(source)
            if match:
                values = {name: self.text(value, depth+1) if name in _TRANSLATE_CAPTURE else value
                          for name, value in match.groupdict().items()}
                return targets.get(self.language, source).format_map(values)
        return source

    def translate(self, context, sourceText, disambiguation=None, n=-1):
        result = self.text(sourceText)
        # None is an untranslated/null QString; an empty string hides Qt text.
        return result if result != sourceText else None


class Localizer(QObject):
    languageChanged = Signal()
    revisionChanged = Signal()

    def __init__(self, app, engine, language=None, settings=None):
        super().__init__(app)
        self._app, self._engine = app, engine
        self._settings = settings if settings is not None else QSettings('SpektraFilm', 'SpektraFilm')
        stored = self._settings.value('interface/language', '')
        selected = normalize_language(language or stored or preferred_language())
        self._translator = CatalogTranslator(selected, self)
        self._qt_translator = QTranslator(self)
        self._revision = 0
        self._install()
        # Persist the first choice, including an initial system-derived choice.
        self._settings.setValue('interface/language', selected)

    @Property(str, notify=languageChanged)
    def language(self):
        return self._translator.language

    @Property('QVariantList', constant=True)
    def languages(self):
        return [item.copy() for item in LANGUAGE_CHOICES]

    @Property(int, notify=revisionChanged)
    def revision(self):
        return self._revision

    def _install(self):
        legacy = getattr(self._app, '_studio_translator', None)
        if legacy is not None:
            self._app.removeTranslator(legacy)
        self._app.removeTranslator(self._qt_translator)
        self._app.removeTranslator(self._translator)
        qt_locale = {'zh-Hans': 'zh_CN', 'zh-Hant': 'zh_TW', 'ja': 'ja'}.get(self.language)
        if qt_locale:
            paths = [str(Path(__file__).resolve().parents[1] / 'assets' / 'qt'),
                     QLibraryInfo.path(QLibraryInfo.TranslationsPath)]
            for path in paths:
                if self._qt_translator.load('qtbase_' + qt_locale, path):
                    self._app.installTranslator(self._qt_translator)
                    break
        self._app.installTranslator(self._translator)

    @Slot(str)
    def setLanguage(self, language):
        selected = normalize_language(language)
        if selected == self.language:
            return
        self._translator.language = selected
        self._settings.setValue('interface/language', selected)
        self._install()
        self._revision += 1
        self.languageChanged.emit()
        self.revisionChanged.emit()
        self._engine.retranslate()

    @Slot(str, result=str)
    @Slot(str, int, result=str)
    def text(self, source, revision=0):
        return self._translator.text(source)


def install_localization(app, engine, language=None, settings=None):
    """Install before engine.load(); retain the object and publish as i18n."""
    localizer = Localizer(app, engine, language, settings)
    engine.rootContext().setContextProperty('i18n', localizer)
    app._localizer = localizer
    return localizer


def tr(source):
    return QCoreApplication.translate('SpektraFilm', str(source))
