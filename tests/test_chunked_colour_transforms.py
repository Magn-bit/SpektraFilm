import importlib
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import colour
import numpy as np
from colour.utilities import domain_range_scale

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vendor'))
scanning = importlib.import_module('spektrafilm.runtime.stages.scanning')
upsampling = importlib.import_module('spektrafilm.utils.spectral_upsampling')


class ChunkedColourTransformTests(unittest.TestCase):
    def setUp(self):
        self.pixels = np.random.default_rng(9104).uniform(-.3, 4., (19, 23, 3))
        self.pixels[0, :6] = np.array([
            [0., 0., 0.], [-1., -.01, 0.], [.0031308, .04045, 1.],
            [1., 2., 10.], [np.nan, .2, .3], [np.inf, 1., -np.inf],
        ])

    def reference_scan(self, values, space):
        return colour.RGB_to_RGB(values, space, space, apply_cctf_decoding=False,
                                 apply_cctf_encoding=True)

    def reference_tc(self, values, space, decode, illuminant):
        xyz = colour.RGB_to_XYZ(values, colourspace=space,
            apply_cctf_decoding=decode, illuminant=upsampling._illuminant_to_xy(illuminant),
            chromatic_adaptation_transform='CAT16')
        brightness = np.sum(xyz, axis=-1)
        xy = xyz[..., :2] / np.fmax(brightness[..., None], 1e-10)
        return upsampling._tri2quad(xy), np.nan_to_num(brightness)

    def test_scan_preserves_original_matrix_transfer_and_domain_range(self):
        stage = object.__new__(scanning.ScanningStage)
        for space in ('sRGB', 'Display P3', 'Adobe RGB (1998)', 'ProPhoto RGB',
                      'ITU-R BT.2020', 'ACES2065-1'):
            stage._io = SimpleNamespace(output_cctf_encoding=True, output_color_space=space)
            for scale in ('reference', '1', '100'):
                for values in (self.pixels, self.pixels[:, ::2], self.pixels.astype(np.float32)):
                    saved = values.copy()
                    with self.subTest(space=space, scale=scale, dtype=values.dtype), \
                            domain_range_scale(scale), np.errstate(invalid='ignore', over='ignore'):
                        reference = self.reference_scan(values, space)
                        with patch.object(scanning, '_ENCODING_CHUNK_PIXELS', 51):
                            actual = stage._apply_cctf_encoding(values)
                        np.testing.assert_array_equal(actual, reference)
                        np.testing.assert_array_equal(values, saved)
                        self.assertFalse(np.shares_memory(actual, values))

    def test_scan_disabled_returns_existing_array_and_empty_input_keeps_shape(self):
        stage = object.__new__(scanning.ScanningStage)
        stage._io = SimpleNamespace(output_cctf_encoding=False, output_color_space='sRGB')
        self.assertIs(stage._apply_cctf_encoding(self.pixels), self.pixels)
        stage._io.output_cctf_encoding = True
        actual = stage._apply_cctf_encoding(np.empty((0, 7, 3)))
        self.assertEqual(actual.shape, (0, 7, 3))

    def test_exposure_projection_keeps_colour_domains_adaptation_and_geometry(self):
        for space in ('sRGB', 'Display P3', 'ProPhoto RGB', 'ITU-R BT.2020'):
            for decode in (False, True):
                for illuminant in ('D55', 'D65'):
                    for scale in ('reference', '1', '100'):
                        values = self.pixels[:, ::2]
                        with self.subTest(space=space, decode=decode, illuminant=illuminant, scale=scale), \
                                domain_range_scale(scale), np.errstate(invalid='ignore', over='ignore'):
                            reference_tc, reference_b = self.reference_tc(values, space, decode, illuminant)
                            with patch.object(upsampling, '_RGB_TO_TC_CHUNK_PIXELS', 51):
                                actual_tc, actual_b = upsampling._rgb_to_tc_b(values, space, decode, illuminant)
                            np.testing.assert_array_equal(actual_tc, reference_tc)
                            np.testing.assert_array_equal(actual_b, reference_b)
                            self.assertFalse(np.shares_memory(actual_tc, values))
                            self.assertFalse(np.shares_memory(actual_b, values))

    def test_exposure_flat_and_singleton_inputs_preserve_geometry(self):
        for values in (self.pixels.reshape(-1, 3), self.pixels[:1],
                       self.pixels[0, 0], np.empty((0, 7, 3))):
            with np.errstate(invalid='ignore', over='ignore'):
                reference_tc, reference_b = self.reference_tc(values, 'sRGB', True, 'D55')
                with patch.object(upsampling, '_RGB_TO_TC_CHUNK_PIXELS', 51):
                    actual_tc, actual_b = upsampling._rgb_to_tc_b(values, 'sRGB', True, 'D55')
            np.testing.assert_array_equal(actual_tc, reference_tc)
            np.testing.assert_array_equal(actual_b, reference_b)


if __name__ == '__main__':
    unittest.main()
