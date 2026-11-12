"""Packaging gates reject incomplete data and a smoke using the wrong film."""
from dataclasses import asdict
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from desktop.imaging import Settings
from scripts import verify_packaged_release as verification


class PackagedResourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.candidate = self.root / 'candidate'
        self.packaged = self.candidate / '_internal'
        self.ids = ['kodak_portra_400', *sorted(verification.ADDITIONAL_PROFILES)]
        self.data = self.root / 'vendor/spektrafilm/data'
        for folder in ('assets/luts', 'licenses', 'vendor/spektrafilm/data/profiles',
                       'vendor/spektrafilm/data/profile_extensions'):
            (self.root / folder).mkdir(parents=True, exist_ok=True)
        # Tiny binary LUT fixtures exercise size/hash gates, not spectral math.
        stocks = [dict(id=stock, file=stock + '.f32') for stock in self.ids]
        self.manifest = dict(size=2, stocks=stocks)
        self.write_json(self.root / 'assets/luts/manifest.json', self.manifest)
        for stock in self.ids:
            (self.root / 'assets/luts' / (stock + '.f32')).write_bytes(bytes(2 ** 3 * 3 * 4))
            self.write_json(self.data / 'profiles' / (stock + '.json'),
                            dict(info=dict(stock=stock, stage='filming')))
        self.write_json(self.data / 'profiles/paper.json', dict(info=dict(stock='paper', stage='printing')))
        self.write_json(self.data / 'profile_extensions/manifest.json',
                        dict(profiles={stock: {} for stock in verification.ADDITIONAL_PROFILES}))
        for stock in verification.ADDITIONAL_PROFILES:
            self.write_json(self.data / 'profile_extensions' / (stock + '.provenance.json'), dict(stock=stock))
        (self.root / 'licenses/JanLohse-spectral-data-MIT.txt').write_text('MIT test fixture', encoding='utf-8')
        for source, destination in ((self.root / 'assets', self.packaged / 'assets'),
                                    (self.data, self.packaged / 'spektrafilm/data'),
                                    (self.root / 'licenses', self.packaged / 'licenses')):
            shutil.copytree(source, destination)
        self.root_patch = patch.object(verification, 'ROOT', self.root)
        self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop()
        self.temp.cleanup()

    @staticmethod
    def write_json(path, value):
        path.write_text(json.dumps(value), encoding='utf-8')

    def test_complete_resource_catalog_records_count_and_hashes(self):
        result = verification.verify_windows_resources(self.candidate)
        self.assertEqual(result['catalog_stocks'], self.ids)
        self.assertEqual(result['catalog_count'], len(self.ids))
        self.assertEqual(set(result['additional_profiles']), verification.ADDITIONAL_PROFILES)
        self.assertIn('spektrafilm/data/profiles/agfa_vista_100.json', result['resource_sha256'])
        self.assertIn('spektrafilm/data/profile_extensions/agfa_vista_100.provenance.json', result['resource_sha256'])
        self.assertIn('licenses/JanLohse-spectral-data-MIT.txt', result['resource_sha256'])

    def test_missing_additional_profile_is_rejected(self):
        (self.packaged / 'spektrafilm/data/profiles/agfa_vista_100.json').unlink()
        with self.assertRaisesRegex(ValueError, 'spectral profile'):
            verification.verify_windows_resources(self.candidate)

    def test_stale_additional_provenance_is_rejected(self):
        (self.packaged / 'spektrafilm/data/profile_extensions/agfa_vista_100.provenance.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'spectral provenance'):
            verification.verify_windows_resources(self.candidate)

    def test_stale_lut_of_correct_size_is_rejected(self):
        lut = self.packaged / 'assets/luts/agfa_vista_100.f32'
        lut.write_bytes(bytes([1]) + lut.read_bytes()[1:])
        with self.assertRaisesRegex(ValueError, 'preview LUT'):
            verification.verify_windows_resources(self.candidate)

    def test_retired_lut_is_rejected(self):
        (self.packaged / 'assets/luts/retired.f32').write_bytes(bytes(2 ** 3 * 3 * 4))
        with self.assertRaisesRegex(ValueError, 'outdated set'):
            verification.verify_windows_resources(self.candidate)

    def test_missing_additional_license_is_rejected(self):
        (self.packaged / 'licenses/JanLohse-spectral-data-MIT.txt').unlink()
        with self.assertRaisesRegex(ValueError, 'MIT license'):
            verification.verify_windows_resources(self.candidate)


class SmokeReportTests(unittest.TestCase):
    @staticmethod
    def report():
        return json.loads(json.dumps(dict(ok=True, smoke_stock='agfa_vista_100',
            settings=asdict(Settings(stock='agfa_vista_100', spectral=True, film_enabled=True,
                                    lens_correction=False, defringe=False)),
            checks=['asynchronous import', 'rendered preview', 'grouped undo', 'redo',
                    'full-size export', 'embedded sRGB profile', 'source integrity', 'requested film selected'])))

    def test_additional_film_full_spectral_report_is_accepted(self):
        verification.verify_film_only_report(self.report(), expected_stock='agfa_vista_100')

    def test_default_film_cannot_pass_an_additional_film_smoke(self):
        report = self.report()
        report['settings']['stock'] = 'kodak_portra_400'
        with self.assertRaisesRegex(ValueError, 'requested smoke film'):
            verification.verify_film_only_report(report, expected_stock='agfa_vista_100')

    def test_hidden_editor_values_are_still_rejected_for_additional_films(self):
        report = self.report()
        report['settings']['contrast'] = 10
        with self.assertRaisesRegex(ValueError, 'Removed editor'):
            verification.verify_film_only_report(report, expected_stock='agfa_vista_100')


if __name__ == '__main__':
    unittest.main()
