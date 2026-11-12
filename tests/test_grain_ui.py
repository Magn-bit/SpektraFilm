"""Real Studio interaction contract for the compact grain menu.

Only the expensive pixel renderer is isolated: import, QML bindings, keyboard
shortcuts, history, scrolling and sidecar persistence use the real application.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PIL import Image
from PySide6.QtCore import QCoreApplication, QEvent, QMetaObject, QObject, QPointF, Qt, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

from desktop.controller import Controller, PhotoProvider
from desktop.imaging import FILM_FIELDS, Settings
from desktop.typography import load_mincho


class GrainUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setOrganizationName('SpektraFilm')
        cls.app.setApplicationName('SpektraFilm interaction test')
        cls.root = Path(__file__).resolve().parents[1]
        cls.family = load_mincho(cls.app, cls.root)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.photo = self.folder / 'grain-fixture.png'
        Image.new('RGB', (96, 64), (116, 137, 151)).save(self.photo)
        self.original = self.photo.read_bytes()
        self.renderers = [
            patch('desktop.controller.render', side_effect=lambda image, settings, **kwargs: image.copy()),
            patch('desktop.controller.render_interactive', side_effect=lambda image, settings, **kwargs: image.copy()),
        ]
        for renderer in self.renderers:
            renderer.start()
            self.addCleanup(renderer.stop)

        self.ctrl = Controller(PhotoProvider(), self.temp.name)
        self.ctrl._color_display.snapshot=lambda:None
        self.engine = QQmlApplicationEngine()
        self.engine.addImageProvider('photos', self.ctrl.provider)
        context = self.engine.rootContext()
        for key, value in {
            'ctrl': self.ctrl,
            'minchoFamily': self.family,
            'interfaceDisplayFamily': self.app._interface_font_selection['display'],
            'interfaceEditorialFamily': self.app._interface_font_selection['editorial'],
            'systemReduceMotion': True,
            'assetsUrl': QUrl.fromLocalFile(str(self.root / 'assets') + '/').toString(),
            'interfaceFontDescription': 'interaction test',
        }.items():
            context.setContextProperty(key, value)
        self.qml_warnings = []
        self.engine.warnings.connect(lambda errors: self.qml_warnings.extend(error.toString() for error in errors))
        self.engine.load(QUrl.fromLocalFile(str(self.root / 'desktop/qml/Studio.qml')))
        self.assertTrue(self.engine.rootObjects(), '\n'.join(self.qml_warnings))
        self.window = self.engine.rootObjects()[0]
        self.window.resize(1120, 760)
        self.window.setVisible(True)
        self.window.requestActivate()
        self.wait(lambda: self.window.isActive())
        self.picker = self.child('grainTypePicker')
        self.menu = self.child('grainTypeMenu')

    def tearDown(self):
        self.window.close()
        self.ctrl.close()
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()
        self.temp.cleanup()

    def child(self, name):
        item = self.window.findChild(QObject, name)
        self.assertIsNotNone(item, name)
        return item

    def wait(self, predicate, timeout=6):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(5)
            time.sleep(.001)  # Allow Python QRunnable workers to acquire the GIL.
        self.assertTrue(predicate(), self.ctrl.status + '\n' + '\n'.join(self.qml_warnings))

    def import_photo(self, legacy=False):
        if legacy:
            dirty = asdict(Settings())
            dirty.update(grain_type='classic', contrast=85, temperature=2800,
                         film_enabled=False, spectral=False)
            self.ctrl._edit_path(str(self.photo)).write_text(
                json.dumps({'version': 1, 'settings': dirty}), encoding='utf-8')
        self.ctrl.add_paths([str(self.photo)])
        self.wait(lambda: bool(self.ctrl.frame) and not self.ctrl.busy)
        self.assertEqual((self.ctrl.imageWidth, self.ctrl.imageHeight), (96, 64))
        # New photos open naturally; grain controls belong to enabled film.
        self.ctrl.setFilmEnabled(True)
        self.wait(lambda:not self.ctrl.busy)
        self.assertTrue(self.picker.property('enabled'))
        QTest.qWait(30)

    def click(self, item):
        self.assertIsInstance(item, QQuickItem)
        point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, point)
        self.app.processEvents()

    def assert_selected(self, grain_type):
        self.assertEqual(self.ctrl.settings['grain_type'], grain_type)
        checked = [name for name in ('fine', 'classic', 'coarse', 'clustered')
                   if self.child('grainType_' + name).property('checked')]
        self.assertEqual(checked, [grain_type])

    def assert_film_only(self):
        neutral = asdict(Settings(spectral=True, film_enabled=True,
                                  lens_correction=False, defringe=False))
        for key, value in neutral.items():
            if key not in FILM_FIELDS:
                self.assertEqual(self.ctrl.settings[key], value, key)

    def test_keyboard_mouse_history_preserve_live_parameter_panel_and_scroll(self):
        self.import_photo(legacy=True)
        self.assert_film_only()
        scroll = self.child('parameterScroll')
        flick = scroll.property('contentItem')
        vignette = self.child('parameter_vignette')
        scroll_destroyed = QSignalSpy(scroll.destroyed)
        picker_destroyed = QSignalSpy(self.picker.destroyed)
        self.wait(lambda: flick.property('contentHeight') > flick.height() + 1)

        # Use a genuinely scrolled panel while leaving the picker in view.
        offset = self.picker.mapToItem(flick, QPointF(0, 0)).y() - flick.height() * .45
        max_offset = flick.property('contentHeight') - flick.height()
        flick.setProperty('contentY', max(1.0, min(max_offset, offset)))
        QTest.qWait(30)
        initial_y = flick.property('contentY')
        initial_height = flick.property('contentHeight')
        self.assertGreater(initial_y, 0)

        def stable_panel():
            self.wait(lambda: not self.ctrl.busy)
            self.assertTrue(isValid(scroll))
            self.assertTrue(isValid(flick))
            self.assertTrue(isValid(vignette))
            self.assertIs(self.child('parameterScroll'), scroll)
            self.assertIs(scroll.property('contentItem'), flick)
            self.assertIs(self.child('parameter_vignette'), vignette)
            self.assertEqual(scroll_destroyed.count(), 0)
            self.assertEqual(picker_destroyed.count(), 0)
            self.assertAlmostEqual(flick.property('contentY'), initial_y, delta=.5)
            self.assertAlmostEqual(flick.property('contentHeight'), initial_height, delta=.5)
            self.assert_film_only()

        # Keyboard opens the actual menu; navigation starts on classic.
        self.picker.forceActiveFocus()
        QTest.keyClick(self.window, Qt.Key_Space)
        self.wait(lambda: self.menu.property('opened'))
        self.assertEqual(self.menu.property('currentIndex'), 1)
        QTest.keyClick(self.window, Qt.Key_Up)
        QTest.keyClick(self.window, Qt.Key_Return)
        self.wait(lambda: not self.menu.property('visible'))
        self.assert_selected('fine')
        self.assertTrue(self.ctrl.canUndo)
        stable_panel()

        # Mouse reopens it and selects the last option, without panel rebuild.
        self.click(self.picker)
        self.wait(lambda: self.menu.property('opened'))
        self.assertEqual(self.menu.property('currentIndex'), 0)
        self.click(self.child('grainType_clustered'))
        self.wait(lambda: not self.menu.property('visible'))
        self.assert_selected('clustered')
        stable_panel()

        for key, modifiers, expected in [
            (Qt.Key_Z, Qt.ControlModifier, 'fine'),
            (Qt.Key_Z, Qt.ControlModifier, 'classic'),
            (Qt.Key_Y, Qt.ControlModifier, 'fine'),
            (Qt.Key_Z, Qt.ControlModifier | Qt.ShiftModifier, 'clustered'),
        ]:
            QTest.keyClick(self.window, key, modifiers)
            self.wait(lambda: self.ctrl.settings['grain_type'] == expected)
            self.assert_selected(expected)
            stable_panel()

        self.assertFalse(self.ctrl.canRedo)
        record = json.loads(self.ctrl._edit_path(str(self.photo)).read_text(encoding='utf-8'))
        self.assertEqual(set(record['settings']), set(FILM_FIELDS))
        self.assertEqual(record['settings']['grain_type'], 'clustered')
        self.assertEqual(self.photo.read_bytes(), self.original)

    def test_disabled_empty_state_cancel_and_invalid_types_do_not_commit_edits(self):
        self.assertFalse(self.picker.property('enabled'))
        self.click(self.picker)
        QTest.qWait(30)
        self.assertFalse(self.menu.property('visible'))
        self.assertFalse(self.ctrl.canUndo)
        self.import_photo()
        before = self.ctrl.settings
        scroll = self.child('parameterScroll').property('contentItem')
        scroll.setProperty('contentY', max(0, scroll.property('contentHeight')-scroll.property('height')))
        QTest.qWait(30)
        self.click(self.picker)
        self.wait(lambda: self.menu.property('opened'))
        QTest.keyClick(self.window, Qt.Key_Down)
        QTest.keyClick(self.window, Qt.Key_Escape)
        self.wait(lambda: not self.menu.property('visible'))
        self.assertEqual(self.ctrl.settings, before)
        self.assertFalse(self.ctrl.canUndo)
        for invalid in ('', 'unsupported', 'Fine', 'temperature'):
            self.ctrl.setGrainType(invalid)
        self.assertEqual(self.ctrl.settings, before)
        self.assertFalse(self.ctrl.canUndo)
        self.assert_film_only()

    def test_precision_input_reset_and_last_parameter_access(self):
        self.import_photo()
        self.window.resize(1366, 768)
        QTest.qWait(30)
        field = self.child('parameterValue_exposure')
        self.click(field)
        QTest.keyClick(self.window, Qt.Key_A, Qt.ControlModifier)
        for key in (Qt.Key_Plus, Qt.Key_1, Qt.Key_Period, Qt.Key_2):
            QTest.keyClick(self.window, key)
        QTest.keyClick(self.window, Qt.Key_Return)
        self.wait(lambda: self.ctrl.settings['exposure'] == 1.2)
        self.assertTrue(self.ctrl.canUndo)
        self.assertEqual(field.property('text'), '+1.20')
        self.ctrl.undo()
        self.wait(lambda: self.ctrl.settings['exposure'] == 0)
        self.ctrl.redo()
        self.wait(lambda: self.ctrl.settings['exposure'] == 1.2)
        QMetaObject.invokeMethod(self.child('parameter_exposure'), 'resetValue')
        self.wait(lambda: self.ctrl.settings['exposure'] == 0)
        self.ctrl.undo()
        self.wait(lambda: self.ctrl.settings['exposure'] == 1.2)

        self.child('printSection').setProperty('expanded', True)
        QTest.qWait(40)
        scroll = self.child('parameterScroll')
        flick = scroll.property('contentItem')
        for width, height in ((1366, 768), (1440, 900), (1120, 760)):
            self.window.resize(width, height)
            QTest.qWait(30)
            flick.setProperty('contentY', max(0, flick.property('contentHeight')-flick.property('height')))
            QTest.qWait(30)
            parameter = self.child('parameter_print_m')
            top = parameter.mapToItem(scroll, QPointF(0, 0)).y()
            bottom = parameter.mapToItem(scroll, QPointF(0, parameter.height())).y()
            self.assertGreaterEqual(top, -1)
            self.assertLessEqual(bottom, scroll.height()+1)
            self.assertGreater(parameter.width(), 200)

    def test_keyboard_fine_coarse_and_double_click_handle_use_real_values(self):
        self.import_photo()
        self.window.setProperty('activeTask','basic');QTest.qWait(30)
        slider=self.child('parameterSlider_exposure')
        field=self.child('parameterValue_exposure')
        slider.forceActiveFocus()
        QTest.keyClick(self.window,Qt.Key_Right,Qt.ShiftModifier)
        self.wait(lambda:abs(self.ctrl.settings['exposure']-.001)<1e-9)
        self.assertEqual(field.property('text'),'+0.001')
        self.ctrl.undo()
        self.wait(lambda:self.ctrl.settings['exposure']==0)
        self.assertEqual(field.property('text'),'0.00')
        QTest.keyClick(self.window,Qt.Key_Right,Qt.AltModifier)
        self.wait(lambda:abs(self.ctrl.settings['exposure']-.1)<1e-9)
        self.assertEqual(field.property('text'),'+0.10')
        handle=self.child('parameterHandle_exposure')
        point=handle.mapToScene(QPointF(handle.width()/2,handle.height()/2)).toPoint()
        QTest.mouseDClick(self.window,Qt.LeftButton,Qt.NoModifier,point)
        self.wait(lambda:self.ctrl.settings['exposure']==0)
        self.ctrl.undo()
        self.wait(lambda:abs(self.ctrl.settings['exposure']-.1)<1e-9)

        self.click(field)
        QTest.keyClick(self.window,Qt.Key_A,Qt.ControlModifier)
        for key in (Qt.Key_Minus,Qt.Key_0,Qt.Key_Period,Qt.Key_1,Qt.Key_2,Qt.Key_3):QTest.keyClick(self.window,key)
        QTest.keyClick(self.window,Qt.Key_Return)
        self.wait(lambda:abs(self.ctrl.settings['exposure']+.123)<1e-9)
        self.assertEqual(field.property('text'),'-0.123')
        QTest.keyClick(self.window,Qt.Key_Up,Qt.ShiftModifier)
        self.wait(lambda:abs(self.ctrl.settings['exposure']+.122)<1e-9)
        self.assertEqual(field.property('text'),'-0.122')

    def test_restore_defaults_is_current_photo_only_and_disabled_when_unmodified(self):
        self.import_photo()
        reset=self.child('resetPhotoButton')
        self.assertEqual(reset.property('text'),'恢复默认')
        self.assertFalse(reset.property('enabled'))
        second=self.folder/'second.png'
        Image.new('RGB',(64,96),(90,110,130)).save(second)
        self.ctrl.add_paths([str(second)])
        self.wait(lambda:len(self.ctrl.photos)==2 and not self.ctrl.busy)
        self.ctrl.updateParameter('exposure',.7)
        self.ctrl.selectPhoto(0)
        self.wait(lambda:not self.ctrl.busy)
        self.ctrl.selectStock('kodak_ektar_100')
        self.ctrl.updateParameter('exposure',1.1)
        self.wait(lambda:not self.ctrl.busy)
        self.assertTrue(reset.property('enabled'))
        self.click(reset)
        self.wait(lambda:not self.ctrl.busy)
        self.assertFalse(reset.property('enabled'))
        self.assertEqual(self.ctrl.settings['stock'],'kodak_portra_400')
        self.assertEqual(self.ctrl.settings['exposure'],0)
        self.ctrl.undo();self.wait(lambda:not self.ctrl.busy)
        self.assertEqual(self.ctrl.settings['stock'],'kodak_ektar_100')
        self.assertEqual(self.ctrl.settings['exposure'],1.1)
        self.ctrl.redo();self.wait(lambda:not self.ctrl.busy)
        self.assertFalse(reset.property('enabled'))
        self.ctrl.selectPhoto(1);self.wait(lambda:not self.ctrl.busy)
        self.assertEqual(self.ctrl.settings['exposure'],.7)


if __name__ == '__main__':
    unittest.main()
