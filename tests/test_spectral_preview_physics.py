"""Proxy previews retain grain controls and the full-frame physical scale."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor'))
from desktop import imaging
import spektrafilm
sys.path.append(str(ROOT/'android/app/src/main/python'))
import studio_spectral


class SpectralPreviewPhysicsTests(unittest.TestCase):
    def test_desktop_preview_grain_reaches_pixels_instead_of_disappearing(self):
        image=Image.new('RGB',(256,192),(128,128,128))
        original_init=imaging.init_film_params
        def params(stock,paper):
            result=original_init(stock,paper)
            result.print_render.glare.active=False
            return result
        with imaging._SPECTRAL_CONTEXTS_LOCK:
            imaging._SPECTRAL_CONTEXTS.clear()
            imaging._SPECTRAL_CONTEXT_SIGNATURES.clear()
        settings=imaging.Settings(spectral=True,grain=100,grain_size=2.5,halation=0)
        with patch.object(imaging,'init_film_params',side_effect=params):
            without=np.asarray(imaging.render(image,replace(settings,grain=0),preview=True))
            with_grain=np.asarray(imaging.render(image,settings,preview=True))
            fine=np.asarray(imaging.render(image,replace(settings,grain_type='fine'),preview=True))
        self.assertGreater(float(np.abs(with_grain.astype(float)-without).mean()),.1)
        self.assertFalse(np.array_equal(fine,with_grain))
        simulator=next(reversed(imaging._SPECTRAL_CONTEXTS.values()))
        self.assertTrue(simulator._pipeline.film_render.grain.active)
        self.assertAlmostEqual(simulator._pipeline._resize_service.pixel_size_um,35000/256)

    def test_android_whole_proxy_and_export_tile_have_distinct_physical_scale(self):
        def params(preview):
            return studio_spectral._make_params('kodak_portra_400',768,512,9600,6400,
                                                0,1,1,'classic',0,preview)
        proxy,tile=params(True),params(False)
        self.assertTrue(proxy.film_render.grain.active)
        self.assertFalse(proxy.settings.preview_mode)
        self.assertEqual(proxy.camera.film_format_mm,35)
        self.assertAlmostEqual(tile.camera.film_format_mm,35*768/9600)
        self.assertEqual(proxy.film_render.grain.particle_area_um2,
                         tile.film_render.grain.particle_area_um2)


if __name__=='__main__':
    unittest.main()
