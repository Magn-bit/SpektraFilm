"""Data integrity and parameter parity for the additional spectral models.

The small chart test uses the actual host Simulator, with spatial/stochastic
effects disabled so it verifies spectral data rather than random grain. Android
parameter tests check its shipped bridge/resources, not Android device speed.
"""
from dataclasses import asdict, is_dataclass
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'vendor'))

from spektrafilm import Simulator, digest_params, init_params
from spektrafilm.profiles.io import _validate_profile, load_profile
from desktop import imaging
from shared.film_profiles import extension_profiles, init_film_params, print_for_stock
from shared.darkroom import BLACK_AND_WHITE

PROFILE_ROOT = ROOT / 'vendor/spektrafilm/data/profiles'
EXTENSION_ROOT = ROOT / 'vendor/spektrafilm/data/profile_extensions'
ANDROID_ROOT = ROOT / 'android/app/src/main/python'
EVIDENCE_ROOT = ROOT / 'output/film-profile-research/evidence/spectral_film_lut'
SOURCE_COMMIT = 'bcbcfc6861f49cc706dc5d00ea048e4853060aab'
SOURCE_HASHES = {
    'fujifilm_velvia_50': ('reversal_film/fuji_velvia_50.py', '4a9c61abee7c319d0ec0ac62ff758f3314628c983c905d1d579a6c6fc301f26c'),
    'agfa_vista_100': ('negative_film/agfa_vista_100.py', '57d9455c7eb56f25ae5e21dfcbcc30cf2359e25e9d59f357e0b0e3d5630c9410'),
    'fujifilm_natura_1600': ('negative_film/fuji_natura_1600.py', '5c6afce79b702ea74496f9f63e43695fdd39ba2164c7ff010da71227ae2949fa'),
}
DENSITY_SOURCE_HASH = 'c04ea67f57bfef6852ac50d0306291f98b59c1509ff3a4dbd98ea2bc9564ba75'
LICENSE_HASH = '3cdc90b3e7727be6e5930102fadeaf35cf3d3bd7c492b90d6d16fb9ad8c3a1bd'


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AdditionalProfileTests(unittest.TestCase):
    def assert_tree_equal(self, left, right, path='params'):
        if is_dataclass(left):
            left, right = asdict(left), asdict(right)
        if isinstance(left, dict):
            self.assertEqual(set(left), set(right), path)
            for key in left:
                self.assert_tree_equal(left[key], right[key], path + '.' + str(key))
        elif isinstance(left, (np.ndarray, list, tuple)):
            np.testing.assert_allclose(left, right, rtol=1e-12, atol=1e-12, err_msg=path)
        elif isinstance(left, (float, np.floating)):
            self.assertAlmostEqual(left, right, places=12, msg=path)
        else:
            self.assertEqual(left, right, path)

    def test_installed_models_match_pinned_sources_hashes_and_provenance(self):
        manifest = extension_profiles()
        self.assertEqual(set(manifest), set(SOURCE_HASHES))
        for stock, (source_file, source_hash) in SOURCE_HASHES.items():
            with self.subTest(stock=stock):
                entry = manifest[stock]
                profile = read_json(PROFILE_ROOT / (stock + '.json'))
                provenance = read_json(EXTENSION_ROOT / entry['provenance_file'])
                self.assertEqual(sha256(PROFILE_ROOT / (stock + '.json')), entry['profile_sha256'])
                self.assertEqual(provenance['profile_sha256'], entry['profile_sha256'])
                self.assertEqual(provenance['source_sha256'], source_hash)
                self.assertEqual(entry['source_sha256'], source_hash)
                self.assertEqual(provenance['density_source_sha256'], DENSITY_SOURCE_HASH)
                self.assertEqual(provenance['source_url'],
                    f'https://github.com/JanLohse/spectral_film_lut/blob/{SOURCE_COMMIT}/src/spectral_film_lut/{source_file}')
                self.assertEqual(provenance['stock'], stock)
                self.assertEqual(profile['info']['stock'], stock)
                self.assertEqual(entry['model_status'], 'estimated')
                self.assertFalse(provenance['grain_calibrated'])
                self.assertFalse(provenance['dir_couplers_calibrated'])
                self.assertTrue(provenance['assumptions'])
                self.assertIn('MIT', profile['metadata']['license'])
                self.assertIn('Jan Lohse', profile['metadata']['copyright'])
                self.assertIn(SOURCE_COMMIT, profile['metadata']['citation'])

    @unittest.skipUnless(EVIDENCE_ROOT.is_dir(), 'Optional pinned raw-source research evidence is not retained')
    def test_retained_raw_source_evidence_has_the_claimed_hashes(self):
        for stock, (source_file, expected) in SOURCE_HASHES.items():
            with self.subTest(stock=stock):
                self.assertEqual(sha256(EVIDENCE_ROOT / 'src/spectral_film_lut' / source_file), expected)
        self.assertEqual(sha256(EVIDENCE_ROOT / 'src/spectral_film_lut/densiometry.py'), DENSITY_SOURCE_HASH)
        self.assertEqual(sha256(EVIDENCE_ROOT / 'LICENSE'), LICENSE_HASH)

    def test_mit_notice_preserves_the_pinned_complete_license(self):
        notice = ROOT / 'licenses/JanLohse-spectral-data-MIT.txt'
        self.assertEqual(sha256(notice), LICENSE_HASH)
        self.assertIn('Jan Lohse', notice.read_text(encoding='utf-8'))

    def test_spectral_arrays_are_finite_physical_monotone_and_layers_sum(self):
        for stock in SOURCE_HASHES:
            with self.subTest(stock=stock):
                profile = load_profile(stock)
                _validate_profile(profile, stock)
                data = profile.data
                for name in ('wavelengths', 'log_sensitivity', 'channel_density', 'base_density',
                             'midscale_neutral_density', 'log_exposure', 'density_curves', 'density_curves_layers'):
                    self.assertTrue(np.isfinite(getattr(data, name)).all(), name)
                np.testing.assert_array_equal(data.wavelengths, np.arange(380, 781, 5))
                self.assertTrue(np.all(np.diff(data.log_exposure) > 0))
                self.assertTrue(np.all(data.channel_density >= 0))
                self.assertTrue(np.all(data.base_density >= 0))
                self.assertTrue(np.all(data.density_curves_layers >= 0))
                np.testing.assert_allclose(data.density_curves_layers.sum(axis=1), data.density_curves, atol=1e-12)
                direction = -1 if profile.is_positive else 1
                self.assertGreaterEqual(float(np.min(np.diff(data.density_curves, axis=0) * direction)), -1e-12)
                self.assertTrue(np.all(data.density_curves_model.sigmas > 0))

    def test_extension_paper_neutral_and_dir_policy_survives_digest(self):
        for stock, entry in extension_profiles().items():
            with self.subTest(stock=stock):
                params = init_film_params(stock)
                provenance = read_json(EXTENSION_ROOT / entry['provenance_file'])
                self.assertEqual(params.print.info.stock, entry['paper'])
                self.assertFalse(params.settings.neutral_print_filters_from_database)
                self.assertFalse(params.film_render.dir_couplers.active)
                self.assertFalse(params.scanner.black_correction)
                self.assertFalse(params.scanner.white_correction)
                self.assertTrue(params.film_render.grain.active)
                self.assertTrue(params.film_render.halation.active)
                if params.film.is_negative:
                    self.assertEqual(entry['paper'], 'fujifilm_crystal_archive_typeii')
                    neutral = provenance['verification']['neutral_print']
                    np.testing.assert_allclose(entry['neutral_filters_cmy'], neutral['cmy_cc'], atol=1e-12)
                    self.assertFalse(neutral['measured_calibration'])
                    self.assertTrue(neutral['solver_success'])
                    self.assertLess(neutral['log_rgb_ratio_residual_norm'], 1e-6)
                    self.assertEqual(params.enlarger.illuminant, neutral['illuminant'])
                    np.testing.assert_allclose(
                        [params.enlarger.c_filter_neutral, params.enlarger.m_filter_neutral, params.enlarger.y_filter_neutral],
                        neutral['cmy_cc'], atol=1e-12)
                else:
                    self.assertIsNone(entry['neutral_filters_cmy'])
                    self.assertIsNone(provenance['verification']['neutral_print'])
                digested = digest_params(params)
                self.assertFalse(digested.film_render.dir_couplers.active)
                self.assertEqual(digested.print.info.stock, entry['paper'])
                self.assertEqual(print_for_stock(stock), entry['paper'])
                self.assertEqual(print_for_stock(stock, 'kodak_ultra_endura'), 'kodak_ultra_endura')

    def test_original_twenty_preserve_all_params_and_requested_paper(self):
        originals = []
        for path in PROFILE_ROOT.glob('*.json'):
            info = read_json(path)['info']
            if (info['stage'] == 'filming' and info['stock'] not in SOURCE_HASHES
                    and info['stock'] not in BLACK_AND_WHITE):
                originals.append(info['stock'])
        self.assertEqual(len(originals), 20)
        for stock in originals:
            for paper in ('kodak_portra_endura', 'kodak_ultra_endura'):
                with self.subTest(stock=stock, paper=paper):
                    actual = init_film_params(stock, paper)
                    reference = init_params(stock, paper)
                    self.assertEqual(print_for_stock(stock, paper), paper)
                    self.assert_tree_equal(actual, reference)

    def test_actual_simulator_gray_and_color_chart_outputs_are_finite_and_distinct(self):
        grays = np.repeat(np.array([0, .002, .01, .04, .184, .4, .8, 1])[:, None], 3, axis=1)
        chart = np.array([[.7, .03, .02], [.03, .6, .04], [.02, .04, .65],
                          [.6, .5, .02], [.45, .02, .5], [.02, .5, .55],
                          [.35, .15, .08], [.6, .35, .22], [.09, .18, .04], [.05, .15, .35]])
        values = np.concatenate([grays, chart])[None, ...]
        outputs = {}
        for stock in SOURCE_HASHES:
            with self.subTest(stock=stock):
                params = init_film_params(stock)
                params.io.input_color_space = 'sRGB'
                params.io.input_cctf_decoding = False
                params.io.output_color_space = 'sRGB'
                params.io.output_cctf_encoding = False
                params.io.scan_film = params.film.is_positive
                params.camera.auto_exposure = False
                params.debug.deactivate_spatial_effects = True
                params.debug.deactivate_stochastic_effects = True
                params.scanner.unsharp_mask = (0, 0)
                params.settings.use_enlarger_lut = False
                params.settings.use_scanner_lut = False
                output = Simulator(digest_params(params)).process(values.copy())
                self.assertEqual(output.shape, values.shape)
                self.assertTrue(np.isfinite(output).all())
                gray_luma = output[0, :len(grays)] @ np.array([.2126, .7152, .0722])
                self.assertGreaterEqual(float(np.min(np.diff(gray_luma))), -1e-6)
                self.assertGreater(float(np.ptp(gray_luma)), .5)
                self.assertLess(float(np.ptp(output[0, 4])), 1e-4)
                outputs[stock] = output
        for left, right in itertools.combinations(outputs, 2):
            self.assertGreater(float(np.mean(np.abs(outputs[left] - outputs[right]))), .001,
                               f'{left} and {right} must not be duplicate transforms')

    def test_desktop_and_android_bridge_build_equivalent_full_frame_params(self):
        mobile_helper = load_module('_tested_mobile_film_profiles', ANDROID_ROOT / 'film_profiles.py')
        with patch.dict(sys.modules, {'film_profiles': mobile_helper}):
            bridge = load_module('_tested_additional_profile_bridge', ANDROID_ROOT / 'studio_spectral.py')
        for stock in (*SOURCE_HASHES, 'kodak_portra_400'):
            for preview in (False, True):
                with self.subTest(stock=stock, preview=preview):
                    captured = []
                    def capture(values, params, key, signature):
                        captured.append(digest_params(params))
                        return values.copy()
                    settings = imaging.Settings(stock=stock, exposure=.4, grain=37,
                        grain_size=.8, grain_type='fine', halation=16, spectral=True,
                        film_format_mm=70,glare=4,print_exposure=.3,print_y=18,print_m=-12)
                    with patch.dict(imaging._SPECTRAL_CONTEXTS, {}, clear=True), \
                            patch.object(imaging, '_process_spectral_cached', side_effect=capture):
                        imaging._spectral(np.full((8, 12, 3), .3), settings, preview=preview)
                    self.assertEqual(len(captured), 1)
                    mobile = bridge._make_params(stock, 12, 8, 12, 8, .4, .37, .8, 'fine', .16, preview,
                        film_format_mm=70,glare=4,print_exposure=.3,print_y=18,print_m=-12)
                    self.assert_tree_equal(captured[0], mobile)

    def test_android_sources_include_exact_profiles_provenance_helper_and_license(self):
        self.assertEqual((ANDROID_ROOT / 'film_profiles.py').read_bytes(), (ROOT / 'shared/film_profiles.py').read_bytes())
        paths = [Path('profile_extensions/manifest.json')]
        paths += [Path('profiles') / (stock + '.json') for stock in SOURCE_HASHES]
        paths += [Path('profile_extensions') / (stock + '.provenance.json') for stock in SOURCE_HASHES]
        for relative in paths:
            with self.subTest(path=str(relative)):
                self.assertEqual((ANDROID_ROOT / 'spektrafilm/data' / relative).read_bytes(),
                                 (ROOT / 'vendor/spektrafilm/data' / relative).read_bytes())
        self.assertEqual((ROOT / 'android/app/src/main/assets/licenses/JanLohse-spectral-data-MIT.txt').read_bytes(),
                         (ROOT / 'licenses/JanLohse-spectral-data-MIT.txt').read_bytes())

    def test_dynamic_catalog_covers_every_camera_profile_with_valid_preview_luts(self):
        manifest = read_json(ROOT / 'assets/luts/manifest.json')
        camera_ids = {read_json(path)['info']['stock'] for path in PROFILE_ROOT.glob('*.json')
                      if read_json(path)['info']['stage'] == 'filming'}
        stocks = imaging.catalog()
        ids = [stock['id'] for stock in stocks]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), camera_ids)
        self.assertTrue(set(SOURCE_HASHES).issubset(ids))
        self.assertEqual(stocks, manifest['stocks'])
        for stock in stocks:
            with self.subTest(stock=stock['id']):
                lut = np.fromfile(ROOT / 'assets/luts' / stock['file'].removeprefix('luts/'), dtype='<f4')
                self.assertEqual(lut.size, manifest['size'] ** 3 * 3)
                self.assertTrue(np.isfinite(lut).all())
                self.assertGreaterEqual(float(lut.min()), 0)
                self.assertLessEqual(float(lut.max()), 1)
                if stock['id'] in SOURCE_HASHES:
                    self.assertEqual(stock['model_status'], 'estimated')
                    self.assertEqual(stock['profile_license'], 'MIT')
                    self.assertEqual(stock['profile_sha256'], extension_profiles()[stock['id']]['profile_sha256'])


if __name__ == '__main__':
    unittest.main()
