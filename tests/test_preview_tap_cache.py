"""Real-engine contracts for the bounded desktop exposure-tap cache."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import tempfile
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vendor'))
from desktop import imaging


class PreviewTapCacheTests(unittest.TestCase):
    def setUp(self):
        self.original_init = imaging.init_film_params
        self.params_patch = patch('desktop.imaging.init_film_params', side_effect=self.params)
        self.params_patch.start()
        self.addCleanup(self.params_patch.stop)
        with imaging._SPECTRAL_CONTEXTS_LOCK:
            imaging._SPECTRAL_CONTEXTS.clear()
            imaging._SPECTRAL_CONTEXT_SIGNATURES.clear()
        yy, xx = np.mgrid[:32, :48]
        pixels = np.stack((30 + xx * 4, 22 + yy * 6, 35 + (xx + yy) * 2), axis=2)
        self.image = Image.fromarray(pixels.astype(np.uint8))
        self.image._spektrafilm_preview_cache = {}
        self.settings = imaging.Settings(spectral=True, grain=12, halation=0)

    def params(self, stock, paper):
        params = self.original_init(stock, paper)
        params.debug.deactivate_stochastic_effects = True
        return params

    def render_calls(self, image, settings):
        from spektrafilm import Simulator
        with patch.object(Simulator, 'process_tap', autospec=True,
                          side_effect=Simulator.process_tap) as calls:
            output = imaging.render(image, settings, preview=True)
        return output, [(call.kwargs['inject'], call.kwargs['collect'])
                        for call in calls.call_args_list]

    def test_grain_settings_reuse_exposure_and_equal_cold_deterministic_result(self):
        self.render_calls(self.image, self.settings)
        for field, value in (('grain', 28), ('grain_size', 1.8), ('grain_type', 'fine')):
            with self.subTest(field=field):
                settings = replace(self.settings, **{field: value})
                cached, calls = self.render_calls(self.image, settings)
                self.assertNotIn(('rgb_in', 'log_e_film'), calls)
                self.assertIn(('log_e_film', 'rgb_out'), calls)
                cold = self.image.copy()
                cold._spektrafilm_preview_cache = {}
                # A fresh simulator ensures this is an independent cold stage computation.
                with imaging._SPECTRAL_CONTEXTS_LOCK:
                    imaging._SPECTRAL_CONTEXTS.clear()
                    imaging._SPECTRAL_CONTEXT_SIGNATURES.clear()
                expected, cold_calls = self.render_calls(cold, settings)
                self.assertIn(('rgb_in', 'log_e_film'), cold_calls)
                np.testing.assert_array_equal(np.asarray(cached), np.asarray(expected))
                self.settings = settings

    def test_exposure_halation_and_stock_changes_invalidate_exposure(self):
        self.render_calls(self.image, self.settings)
        for settings in (replace(self.settings, exposure=.6),
                         replace(self.settings, exposure=.6, halation=17),
                         replace(self.settings, stock='kodak_ektar_100', exposure=.6, halation=17)):
            with self.subTest(settings=settings):
                before = self.image._spektrafilm_spectral_stage_cache['log_e_film']
                _, calls = self.render_calls(self.image, settings)
                self.assertIn(('rgb_in', 'log_e_film'), calls)
                self.assertIsNot(before, self.image._spektrafilm_spectral_stage_cache['log_e_film'])

    def test_source_file_change_discards_object_scoped_tap(self):
        from PySide6.QtWidgets import QApplication
        from desktop.controller import Controller, PhotoProvider
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.png'
            self.image.save(path)
            controller = Controller(PhotoProvider(), directory)
            try:
                first = controller._source(str(path), 64)
                self.render_calls(first, self.settings)
                self.assertTrue(hasattr(first, '_spektrafilm_spectral_stage_cache'))
                old_stamp = controller._source_stamps[str(path)]
                Image.new('RGB', self.image.size, (50, 150, 110)).save(path)
                stamp = max(path.stat().st_mtime_ns, old_stamp[0] + 1_000_000)
                os.utime(path, ns=(stamp, stamp))
                second = controller._source(str(path), 64)
                self.assertIsNot(first, second)
                self.assertFalse(hasattr(second, '_spektrafilm_spectral_stage_cache'))
                _, calls = self.render_calls(second, replace(self.settings, grain=29))
                self.assertIn(('rgb_in', 'log_e_film'), calls)
            finally:
                controller.close()
                app.processEvents()

    def test_cached_exposure_survives_downstream_processing_and_output_mutation(self):
        self.render_calls(self.image, self.settings)
        tap = self.image._spektrafilm_spectral_stage_cache['log_e_film']
        saved = tap.copy()
        for settings in (replace(self.settings, grain=35), replace(self.settings, grain=51)):
            output, _ = self.render_calls(self.image, settings)
            output.paste((0, 0, 0), (0, 0, *output.size))
            self.assertIs(tap, self.image._spektrafilm_spectral_stage_cache['log_e_film'])
            np.testing.assert_array_equal(tap, saved)

    def test_full_render_does_not_create_preview_tap_cache(self):
        image = self.image.copy()
        imaging.render(image, self.settings, preview=False)
        self.assertFalse(hasattr(image, '_spektrafilm_spectral_stage_cache'))

    def test_preview_mode_explicitly_disables_grain_before_execution(self):
        from spektrafilm.runtime.params_builder import digest_params
        params = self.original_init('kodak_portra_400', 'kodak_portra_endura')
        params.settings.preview_mode = True
        params.film_render.grain.active = True
        params.film_render.grain.particle_area_um2 = 1.5
        digested = digest_params(params)
        self.assertFalse(digested.film_render.grain.active)
        self.assertEqual(digested.film_render.grain.particle_area_um2, 0)

    def test_stochastic_full_params_keep_tap_immutable_and_restore_pixel_scale(self):
        values = np.asarray(self.image).astype(np.float64) / 255
        cache = {}
        key = ('kodak_portra_400', 'kodak_portra_endura')
        stage_signature = ('same-source-and-exposure', values.shape)

        def params(grain_area):
            p = self.original_init(*key)
            p.io.input_color_space = 'sRGB'
            p.io.input_cctf_decoding = True
            p.camera.auto_exposure = False
            p.settings.use_enlarger_lut = True
            p.settings.use_scanner_lut = True
            p.settings.preview_mode = False
            p.film_render.grain.active = True
            p.film_render.grain.particle_area_um2 = grain_area
            p.film_render.halation.active = False
            return p

        imaging._process_spectral_tap_cached(values, params(.2), key, ('grain', .2), cache, stage_signature)
        tap = cache['log_e_film']
        snapshot = tap.copy()
        output = imaging._process_spectral_tap_cached(values, params(.8), key, ('grain', .8), cache, stage_signature)
        self.assertIs(tap, cache['log_e_film'])
        np.testing.assert_array_equal(tap, snapshot)
        self.assertFalse(np.shares_memory(output, tap))
        output[...] = 0
        np.testing.assert_array_equal(tap, snapshot)
        self.assertEqual(imaging._SPECTRAL_CONTEXTS[key]._pipeline._resize_service.pixel_size_um,
                         35000 / max(values.shape[:2]))


if __name__ == '__main__':
    unittest.main()
