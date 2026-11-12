"""Key integration checks for the shared GPU editor, not the whole old suite."""
import unittest
import numpy as np

from desktop.native_spectral import available, process_editor
from shared.color_tools import apply_color_tools
from shared.hsl import apply_hsl
from shared.local_masks import apply_masks


@unittest.skipUnless(available(), 'Windows Vulkan editor runtime required')
class NativeEditorIntegration(unittest.TestCase):
    def test_existing_color_and_mask_contract_matches_reference(self):
        source = np.random.default_rng(42).uniform(.03, .97, (97, 131, 3)).astype(np.float32)
        edits = dict(
            hsl=dict(orange=dict(hue=18, saturation=-21, luminance=14),
                     blue=dict(hue=-27, saturation=16, luminance=-12)),
            curves=dict(master=[[0, 0], [.24, .18], [.67, .75], [1, 1]],
                        luma=[[0, 0], [.4, .43], [1, 1]]),
            grading=dict(shadows=dict(hue=210, saturation=13, luminance=5),
                         highlights=dict(hue=43, saturation=9), balance=6, blending=63),
            masks=[dict(kind='radial', center=[.61, .43], radius_x=.34, radius_y=.27,
                        rotation=23, feather=.72, exposure=.32, saturation=-10),
                   dict(kind='brush', temperature=17, opacity=.64,
                        strokes=[dict(points=[[.1,.2],[.5,.7],[.8,.6]], radius=.17, flow=.8),
                                 dict(points=[[.4,.5],[.6,.6]], radius=.1, erase=True)])])
        expected = source.copy()
        apply_hsl(expected, edits['hsl'])
        apply_color_tools(expected, edits['curves'], edits['grading'])
        apply_masks(expected, edits['masks'])
        actual = process_editor(source, edits)
        np.testing.assert_allclose(actual, expected, atol=8e-5, rtol=1e-4)

    def test_negative_exposure_uses_superwhite_source_before_output_clamp(self):
        source = np.tile(np.array([4., .5, -.02], dtype=np.float32), (16, 19, 1))
        out = process_editor(source, {'exposure': -2}, stage='all', source_linear=True)
        linear = np.clip(source/4, 0, 1)
        expected = np.where(linear <= .0031308, linear*12.92,
                            1.055*np.maximum(linear, 0)**(1/2.4)-.055)
        np.testing.assert_allclose(out, expected, atol=2e-6, rtol=2e-6)
        self.assertEqual(out.shape, source.shape)

    def test_mask_source_coordinates_match_arbitrary_export_tiles(self):
        source = np.full((197, 263, 3), .42, dtype=np.float32)
        edits = dict(masks=[dict(kind='linear', start=[.2,.1], end=[.7,.9], exposure=.7),
                            dict(kind='brush', exposure=-.5, strokes=[
                                dict(points=[[.13,.18],[.45,.69],[.86,.81]], radius=.09),
                                dict(points=[[.4,.62],[.62,.71]], radius=.06, erase=True)])])
        whole = process_editor(source, edits)
        top, left, bottom, right = 39, 27, 169, 219
        tile = process_editor(source[top:bottom, left:right], edits,
                              source_size=(263,197), origin=(left,top))
        np.testing.assert_allclose(tile, whole[top:bottom,left:right], atol=2e-6, rtol=2e-6)

    def test_spatial_inplace_keeps_original_halo_across_strips(self):
        source = np.random.default_rng(23).uniform(.08,.92,(1103,89,3)).astype(np.float32)
        edits = dict(texture=34, clarity=27, contrast=12, temperature=5400)
        expected = process_editor(source, edits, stage='all')
        inplace = source.copy()
        process_editor(inplace, edits, stage='all', out=inplace)
        np.testing.assert_allclose(inplace, expected, atol=2e-6, rtol=2e-6)


if __name__ == '__main__':
    unittest.main()
