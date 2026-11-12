"""Small quality checks for the shared continuous HDR tone model."""
import unittest

import numpy as np

from desktop.native_spectral import available, process_editor
from shared.levels import apply_hdr_linear, apply_hdr_tone,hdr_luminance_base
from shared.local_masks import apply_masks


class HdrToneQuality(unittest.TestCase):
    def test_detail_base_preserves_texture_and_does_not_blend_exposure_edges(self):
        x=np.arange(97,dtype=np.float32)
        texture=1.+.09*np.cos(x*np.float32(np.pi))
        linear=np.broadcast_to(texture[None,:,None]*.025,(29,97,3)).copy()
        encoded=np.where(linear<=.0031308,linear*12.92,1.055*linear**(1/2.4)-.055)
        base=hdr_luminance_base(encoded,pixel_scale=(48,48))
        detail=linear.copy();point=linear.copy()
        apply_hdr_linear(detail,shadows=80,detail_base=base)
        apply_hdr_linear(point,shadows=80)
        contrast=lambda values:np.std(np.log2(values[5:24,8:88,0]))
        initial=contrast(linear)
        self.assertLess(abs(contrast(detail)-initial),abs(contrast(point)-initial))
        edge=np.full((17,97,3),.025,np.float32);edge[:,49:]=1.5
        enc=np.where(edge<=.0031308,edge*12.92,1.055*edge**(1/2.4)-.055)
        smooth=hdr_luminance_base(enc)
        # A six-stop discontinuity must not create bright/dark fringe gains.
        self.assertLess(float(np.max(np.abs(smooth-edge[...,0]))),.001)

    def test_zero_is_exact_bypass_and_source_headroom_is_preserved(self):
        pixels = np.array([[[-.03, .01, 0.2], [1.4, 2.0, .8]]], np.float32)
        original = pixels.copy()
        apply_hdr_tone(pixels)
        np.testing.assert_array_equal(pixels, original)

    def test_zone_combinations_are_finite_and_monotonic(self):
        ramp = np.linspace(0, 6, 4097, dtype=np.float32)
        rgb = np.repeat(ramp[:, None, None], 3, axis=2)
        for controls in ((100, 100, 100, 100), (-100, -100, -100, -100),
                         (100, -100, -100, 100), (-100, 100, 100, -100)):
            output = rgb.copy()
            linear = output[:, 0].copy()
            apply_hdr_linear(linear, *controls)
            self.assertTrue(np.isfinite(linear).all())
            self.assertTrue(np.all(np.diff(linear[:, 0]) >= -2e-6), controls)

    def test_chromatic_ratios_and_black_anchor_are_preserved(self):
        linear = np.array([[[0., 0., 0.], [.08, .16, .32],
                           [1.0, 1.5, 2.0]]], np.float32)
        before = linear[0, 1, 1:] / linear[0, 1, 0]
        apply_hdr_linear(linear, highlights=-80, shadows=75, whites=-60, blacks=35)
        self.assertEqual(float(linear[0, 0].max()), 0.)
        np.testing.assert_allclose(linear[0, 1, 1:] / linear[0, 1, 0], before,
                                   rtol=2e-6, atol=2e-6)
        expanded = np.array([[[1., 1.5, 2.]]], np.float32)
        apply_hdr_linear(expanded, highlights=100, whites=100)
        self.assertGreater(float(expanded.max()), 1., 'HDR keeps float headroom before final clamp')

    @unittest.skipUnless(available(), 'Windows Vulkan editor runtime required')
    def test_native_hdr_and_local_recovery_keep_the_same_headroom(self):
        rgb = np.random.default_rng(26).uniform(.01, 1.7, (67, 97, 3)).astype(np.float32)
        edits = dict(highlights=-79, shadows=66, whites=-42, blacks=29)
        expected = rgb.copy()
        apply_hdr_tone(expected, edits['highlights'], edits['shadows'])
        apply_hdr_tone(expected, whites=edits['whites'], blacks=edits['blacks'])
        actual = process_editor(rgb, edits, clamp_output=False)
        np.testing.assert_allclose(actual, expected, atol=3e-6, rtol=3e-6)
        # A dark local exposure can recover source values that exceed display
        # white. A second transparent mask must not destroy this information.
        masks = [dict(kind='radial', center=[.5, .5], radius_x=2, radius_y=2,
                      feather=0, exposure=-2, highlights=-30, shadows=15),
                 dict(kind='linear', start=[0, 0], end=[1, 0], highlights=-10)]
        expected = rgb.copy()
        apply_masks(expected, masks)
        actual = process_editor(rgb, {'masks': masks})
        np.testing.assert_allclose(actual, expected, atol=3e-6, rtol=3e-6)
        np.testing.assert_array_equal(rgb, np.random.default_rng(26).uniform(.01, 1.7, rgb.shape).astype(np.float32))

    @unittest.skipUnless(available(), 'Windows Vulkan editor runtime required')
    def test_cached_detail_plane_matches_native_and_strip_halo(self):
        source=np.random.default_rng(67).uniform(.01,1.4,(1031,61,3)).astype(np.float32)
        edits=dict(highlights=-71,shadows=58,contrast=8,warmth=3,saturation=9,vibrance=15)
        scale=(3.25,2.5)
        base=hdr_luminance_base(source,scale,contrast=8,warmth=3,saturation=9,vibrance=15)
        native=process_editor(source,edits,pixel_scale=scale,clamp_output=False)
        cached=process_editor(source,edits,pixel_scale=scale,clamp_output=False,tone_base=base)
        np.testing.assert_allclose(cached,native,atol=5e-6,rtol=5e-6)
        inplace=source.copy()
        process_editor(inplace,edits,pixel_scale=scale,clamp_output=False,out=inplace)
        np.testing.assert_allclose(inplace,native,atol=3e-6,rtol=3e-6)


if __name__ == '__main__':
    unittest.main()
