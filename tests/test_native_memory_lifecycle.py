"""Ownership boundaries for native RAW, display surfaces and export scratch."""
import ctypes as ct
import gc
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from desktop import native_spectral, raw_development
from desktop.raw_source import display_image, quantize_display, source_pixels


class NativeMemoryLifecycleTests(unittest.TestCase):
    def test_display_quantization_keeps_high_precision_source_unchanged(self):
        values = np.linspace(-.2, 1.4, 523 * 39 * 3, dtype=np.float32).reshape(523, 39, 3)
        original = values.copy()
        image = display_image(values)
        expected = np.rint(np.clip(values, 0, 1) * 255).astype(np.uint8)
        np.testing.assert_array_equal(np.asarray(image), expected)
        np.testing.assert_array_equal(source_pixels(image), original)
        self.assertIs(source_pixels(image), values)
        rgb16 = (np.arange(521 * 19 * 3, dtype=np.uint16).reshape(521, 19, 3))[:, ::-1]
        np.testing.assert_array_equal(quantize_display(rgb16), (rgb16 >> 8).astype(np.uint8))

    def test_last_raw_view_releases_native_owner_once(self):
        samples = (ct.c_float * 36)(*np.linspace(-.2, 1.8, 36))

        class FakeLibrary:
            frees = 0

            def spk_raw_decode(self, path, policy, preview, result):
                output = result._obj
                output.rgb = ct.cast(samples, ct.POINTER(ct.c_float))
                output.width, output.height, output.owner = 4, 3, 987654321
                output.metadata_json = b'{"source_width":4,"source_height":3}'
                return 0

            def spk_raw_free(self, result):
                self.frees += 1
                result._obj.owner = None

        library = FakeLibrary()
        before = raw_development.memory_info()['live_source_bytes']
        with patch.object(raw_development, '_library', return_value=library):
            pixels, _ = raw_development.decode_raw('synthetic.dng')
        view = np.asarray(pixels)[1:]
        self.assertFalse(pixels.flags.writeable)
        self.assertEqual(raw_development.memory_info()['live_source_bytes'], before + 36 * 4)
        del pixels
        gc.collect()
        self.assertEqual(library.frees, 0)
        self.assertGreater(float(view.max()), 1)
        del view
        gc.collect()
        self.assertEqual(library.frees, 1)
        self.assertEqual(raw_development.memory_info()['live_source_bytes'], before)

    def test_export_mapping_outlives_original_array_until_last_view(self):
        before = sum(native_spectral._MAPPED_RESULTS.values())
        output = native_spectral._mapped_result((17, 23, 3))
        path = Path(output.filename)
        view = np.asarray(output)[3:9]
        view[:] = 1.25
        del output
        gc.collect()
        self.assertTrue(path.is_file())
        self.assertEqual(sum(native_spectral._MAPPED_RESULTS.values()), before + 17 * 23 * 3 * 4)
        self.assertEqual(float(view.mean()), 1.25)
        del view
        gc.collect()
        self.assertFalse(path.exists())
        self.assertEqual(sum(native_spectral._MAPPED_RESULTS.values()), before)

    def test_raw_display_stripes_match_whole_frame_transform(self):
        if not native_spectral.available():
            self.skipTest('native Vulkan runtime unavailable')
        pixels = np.linspace(-.04, 1.5, 531 * 31 * 3, dtype=np.float32).reshape(531, 31, 3)
        original = pixels.copy()
        metadata = {'source_width': 31, 'source_height': 531}
        with patch.object(raw_development, 'decode_raw', return_value=(pixels, metadata)):
            image = raw_development.read_developed_raw('synthetic-stripes.dng')
        ev = image.info['_spektrafilm_source_metadata']['baseline_exposure_ev']
        whole = native_spectral.process_editor(pixels, {}, stage='pre', source_color_space='ProPhoto RGB',
                    source_linear=True, exposure_ev=ev, clamp_output=True)
        np.testing.assert_array_equal(np.asarray(image), quantize_display(whole))
        np.testing.assert_array_equal(source_pixels(image), original)
        self.assertEqual(image.size, (31, 531))
        native_spectral.trim_memory()

    def test_preview_budget_evicts_native_sessions_without_losing_result(self):
        if not native_spectral.available():
            self.skipTest('native Vulkan runtime unavailable')
        from desktop.imaging import Settings
        previous = dict(native_spectral._CACHE_LIMITS)
        try:
            native_spectral.set_cache_limits(max_entries=1, source_bytes=1024 * 1024,
                                             retained_bytes=4 * 1024 * 1024)
            pixels = np.full((48, 64, 3), .4, dtype=np.float32)
            first = native_spectral.render_spectral(pixels, Settings(), preview=True, source_token='cache-one')
            native_spectral.render_spectral(pixels, Settings(), preview=True, source_token='cache-two')
            self.assertEqual(native_spectral.memory_info()['session_cache']['entries'], 1)
            native_spectral.set_cache_limits(retained_bytes=0)
            report = native_spectral.memory_info()
            self.assertEqual(report['session_cache']['entries'], 0)
            self.assertEqual(report['native']['persistent']['source_bytes'], 0)
            self.assertTrue(np.isfinite(first).all())
            self.assertEqual(first.shape, pixels.shape)
            self.assertGreaterEqual(native_spectral.trim_memory(), 0)
        finally:
            native_spectral.clear_sessions()
            native_spectral.set_cache_limits(**previous)


if __name__ == '__main__':
    unittest.main()
