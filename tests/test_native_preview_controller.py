"""Native preview scheduling and the public darkroom settings contract.

Pixel generation is deterministic here so delayed frames can be controlled.
The actual Vulkan / RGB16 / TIFF16 path has a separate integration acceptance.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from PIL import Image
from PySide6.QtWidgets import QApplication

from desktop.controller import Controller, PhotoProvider
from desktop.imaging import Settings
from dataclasses import fields


class NativePreviewControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'source.png'
        Image.new('RGB',(1280,960),(120,100,80)).save(self.path)
        self.calls=[]
        self.patches=[patch.dict(os.environ,{'SPEKTRAFILM_COMPUTE':'auto'}),
                      patch('desktop.native_spectral.available',return_value=True),
                      patch('desktop.controller.render',side_effect=self.render),
                      patch('desktop.controller.render_interactive',side_effect=AssertionError('Native drag must keep the full spectral model'))]
        for item in self.patches:item.start()
        self.ctrl=Controller(PhotoProvider(),self.temp.name)
        # This fixture controls scheduling, not monitor colour transforms.
        # The production canvas now renders float pixels via that separate
        # colour-managed path, whose native integration is tested elsewhere.
        self.ctrl._color_display.snapshot=lambda:None

    def tearDown(self):
        self.ctrl.close();self.app.processEvents()
        for item in reversed(self.patches):item.stop()
        self.temp.cleanup()

    def render(self,image,settings,**kwargs):
        self.calls.append((image.size,settings))
        self.assertTrue(settings.spectral)
        return Image.new('RGB',image.size,(round(100+settings.exposure*50),0,0))

    def wait(self,predicate):
        deadline=time.monotonic()+5
        while not predicate() and time.monotonic()<deadline:
            self.app.processEvents();time.sleep(.003)
        self.assertTrue(predicate(),self.ctrl.status)

    def load(self):
        self.ctrl.add_paths([str(self.path)])
        self.wait(lambda:bool(self.ctrl.frame) and not self.ctrl.busy)

    def red(self):
        return self.ctrl.provider.images['frame'].pixelColor(0,0).red()

    def test_native_live_final_undo_and_redo_keep_one_model_and_latest_value(self):
        self.load();self.calls.clear()
        self.ctrl.beginEdit()
        for value in (.2,.5,1.2):self.ctrl.updateParameter('exposure',value)
        self.wait(lambda:self.ctrl._quality_generation==self.ctrl._generation and self.ctrl._quality==1)
        self.assertEqual(self.red(),160)
        self.assertIn(((640,480),self.ctrl._settings),self.calls)
        self.assertEqual(self.ctrl.status,'准备就绪')
        self.ctrl.endEdit()
        self.wait(lambda:not self.ctrl.busy)
        self.assertEqual((self.red(),self.ctrl._quality),(160,2))
        self.assertEqual(len(self.ctrl._history[self.ctrl.currentIndex]),1)
        self.ctrl.undo();self.wait(lambda:not self.ctrl.busy)
        self.assertEqual(self.red(),100)
        self.ctrl.redo();self.wait(lambda:not self.ctrl.busy)
        self.assertEqual(self.red(),160)
        self.assertTrue(all(settings.spectral for _,settings in self.calls))

    def test_late_drag_frame_cannot_replace_released_value_or_undo(self):
        self.load()
        started=threading.Event();release=threading.Event();published=[]
        self.ctrl.frameChanged.connect(lambda:published.append(self.red()) if self.ctrl.frame else None)
        def delayed(image,settings,**kwargs):
            if image.width==640 and settings.exposure==.2:
                started.set()
                if not release.wait(4):raise RuntimeError('Delayed preview test timed out')
            return self.render(image,settings,**kwargs)
        with patch('desktop.controller.render',side_effect=delayed):
            try:
                self.ctrl.beginEdit();self.ctrl.updateParameter('exposure',.2)
                self.wait(started.is_set)
                self.ctrl.updateParameter('exposure',1.2);self.ctrl.endEdit()
                self.wait(lambda:self.ctrl._quality_generation==self.ctrl._generation and self.ctrl._quality==2)
                self.assertEqual(self.red(),160)
                self.ctrl.undo()
                self.wait(lambda:self.ctrl._quality_generation==self.ctrl._generation and self.ctrl._quality==2)
                self.assertEqual(self.red(),100)
            finally:release.set()
            self.wait(lambda:not self.ctrl.busy)
        self.assertEqual(self.red(),100)
        self.assertNotIn(110,published)

    def test_darkroom_parameters_persist_and_survive_canonicalization(self):
        self.load()
        self.ctrl.setPaper('kodak_ultra_endura')
        self.ctrl.beginEdit()
        values={'film_format_mm':70.,'glare':6.,'print_exposure':.7,'print_y':18.,'print_m':-21.}
        for key,value in values.items():self.ctrl.updateParameter(key,value)
        self.ctrl.endEdit();self.wait(lambda:not self.ctrl.busy)
        saved=json.loads(self.ctrl._edit_path(str(self.path)).read_text(encoding='utf-8'))['settings']
        self.assertEqual(set(saved),{field.name for field in fields(Settings)})
        self.assertEqual(saved['paper'],'kodak_ultra_endura')
        for key,value in values.items():self.assertEqual(saved[key],value,key)
        _,_,_,status=self.ctrl._render_photo(str(self.path),replace(self.ctrl._settings,contrast=80),640,interactive=True)
        self.assertEqual(status['spectral_backend'],'Vulkan')
        self.assertEqual(self.calls[-1][1].contrast,80)


if __name__=='__main__':unittest.main()
