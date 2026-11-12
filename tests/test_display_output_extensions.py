"""The ICC/display and HEIF boundary added at the 2.2 integration milestone."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from desktop.color_display import transform_pixels
from desktop.output import export_pixels
from desktop.imaging import read_photo
from shared.color_management import convert_pixels,icc_profile
from shared.output_recipes import OutputRecipe


class DisplayOutputExtensions(unittest.TestCase):
    def test_standard_display_fast_path_matches_icc_for_all_builtin_spaces(self):
        # A different description bypasses the built-in fast-path identity
        # while leaving the actual ICC matrices/TRCs unchanged.
        profile=icc_profile('sRGB').replace('SpektraFilm'.encode('utf-16-be'),
                                          'SpektraTest'.encode('utf-16-be'))
        values=np.random.default_rng(12).uniform(.015,.97,(17,29,3)).astype(np.float32)
        for space in ('sRGB','Display P3','Adobe RGB (1998)','ProPhoto RGB'):
            source=convert_pixels(values,target=space);saved=source.copy()
            actual=transform_pixels(source,space,dict(monitor=None))
            with patch('desktop.color_display._standard_srgb_monitor',return_value=False):
                reference=transform_pixels(source,space,dict(monitor=profile))
            # ICC stores matrix coefficients in 16.16 and a rounded TRC;
            # direct matrices retain their unrounded definition. The measured
            # bound stays below 0.11 of one 8-bit display code value.
            np.testing.assert_allclose(actual,reference,atol=.0004,rtol=.00001,err_msg=space)
            np.testing.assert_array_equal(source,saved)

    def test_windows_srgb_profile_is_recognized_by_colourants_and_trc(self):
        from desktop.color_display import _standard_srgb_monitor,system_monitor_profile
        path=system_monitor_profile()
        if not path:self.skipTest('No system monitor profile')
        profile=Path(path).read_bytes()
        if Path(path).name.lower()!='srgb color space profile.icm':self.skipTest('Display uses a calibrated ICC')
        self.assertTrue(_standard_srgb_monitor(profile))
        self.assertFalse(_standard_srgb_monitor(icc_profile('Display P3')))
        values=np.random.default_rng(13).uniform(.02,.98,(19,27,3)).astype(np.float32)
        actual=transform_pixels(values,'sRGB',dict(monitor=profile))
        with patch('desktop.color_display._standard_srgb_monitor',return_value=False):
            reference=transform_pixels(values,'sRGB',dict(monitor=profile))
        # Windows' older sRGB profile has rounded D50 colourants and sampled
        # TRCs. The vector path honors both; compare against actual LittleCMS.
        np.testing.assert_allclose(actual,reference,atol=.00016,rtol=.00001)

    def test_float_display_matches_matrix_and_preserves_source(self):
        values=np.random.default_rng(37).uniform(.1,.8,(19,31,3)).astype(np.float32)
        wide=convert_pixels(values,target='ProPhoto RGB');saved=wide.copy()
        display=transform_pixels(wide,'ProPhoto RGB',dict(monitor=icc_profile('Adobe RGB (1998)')))
        np.testing.assert_allclose(display,convert_pixels(values,target='Adobe RGB (1998)'),atol=.00015)
        np.testing.assert_array_equal(wide,saved)

    def test_softproof_gamut_warning_and_original_pixel_dimensions(self):
        values=np.zeros((61,93,3),np.float32);values[:]=(.2,.4,.3);values[:,40:]=(.1,.9,.15)
        proof=transform_pixels(values,'ProPhoto RGB',dict(monitor=icc_profile('sRGB'),proof=icc_profile('sRGB'),gamut=True))
        self.assertTrue(np.isfinite(proof).all());self.assertEqual(proof.shape,values.shape)
        self.assertTrue(np.any((proof[...,0]>.95)&(proof[...,2]>.95)&(proof[...,1]<.05)))

    def test_heif_round_trip_keeps_pixels_and_embeds_adobe_profile(self):
        values=np.full((61,93,3),(.25,.4,.6),np.float32)
        with tempfile.TemporaryDirectory() as root:
            destination=Path(root)/'photo.heic'
            export_pixels(values,destination,OutputRecipe(format='heif',color_space='Adobe RGB (1998)',quality=100))
            import pillow_heif
            with Image.open(destination) as image:
                self.assertEqual(image.size,(93,61))
                self.assertEqual(image.info.get('icc_profile'),icc_profile('Adobe RGB (1998)'))
            source=read_photo(str(destination));self.assertEqual(source.size,(93,61));source.close()


if __name__=='__main__':unittest.main()
