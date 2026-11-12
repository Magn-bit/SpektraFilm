import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'vendor'))

from spektrafilm.runtime.params_builder import init_params
from spektrafilm.utils.gamut_compression import (
    _CAM16UCS_CHUNK_PIXELS,
    compress_rgb,
    compress_rgb_cam16ucs_chroma,
)


class GamutCompressionTests(unittest.TestCase):
    def test_chunked_cam16_matches_upstream_full_frame_bit_for_bit(self):
        spec = init_params('kodak_portra_400', 'kodak_portra_endura').io.output_gamut_compress
        pixels = np.random.default_rng(71).uniform(-0.15, 1.25,
                                                    (_CAM16UCS_CHUNK_PIXELS * 2 + 37, 3))
        expected = compress_rgb_cam16ucs_chroma(
            pixels, output_color_space='sRGB', threshold=spec.knee[0],
            limit=spec.knee[1], power=spec.knee[2],
            lightness_compression=spec.lightness_compression,
        )
        actual = compress_rgb(pixels, spec, output_color_space='sRGB')
        np.testing.assert_array_equal(actual, expected)


if __name__ == '__main__':
    unittest.main()
