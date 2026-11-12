from dataclasses import asdict, replace
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch, Mock

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor'))
from desktop.imaging import Settings, render, render_interactive
from shared.color_tools import CurveSet, ColorGrading, TonalGrade, color_tools_json
from shared.local_masks import MaskLayer, masks_to_json


class ColorPipelineTests(unittest.TestCase):
    def setUp(self):
        self.curves=CurveSet(master=((0.,0.),(.4,.45),(1.,1.)),luma=((0.,0.),(.6,.64),(1.,1.)))
        self.grading=ColorGrading(shadows=TonalGrade(216,12),highlights=TonalGrade(42,9))

    def bridge(self):
        directory=str(ROOT/'android/app/src/main/python')
        sys.path.insert(0,directory)
        self.addCleanup(lambda:sys.path.remove(directory))
        spec=importlib.util.spec_from_file_location('color_pipeline_bridge',Path(directory)/'studio_spectral.py')
        bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
        return bridge

    def test_settings_roundtrip_and_film_off_fast_fine_match(self):
        settings=Settings(film_enabled=False,curves=self.curves,grading=self.grading)
        self.assertEqual(Settings.from_mapping(asdict(settings)),settings)
        image=Image.new('RGB',(131,79),(90,120,145))
        fast=np.asarray(render_interactive(image,settings))
        fine=np.asarray(render(image,settings))
        np.testing.assert_array_equal(fast,fine)
        self.assertGreater(float(fine.mean()),float(np.asarray(image).mean()))

    def test_post_development_colour_changes_reuse_spectral_preview(self):
        image=Image.new('RGB',(91,61),(91,100,110));image._spektrafilm_preview_cache={}
        settings=Settings(spectral=True)
        with patch('desktop.imaging._spectral',return_value=np.full((61,91,3),.4,np.float32)) as spectral:
            first=render(image,settings,preview=True)
            second=render(image,replace(settings,curves=self.curves,grading=self.grading),preview=True)
            self.assertEqual(spectral.call_count,1)
            render(image,replace(settings,grain=25),preview=True)
            self.assertEqual(spectral.call_count,2)
        self.assertFalse(np.array_equal(np.asarray(first),np.asarray(second)))

    def test_highlights_positive_brightens_like_local_highlights(self):
        image=Image.new('RGB',(39,27),(200,200,200))
        settings=Settings(film_enabled=False)
        dark=render(image,replace(settings,highlights=-50)).getpixel((10,10))[0]
        light=render(image,replace(settings,highlights=50)).getpixel((10,10))[0]
        self.assertLess(dark,200)
        self.assertGreater(light,200)

    def test_android_colour_and_gradient_tiles_equal_whole_output(self):
        bridge=self.bridge()
        source=np.full((47,61),0xff64788c,dtype='<u4')
        payload=color_tools_json(self.curves,self.grading)
        masks=masks_to_json((MaskLayer(kind='radial',center=(.4,.6),radius_x=.3,radius_y=.2,
                                      rotation=21,exposure=.5),))
        def run(tile,x=0,y=0):
            return bridge.render_argb(tile.tobytes(),tile.shape[1],tile.shape[0],
                'kodak_portra_400',0,0,0,1,source_width=61,source_height=47,
                film_enabled=False,color_json=payload,masks_json=masks,origin_x=x,origin_y=y)
        whole=np.frombuffer(run(source),dtype='<u4').reshape(47,61)
        tiled=np.empty_like(source)
        for y in range(0,47,11):
            for x in range(0,61,19):
                tile=source[y:y+11,x:x+19].copy()
                tiled[y:y+11,x:x+19]=np.frombuffer(run(tile,x,y),dtype='<u4').reshape(tile.shape)
        np.testing.assert_array_equal(tiled,whole)
        lut=bridge.render_lut_argb(source.tobytes(),61,47,b'',2,0,0,0,1,
            film_enabled=False,color_json=payload,masks_json=masks,source_width=61,source_height=47)
        np.testing.assert_array_equal(np.frombuffer(lut,dtype='<u4').reshape(47,61),whole)

    def test_android_preview_cache_excludes_post_processing_and_never_caches_export(self):
        bridge=self.bridge()
        source=np.full((7,11),0xff64788c,dtype='<u4')
        simulator=Mock();simulator.process.side_effect=lambda rgb:rgb.copy()
        simulator._pipeline.process.side_effect=lambda rgb,**taps:rgb.copy()
        with patch.object(bridge,'Simulator',return_value=simulator),patch.object(bridge,'_make_params',return_value=object()):
            def run(**kwargs):
                return bridge.render_argb(source.tobytes(),11,7,'kodak_portra_400',0,0,0,1,**kwargs)
            run(preview_mode=True)
            run(preview_mode=True,color_json=color_tools_json(self.curves,self.grading))
            self.assertEqual(simulator._pipeline.process.call_count,2)
            self.assertEqual(simulator.process.call_count,0)
            run(preview_mode=False)
            run(preview_mode=False)
            self.assertEqual(simulator.process.call_count,2)
            self.assertEqual(simulator._pipeline.process.call_count,2)


if __name__=='__main__':unittest.main()
