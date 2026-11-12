"""Crop keeps source pixels/film scale and participates in real editor state."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image
from PySide6.QtWidgets import QApplication
from desktop.controller import Controller, PhotoProvider
from desktop.imaging import Settings, film_settings, render_pixels, export_photo
from shared.geometry import Geometry, crop_box


class CropWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def wait(self,ctrl,predicate):
        deadline=time.monotonic()+8
        while not predicate() and time.monotonic()<deadline:
            self.app.processEvents();time.sleep(.003)
        self.assertTrue(predicate(),ctrl.status)

    def test_actual_spectral_crop_is_exact_subrectangle_and_tiff16(self):
        # A small but real Vulkan computation verifies that crop is downstream
        # of physical effects; no camera decode or large-image benchmark here.
        import tifffile
        y,x=np.mgrid[:128,:320]
        rgb=np.stack([40+x*.45,50+y*.65,35+(x+y)*.3],axis=-1).astype(np.uint8)
        base=film_settings(Settings(grain=0,halation=0))
        selected=replace(base,geometry=Geometry(crop=(.1,.2,.8,.9)))
        image=Image.fromarray(rgb)
        full=render_pixels(image,base)
        left,top,right,bottom=crop_box(*image.size,selected.geometry)
        cropped=render_pixels(image,selected)
        np.testing.assert_array_equal(cropped,full[top:bottom,left:right])
        self.assertEqual(cropped.dtype,np.float32)
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.png';target=Path(folder)/'crop.tif'
            image.save(source)
            self.assertEqual(export_photo(str(source),str(target),selected),(right-left,bottom-top))
            result=tifffile.imread(target)
            self.assertEqual(result.dtype,np.uint16)
            np.testing.assert_allclose(result,np.rint(np.clip(cropped,0,1)*65535),atol=1)
            with Image.open(source) as original:self.assertEqual(original.size,(320,128))

    def test_crop_history_persistence_comparison_and_batch_exclusion(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);first=root/'first.png';second=root/'second.png'
            Image.new('RGB',(200,100),(155,120,95)).save(first)
            Image.new('RGB',(200,100),(95,120,155)).save(second)
            ctrl=Controller(PhotoProvider(),folder)
            try:
                with patch('desktop.imaging._spectral',side_effect=lambda rgb,s,**kwargs:rgb.astype(np.float32)/255):
                    ctrl.add_paths([str(first),str(second)])
                    self.wait(ctrl,lambda:not ctrl.busy and bool(ctrl.frame))
                    ctrl.selectPhoto(0)
                    self.wait(ctrl,lambda:not ctrl.busy)
                    ctrl.applyCrop([.1,.2,.7,.8])
                    self.wait(ctrl,lambda:not ctrl.busy)
                    self.assertEqual((ctrl.imageWidth,ctrl.imageHeight),(120,60))
                    self.assertEqual(ctrl.provider.images['original'].size(),ctrl.provider.images['frame'].size())
                    ctrl.undo();self.assertEqual((ctrl.imageWidth,ctrl.imageHeight),(200,100))
                    ctrl.redo();self.assertEqual((ctrl.imageWidth,ctrl.imageHeight),(120,60))
                    record=json.loads(ctrl._edit_path(str(first)).read_text(encoding='utf-8'))
                    self.assertEqual(record['version'],3)
                    self.assertEqual(record['settings']['geometry']['crop'],[.1,.2,.7,.8])
                    ctrl.selectAllPhotos();ctrl.applyCurrentSettings()
                    self.assertEqual(ctrl._photos[1]['settings']['geometry']['crop'],(0.,0.,1.,1.))
                    self.assertEqual(ctrl._photos[0]['settings']['geometry']['crop'],(.1,.2,.7,.8))
                    self.wait(ctrl,lambda:not ctrl.busy)
            finally:
                ctrl.close();self.app.processEvents()


if __name__=='__main__':unittest.main()
