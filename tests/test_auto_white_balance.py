"""Auto white balance should use distributed neutral evidence, not scene color."""
import unittest

import numpy as np

from desktop.imaging import Settings
from shared.auto_adjust import analyze_auto, _wb_matrix


class AutoWhiteBalanceTests(unittest.TestCase):
    def test_distributed_neutrals_resist_saturated_color_blocks(self):
        height, width = 192, 256
        levels = np.linspace(.025, .72, width, dtype=np.float32)
        neutral = np.repeat(np.broadcast_to(levels, (height, width))[..., None], 3, axis=2)
        cast = neutral @ np.linalg.inv(_wb_matrix(4800, 18)).T
        scene = cast.copy()
        distractors = np.asarray(((.82, .08, .025), (.025, .11, .78), (.08, .72, .06)), np.float32)
        for row in range(8):
            for column in range(8):
                if (row + column) % 3 == 0:
                    y0, y1 = row * height // 8, (row + 1) * height // 8
                    x0, x1 = column * width // 8, (column + 1) * width // 8
                    scene[y0:y1, x0:x1] = distractors[(row + column) % len(distractors)]

        result = analyze_auto(scene, 'white_balance', Settings(), source_linear=True)
        self.assertGreaterEqual(result['confidence'], .4, result)
        self.assertAlmostEqual(result['changes']['temperature'], 4800, delta=450)
        self.assertAlmostEqual(result['changes']['tint'], 18, delta=22)

        corrected = cast @ _wb_matrix(result['changes']['temperature'], result['changes']['tint']).T
        channel_means = corrected.mean(axis=(0, 1))
        self.assertLess(float(np.std(channel_means / channel_means.mean())), .025)

    def test_scene_without_neutral_evidence_is_left_unchanged(self):
        colors = np.asarray(((.9, .025, .02), (.02, .08, .9), (.04, .85, .03)), np.float32)
        scene = np.tile(colors, (80, 80, 1))
        result = analyze_auto(scene, 'white_balance', Settings(), source_linear=True)
        self.assertEqual(result['changes'], {})
        self.assertLess(result['confidence'], .4)


if __name__ == '__main__':
    unittest.main()
