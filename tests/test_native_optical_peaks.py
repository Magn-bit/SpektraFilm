"""Bounded all-pixel exposure reductions; no large-RAW repetition."""
import unittest
from dataclasses import replace
from unittest.mock import patch

import numpy as np

from desktop import native_spectral as native
from desktop.imaging import Settings


@unittest.skipUnless(native.available(), 'Windows Vulkan spectral runtime required')
class NativeOpticalPeaks(unittest.TestCase):
    def setUp(self):
        # Two measurement strips and multiple render regions, with the global
        # highlight confined to a tiny patch absent from most region halos.
        height, width = 571, 421
        x = np.geomspace(.04, 2.8, width, dtype=np.float32)
        self.source = np.broadcast_to(x[None, :, None], (height, width, 3)).copy()
        self.source *= np.array([.91, 1., 1.07], np.float32)
        self.source[12:18, 10:16] = 4.5
        self.original = self.source.copy()
        self.settings = Settings(stock='kodak_vision3_500t', grain=0, halation=1,
            glare=0, film_format_mm=120, dir_couplers_amount=0, halation_scatter_amount=0,
            halation_boost_ev=2, halation_protect_ev=0, halation_headroom_ev=4)
        self.engine = native._get_engine()

    def tearDown(self):
        np.testing.assert_array_equal(self.source, self.original)
        native.clear_sessions()

    def values(self, settings):
        values = native.parameters(settings)
        # Use the native, publicly sourced 500T-derived no-remjet profile to
        # exercise headroom as well as boost. This does not add an unavailable
        # material to the product catalogue or change its profile data.
        values.update(film_stock='cinestill_800t', dir_couplers_active=False)
        return values

    def test_global_peaks_match_all_source_strips_and_boost_is_gpu_exact(self):
        values = self.values(self.settings)
        expected = self.engine.analyze(self.source, values, 'exposure_peaks')
        peaks = dict(frame_exposure_peak=0., frame_boosted_peak=0.)
        for top in range(0, self.source.shape[0], 113):
            region = dict(values, tile_full_width=421, tile_full_height=571,
                          tile_origin_x=0, tile_origin_y=top)
            measured = self.engine.analyze(self.source[top:top+113], region, 'exposure_peaks')
            peaks = {key: max(peaks[key], measured[key]) for key in peaks}
        self.assertEqual(peaks, expected)
        self.assertGreater(peaks['frame_boosted_peak'], peaks['frame_exposure_peak'] * 3.99)

    def test_boost_and_headroom_share_frame_peaks_across_different_region_plans(self):
        for boost, headroom in ((2, 0), (0, 4), (2, 4)):
            settings = replace(self.settings, halation_boost_ev=boost, halation_headroom_ev=headroom)
            values = self.values(settings)
            whole = self.engine.render(self.source, dict(values, striped=False), None)
            for core in (128, 192):
                with self.subTest(boost=boost, headroom=headroom, core=core):
                    result = native._render_regions(self.engine, self.source, settings, values,
                                                    core_edge=core, seed=743)
                    np.testing.assert_allclose(result, whole, atol=3./65535., rtol=0.)
                    details = native.backend_info()['last_render']
                    self.assertEqual(details['optical_peak_prepass_regions'], 2)
                    self.assertGreater(details['bounded_regions'], 1)
                    self.assertEqual(result.shape, self.source.shape)
                    del result

    def test_ordinary_optics_skip_the_extra_global_scan(self):
        settings = replace(self.settings, halation=0, halation_boost_ev=0, halation_headroom_ev=0)
        values = self.values(settings)
        whole = self.engine.render(self.source, dict(values, striped=False), None)
        with patch.object(self.engine, 'analyze', side_effect=AssertionError('unused peak prepass')):
            result = native._render_regions(self.engine, self.source, settings, values,
                                            core_edge=192, seed=743)
        np.testing.assert_allclose(result, whole, atol=3./65535., rtol=0.)
        details = native.backend_info()['last_render']
        self.assertEqual(details['optical_peaks'], {})
        self.assertEqual(details['optical_peak_prepass_regions'], 0)
        del result


if __name__ == '__main__':
    unittest.main()
