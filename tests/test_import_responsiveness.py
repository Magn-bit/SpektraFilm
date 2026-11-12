"""Import UI stays live during slow file IO; confirmed picker locations survive."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import tempfile
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

from PIL import Image
from PySide6.QtCore import QSettings,QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication,QFileDialog
from desktop.controller import Controller,PhotoProvider
from desktop.dialogs import StudioFileDialog


class ImportResponsivenessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')

    def wait(self,predicate,timeout=8):
        end=time.monotonic()+timeout
        while not predicate() and time.monotonic()<end:
            self.app.processEvents();time.sleep(.003)
        self.assertTrue(predicate(),'async import timed out')

    def test_first_preview_precedes_slow_tail_and_file_io_is_off_gui(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);paths=[]
            for index in range(18):
                path=folder/f'{index:02}.png';Image.new('RGB',(64,48)).save(path);paths.append(str(path))
            ctrl=Controller(PhotoProvider(),str(folder/'state'))
            release=threading.Event();tail=threading.Event();rendered=[];threads=[];ticks=[]
            timer=QTimer();timer.setInterval(5);timer.timeout.connect(lambda:ticks.append(time.perf_counter()))
            def dimensions(path):
                threads.append(threading.get_ident())
                if path==paths[1]:tail.set();release.wait(5)
                return 64,48
            def preview(path,settings,edge,**kwargs):
                rendered.append(path)
                image=QImage(64,48,QImage.Format_RGB32);image.fill(0xff807060)
                return image,image,1.,{},{}
            ctrl._preview_images=preview
            try:
                with patch('desktop.controller.photo_dimensions',side_effect=dimensions):
                    # Both operations can be slow on an external drive. Neither
                    # is allowed on the caller's event thread during enqueue.
                    with (patch.object(Path,'resolve',side_effect=AssertionError('GUI resolve')),
                          patch.object(Path,'is_file',side_effect=AssertionError('GUI stat'))):
                        start=time.perf_counter();ctrl.add_paths(paths);enqueue_ms=(time.perf_counter()-start)*1000
                    timer.start();self.wait(lambda:tail.is_set() and bool(ctrl.frame))
                    self.assertEqual(rendered[0],paths[0]);self.assertEqual(ctrl.currentPath,paths[0])
                    before=len(ticks);self.wait(lambda:len(ticks)>=before+5)
                    self.assertNotIn(threading.get_ident(),threads)
                    release.set();self.wait(lambda:not ctrl.busy)
                    self.assertEqual(len(ctrl.photos),18)
                    print(f'import enqueue 18 files: {enqueue_ms:.3f}ms; heartbeat continued during blocked IO')
            finally:
                release.set();timer.stop();ctrl.close();self.app.processEvents()

    def test_confirmed_locations_shared_for_photo_sources_and_cancel_preserves_them(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);first=root/'first';second=root/'second';first.mkdir();second.mkdir()
            photo=second/'照片.png';photo.write_bytes(b'fixture')
            ini=root/'locations.ini'
            def settings():return QSettings(str(ini),QSettings.IniFormat)
            def choose(folder,file=None,cancel=False):
                def accept():
                    dialog=self.app.activeModalWidget();self.assertIsInstance(dialog,StudioFileDialog)
                    dialog.picker.setDirectory(str(folder))
                    if file:dialog.picker.selectFile(str(file))
                    if cancel:dialog.reject()
                    else:dialog.picker.accept()
                QTimer.singleShot(20,accept)
            with patch.object(StudioFileDialog,'_locations',new=staticmethod(settings)):
                choose(first)
                value=StudioFileDialog.getExistingDirectory(directory=str(root),location_key='photo-import')
                self.assertEqual(Path(value),first)
                choose(second,cancel=True)
                self.assertEqual(StudioFileDialog.getExistingDirectory(location_key='photo-import'),'')
                self.assertEqual(Path(settings().value('photo-import')),first)
                choose(second,file=photo)
                paths,_=StudioFileDialog.getOpenFileNames(location_key='photo-import')
                self.assertEqual([Path(p) for p in paths],[photo])
                settings().sync()
                self.assertEqual(Path(StudioFileDialog._initial_directory(str(first),'photo-import',True)),second)
                self.assertEqual(Path(StudioFileDialog._initial_directory(str(first),'photo-export',True)),first)
                # A removed directory falls back to its surviving parent.
                settings().setValue('photo-import',str(second/'removed'))
                self.assertEqual(Path(StudioFileDialog._initial_directory('','photo-import',True)),second)
            restored=QSettings(str(ini),QSettings.IniFormat)
            self.assertEqual(Path(restored.value('photo-import')),second/'removed')
            restored.sync()
            reopened=subprocess.check_output([sys.executable,'-X','utf8','-c',
                'from PySide6.QtCore import QSettings;import sys;print(QSettings(sys.argv[1],QSettings.IniFormat).value("photo-import"))',str(ini)],
                text=True,encoding='utf-8')
            self.assertEqual(Path(reopened.strip()),second/'removed')


if __name__=='__main__':unittest.main()
