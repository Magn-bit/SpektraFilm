"""Small evidence checks for conservative automatic perspective proposals."""
import unittest

import numpy as np
from PIL import Image, ImageDraw

from shared.auto_adjust import analyze_auto
from shared.geometry import Geometry, apply_geometry_pixels


def _grid(width=480, height=360):
    image = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(image)
    for y in range(30, height - 20, 45):
        draw.line((15, y, width - 15, y), fill='black', width=3)
    for x in range(30, width - 20, 55):
        draw.line((x, 15, x, height - 15), fill='black', width=3)
    return np.asarray(image, dtype=np.float32) / 255.


class AutomaticPerspectiveTest(unittest.TestCase):
    def test_full_perspective_uses_distributed_line_families(self):
        source = _grid()
        transformed = apply_geometry_pixels(source, Geometry(vertical=20, horizontal=-15))
        proposal = analyze_auto(transformed, 'geometry_full', {'geometry': Geometry()})
        self.assertIn('geometry', proposal['changes'])
        solved = proposal['changes']['geometry']
        self.assertLess(abs(solved['vertical'] + 20), 6)
        self.assertLess(abs(solved['horizontal'] - 15), 15)
        self.assertGreaterEqual(proposal['confidence'], .45)

    def test_weak_scene_is_left_unchanged(self):
        flat = np.full((120, 160, 3), .4, dtype=np.float32)
        proposal = analyze_auto(flat, 'geometry_full', {'geometry': Geometry()})
        self.assertEqual(proposal['changes'], {})

    def test_reapplying_after_correction_does_not_propose_again(self):
        source = _grid()
        transformed = apply_geometry_pixels(source, Geometry(vertical=20, horizontal=-15))
        proposal = analyze_auto(transformed, 'geometry_full', {'geometry': Geometry()})
        corrected = apply_geometry_pixels(transformed, Geometry(**proposal['changes']['geometry']))
        repeat = analyze_auto(corrected, 'geometry_full', {'geometry': Geometry()})
        self.assertEqual(repeat['changes'], {})


if __name__ == '__main__':
    unittest.main()
