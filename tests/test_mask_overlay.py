"""Stroke-prefix publication must stay accurate across erase, undo and geometry."""
from dataclasses import replace
import unittest
import numpy as np
from PySide6.QtCore import QCoreApplication

from desktop.mask_overlay import MaskOverlay, _BrushRaster
from shared.geometry import Geometry
from shared.local_masks import MaskLayer, MaskStroke, rasterize_mask


class MaskOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_incremental_soft_flow_and_eraser_match_final_raster(self):
        raster = _BrushRaster()
        first = MaskStroke(((.2,.35),(.35,.45),(.55,.5)), .12, .7, .45)
        layer = MaskLayer(id='a', strokes=(first,))
        for length in range(1,4):
            partial = replace(layer, strokes=(replace(first, points=first.points[:length]),))
            np.testing.assert_allclose(raster.render(partial, 170,110), rasterize_mask(partial,170,110), atol=2e-7)
        erase = MaskStroke(((.3,.4),(.5,.5),(.65,.55)), .08, .5, .6, True)
        for length in range(1,4):
            partial = replace(layer, strokes=(first,replace(erase, points=erase.points[:length])), inverted=True)
            np.testing.assert_allclose(raster.render(partial,170,110), rasterize_mask(partial,170,110), atol=2e-7)

    def test_only_true_continuation_of_same_stroke_can_publish(self):
        overlay = MaskOverlay(None)
        first = MaskStroke(((.2,.3),), .08, .7, .5)
        before = MaskLayer(id='a', strokes=(first,))
        after = replace(before, strokes=(replace(first,points=first.points+((.5,.6),)),))
        key = (before,(1200,800),Geometry())
        overlay.key = (after,*key[1:])
        self.assertTrue(overlay._publishable(key))
        for changed in (replace(after,id='b'), replace(after,inverted=True),
                        replace(after,strokes=()),
                        replace(after,strokes=(replace(first,erase=True),)),
                        replace(after,strokes=(replace(first,points=((.7,.3),)),))):
            overlay.key = (changed,*key[1:])
            self.assertFalse(overlay._publishable(key))
        overlay.key = (after,key[1],Geometry(rotation=3))
        self.assertFalse(overlay._publishable(key))
        overlay.key = None
        self.assertFalse(overlay._publishable(key))
        overlay.close()


if __name__ == '__main__':
    unittest.main()
