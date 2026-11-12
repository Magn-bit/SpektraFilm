import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import time
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from dataclasses import replace
import numpy as np
from PIL import Image
from PySide6.QtCore import QMimeData,QUrl,Qt,QPointF
from PySide6.QtGui import QImage,QWindow,QDragEnterEvent,QDropEvent
from PySide6.QtWidgets import QApplication
from desktop.controller import Controller,PhotoProvider
from desktop.imaging import Settings,render
from desktop.import_bridge import PhotoImportBridge,mime_paths

class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.renderer=patch('desktop.controller.render',side_effect=lambda im,s,**kwargs:render(im,replace(s,spectral=False)))
        self.renderer.start();self.addCleanup(self.renderer.stop)
        self.physics=patch('desktop.imaging._spectral',side_effect=lambda rgb,s,**kwargs:rgb.astype('float32')/255 if rgb.dtype.name=='uint8' else rgb.copy())
        self.physics.start();self.addCleanup(self.physics.stop)
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.ctrl=Controller(PhotoProvider(),self.temp.name)
        self.paths=[]
        for i in range(3):
            path=self.folder/f'照片 {i}.png'
            Image.new('RGB',(120,80),(110+i*20,120,140)).save(path)
            self.paths.append(str(path))
    def tearDown(self):
        self.app.clipboard().clear()
        self.ctrl.close();self.app.processEvents();self.temp.cleanup()
    def wait(self,predicate,timeout=6):
        end=time.monotonic()+timeout
        while not predicate() and time.monotonic()<end:
            self.app.processEvents();time.sleep(.003)
        self.assertTrue(predicate(),self.ctrl.status)
    def load(self):
        self.ctrl.add_paths(self.paths);self.wait(lambda:not self.ctrl.busy and bool(self.ctrl.frame))

    def test_qt_window_drop_accepts_local_unicode_files(self):
        window=QWindow();bridge=PhotoImportBridge(self.app,window,self.ctrl)
        mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(self.paths[0])])
        event=QDragEnterEvent(QPointF(10,10).toPoint(),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier)
        self.app.sendEvent(window,event);self.assertTrue(event.isAccepted())
        drop=QDropEvent(QPointF(10,10),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier)
        self.app.sendEvent(window,drop);self.assertTrue(drop.isAccepted())
        self.wait(lambda:not self.ctrl.busy and len(self.ctrl.photos)==1)
        window.removeEventFilter(bridge);self.app.removeNativeEventFilter(bridge);window.destroy()

    def test_clipboard_file_list_and_duplicate_coalescing(self):
        mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(p) for p in self.paths])
        self.app.clipboard().setMimeData(mime)
        self.assertTrue(self.ctrl.canPaste)
        self.ctrl.pastePhotos();self.ctrl.pastePhotos()
        self.wait(lambda:not self.ctrl.busy and len(self.ctrl.photos)==3)

    def test_clipboard_bitmap_becomes_editable_photo(self):
        image=QImage(40,30,QImage.Format_RGB32);image.fill(Qt.red)
        self.app.clipboard().setImage(image);self.ctrl.pastePhotos()
        self.wait(lambda:not self.ctrl.busy and bool(self.ctrl.frame))
        path=Path(self.ctrl.photos[0]['path']);self.assertTrue(path.is_file())
        target=self.folder/'pasted.jpg'
        self.assertTrue(self.ctrl.export_to(str(target),preset='JPG_HIGH'))
        self.wait(lambda:not self.ctrl.busy)
        with Image.open(target) as output:self.assertEqual(output.size,(40,30))

    def test_text_clipboard_never_fetches_remote_content(self):
        mime=QMimeData();mime.setText('https://example.com/photo.jpg')
        self.assertEqual(mime_paths(mime),[])
        mime.setText('"'+self.paths[0]+'"');self.assertEqual(mime_paths(mime),[self.paths[0]])

    def test_multi_selection_and_stock_keep_individual_adjustments(self):
        self.load();self.ctrl.updateParameter('exposure',.7)
        self.ctrl.selectPhoto(1);self.ctrl.updateParameter('vignette',12)
        self.ctrl.selectWithModifiers(0,Qt.ControlModifier.value)
        self.assertEqual(self.ctrl.selectedIndices,[0,1])
        self.ctrl.selectStock('kodak_gold_200')
        self.assertEqual(self.ctrl.photos[0]['settings']['exposure'],.7)
        self.assertEqual(self.ctrl.photos[1]['settings']['vignette'],12)
        self.assertEqual(self.ctrl.photos[2]['settings']['stock'],'kodak_portra_400')
        self.ctrl.selectPhoto(1);self.ctrl.undo()
        self.assertEqual(self.ctrl.settings['stock'],'kodak_portra_400')
        self.assertEqual(self.ctrl.settings['vignette'],12)
        self.ctrl.selectWithModifiers(2,Qt.ShiftModifier.value)
        self.assertEqual(self.ctrl.selectedIndices,[1,2])

    def test_batch_snapshots_each_photo_settings_and_avoids_collisions(self):
        self.load();self.ctrl.updateParameter('exposure',.5)
        self.ctrl.selectPhoto(1);self.ctrl.updateParameter('vignette',12)
        self.ctrl.selectAllPhotos();self.wait(lambda:not self.ctrl.busy)
        share_folder=self.folder/'分享 JPG';share_folder.mkdir()
        (share_folder/'照片 0_Portra 400.jpg').write_bytes(b'existing')
        captured=[]
        def save(source,target,settings,preset):
            captured.append((Path(source).name,settings,preset));Path(target).write_bytes(b'export')
        with patch('desktop.controller.export_preset',side_effect=save):
            self.assertTrue(self.ctrl.export_batch('JPG_SHARE'))
            self.wait(lambda:not self.ctrl.busy)
        self.assertEqual(len(captured),3)
        self.assertEqual(captured[0][1].exposure,.5)
        self.assertEqual(captured[1][1].vignette,12)
        self.assertEqual(captured[2][1].vignette,0)
        self.assertEqual((share_folder/'照片 0_Portra 400.jpg').read_bytes(),b'existing')
        self.assertTrue((share_folder/'照片 0_Portra 400_2.jpg').is_file())
        self.assertEqual(self.ctrl.batchProgress,3)

    def test_batch_continues_after_one_failure_and_reports_it(self):
        self.load();self.ctrl.selectAllPhotos();self.wait(lambda:not self.ctrl.busy)
        def save(source,target,settings,preset):
            if source==self.paths[1]:raise OSError('模拟磁盘错误')
            Path(target).write_bytes(b'export')
        with patch('desktop.controller.export_preset',side_effect=save):
            self.assertTrue(self.ctrl.export_batch('TIFF'));self.wait(lambda:not self.ctrl.busy)
        self.assertEqual(len(self.ctrl.batchResult['completed']),2)
        self.assertEqual(len(self.ctrl.batchResult['errors']),1)
        self.assertFalse(self.ctrl.export_batch('RAW'))

    def test_batch_cancel_finishes_current_file_only(self):
        self.load();self.ctrl.selectAllPhotos();self.wait(lambda:not self.ctrl.busy)
        entered=threading.Event();release=threading.Event()
        def save(source,target,settings,preset):
            entered.set();release.wait(4);Path(target).write_bytes(b'export')
        with patch('desktop.controller.export_preset',side_effect=save):
            try:
                self.assertTrue(self.ctrl.export_batch('JPG_HIGH'))
                self.wait(entered.is_set);self.ctrl.cancelBatchExport()
            finally:release.set()
            self.wait(lambda:not self.ctrl.busy)
        self.assertTrue(self.ctrl.batchResult['cancelled'])
        self.assertEqual(len(self.ctrl.batchResult['completed']),1)
        self.assertTrue((self.folder/'高品质 JPG'/'照片 0_Portra 400.jpg').is_file())

    def test_batch_exports_to_each_source_folder_and_selected_type_subfolder(self):
        self.load()
        second=self.folder/'另一目录';second.mkdir()
        other=second/'另外一张.png';Image.new('RGB',(80,60),(90,100,110)).save(other)
        self.ctrl.add_paths([str(other)]);self.wait(lambda:not self.ctrl.busy and len(self.ctrl.photos)==4)
        self.ctrl.selectAllPhotos();self.wait(lambda:not self.ctrl.busy)
        captured=[]
        def save(source,target,settings,preset):
            captured.append(Path(target));Path(target).write_bytes(b'export')
        with patch('desktop.controller.export_preset',side_effect=save):
            self.assertTrue(self.ctrl.export_batch('TIFF'));self.wait(lambda:not self.ctrl.busy)
        self.assertEqual(len(captured),4)
        self.assertTrue(all(path.parent.name=='无损 TIFF' for path in captured))
        self.assertEqual({path.parent.parent for path in captured},{self.folder,second})

    def test_single_preset_export_uses_source_folder_and_type_subfolder(self):
        self.load()
        destination=self.folder/'用户选择的位置';destination.mkdir()
        with patch('desktop.controller.QFileDialog.getExistingDirectory',return_value=str(destination)):
            self.ctrl.exportPreset('JPG_HIGH')
        self.wait(lambda:not self.ctrl.busy)
        output=destination/'高品质 JPG'/'照片 0_Portra 400.jpg'
        self.assertTrue(output.is_file())
        with Image.open(output) as image:self.assertTrue(image.info.get('icc_profile'))

    def test_export_dialog_cancel_does_not_start_a_job(self):
        self.load()
        with patch('desktop.controller.QFileDialog.getExistingDirectory',return_value=''):
            self.ctrl.exportPreset('JPG_HIGH')
        self.assertFalse(self.ctrl.exporting)
        self.assertTrue(self.ctrl.canStartExport)

    def test_film_switch_publishes_new_lut_preview_before_slow_spectral_result(self):
        y,x=np.mgrid[:80,:120]
        rgb=np.stack([x*2,y*3,(x*3+y*2)%256],axis=-1).astype(np.uint8)
        Image.fromarray(rgb,'RGB').save(self.paths[0])
        self.load()
        self.ctrl.setFilmEnabled(True)
        self.wait(lambda:not self.ctrl.busy)
        before=self.ctrl.provider.images['frame'].pixelColor(110,70).getRgb()
        entered=threading.Event();release=threading.Event()
        def slow_spectral(image,settings,**kwargs):
            if settings.spectral:
                entered.set();release.wait(4)
            return render(image,replace(settings,spectral=False))
        with patch('desktop.controller.render',side_effect=slow_spectral):
            try:
                self.ctrl.selectStock('kodak_gold_200')
                generation=self.ctrl._generation
                self.wait(lambda:self.ctrl._quality_generation==generation and self.ctrl._quality==1)
                self.wait(entered.is_set)
                after=self.ctrl.provider.images['frame'].pixelColor(110,70).getRgb()
                self.assertEqual(self.ctrl.settings['stock'],'kodak_gold_200')
                self.assertNotEqual(before,after)
            finally:release.set()
            self.wait(lambda:not self.ctrl.busy)
        self.assertEqual(self.ctrl._quality,2)

    def test_photo_switch_publishes_interactive_frame_before_spectral_render(self):
        self.ctrl.add_paths(self.paths[:2]);self.wait(lambda:not self.ctrl.busy and bool(self.ctrl.frame))
        entered=threading.Event();release=threading.Event()
        def slow_spectral(image,settings,**kwargs):
            if settings.spectral:
                entered.set();release.wait(4)
            return render(image,replace(settings,spectral=False))
        with patch('desktop.controller.render',side_effect=slow_spectral):
            try:
                self.ctrl.selectPhoto(1)
                generation=self.ctrl._generation
                self.wait(lambda:self.ctrl._quality_generation==generation and self.ctrl._quality==1)
                self.wait(entered.is_set)
                self.assertEqual(self.ctrl.provider.images['original'].pixelColor(0,0).getRgb()[:3],(130,120,140))
            finally:release.set()
            self.wait(lambda:not self.ctrl.busy)
        self.assertEqual(self.ctrl._quality,2)

    def test_interactive_preview_bypasses_blocked_spectral_job(self):
        self.load();entered=threading.Event();release=threading.Event()
        def slow(image,settings,**kwargs):
            if settings.spectral:entered.set();release.wait(4)
            return render(image,replace(settings,spectral=False))
        with patch('desktop.controller.render',side_effect=slow):
            try:
                self.ctrl.retry();self.wait(entered.is_set)
                self.ctrl.beginEdit();self.ctrl.updateParameter('exposure',1.1)
                generation=self.ctrl._generation
                self.wait(lambda:self.ctrl._quality_generation==generation and self.ctrl._quality==1)
                self.assertFalse(release.is_set());self.assertTrue(self.ctrl.busy)
                self.ctrl.endEdit()
            finally:release.set()
            self.wait(lambda:not self.ctrl.busy)
        self.assertEqual(self.ctrl._quality,2)

    def test_repeated_adjustments_reuse_decode_and_optical_preparation(self):
        self.load()
        with patch('desktop.controller.read_photo',side_effect=AssertionError('unexpected re-decode')),patch('desktop.lens.prepare_photo',side_effect=AssertionError('unexpected re-correction')):
            for value in (.1,.3,.7):
                self.ctrl.beginEdit();self.ctrl.updateParameter('exposure',value)
                self.wait(lambda:self.ctrl._quality_generation==self.ctrl._generation)
                self.ctrl.endEdit();self.wait(lambda:not self.ctrl.busy)

    def test_late_interactive_result_never_replaces_fine_result(self):
        self.load();entered=threading.Event();release=threading.Event()
        def slow(image,settings,**kwargs):
            entered.set();release.wait(4);return image.copy()
        with patch('desktop.controller.render_interactive',side_effect=slow):
            try:
                self.ctrl.beginEdit();self.ctrl.updateParameter('vignette',15);self.wait(entered.is_set)
                self.ctrl.endEdit();generation=self.ctrl._generation
                self.wait(lambda:self.ctrl._quality_generation==generation and self.ctrl._quality==2)
                frame=self.ctrl.frame
            finally:release.set()
            self.wait(lambda:not self.ctrl.busy)
        self.assertEqual(self.ctrl.frame,frame)

    def test_export_is_not_queued_behind_a_slow_spectral_preview(self):
        self.load();entered=threading.Event();release=threading.Event()
        def slow_preview(image,settings,**kwargs):
            entered.set();release.wait(4)
            return render(image,replace(settings,spectral=False))
        target=self.folder/'priority-export.jpg'
        with patch('desktop.controller.render',side_effect=slow_preview):
            try:
                self.ctrl.updateParameter('exposure',.2)
                self.wait(entered.is_set)
                self.assertTrue(self.ctrl.export_to(str(target),preset='JPG_HIGH'))
                self.wait(target.is_file)
                self.assertFalse(release.is_set())
            finally:release.set()
            self.wait(lambda:not self.ctrl.busy)
        with Image.open(target) as image:self.assertEqual(image.size,(120,80))

    def test_continuous_faster_input_still_publishes_interaction_frames(self):
        self.load();published=[]
        self.ctrl.frameChanged.connect(lambda:published.append(self.ctrl._display_generation))
        def slower_than_input(image,settings,**kwargs):
            time.sleep(.04);return image.copy()
        with patch('desktop.controller.render_interactive',side_effect=slower_than_input):
            self.ctrl.beginEdit()
            for step in range(28):
                self.ctrl.updateParameter('exposure',.05*(step+1))
                end=time.monotonic()+.009
                while time.monotonic()<end:self.app.processEvents();time.sleep(.001)
            self.assertGreaterEqual(len(published),2,'Continuous input starved all preview frames')
            self.assertEqual(published,sorted(set(published)))
            self.ctrl.endEdit();self.wait(lambda:not self.ctrl.busy)
        self.assertEqual(self.ctrl._quality_generation,self.ctrl._generation)
        self.assertEqual(self.ctrl._quality,2)

    def test_source_change_invalidates_decode_and_corrected_cache(self):
        self.load();Image.new('RGB',(63,41),(20,30,40)).save(self.paths[0])
        self.assertEqual(self.ctrl._source(self.paths[0],1440).size,(63,41))

if __name__=='__main__':unittest.main()
