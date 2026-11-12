import json
import math
from dataclasses import replace
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw

from desktop import lens


class LensTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.TemporaryDirectory()
        self.root = Path(self.store.name)
        self.env = patch.dict(os.environ, {'SPEKTRAFILM_LCP_PATH': str(self.root)})
        self.env.start()
        self.tool = patch('desktop.lens._exiftool', return_value=None)
        self.tool.start()
        lens._metadata.cache_clear()
        lens._find_profile.cache_clear()
        lens._profile_paths.cache_clear()
        lens._read_profile.cache_clear()
        lens._profile_header.cache_clear()
        lens._identity_index.cache_clear()
        self.photo = self.root / 'photo.jpg'
        exif = Image.Exif()
        for key, value in {271: 'TEST', 272: 'Test camera', 42036: 'Test 35mm F2', 37386: 35.0, 274: 1}.items():
            exif[key] = value
        Image.new('RGB', (240, 160), (120, 120, 120)).save(self.photo, exif=exif)

    def tearDown(self):
        self.tool.stop()
        self.env.stop()
        self.store.cleanup()

    def profile(self, *, coefficient='.12', raw=False, model='', name='test.lcp', ca=False, focal=35):
        chrom = ''
        if ca:
            chrom = '''<st:ChromaticGreenModel st:FocalLengthX="1" st:FocalLengthY="1"/>
                <st:ChromaticRedGreenModel st:FocalLengthX="1" st:FocalLengthY="1" st:ScaleFactor="1.002"/>
                <st:ChromaticBlueGreenModel st:FocalLengthX="1" st:FocalLengthY="1" st:ScaleFactor="0.998"/>'''
        path = self.root / name
        path.write_text(f'''<x xmlns:st="http://ns.adobe.com/photoshop/1.0/camera-profile"
            xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
            <rdf:Description st:Make="TEST" st:Model="{model}" st:Lens="Test 35mm F2"
                st:CameraRawProfile="{raw}" st:SensorFormatFactor="1" st:FocalLength="{focal}">
                <st:PerspectiveModel st:Version="2" st:FocalLengthX="1" st:FocalLengthY="1"
                    st:ImageXCenter=".46" st:ImageYCenter=".52" st:RadialDistortParam1="{coefficient}">{chrom}</st:PerspectiveModel>
            </rdf:Description></x>''', encoding='utf-8')
        return path

    def test_pillow_metadata_and_exact_match(self):
        self.profile()
        status = lens.inspect_photo(str(self.photo))
        self.assertTrue(status['matched'])
        self.assertEqual(status['lens'], 'Test 35mm F2')
        self.assertEqual(status['focal_length'], 35)
        self.assertEqual(status['metadata_source'], 'pillow')
        json.dumps(status)

    def test_raw_profiles_do_not_apply_to_jpeg(self):
        self.profile(raw=True)
        self.assertFalse(lens.inspect_photo(str(self.photo))['matched'])

    def test_wrong_camera_specific_profile_is_skipped(self):
        self.profile(model='Another camera')
        self.assertFalse(lens.inspect_photo(str(self.photo))['matched'])

    def test_ambiguous_profiles_are_not_guessed(self):
        self.profile(name='one.lcp')
        self.profile(name='two.lcp')
        status = lens.inspect_photo(str(self.photo))
        self.assertFalse(status['matched'])
        self.assertEqual(status['reason'], 'ambiguous_profile')

    def test_camera_specific_profile_takes_priority(self):
        self.profile(name='generic.lcp')
        specific = self.profile(name='specific.lcp', model='Test camera')
        self.assertEqual(lens.inspect_photo(str(self.photo))['profile_path'], str(specific))

    def test_broken_or_nonfinite_profile_does_not_abort_import(self):
        self.profile(coefficient='NaN')
        (self.root / 'broken.lcp').write_text('<broken', encoding='utf-8')
        source = Image.new('RGB', (30, 20), 'gray')
        result, status = lens.prepare_photo(source, str(self.photo), defringe=False)
        self.assertIs(result, source)
        self.assertFalse(status['distortion'])

    def test_missing_metadata_preserves_geometry(self):
        self.profile()
        source = Image.new('RGB', (30, 20), 'gray')
        result, status = lens.prepare_photo(source, str(self.root / 'absent.arw'), defringe=False)
        self.assertIs(result, source)
        self.assertEqual(status['reason'], 'metadata_missing')
        self.assertIn('缺少镜头信息', status['summary'])

    def test_disabled_processing_is_identity(self):
        self.profile()
        source = Image.new('RGB', (30, 20), 'gray')
        result, status = lens.prepare_photo(source, str(self.photo), correction=False, defringe=False)
        self.assertIs(result, source)
        self.assertEqual(status['reason'], 'disabled')
        self.assertEqual(status['summary'], '镜头校正已关闭')
        self.assertFalse(status['correction_enabled'])

    def test_zero_polynomial_is_pixel_exact(self):
        self.profile(coefficient='0')
        source = Image.fromarray(np.random.default_rng(4).integers(0, 255, (80, 120, 3), dtype=np.uint8))
        result, status = lens.prepare_photo(source, str(self.photo), defringe=False)
        self.assertTrue(status['distortion'])
        self.assertTrue(np.array_equal(np.asarray(result), np.asarray(source)))
        self.assertIn('已矫正 Test 35mm F2', status['summary'])
        self.assertIn(status['profile'], status['summary'])
        self.assertEqual(status['profile_path'], str(self.root / 'test.lcp'))

    def test_positive_distortion_autocrops_and_preserves_dimensions(self):
        self.profile()
        source = Image.new('RGB', (240, 160), (90, 90, 90))
        result, status = lens.prepare_photo(source, str(self.photo), defringe=False)
        self.assertEqual(result.size, source.size)
        self.assertTrue(status['distortion'])
        self.assertGreater(status['crop_scale'], 1)
        self.assertEqual(np.asarray(result).min(), 90)

    def test_all_exif_rotations_and_reflections_use_sensor_coordinates(self):
        profile = lens._profile(str(self.profile()))
        metadata = lens.inspect_photo(str(self.photo))
        source = Image.fromarray(np.random.default_rng(8).integers(0, 255, (80, 120, 3), dtype=np.uint8))
        baseline = lens._optical(source, profile, metadata)[0]
        for orientation, transpose in lens._ORIENT.items():
            with self.subTest(orientation=orientation):
                display = source.transpose(transpose)
                result = lens._optical(display, profile, dict(metadata, orientation=orientation))[0]
                self.assertTrue(np.array_equal(np.asarray(result), np.asarray(baseline.transpose(transpose))))

    def test_known_curved_calibration_line_becomes_straight(self):
        profile = lens._profile(str(self.profile(coefficient='.8')))
        metadata = lens.inspect_photo(str(self.photo))
        width, height = 512, 384
        ideal_x = width * .27
        points = []
        for y in np.linspace(0, height - 1, height * 3):
            nx, ny = (ideal_x - width * .46) / width, (y - height * .52) / width
            factor = 1 + .8 * (nx * nx + ny * ny)
            points.append((nx * factor * width + width * .46, ny * factor * width + height * .52))
        source = Image.new('RGB', (width, height), 'black')
        ImageDraw.Draw(source).line(points, fill='white', width=4)
        result, _, zoom, _ = lens._optical(source, profile, metadata)
        array = np.asarray(result)
        expected_x = (ideal_x - width / 2) * zoom + width / 2
        positions = []
        for row in range(20, height - 20, 12):
            low, high = int(expected_x) - 7, int(expected_x) + 8
            region = array[row, low:high, 0]
            self.assertGreater(region.max(), 170)
            positions.append(low + np.argmax(region))
        self.assertLessEqual(np.ptp(positions), 2)

    def test_chromatic_models_apply_only_as_complete_set(self):
        self.profile(ca=True)
        source = Image.new('RGB', (180, 120), (90, 90, 90))
        result, status = lens.prepare_photo(source, str(self.photo), defringe=False)
        self.assertTrue(status['chromatic_aberration'])
        self.assertEqual(result.size, source.size)

    def test_incomplete_chromatic_models_are_not_applied(self):
        profile = lens._profile(str(self.profile(ca=True)))
        profile = dict(profile, samples=[dict(sample, chrom={k: v for k, v in sample['chrom'].items()
                                                           if k != 'ChromaticBlueGreenModel'})
                                         for sample in profile['samples']])
        _, chrom, _ = lens._select(profile, lens.inspect_photo(str(self.photo)))
        self.assertIsNone(chrom)

    def test_zoom_coefficients_interpolate_in_log_focal_length(self):
        profile = lens._profile(str(self.profile(coefficient='.1')))
        low = profile['samples'][0]
        high = dict(low, focal=70., base=replace(low['base'], k1=.3))
        profile = dict(profile, samples=[low, high])
        metadata = dict(lens.inspect_photo(str(self.photo)), focal_length=math.sqrt(35 * 70))
        base, _, samples = lens._select(profile, metadata)
        self.assertAlmostEqual(base.k1, .2)
        self.assertEqual(samples, [35, 70])

    def test_focal_length_outside_calibration_is_not_extrapolated(self):
        self.profile(focal=100)
        source = Image.new('RGB', (30, 20), 'gray')
        result, status = lens.prepare_photo(source, str(self.photo), defringe=False)
        self.assertIs(result, source)
        self.assertFalse(status['distortion'])
        self.assertEqual(status['reason'], 'focal_outside_calibration')
        self.assertIn('镜头配置未应用', status['summary'])
        self.assertIn('焦距超出配置范围', status['summary'])

    def test_unmatched_lens_is_named_without_claiming_a_correction(self):
        source = Image.new('RGB', (30, 20), 'gray')
        result, status = lens.prepare_photo(source, str(self.photo), defringe=False)
        self.assertIs(result, source)
        self.assertFalse(status['distortion'])
        self.assertIn('镜头未匹配 · Test 35mm F2', status['summary'])
        self.assertNotIn('已矫正', status['summary'])

    def test_defringe_reduces_thin_purple_edge(self):
        array = np.full((80, 120, 3), 245, dtype=np.uint8)
        array[:, 61:] = 25
        array[:, 59:61] = (190, 70, 210)
        source = Image.fromarray(array)
        result, pixels = lens._defringe(source)
        self.assertGreater(pixels, 0)
        self.assertLess(int(np.asarray(result)[40, 60, 0]) - int(np.asarray(result)[40, 60, 1]), 50)
        self.assertTrue(np.array_equal(np.asarray(result)[:, :58], array[:, :58]))

    def test_broad_purple_subject_is_preserved(self):
        array = np.full((80, 120, 3), 245, dtype=np.uint8)
        array[15:65, 25:95] = (165, 55, 190)
        source = Image.fromarray(array)
        result, pixels = lens._defringe(source)
        self.assertEqual(pixels, 0)
        self.assertTrue(np.array_equal(np.asarray(result), array))

    def test_nested_rdf_and_element_style_profile(self):
        path = self.profile()
        text = path.read_text(encoding='utf-8')
        text = text.replace('<st:PerspectiveModel st:Version="2"', '<st:PerspectiveModel><rdf:Description st:Version="2"')
        text = text.replace('</st:PerspectiveModel>', '</rdf:Description></st:PerspectiveModel>')
        path.write_text(text, encoding='utf-8')
        self.assertTrue(lens.inspect_photo(str(self.photo))['matched'])

    def test_local_sony_profile_parses_and_maps_when_available(self):
        path = Path('C:/ProgramData/Adobe/CameraRaw/LensProfiles/1.0/Sony/SONY (Sony FE 24-70mm F2.8 GM II) - RAW.lcp')
        if not path.is_file():
            self.skipTest('Local Adobe profile is optional and never bundled')
        profile = lens._profile(str(path))
        metadata = dict(focal_length=24., focal_35mm=24., focus_distance=0., orientation=1)
        result, ca, zoom, samples = lens._optical(Image.new('RGB', (180, 120), (80, 80, 80)), profile, metadata)
        self.assertEqual(result.size, (180, 120))
        self.assertGreaterEqual(zoom, 1)
        self.assertEqual(samples, [24, 24])


if __name__ == '__main__':
    unittest.main()
