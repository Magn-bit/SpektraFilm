import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from opt_einsum import contract

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vendor'))
couplers = importlib.import_module('spektrafilm.model.couplers')
filters = importlib.import_module('spektrafilm.utils.fast_gaussian_filter')


class ExactFilterShortcutTests(unittest.TestCase):
    def test_radius_zero_matches_the_existing_fir_and_owns_output(self):
        rng = np.random.default_rng(4508)
        for shape in ((1, 1), (2, 19), (29, 31), (17, 21)):
            image = rng.normal(size=shape)
            if shape == (17, 21):
                image = image[:, ::2]  # The public channel adapter permits strided input.
            saved = image.copy()
            for truncate in (1., 3., 4.):
                for sigma in (1e-10, .1/truncate, np.nextafter(.5/truncate, 0)):
                    if int(truncate*sigma+.5) != 0:
                        continue
                    with self.subTest(shape=shape, truncate=truncate, sigma=sigma):
                        kernel, radius = filters._gaussian_kernel_1d(sigma, truncate)
                        reference = np.empty_like(image)
                        filters._fir_2d_fused(image, reference, kernel, radius)
                        with patch.object(filters, '_fir_2d_fused', side_effect=AssertionError('unit FIR dispatched')):
                            actual = filters._gaussian_filter_2d_small(image, sigma, truncate)
                        np.testing.assert_array_equal(actual, reference)
                        self.assertFalse(np.shares_memory(actual, image))
                        actual[...] = 0
                        np.testing.assert_array_equal(image, saved)

    def test_radius_transition_still_runs_real_kernel(self):
        image = np.random.default_rng(4509).normal(size=(27, 19))
        sigma = .5/3
        self.assertEqual(int(sigma*3+.5), 1)
        with patch.object(filters, '_fir_2d_fused', wraps=filters._fir_2d_fused) as called:
            actual = filters._gaussian_filter_2d_small(image, sigma, 3.)
        self.assertEqual(called.call_count, 1)
        kernel, radius = filters._gaussian_kernel_1d(sigma, 3.)
        reference = np.empty_like(image)
        filters._fir_2d_fused(image, reference, kernel, radius)
        np.testing.assert_array_equal(actual, reference)

    def test_public_multichannel_identity_keeps_values_and_ownership(self):
        image = np.random.default_rng(4510).uniform(-3, 2, (23, 29, 3))[:, ::2]
        actual = filters.fast_gaussian_filter(image, (.01, .10, .15))
        np.testing.assert_array_equal(actual, image)
        self.assertFalse(np.shares_memory(actual, image))

    def test_dir_endpoints_and_interior_match_original_expression(self):
        rng = np.random.default_rng(4511)
        for shape in ((1, 1, 3), (19, 23, 3)):
            density = rng.uniform(.01, 1.8, shape)
            log_raw = rng.uniform(-4, 1, shape)
            saved_density, saved_raw = density.copy(), log_raw.copy()
            matrix = rng.uniform(0, .4, (3, 3))
            maximum = np.array([1.7, 1.8, 1.9])
            for weight in (0., 1., np.nextafter(0., 1.), .06, np.nextafter(1., 0.)):
                for positive in (False, True):
                    for high_shift in (0., .13):
                        with self.subTest(shape=shape, weight=weight, positive=positive, high_shift=high_shift):
                            silver = maximum-density if positive else density.copy()
                            if high_shift:
                                silver += high_shift*silver**2
                            correction = contract('ijk,km->ijm', silver, matrix)
                            reference = log_raw - (
                                (1-weight)*filters.fast_gaussian_filter(correction, 1.5)
                                + weight*filters.fast_exponential_filter(correction, 2.7))
                            with patch.object(couplers, 'fast_gaussian_filter', wraps=couplers.fast_gaussian_filter) as gaussian, \
                                    patch.object(couplers, 'fast_exponential_filter', wraps=couplers.fast_exponential_filter) as exponential:
                                actual = couplers.compute_exposure_correction_dir_couplers(
                                    log_raw, density, maximum, matrix, 1.5, 2.7, weight,
                                    high_exposure_couplers_shift=high_shift, positive=positive)
                            np.testing.assert_array_equal(actual, reference)
                            self.assertEqual(gaussian.call_count, 0 if weight == 1 else 1)
                            self.assertEqual(exponential.call_count, 0 if weight == 0 else 1)
                            np.testing.assert_array_equal(density, saved_density)
                            np.testing.assert_array_equal(log_raw, saved_raw)
                            self.assertFalse(np.shares_memory(actual, log_raw))

    def test_nonfinite_diagnostic_input_retains_original_branch_propagation(self):
        density = np.ones((2, 3, 3))
        density[0, 0, 0] = np.inf
        log_raw = np.full(density.shape, -1.)
        matrix = np.eye(3)
        with np.errstate(invalid='ignore'):
            for weight in (0., 1.):
                correction = contract('ijk,km->ijm', density, matrix)
                reference = log_raw - (
                    (1-weight)*filters.fast_gaussian_filter(correction, 1.5)
                    + weight*filters.fast_exponential_filter(correction, 2.7))
                with patch.object(couplers, 'fast_gaussian_filter', wraps=couplers.fast_gaussian_filter) as gaussian, \
                        patch.object(couplers, 'fast_exponential_filter', wraps=couplers.fast_exponential_filter) as exponential:
                    actual = couplers.compute_exposure_correction_dir_couplers(
                        log_raw, density, np.ones(3), matrix, 1.5, 2.7, weight)
                np.testing.assert_array_equal(actual, reference)
                self.assertEqual(gaussian.call_count, 1)
                self.assertEqual(exponential.call_count, 1)


if __name__ == '__main__':
    unittest.main()
