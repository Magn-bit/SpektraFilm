import importlib.util
import json
from dataclasses import asdict, replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'vendor'))
from shared.local_masks import MaskLayer, MaskStroke, apply_masks, normalize_masks, masks_to_json, rasterize_mask
from desktop.imaging import Settings, render, render_interactive, export_photo


class LocalMaskTests(unittest.TestCase):
    def test_vector_document_roundtrip_and_untrusted_value_validation(self):
        layer = MaskLayer('sky', '天空', exposure=-.8,
                          strokes=(MaskStroke(((.1,.2),(.8,.2)), .12, .8, .6),))
        self.assertEqual(normalize_masks(masks_to_json((layer,))), (layer,))
        self.assertEqual(Settings.from_mapping({'masks': [asdict(layer)]}).masks, (layer,))
        bad = normalize_masks([{'exposure':float('nan'), 'opacity':9, 'strokes':[
            {'points':[[1.5,-.2],['bad',.2],[.2,float('inf')]], 'radius':-1}]}])[0]
        self.assertEqual(bad.exposure, 0)
        self.assertEqual(bad.opacity, 1)
        self.assertEqual(bad.strokes[0].points, ((1.,0.),))
        self.assertEqual(bad.strokes[0].radius, .002)
        self.assertEqual(normalize_masks('malformed'), ())

    def test_continuous_brush_is_independent_of_pointer_sample_density(self):
        sparse = MaskStroke(((.2,.5),(.8,.5)), .13, .8, .6)
        dense = replace(sparse, points=tuple((float(x),.5) for x in np.linspace(.2,.8,61)))
        first = rasterize_mask(MaskLayer(strokes=(sparse,)), 241, 159)
        second = rasterize_mask(MaskLayer(strokes=(dense,)), 241, 159)
        np.testing.assert_allclose(first, second, atol=1e-7)
        self.assertAlmostEqual(float(first.max()), .6, places=6)

    def test_soft_edges_flow_erasure_inversion_and_opacity(self):
        stroke = MaskStroke(((.5,.5),), .3, 1., .5)
        alpha = rasterize_mask(MaskLayer(strokes=(stroke,)), 101, 101)
        self.assertAlmostEqual(float(alpha[50,50]), .5)
        self.assertGreater(alpha[50,65], 0)
        self.assertLess(alpha[50,65], alpha[50,50])
        self.assertEqual(alpha[0,0], 0)
        accumulated = rasterize_mask(MaskLayer(strokes=(stroke,stroke)), 101, 101)
        self.assertAlmostEqual(float(accumulated[50,50]), .75)
        erased = rasterize_mask(MaskLayer(strokes=(stroke, replace(stroke, erase=True, flow=1))), 101, 101)
        self.assertEqual(erased[50,50], 0)
        inverted = rasterize_mask(MaskLayer(inverted=True,strokes=(stroke,)), 101, 101)
        np.testing.assert_allclose(inverted, 1-alpha)
        image = np.full((101,101,3), .4, np.float32)
        result = apply_masks(image.copy(), (MaskLayer(exposure=1,opacity=0,strokes=(stroke,)),))
        np.testing.assert_array_equal(result, image)

    def test_region_raster_and_local_edits_are_seamless_across_tiles(self):
        layer = MaskLayer(exposure=.8,temperature=20,tint=-12,saturation=18,
            highlights=-22,shadows=15,strokes=(
                MaskStroke(((.1,.1),(.9,.8)), .17, .8, .65),
                MaskStroke(((.4,.4),(.5,.5)), .05, .6, .4, True)))
        source = np.random.default_rng(51).uniform(.1,.85,(183,271,3)).astype(np.float32)
        whole = apply_masks(source.copy(), (layer,))
        tiled = source.copy()
        for top in range(0,183,37):
            for left in range(0,271,43):
                tile = tiled[top:top+37,left:left+43].copy()
                apply_masks(tile, (layer,), 271,183,left,top)
                tiled[top:top+37,left:left+43] = tile
        np.testing.assert_array_equal(whole,tiled)

    def test_mask_only_changes_its_coverage_and_neutral_is_bit_exact(self):
        source = np.random.default_rng(9).uniform(.1,.7,(61,83,3)).astype(np.float32)
        stroke = MaskStroke(((.5,.5),), .2, .75)
        layer = MaskLayer(exposure=1,strokes=(stroke,))
        alpha = rasterize_mask(layer,83,61)
        result = apply_masks(source.copy(), (layer,))
        np.testing.assert_array_equal(result[alpha==0], source[alpha==0])
        self.assertGreater(float(result[30,41].sum()),float(source[30,41].sum()))
        for neutral in (replace(layer,enabled=False), replace(layer,exposure=0), replace(layer,opacity=0)):
            np.testing.assert_array_equal(apply_masks(source.copy(),(neutral,)),source)

    def test_lower_level_render_helpers_keep_local_edits_without_film(self):
        with tempfile.TemporaryDirectory() as directory:
            src=Path(directory)/'input.png';dst=Path(directory)/'local.tif'
            image=Image.new('RGB',(173,119),(100,110,120));image.save(src)
            layer=MaskLayer('one','局部',exposure=.8,strokes=(MaskStroke(((.3,.5),),.25),))
            settings=Settings(film_enabled=False,lens_correction=False,defringe=False,masks=(layer,))
            with patch('desktop.imaging._spectral',side_effect=AssertionError('No film pass')):
                fine=render(image,settings)
                fast=render_interactive(image,settings)
            np.testing.assert_array_equal(np.asarray(fine),np.asarray(fast))
            self.assertEqual(fine.getpixel((172,0)),image.getpixel((172,0)))
            self.assertGreater(fine.getpixel((52,59))[0],image.getpixel((52,59))[0])

    def test_android_copy_matches_shared_source_and_bridge_preserves_tile_coordinates(self):
        self.assertEqual((ROOT/'shared/local_masks.py').read_bytes(),
                         (ROOT/'android/app/src/main/python/local_masks.py').read_bytes())
        sys.path.insert(0,str(ROOT/'android/app/src/main/python'))
        try:
            spec=importlib.util.spec_from_file_location('mask_bridge',ROOT/'android/app/src/main/python/studio_spectral.py')
            bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
            source=np.full((47,61),0xff646e78,dtype='<u4')
            layer=MaskLayer(exposure=1,strokes=(MaskStroke(((.4,.5),(.7,.6)),.2),))
            payload=masks_to_json((layer,))
            whole=bridge.apply_masks_argb(source.tobytes(),61,47,payload)
            stitched=np.empty_like(source)
            for left,right in ((0,23),(23,61)):
                tile=source[:,left:right].copy()
                result=bridge.apply_masks_argb(tile.tobytes(),right-left,47,payload,61,47,left,0)
                stitched[:,left:right]=np.frombuffer(result,dtype='<u4').reshape(47,right-left)
            np.testing.assert_array_equal(np.frombuffer(whole,dtype='<u4').reshape(47,61),stitched)
            basic=bridge.render_argb(source.tobytes(),61,47,'kodak_portra_400',0,0,0,1,
                                     film_enabled=False,masks_json=payload)
            np.testing.assert_array_equal(np.frombuffer(basic,dtype='<u4'),np.frombuffer(whole,dtype='<u4'))
        finally:
            sys.path.remove(str(ROOT/'android/app/src/main/python'))


if __name__=='__main__': unittest.main()
