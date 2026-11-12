"""Real GPU output-gamut parity and explicit CPU reference contracts."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor'))
sys.path.insert(0,str(ROOT))

from desktop import compute
from spektrafilm.utils.gamut_compression import OutputGamutCompressSpec,compress_rgb


class GpuComputeTests(unittest.TestCase):
    def test_explicit_cpu_keeps_reference_exact(self):
        source=np.random.default_rng(38).uniform(0,1.5,(256,256,3))
        spec=OutputGamutCompressSpec()
        expected=compress_rgb(source,spec,output_color_space='sRGB')
        with patch.dict(os.environ,{'SPEKTRAFILM_COMPUTE':'cpu'}):
            actual=compute.compress_output_gamut(source,spec,output_color_space='sRGB')
        np.testing.assert_array_equal(actual,expected)

    def test_unvalidated_spec_stays_on_reference(self):
        source=np.random.default_rng(19).uniform(0,1.2,(260,256,3))
        spec=OutputGamutCompressSpec(algorithm='aces_rgc')
        expected=compress_rgb(source,spec,output_color_space='sRGB')
        with patch.dict(os.environ,{'SPEKTRAFILM_COMPUTE':'auto'}),patch.object(compute,'_GPU') as gpu:
            actual=compute.compress_output_gamut(source,spec,output_color_space='sRGB')
        gpu.compress_for_spec.assert_not_called()
        np.testing.assert_array_equal(actual,expected)

    @unittest.skipUnless(os.environ.get('SPEKTRAFILM_TEST_GPU')=='1','requires an explicit GPU validation run')
    def test_vulkan_matches_cpu_across_chunk_boundaries(self):
        import colour
        source=np.random.default_rng(83).uniform(-.02,2,(262,258,3)).astype(np.float64)
        original=source.copy()
        spec=OutputGamutCompressSpec()
        expected=compress_rgb(source,spec,output_color_space='sRGB')
        from desktop.gpu_gamut_prototype import GamutGpuPrototype
        with GamutGpuPrototype(max_pixels_per_dispatch=16384) as gpu:
            with patch.dict(os.environ,{'SPEKTRAFILM_COMPUTE':'auto'}),patch.object(compute,'_GPU',gpu):
                actual=compute.compress_output_gamut(source,spec,output_color_space='sRGB')
        self.assertEqual(actual.shape,source.shape)
        self.assertTrue(np.isfinite(actual).all())
        np.testing.assert_array_equal(source,original)
        self.assertLess(float(np.abs(expected-actual).max()),2e-5)
        def lab(rgb):
            return colour.XYZ_to_Lab(colour.RGB_to_XYZ(rgb,'sRGB',apply_cctf_decoding=False))
        de=colour.delta_E(lab(expected),lab(actual),method='CIE 2000')
        self.assertLess(float(np.max(de)),.005)

    @unittest.skipUnless(os.environ.get('SPEKTRAFILM_TEST_GPU')=='1','requires an explicit GPU validation run')
    def test_full_spectral_pixels_keep_grain_and_match_cpu_encoding(self):
        from PIL import Image
        from desktop import imaging
        pixels=np.random.default_rng(217).integers(0,256,(256,256,3),dtype=np.uint8)
        source=Image.fromarray(pixels)
        settings=imaging.Settings(spectral=True,grain=23,halation=18)
        original_init=imaging.init_film_params
        def params(stock,paper):
            result=original_init(stock,paper)
            result.print_render.glare.active=False
            return result
        with imaging._SPECTRAL_CONTEXTS_LOCK:
            imaging._SPECTRAL_CONTEXTS.clear()
            imaging._SPECTRAL_CONTEXT_SIGNATURES.clear()
        with patch.object(imaging,'init_film_params',side_effect=params):
            with patch.dict(os.environ,{'SPEKTRAFILM_COMPUTE':'cpu'}):
                expected=np.asarray(imaging.render(source,settings))
            with patch.dict(os.environ,{'SPEKTRAFILM_COMPUTE':'auto'}):
                actual=np.asarray(imaging.render(source,settings))
        self.assertEqual(compute.status()['gamut_backend'],'Vulkan')
        error=np.abs(actual.astype(int)-expected.astype(int))
        self.assertLessEqual(int(error.max()),1)
        self.assertLess(float(error.mean()),.01)
        np.testing.assert_array_equal(np.asarray(source),pixels)

    def test_device_error_preserves_cpu_formula_even_when_cleanup_fails(self):
        source=np.full((256,256,3),.3)
        spec=OutputGamutCompressSpec()
        expected=compress_rgb(source,spec,output_color_space='sRGB')
        from unittest.mock import Mock
        gpu=Mock()
        gpu.compress_for_spec.side_effect=RuntimeError('lost device')
        gpu.close.side_effect=RuntimeError('already lost')
        with patch.dict(os.environ,{'SPEKTRAFILM_COMPUTE':'auto'}), \
             patch.object(compute,'_GPU',gpu),patch.object(compute,'_UNAVAILABLE',False), \
             patch.object(compute,'_STATUS',{}),self.assertLogs('desktop.compute',level='WARNING'):
            actual=compute.compress_output_gamut(source,spec,output_color_space='sRGB')
            self.assertTrue(compute._UNAVAILABLE)
            self.assertIsNone(compute._GPU)
        np.testing.assert_array_equal(actual,expected)


if __name__=='__main__':
    unittest.main()
