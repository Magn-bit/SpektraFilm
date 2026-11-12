"""Small integration fixtures for scene-domain curves and real print layers."""
import ctypes as ct
import json
import unittest

import numpy as np

from desktop import native_spectral as native
from desktop.imaging import Settings


@unittest.skipUnless(native.available(), 'Windows Vulkan runtime required')
class NativeScenePair(unittest.TestCase):
    def setUp(self):
        self.engine = native._get_engine()
        x = np.linspace(.055, .23, 96, dtype=np.float32)
        self.source = np.broadcast_to(x[None, :, None], (64, 96, 3)).copy()
        self.source *= np.array([.94, 1., 1.06], np.float32)
        self.values = native.parameters(Settings(stock='kodak_portra_400', grain=0,
            halation=0, glare=0, dir_couplers_amount=0))
        self.values.update(input_cctf_decoding=False, striped=False,
                           dir_couplers_active=False)

    def tearDown(self):
        native.clear_sessions()

    def test_decode_identity_and_one_stop_are_linear_scene_gains(self):
        base = self.engine.render(self.source, self.values, None)
        identity = np.tile(np.linspace(0, 1, 129), (5, 1))
        wire = lambda rows: ','.join(f'{x:.8f}' for x in rows.ravel())
        identity_result = self.engine.render(self.source, dict(self.values,
            scene_curve=wire(identity)), None)
        np.testing.assert_allclose(identity_result, base, atol=2/65535, rtol=0)
        identity[1] = np.minimum(identity[1] + 1/16, 1)
        shifted = self.engine.render(self.source, dict(self.values,
            scene_curve=wire(identity)), None)
        doubled = self.engine.render(self.source * np.float32(2), self.values, None)
        np.testing.assert_allclose(shifted, doubled, atol=2/65535, rtol=0)
        self.assertGreater(float(np.max(np.abs(shifted-base))), .01)
        with self.assertRaisesRegex(native.NativeSpectralError, 'scene_curve'):
            self.engine.render(self.source, dict(self.values, scene_curve='0,1'), None)

    def test_minilab_is_a_real_qualified_pair_and_responds_to_enlarger_controls(self):
        values = dict(self.values, print_stock='kodak_portra_endura', minilab_active=True)
        lab = self.engine.render(self.source, values, None)
        optical = self.engine.render(self.source, dict(values, minilab_active=False), None)
        self.assertEqual(lab.shape, self.source.shape)
        self.assertTrue(np.isfinite(lab).all())
        self.assertGreater(float(np.max(np.abs(lab-optical))), .01)
        for change in (dict(print_exposure=2.), dict(y_filter_shift=.25),
                       dict(m_filter_shift=.25), dict(preflash_exposure=.2)):
            adjusted = self.engine.render(self.source, dict(values, **change), None)
            self.assertTrue(np.isfinite(adjusted).all())
            self.assertGreater(float(np.max(np.abs(adjusted-lab))), .005)
        np.testing.assert_array_equal(self.engine.render(self.source, values, None), lab)

    def test_public_pair_prints_from_one_negative_without_mutating_the_base(self):
        values = dict(self.values, output_color_space='ProPhoto RGB')
        key = ('native-pair-fixture',)
        request = dict(tier='full', target_space='sRGB')
        baseline = self.engine.render(self.source, values, key, pair_request=request)
        request['pair'] = {'gates': [[0, 0, .5, 1], [.5, 0, 1, 1]],
            'left': {'print': {'brightnessStops': 1., 'yFilterShift': 0.,
                'mFilterShift': 0., 'preflashExposure': 0.}}, 'right': None}
        changed = self.engine.render(self.source, values, key, pair_request=request)
        self.assertGreater(float(np.max(np.abs(changed[:, :40]-baseline[:, :40]))), .02)
        np.testing.assert_allclose(changed[:, 56:], baseline[:, 56:], atol=2/65535, rtol=0)
        restored = self.engine.render(self.source, values, key,
            pair_request=dict(tier='full', target_space='sRGB'))
        np.testing.assert_array_equal(restored, baseline)


if __name__ == '__main__':
    unittest.main()
