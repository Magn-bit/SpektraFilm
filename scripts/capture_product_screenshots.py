"""Capture actual product UI using an authorized documentation photograph."""
from pathlib import Path
import argparse
import faulthandler
import json
import os
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'vendor')]
os.environ.pop('QT_QPA_PLATFORM', None)
from PIL import Image
from PySide6.QtCore import QObject, QUrl
from PySide6.QtQml import QQmlApplicationEngine, QQmlEngine, QQmlExpression
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from desktop.controller import Controller, PhotoProvider
from desktop.typography import load_mincho
from desktop.application_identity import configure_process_identity, configure_application_icon, configure_window_icon

SAMPLE_URL = 'https://upload.wikimedia.org/wikipedia/commons/c/c5/Moraine_Lake_17092005.jpg'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--photo', type=Path, help='Use a photograph authorized for the public product page')
    parser.add_argument('--diagnose', action='store_true', help='Print one worker traceback if startup exceeds 20 seconds')
    args = parser.parse_args()
    if args.diagnose:
        faulthandler.dump_traceback_later(20)
    output = ROOT / 'docs/images'
    output.mkdir(parents=True, exist_ok=True)
    scratch = ROOT / 'output/product-screenshots'
    scratch.mkdir(parents=True, exist_ok=True)
    sample = args.photo.resolve() if args.photo else scratch / 'Moraine Lake.jpg'
    if args.photo and not sample.is_file():
        raise FileNotFoundError(sample)
    if not sample.exists():
        request = urllib.request.Request(SAMPLE_URL, headers={'User-Agent': 'SpektraFilm documentation'})
        with urllib.request.urlopen(request, timeout=30) as response:
            sample.write_bytes(response.read())
    configure_process_identity()
    app = QApplication([])
    app.setOrganizationName('SpektraFilm documentation')
    app.setApplicationName('SpektraFilm documentation')
    configure_application_icon(app, ROOT)
    app.setStyle('Fusion')
    QQuickStyle.setStyle('Basic')
    family = load_mincho(app, ROOT)
    captures = []
    with tempfile.TemporaryDirectory(prefix='spektrafilm-docs-') as folder:
        ctrl = Controller(PhotoProvider(), folder)
        ctrl.updatePreference('appearance', 'light')
        ctrl.updatePreference('preview_long_edge', 1080)
        engine = QQmlApplicationEngine()
        engine.addImageProvider('photos', ctrl.provider)
        for key, value in dict(ctrl=ctrl, minchoFamily=family,
                interfaceDisplayFamily=app._interface_font_selection['display'],
                interfaceEditorialFamily=app._interface_font_selection['editorial'],
                systemReduceMotion=True,
                assetsUrl=QUrl.fromLocalFile(str(ROOT / 'assets') + '/').toString()).items():
            engine.rootContext().setContextProperty(key, value)
        warnings = []
        engine.warnings.connect(lambda errors: warnings.extend(error.toString() for error in errors))
        engine.load(QUrl.fromLocalFile(str(ROOT / 'desktop/qml/Studio.qml')))
        assert engine.rootObjects(), warnings
        window = engine.rootObjects()[0]
        configure_window_icon(window, app, ROOT)
        window.resize(1480, 960)
        window.show()

        def wait(predicate, seconds=90):
            end = time.monotonic() + seconds
            next_log = time.monotonic() + 10
            while not predicate() and time.monotonic() < end:
                app.processEvents()
                # qWait keeps the Python GIL on this binding. Yield it between
                # event turns so RAW/metadata workers can make real progress.
                time.sleep(.005)
                if time.monotonic() >= next_log:
                    print('Waiting:', ctrl.status, 'frame:', bool(ctrl.frame),
                          'jobs:', list(ctrl._jobs.values()),
                          'pending:', ctrl._pending, 'editing:', ctrl._before is not None, flush=True)
                    next_log = time.monotonic() + 10
            if not predicate():
                raise RuntimeError((ctrl.status, warnings))

        def walk(parent):
            for child in parent.childItems():
                yield child
                yield from walk(child)

        def item(name):
            found = next((c for c in walk(window.contentItem()) if c.objectName() == name), None)
            return found or window.findChild(QObject, name)

        def js(obj, code):
            expression = QQmlExpression(QQmlEngine.contextForObject(obj), obj, code)
            result = expression.evaluate()
            if expression.hasError():
                raise RuntimeError(expression.error().toString())
            return result

        def top():
            QTest.qWait(100)
            item('parameterScroll').property('contentItem').setProperty('contentY', 0)

        def shot(name):
            QTest.qWait(400)
            original = scratch / (name + '.png')
            assert window.grabWindow().save(str(original))
            with Image.open(original) as image:
                image.thumbnail((1680, 1200), Image.Resampling.LANCZOS)
                image.convert('RGB').save(output / (name + '.jpg'), quality=92, subsampling=0)
            captures.append(name + '.jpg')
            print('Captured', name, flush=True)

        try:
            ctrl.add_paths([str(sample)])
            wait(lambda: bool(ctrl.frame) and not ctrl.busy)
            ctrl.selectStock('kodak_portra_400')
            ctrl.setFilmEnabled(True)
            QTest.qWait(500)
            wait(lambda: not ctrl.busy)
            window.setProperty('activeTask', 'film')
            top()
            shot('workspace')
            library = item('libraryPopup')
            js(library, 'open()')
            wait(lambda: len(ctrl.filmLibrary.model.rows) >= 5
                 and all(row['url'] for row in ctrl.filmLibrary.model.rows[:5]), 100)
            shot('film-library')
            js(library, 'close()')
            window.setProperty('activeTask', 'color')
            color = item('colorToolsPanel')
            color.setProperty('openGroup', 'grading')
            color.setProperty('zone', 'midtones')
            top()
            shot('color-tools')
            color.setProperty('openGroup', 'curves')
            item('curveEditor').setProperty('channel', 'luma')
            ctrl.setCurvePoints('luma', [[0, 0], [.25, .23], [.75, .78], [1, 1]])
            QTest.qWait(500)
            wait(lambda: not ctrl.busy)
            top()
            shot('curves')
            window.setProperty('activeTask', 'local')
            ctrl.addMaskOfKind('radial')
            QTest.qWait(500)
            wait(lambda: not ctrl.busy)
            top()
            shot('masks')
            ctrl.deleteMask()
            window.setProperty('activeTask', 'geometry')
            js(window, 'openCrop()')
            wait(lambda: bool(ctrl.cropSource) and not ctrl.cropBusy)
            crop = item('cropOverlay')
            if crop is not None:
                js(crop, "chooseRatio('XPan 65:24',65/24)")
            shot('crop')
            js(window, 'cancelCrop()')
            assert ctrl.prepareComposition()
            composition = item('compositionDialog')
            js(composition, 'open()')
            ctrl.composition.applyFramePreset('film_135')
            composition.setProperty('frameCategory', 0)
            wait(lambda: not ctrl.composition.state['busy']
                 and not ctrl.composition.state['native_pending']
                 and bool(ctrl.composition.state['native_canvas']), 100)
            shot('film-frame')
            js(composition, 'close()')
            QTest.qWait(120)
            export = item('exportDialog')
            js(export, 'open()')
            QTest.qWait(500)
            wait(lambda: bool(ctrl.outputProof.source) and not ctrl.outputProof.busy, 100)
            shot('export')
            js(export, 'close()')
            report = dict(captures=captures, warnings=warnings, films=len(ctrl.stocks), papers=len(ctrl.papers),
                          sample=(sample.name + ', supplied by the project owner for product screenshots') if args.photo
                          else 'Moraine Lake 17092005, Gorgo, public domain, Wikimedia Commons',
                          scope='Documentation captures of the current source UI and real native preview, presentation images resized for GitHub; not a performance benchmark')
            (scratch / 'capture.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        finally:
            ctrl.close()
            window.close()
            engine.deleteLater()
            app.processEvents()


if __name__ == '__main__':
    main()
