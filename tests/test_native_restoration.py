"""One native fixture for capture-side restoration and spatial boundaries."""
import unittest
from dataclasses import asdict, replace
from unittest.mock import patch

import numpy as np

from desktop.native_spectral import available, process_editor


@unittest.skipUnless(available(), 'Windows Vulkan editor runtime required')
class NativeRestorationIntegration(unittest.TestCase):
    def test_pre_request_does_not_traverse_masks_and_matches_full_settings_pixels(self):
        from desktop import native_spectral
        from desktop.imaging import Settings
        from shared.local_masks import MaskLayer, MaskStroke
        points = tuple((i/3999, .4) for i in range(4000))
        settings = Settings(temperature=5100, tint=7, calibration_red_hue=12,
            calibration_green_saturation=-9, sharpening=27, noise_luminance=36, noise_color=55)
        masked = replace(settings, masks=(MaskLayer(id='large-mask', exposure=.5,
                         strokes=tuple(MaskStroke(points=points) for _ in range(3))),))
        legacy = dict(stage='pre', settings=asdict(masked), source_color_space='sRGB', source_linear=False,
                      origin_x=0., origin_y=0., pixel_scale_x=1., pixel_scale_y=1., exposure_ev=.17)
        with patch.object(native_spectral, 'asdict', side_effect=AssertionError('pre must not deep-copy masks')):
            projected = native_spectral.editor_request(masked, stage='pre', exposure_ev=.17)
        self.assertEqual(set(projected['settings']), set(native_spectral._PRE_EDITOR_FIELDS))
        self.assertEqual(projected, native_spectral.editor_request(asdict(masked), stage='pre', exposure_ev=.17))
        pixels = np.random.default_rng(103).uniform(-.02, 1.1, (71, 113, 3)).astype(np.float32)
        plain = process_editor(pixels, settings, stage='pre', exposure_ev=.17)
        with_masks = process_editor(pixels, masked, stage='pre', exposure_ev=.17)
        reference = np.empty_like(pixels)
        with native_spectral._LOCK:
            native_spectral._get_engine().editor(pixels, legacy, reference)
        np.testing.assert_array_equal(with_masks, plain)
        np.testing.assert_array_equal(with_masks, reference)

    def test_capture_details_invalidate_film_cache_and_strength_does_not_restore_twice(self):
        from desktop.imaging import Settings, render_pixels
        from desktop.raw_source import display_image
        rng = np.random.default_rng(233)
        source = rng.uniform(.14, .74, (79, 113, 3)).astype(np.float32)
        baseline = Settings(film_enabled=True, grain=0, halation=0,
                            lens_correction=False, defringe=False)
        image = display_image(source)
        image._spektrafilm_preview_cache = {}
        plain = render_pixels(image, baseline, preview=True)
        for name in ('sharpening', 'noise_luminance', 'noise_color'):
            edits = replace(baseline, **{name: 83})
            cached = render_pixels(image, edits, preview=True)
            fresh = render_pixels(display_image(source), edits, preview=True)
            np.testing.assert_allclose(cached, fresh, atol=2e-6, rtol=2e-6,
                                       err_msg=f'{name} must invalidate native source and film caches')
            self.assertGreater(float(np.max(np.abs(cached - plain))), 1e-4, name)
        edits = replace(baseline, sharpening=53, noise_luminance=48, noise_color=67, strength=31)
        # Echoing the already restored capture image isolates strength's base
        # branch: blending identical endpoints must never restore it again.
        with patch('desktop.imaging._spectral', side_effect=lambda prepared, *a, **k: prepared.copy()):
            mixed = render_pixels(display_image(source), edits, preview=True)
        expected = process_editor(source, edits, stage='all')
        np.testing.assert_allclose(mixed, expected, atol=2e-6, rtol=2e-6)

    def test_noise_detail_headroom_and_source_space_boundaries(self):
        rng = np.random.default_rng(538)
        height, width = 1081, 193
        x = np.arange(width, dtype=np.float32)
        smooth_edge = .24 + .48 * (.5 + .5 * np.tanh((x - width * .5) / 1.8))
        truth = np.broadcast_to(smooth_edge[None, :, None], (height, width, 3)).copy()
        source = (truth + rng.normal(0, .018, truth.shape) +
                  rng.normal(0, .014, (height, width, 1))).astype(np.float32)
        denoise = {'noise_luminance': 78, 'noise_color': 86}
        filtered = process_editor(source, denoise, stage='pre', clamp_output=False)
        luma = np.array([.2126, .7152, .0722], dtype=np.float32)
        # Noise is measured away from the edge, so sharpening/ringing cannot
        # make a variance reduction look like successful restoration.
        flat = np.s_[30:-30, 12:70]
        before_y, after_y = source @ luma, filtered @ luma
        before_c = source - before_y[..., None]
        after_c = filtered - after_y[..., None]
        self.assertLess(float(after_y[flat].std()), float(before_y[flat].std()) * .8)
        self.assertLess(float(after_c[flat].std()), float(before_c[flat].std()) * .65)
        self.assertGreater(float(after_y[:, 135:170].mean() - after_y[:, 25:65].mean()), .45)

        sharp = process_editor(truth, {'sharpening': 75}, stage='pre', clamp_output=False)
        original_step = np.diff(truth[30, :, 0]).max()
        self.assertGreater(float(np.diff(sharp[30, :, 0]).max()), float(original_step) * 1.1)

        edits = dict(denoise, sharpening=46, texture=11, clarity=7, contrast=9)
        whole = process_editor(source, edits, stage='all', clamp_output=False)
        inplace = source.copy()
        process_editor(inplace, edits, stage='all', clamp_output=False, out=inplace)
        np.testing.assert_allclose(inplace, whole, atol=2e-6, rtol=2e-6)
        # The crop surrounds its validated core with enough original pixels
        # for serial noise->sharpen->clarity kernels, including strip y=512.
        top, left, bottom, right, pad = 467, 71, 607, 121, 56
        y0, x0, y1, x1 = top-pad, left-pad, bottom+pad, right+pad
        tile = process_editor(source[y0:y1, x0:x1], edits, stage='all', clamp_output=False,
                              source_size=(width, height), origin=(x0, y0))
        np.testing.assert_allclose(tile[pad:-pad, pad:-pad], whole[top:bottom, left:right], atol=2e-6, rtol=2e-6)
        # Fractional proxy spacing keeps the same source-pixel kernel support
        # and therefore remains identical across arbitrary source-space tiles.
        scale = (2.4, 3.1)
        proxy_full = process_editor(source, denoise, stage='pre', clamp_output=False,
                                    source_size=(463, 3351), pixel_scale=scale)
        small = process_editor(source[491:537, 41:119], denoise, stage='pre', clamp_output=False,
                               source_size=(463, 3351), origin=(41*scale[0], 491*scale[1]), pixel_scale=scale)
        np.testing.assert_allclose(small[4:-4, 4:-4], proxy_full[495:533, 45:115], atol=2e-6, rtol=2e-6)

        extreme = np.tile(np.array([1.8, 1.3, -.04], dtype=np.float32), (27, 37, 1))
        headroom = process_editor(extreme, dict(denoise, sharpening=80), stage='pre', clamp_output=False)
        self.assertGreater(float(headroom[..., 0].min()), 1.7)
        self.assertLess(float(headroom[..., 2].max()), 0)
        plain = process_editor(source, {}, stage='post', clamp_output=False)
        ignored = process_editor(source, dict(denoise, sharpening=100), stage='post', clamp_output=False)
        np.testing.assert_array_equal(plain, ignored)
        disabled = process_editor(source, {'noise_luminance': 0, 'noise_color': 0, 'sharpening': 0},
                                  stage='all', clamp_output=False)
        identity = process_editor(source, {}, stage='all', clamp_output=False)
        np.testing.assert_array_equal(disabled, identity)


if __name__ == '__main__':
    unittest.main()
