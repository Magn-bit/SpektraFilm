"""Bounded controller auto transactions and shared mask-overlay geometry."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from dataclasses import asdict, replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw
from PySide6.QtWidgets import QApplication

from desktop.controller import Controller, PhotoProvider
from desktop.imaging import Settings
from desktop import native_spectral
from desktop.raw_source import display_image
from shared.auto_adjust import analyze_auto
from shared.geometry import Geometry, apply_geometry_pixels
from shared.local_masks import MaskLayer, MaskStroke, rasterize_mask


class AutoMaskControllerIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    @unittest.skipUnless(native_spectral.available(),'native editor runtime required')
    def test_auto_tone_uses_baseline_once_and_geometry_is_absolute_undoable(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.png';Image.new('RGB',(127,79),'grey').save(path)
            provider=PhotoProvider();ctrl=Controller(provider,folder)
            try:
                linear=np.linspace(.01,.6,79*127*3,dtype=np.float32).reshape(79,127,3)
                image=display_image(linear,metadata={'source_color_space':'sRGB','source_linear':True,'baseline_exposure_ev':.7})
                original=Settings(exposure=.9,temperature=5400,lens_correction=False,defringe=False)
                ctrl._photos.append(dict(path=str(path),name=path.name,width=127,height=79,dimensions='127 × 79',settings=asdict(original)))
                ctrl._current=0;ctrl._settings=original;ctrl._source=lambda *_:image
                ctrl._sync_editor_bindings()

                def run(kind, *, obsolete=False):
                    work=[]
                    with patch.object(ctrl,'_submit',side_effect=lambda fn,context,**_:work.append((fn,context))):
                        ctrl.autoAdjust(kind)
                    fn,context=work.pop()
                    value=fn()
                    if obsolete:ctrl._generation+=1
                    ctrl._done(dict(context,job=-1,ok=True,value=value))
                    ctrl.timer.stop();ctrl.fast_timer.stop()
                    return value

                pre=native_spectral.process_editor(linear,original,stage='pre',exposure_ev=.7,source_linear=True)
                expected=analyze_auto(pre,'tone',original)
                proposal=run('tone')
                self.assertEqual(proposal['changes'],expected['changes'])
                self.assertEqual(ctrl._settings.exposure,expected['changes']['exposure'])
                applied=ctrl._settings
                self.assertEqual(len(ctrl._history[0]),1)
                run('tone')
                self.assertEqual(ctrl._settings,applied,'repeating auto must not add previous exposure again')
                self.assertEqual(len(ctrl._history[0]),1)
                ctrl.undo();ctrl.timer.stop();ctrl.fast_timer.stop();self.assertEqual(ctrl._settings,original)
                ctrl.redo();ctrl.timer.stop();ctrl.fast_timer.stop();self.assertEqual(ctrl._settings,applied)
                before=ctrl._settings
                run('levels',obsolete=True)
                self.assertEqual(ctrl._settings,before,'late proposals must not overwrite changed settings')
                grid=Image.new('RGB',(480,360),'white');draw=ImageDraw.Draw(grid)
                for y in range(40,340,50):draw.line((15,y,465,y),fill='black',width=3)
                for x in range(40,460,70):draw.line((x,15,x,345),fill='black',width=3)
                tilted=grid.rotate(3,resample=Image.Resampling.BILINEAR,fillcolor='white')
                ctrl._source=lambda *_:tilted
                previous=replace(ctrl._settings,geometry=Geometry(rotation=9,crop=(.1,.1,.9,.9)))
                ctrl._settings=previous
                result=run('geometry')
                angle=result['changes']['geometry']['rotation']
                self.assertAlmostEqual(ctrl._settings.geometry.rotation,angle)
                self.assertAlmostEqual(abs(angle),3,delta=.35)
                self.assertEqual(ctrl._settings.geometry.crop,previous.geometry.crop)
            finally:
                ctrl.close()

    def test_mask_overlay_task_matches_geometry_and_recolor_keeps_coverage(self):
        # Run the actual worker synchronously, capturing its immutable QImage
        # result. The expected alpha follows the editor's source-space raster.
        from desktop.mask_overlay import MaskOverlay, _Task
        provider=PhotoProvider();service=MaskOverlay(provider)
        replies=[];service.finished.connect(replies.append)
        width,height=390,270
        layer=MaskLayer(id='sample',kind='radial',center=(.56,.47),radius_x=.24,radius_y=.31,rotation=23,feather=.78)
        geometry=Geometry(rotation=7,vertical=9,crop=(.1,.12,.9,.86))
        try:
            service.update(layer,(width,height),geometry)
            key=service.key
            _Task(service,key,'red').run()
            result=replies.pop()
            self.assertIsNone(result[-1],result[-1])
            alpha=result[2]
            raw=rasterize_mask(layer,width,height)
            expected=apply_geometry_pixels(np.repeat(raw[...,None],3,axis=2),geometry)[...,0]
            # The display may use bicubic resampling; expected actual edits use
            # bilinear. At this soft radial edge only sub-percent differences
            # are acceptable, with identical geometry and output dimensions.
            self.assertEqual(alpha.shape,expected.shape)
            self.assertLess(float(np.mean(np.abs(alpha-expected))),.001)
            service.cache_key,service.cache_alpha=key,alpha
            _Task(service,key,'cyan').run()
            recolor=replies.pop()
            self.assertIsNone(recolor[-1])
            np.testing.assert_array_equal(recolor[2],alpha)
            self.assertEqual(recolor[3].size(),result[3].size())
        finally:service.close()

    @unittest.skipUnless(native_spectral.available(),'native editor runtime required')
    def test_1024_overlay_tracks_actual_source_scaled_mask_and_geometry(self):
        from desktop.mask_overlay import MaskOverlay, _Task
        from shared.color_management import decode
        service=MaskOverlay(PhotoProvider());replies=[];service.finished.connect(replies.append)
        full_width,full_height=2333,1555
        width,height=1024,round(full_height*1024/full_width)
        geometry=Geometry(rotation=-4,vertical=7,crop=(.13,.08,.92,.91))
        layer=MaskLayer(id='scaled-radial',kind='radial',center=(.62,.38),radius_x=.28,radius_y=.34,
                        rotation=26,feather=.79,exposure=1)
        try:
            service.update(layer,(full_width,full_height),geometry)
            _Task(service,service.key,'red').run();result=replies.pop()
            self.assertIsNone(result[-1],result[-1])
            source=np.full((height,width,3),.3,np.float32)
            edited=native_spectral.process_editor(source,{'masks':[asdict(layer)]},stage='post',
                source_size=(full_width,full_height),pixel_scale=(full_width/width,full_height/height))
            # exposure=1 doubles the covered linear value; invert the actual
            # native compositing to obtain its alpha before geometric mapping.
            alpha=(decode(edited[...,0])/float(decode(np.array(.3,np.float32))))-1.
            expected=apply_geometry_pixels(np.repeat(alpha[...,None],3,axis=2),geometry)[...,0]
            actual=result[2]
            self.assertEqual(actual.shape,expected.shape)
            self.assertLess(float(np.mean(np.abs(actual-expected))),.001)
            self.assertLess(float(np.percentile(np.abs(actual-expected),99)),.006)
        finally:service.close()


if __name__=='__main__':unittest.main()
