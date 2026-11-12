"""Bounded real-QML switch checks. No RAW benchmark or export re-test."""
from pathlib import Path
import argparse
import json
import os
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'vendor')]
os.environ.pop('QT_QPA_PLATFORM', None)
from PIL import Image
from PySide6.QtCore import QObject, QPointF, Qt, QUrl
from PySide6.QtQml import QQmlApplicationEngine, QQmlEngine, QQmlExpression
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from desktop.controller import Controller, PhotoProvider
from desktop.typography import load_mincho


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--qml-root', type=Path, default=ROOT / 'desktop/qml')
    parser.add_argument('--output', type=Path, default=ROOT / 'output/switch-controls')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setOrganizationName('SpektraFilm switch checks')
    app.setApplicationName('SpektraFilm switch checks')
    app.setStyle('Fusion')
    QQuickStyle.setStyle('Basic')
    family = load_mincho(app, ROOT)
    report = dict(ok=False, qml_root=str(args.qml_root.resolve()), checks=[], screenshots=[])
    with tempfile.TemporaryDirectory(prefix='spektrafilm-switch-') as folder:
        ctrl = Controller(PhotoProvider(), folder)
        engine = QQmlApplicationEngine()
        engine.addImageProvider('photos', ctrl.provider)
        for key, value in dict(ctrl=ctrl, minchoFamily=family,
                interfaceDisplayFamily=app._interface_font_selection['display'],
                interfaceEditorialFamily=app._interface_font_selection['editorial'],
                systemReduceMotion=False,
                assetsUrl=QUrl.fromLocalFile(str(ROOT / 'assets') + '/').toString()).items():
            engine.rootContext().setContextProperty(key, value)
        warnings = []
        engine.warnings.connect(lambda errors: warnings.extend(error.toString() for error in errors))
        engine.load(QUrl.fromLocalFile(str(args.qml_root.resolve() / 'Studio.qml')))
        assert engine.rootObjects(), warnings
        window = engine.rootObjects()[0]
        window.resize(1366, 768)
        window.show()
        window.requestActivate()

        def wait(predicate, seconds=35):
            end = time.monotonic() + seconds
            while not predicate() and time.monotonic() < end:
                app.processEvents()
                QTest.qWait(5)
            assert predicate(), dict(status=ctrl.status, warnings=warnings)

        def walk(parent):
            for child in parent.childItems():
                yield child
                yield from walk(child)

        def item(name):
            result = next((c for c in walk(window.contentItem()) if c.objectName() == name), None)
            result = result or window.findChild(QObject, name)
            assert result is not None, name
            return result

        def js(obj, code):
            expression = QQmlExpression(QQmlEngine.contextForObject(obj), obj, code)
            value = expression.evaluate()
            assert not expression.hasError(), expression.error().toString()
            return value

        def click(obj, track=False):
            assert obj.isVisible() and obj.isEnabled(), obj.objectName()
            x = obj.width() - 24 if track else obj.width()/2
            point = obj.mapToScene(QPointF(x, obj.height()/2)).toPoint()
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
            QTest.qWait(170)

        def reveal(obj):
            scroll = item('parameterScroll')
            flick = scroll.property('contentItem')
            top = obj.mapToScene(QPointF()).y() - scroll.mapToScene(QPointF()).y()
            target = flick.property('contentY') + top - (scroll.height()-obj.height())/2
            flick.setProperty('contentY', max(0, min(target, flick.property('contentHeight')-flick.height())))
            QTest.qWait(70)

        def state(obj, expected):
            assert obj.property('checked') == expected, obj.objectName()
            assert obj.property('stateText') == ('开启' if expected else '关闭'), obj.objectName()
            assert abs(obj.property('visualPosition') - int(expected)) < .001

        def capture(name):
            QTest.qWait(200)
            path = args.output / (name+'.png')
            assert window.grabWindow().save(str(path))
            report['screenshots'].append(str(path.resolve()))

        try:
            assert not item('filmEnabledButton').isVisible()
            photos = []
            for index, color in enumerate(('#A4B3A2', '#A9B5C0')):
                path = Path(folder) / f'开关检查_{index}.jpg'
                Image.new('RGB', (960, 640), color).save(path)
                photos.append(str(path))
            ctrl.add_paths(photos)
            wait(lambda: ctrl.photoCount == 2 and bool(ctrl.frame) and not ctrl.busy)
            window.setProperty('activeTask', 'basic')
            QTest.qWait(100)
            tools = next(c for c in walk(window.contentItem()) if c.metaObject().indexOfProperty('basicGroup') >= 0)
            tools.setProperty('basicGroup', 'optics')
            QTest.qWait(100)
            lens = item('lensCorrectionToggle')
            reveal(lens)
            original = bool(ctrl.settings['lens_correction'])
            state(lens, original)
            click(lens, track=True)
            assert ctrl.settings['lens_correction'] == (not original)
            state(lens, not original)
            ctrl.undo()
            QTest.qWait(180)
            state(lens, original)
            ctrl.redo()
            QTest.qWait(180)
            state(lens, not original)
            click(lens, track=True)
            state(lens, original)
            lens.forceActiveFocus(Qt.TabFocusReason)
            QTest.keyClick(window, Qt.Key_Space)
            QTest.qWait(180)
            state(lens, not original)
            assert ctrl.settings['lens_correction'] == (not original)
            # Drag the actual knob to the opposite endpoint without a preceding click.
            start = lens.mapToScene(QPointF(lens.width()-33 if original else lens.width()-15,
                                           lens.height()/2)).toPoint()
            end = lens.mapToScene(QPointF(lens.width()-15 if original else lens.width()-33,
                                         lens.height()/2)).toPoint()
            QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
            for step in range(1, 7):
                QTest.mouseMove(window, start+(end-start)*step/6, 12)
            QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, end)
            QTest.qWait(180)
            state(lens, original)
            click(lens, track=True)
            state(lens, not original)
            capture('optics-1366')
            report['checks'].append('Optics real pointer and Space changes, current label/position, undo and redo')

            ctrl.selectPhoto(1)
            wait(lambda: not ctrl.busy)
            state(lens, original)
            ctrl.selectPhoto(0)
            wait(lambda: not ctrl.busy)
            state(lens, not original)
            report['checks'].append('Checked binding survives clicks, undo/redo and photo switches')
            window.setProperty('activeTask', 'film')
            QTest.qWait(120)
            film = item('filmEnabledButton')
            reveal(film)
            state(film, False)
            capture('film-off-1366')
            click(film, track=True)
            state(film, True)
            assert ctrl.settings['film_enabled']
            grain = item('grainToggle')
            reveal(grain)
            before = ctrl.settings['grain_enabled']
            click(grain, track=True)
            state(grain, not before)
            assert ctrl.settings['grain_enabled'] == (not before)
            capture('film-grain-1366')
            reveal(film)
            click(film, track=True)
            state(film, False)
            assert not grain.isEnabled()
            old = grain.property('checked')
            reveal(grain)
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier,
                            grain.mapToScene(QPointF(grain.width()-24, grain.height()/2)).toPoint())
            assert grain.property('checked') == old
            report['checks'].append('Film and grain real switches preserve disabled downstream editing')

            window.resize(1440, 900)
            reveal(film)
            click(film, track=True)
            capture('film-on-1440')
            ctrl.updatePreference('appearance', 'dark')
            QTest.qWait(200)
            capture('film-dark-1440')
            state(film, True)
            ctrl.updatePreference('appearance', 'light')
            settings = item('settingsPanel')
            js(settings, "category='color';open()")
            wait(lambda: settings.property('opened'))
            proof = item('softProofToggle')
            before = ctrl.colorDisplay.proofEnabled
            click(proof)
            assert ctrl.colorDisplay.proofEnabled == (not before)
            state(proof, not before)
            capture('settings-color-1440')
            js(settings, "category='interface'")
            QTest.qWait(120)
            reduced = item('reducedMotionToggle')
            click(reduced)
            state(reduced, True)
            report['checks'].append('Settings full-row hit target, soft proof binding and reduced motion')
            js(settings, 'close()')
            QTest.qWait(400)
            window.setProperty('activeTask', 'local')
            ctrl.addMaskOfKind('linear')
            QTest.qWait(160)
            mask = item('maskEnabledToggle')
            reveal(mask)
            click(mask, track=True)
            assert not ctrl.maskLayers[0]['enabled']
            ctrl.undo()
            QTest.qWait(180)
            state(item('maskEnabledToggle'), True)
            invert = item('maskInvertToggle')
            reveal(invert)
            click(invert)
            assert ctrl.activeMaskGuide['inverted']
            state(invert, True)
            capture('mask-1440')
            report['checks'].append('Mask layer enabled/inverted switches retain live data and history')
            recipe = item('outputRecipeDialog')
            js(recipe, 'createRecipe();open()')
            wait(lambda: recipe.property('opened'))
            after = item('openAfterToggle')
            # Output recipes have a separate scrolling container.
            scroll = after.parentItem()
            while scroll and scroll.metaObject().indexOfProperty('contentY') < 0:
                scroll = scroll.parentItem()
            if scroll:
                scroll.setProperty('contentY', max(0, scroll.property('contentHeight')-scroll.height()))
            QTest.qWait(80)
            click(after)
            state(after, True)
            js(recipe, "setValue('open_after',false)")
            QTest.qWait(100)
            state(after, False)
            capture('recipe-1440')
            report['checks'].append('Recipe switch writes draft and follows external draft replacement')
            js(recipe, 'close()')
            QTest.qWait(400)
            assert ctrl.prepareComposition()
            composition = item('compositionDialog')
            js(composition, 'open()')
            wait(lambda: composition.property('opened'))
            js(composition, 'tool=2')
            QTest.qWait(120)
            info = item('photoInfoToggle')
            before = ctrl.composition.state['show_info']
            click(info, track=True)
            assert ctrl.composition.state['show_info'] == (not before)
            state(info, not before)
            capture('composition-1440')
            js(composition, 'close()')
            QTest.qWait(400)
            export = item('exportDialog')
            js(export, 'open()')
            wait(lambda: export.property('opened'))
            proof = item('outputSoftProofToggle')
            click(proof)
            state(proof, False)
            assert not item('outputGamutToggle').isEnabled()
            capture('proof-1440')
            js(export, 'close()')
            report['checks'].append('Composition switch updates real layout; proof switches wrap and respect dependencies')
            wait(lambda: not ctrl.busy)
            assert not warnings, warnings
            report.update(ok=True, qml_warnings=warnings, sizes=[[1366, 768], [1440, 900]],
                          scope='Actual requested QML assets with source controller; synthetic 960x640 JPEGs; no RAW/export benchmark')
        finally:
            (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            window.close()
            ctrl.close()
            engine.deleteLater()
            app.processEvents()
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
