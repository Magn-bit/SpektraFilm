import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from PySide6.QtWidgets import QApplication
from desktop.controller import Controller,PhotoProvider
from desktop.imaging import render as image_render
from dataclasses import replace

class ControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        # State/queue tests isolate expensive physics; actual EXE tests cover it.
        self.renderer=patch('desktop.controller.render',side_effect=lambda im,s,**kwargs:image_render(im,replace(s,spectral=False)))
        self.renderer.start();self.addCleanup(self.renderer.stop)
        self.physics=patch('desktop.imaging._spectral',side_effect=lambda rgb,s,**kwargs:rgb.astype('float32')/255 if rgb.dtype.name=='uint8' else rgb.copy())
        self.physics.start();self.addCleanup(self.physics.stop)
        self.temp=tempfile.TemporaryDirectory()
        self.directory=Path(self.temp.name)
        self.provider=PhotoProvider()
        self.ctrl=Controller(self.provider,self.temp.name)
        self.first=self.directory/'first.png'
        self.second=self.directory/'second.png'
        Image.new('RGB',(32,24),(150,120,90)).save(self.first)
        Image.new('RGB',(24,32),(90,120,150)).save(self.second)

    def tearDown(self):
        self.ctrl.close()
        self.app.processEvents()
        self.temp.cleanup()

    def wait_for(self,predicate,timeout=5):
        limit=time.monotonic()+timeout
        while not predicate() and time.monotonic()<limit:
            self.app.processEvents()
            time.sleep(.005)
        self.assertTrue(predicate(),'Asynchronous operation timed out: '+self.ctrl.status)

    def load(self,paths=None):
        self.ctrl.add_paths(paths or [str(self.first)])
        self.wait_for(lambda:not self.ctrl.busy and bool(self.ctrl.frame))

    def test_product_settings_always_use_full_spectral_mode(self):
        self.assertTrue(self.ctrl.settings['spectral'])
        self.assertTrue(self.ctrl.settings['film_enabled'])
        self.ctrl.setSpectral(False)
        self.assertTrue(self.ctrl.settings['spectral'])
        self.load()
        self.assertTrue(self.ctrl.photos[0]['settings']['spectral'])
        self.ctrl.reset()
        self.assertTrue(self.ctrl.settings['spectral'])
        self.assertTrue(self.ctrl.settings['film_enabled'])

    def test_film_cannot_be_disabled_by_legacy_calls(self):
        self.load()
        before=self.ctrl.settings
        self.ctrl.setFilmEnabled(False)
        self.ctrl.setSpectral(False)
        self.assertEqual(self.ctrl.settings,before)
        self.assertTrue(self.ctrl.settings['film_enabled'])
        self.assertTrue(self.ctrl.settings['spectral'])

    def test_legacy_edit_without_film_switch_keeps_old_film_behavior(self):
        self.ctrl._edit_path(str(self.first)).write_text(json.dumps({'settings':{'exposure':.25}}),encoding='utf-8')
        self.load()
        self.assertTrue(self.ctrl.settings['film_enabled'])

    def test_drag_is_one_undo_and_redo_step(self):
        self.load()
        self.ctrl.beginEdit()
        for value in [.2,.5,1.2]:self.ctrl.updateParameter('exposure',value)
        self.ctrl.endEdit()
        self.assertTrue(self.ctrl.canUndo)
        self.ctrl.undo();self.assertEqual(self.ctrl.settings['exposure'],0)
        self.assertFalse(self.ctrl.canUndo)
        self.ctrl.redo();self.assertEqual(self.ctrl.settings['exposure'],1.2)










    def test_retry_invalidates_current_render_but_not_source_decode(self):
        self.load();path=str(self.first);epoch=self.ctrl._render_epochs.get(path,0)
        self.assertTrue(any(key[0]==path for key in self.ctrl._mask_bases))
        with patch('desktop.controller.read_photo',side_effect=AssertionError('retry should reuse decoded source')):
            self.ctrl.retry();self.wait_for(lambda:not self.ctrl.busy)
        self.assertEqual(self.ctrl._render_epochs[path],epoch+1)

    def test_each_photo_retains_its_own_edit_history(self):
        self.load([str(self.first),str(self.second)])
        self.ctrl.updateParameter('exposure',1)
        self.ctrl.selectPhoto(1)
        self.assertEqual(self.ctrl.settings['exposure'],0)
        self.assertFalse(self.ctrl.canUndo)
        self.ctrl.updateParameter('vignette',12)
        self.ctrl.selectPhoto(0)
        self.assertEqual(self.ctrl.settings['exposure'],1)
        self.assertEqual(self.ctrl.settings['vignette'],0)
        self.ctrl.undo()
        self.assertEqual(self.ctrl.settings['exposure'],0)
        self.ctrl.selectPhoto(1)
        self.assertEqual(self.ctrl.settings['vignette'],12)

    def test_persisted_edits_restore_in_a_new_controller(self):
        self.load();self.ctrl.updateParameter('vignette',13)
        other=Controller(PhotoProvider(),self.temp.name)
        try:
            other.add_paths([str(self.first)])
            self.wait_for(lambda:not other.busy and bool(other.frame))
            self.assertEqual(other.settings['vignette'],13)
        finally:other.close()

    def test_malformed_saved_values_do_not_break_import(self):
        self.ctrl._edit_path(str(self.first)).write_text(json.dumps({'settings':{'exposure':'bad','strength':None,'stock':[]}}),encoding='utf-8')
        self.load()
        self.assertEqual(self.ctrl.settings['exposure'],0)

    def test_old_render_is_not_published_after_new_settings(self):
        started=threading.Event();release=threading.Event();published=[]
        def controlled_render(image,settings,**kwargs):
            if settings.exposure==0:
                started.set()
                if not release.wait(4):raise RuntimeError('render synchronization timed out')
            return Image.new('RGB',image.size,(210 if settings.exposure==1 else 10,0,0))
        self.ctrl.frameChanged.connect(lambda:published.append(self.provider.images['frame'].pixelColor(0,0).red()) if self.ctrl.frame else None)
        with patch('desktop.controller.render',side_effect=controlled_render):
            try:
                self.ctrl.add_paths([str(self.first)])
                self.wait_for(started.is_set)
                self.ctrl.updateParameter('exposure',1)
            finally:release.set()
            self.wait_for(lambda:not self.ctrl.busy and bool(self.ctrl.frame))
        self.assertEqual(published[-1],210)
        self.assertNotIn(10,published)

    def test_broken_photo_does_not_prevent_valid_import(self):
        broken=self.directory/'broken.jpg';broken.write_bytes(b'invalid')
        errors=[];self.ctrl.toast.connect(errors.append)
        self.load([str(broken),str(self.first)])
        self.assertEqual(len(self.ctrl.photos),1)
        self.assertEqual(self.ctrl.filename,'first.png')
        self.assertEqual(len(errors),1)

    def test_import_is_async_and_duplicate_requests_are_coalesced(self):
        self.ctrl.add_paths([str(self.first),str(self.first)])
        self.assertEqual(len(self.ctrl.photos),0)
        self.assertTrue(self.ctrl.busy)
        self.ctrl.add_paths([str(self.first)])
        self.wait_for(lambda:not self.ctrl.busy and bool(self.ctrl.frame))
        self.assertEqual(len(self.ctrl.photos),1)

    def test_import_registers_paths_without_decoding_the_batch_thumbnails(self):
        with patch('desktop.controller.read_thumbnail',side_effect=AssertionError('thumbnail decode must be on demand')):
            self.ctrl.add_paths([str(self.first),str(self.second)])
            self.wait_for(lambda:not self.ctrl.busy and bool(self.ctrl.frame))
        self.assertEqual(len(self.ctrl.photos),2)
        self.assertEqual(len(self.provider.thumbnail_sources),2)

    def test_thumbnail_cache_is_bounded_and_evicted_entries_reload_on_demand(self):
        from PySide6.QtCore import QSize
        thumb=self.directory/'thumb.png'
        Image.new('RGB',(320,240),(90,120,150)).save(thumb)
        for index in range(70): self.provider.publish_thumbnail(f'thumb{index}',str(thumb),Image.new('RGB',(40,30),(90,120,150)))
        self.assertLessEqual(len(self.provider.thumbnail_order),64)
        restored=self.provider.requestImage('thumb0',QSize(),QSize())
        self.assertFalse(restored.isNull())

    def test_actual_size_reloads_full_resolution(self):
        Image.new('RGB',(1600,80),(140,120,100)).save(self.first)
        self.load()
        self.assertNotIn((str(self.first),0),self.ctrl._cache)
        self.assertEqual(self.provider.images['original'].width(),800)
        self.ctrl.setActualSize(True)
        self.wait_for(lambda:not self.ctrl.busy)
        self.assertEqual(self.ctrl._cache[(str(self.first),0)].size,(1600,80))
        self.assertEqual(self.provider.images['original'].width(),1600)
        self.assertTrue(self.ctrl.detailReady)
        self.ctrl.setActualSize(False)
        self.wait_for(lambda:not self.ctrl.busy)
        self.assertEqual(self.provider.images['original'].width(),800)

    def test_remove_remaps_surviving_history_and_keeps_sources(self):
        third=self.directory/'third.png';Image.new('RGB',(24,24),'green').save(third)
        self.load([str(self.first),str(self.second),str(third)])
        self.ctrl.updateParameter('exposure',.8)
        self.ctrl.selectPhoto(2);self.ctrl.updateParameter('vignette',11)
        self.ctrl.selectPhoto(1);self.ctrl.removeSelectedPhotos()
        self.wait_for(lambda:not self.ctrl.busy)
        self.assertEqual([p['name'] for p in self.ctrl.photos],['first.png','third.png'])
        self.assertEqual(self.ctrl.currentIndex,1)
        self.assertEqual(self.ctrl.settings['vignette'],11)
        self.ctrl.undo();self.assertEqual(self.ctrl.settings['vignette'],0)
        self.ctrl.selectPhoto(0);self.assertEqual(self.ctrl.settings['exposure'],.8)
        self.ctrl.undo();self.assertEqual(self.ctrl.settings['exposure'],0)
        self.assertTrue(all(p.is_file() for p in (self.first,self.second,third)))

    def test_remove_all_clears_frame_keeps_edits_and_thumbnail_keys_unique(self):
        self.load([str(self.first),str(self.second)])
        self.ctrl.updateParameter('vignette',12)
        keys={p['thumbnail'] for p in self.ctrl.photos}
        self.ctrl.selectAllPhotos();self.ctrl.removeSelectedPhotos()
        self.wait_for(lambda:not self.ctrl.busy)
        self.assertEqual(self.ctrl.currentIndex,-1);self.assertEqual(self.ctrl.photos,[])
        self.assertEqual(self.ctrl.frame,'');self.assertNotIn('frame',self.provider.images)
        self.assertEqual(self.ctrl.selectedCount,0)
        self.assertTrue(self.ctrl._edit_path(str(self.first)).exists())
        self.load();self.assertEqual(self.ctrl.settings['vignette'],12)
        self.assertNotIn(self.ctrl.photos[0]['thumbnail'],keys)

    def test_remove_during_render_never_resurrects_old_frame(self):
        self.load()
        entered=threading.Event();release=threading.Event()
        def delayed(image,settings,**kwargs):
            entered.set();release.wait(4);return image.copy()
        with patch('desktop.controller.render',side_effect=delayed):
            try:
                self.ctrl.updateParameter('exposure',.4)
                self.wait_for(entered.is_set)
                self.ctrl.removeSelectedPhotos()
            finally:release.set()
            self.wait_for(lambda:not self.ctrl.busy)
        self.assertEqual(self.ctrl.frame,'');self.assertEqual(self.ctrl.currentIndex,-1)
        self.assertNotIn('frame',self.provider.images)

    def test_remove_is_blocked_during_export(self):
        self.load();self.ctrl._exporting=True
        self.ctrl.removeSelectedPhotos()
        self.assertEqual(len(self.ctrl.photos),1)
        self.ctrl._exporting=False

    def test_source_dimensions_are_independent_of_preview_size(self):
        Image.new('RGB',(2000,100),(140,120,100)).save(self.first)
        self.load()
        self.assertEqual((self.ctrl.imageWidth,self.ctrl.imageHeight),(2000,100))
        self.assertFalse(self.ctrl.detailReady)

    def test_high_quality_export_uses_original_not_preview_dimensions(self):
        Image.new('RGB',(1600,80),(140,120,100)).save(self.first)
        self.load()
        self.assertEqual(self.provider.images['original'].width(),800)
        target=self.directory/'original-size.jpg'
        self.assertTrue(self.ctrl.export_to(str(target),preset='JPG_HIGH'))
        self.wait_for(lambda:not self.ctrl.busy)
        with Image.open(target) as image:
            self.assertEqual(image.size,(1600,80))
        self.assertFalse(self.ctrl.canExportRaw)
        self.assertFalse(self.ctrl.export_to(str(self.directory/'fake.dng'),preset='RAW'))

    def test_export_can_start_while_preview_is_pending_and_uses_current_settings(self):
        self.load()
        target=self.directory/'export.png'
        self.ctrl.updateParameter('exposure',1)
        self.assertTrue(self.ctrl.canStartExport)
        self.assertTrue(self.ctrl.export_to(str(target)))
        self.wait_for(lambda:not self.ctrl.busy)
        with Image.open(target) as image:
            self.assertEqual(image.size,(32,24))
            self.assertIn('icc_profile',image.info)

if __name__=='__main__':unittest.main()
