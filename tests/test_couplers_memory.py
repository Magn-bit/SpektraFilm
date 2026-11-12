import unittest

import numpy as np
from opt_einsum import contract

from spektrafilm.model.couplers import compute_exposure_correction_dir_couplers
from spektrafilm.utils.fast_gaussian_filter import (
    _EXPONENTIAL_GAUSSIAN_FITS,
    fast_exponential_filter,
    fast_gaussian_filter,
)


class CouplerMemoryTests(unittest.TestCase):
    def test_exponential_filter_matches_original_mixture_expression(self):
        rng = np.random.default_rng(450)
        image = rng.normal(size=(37, 29, 3))
        decay = np.array([1.3, 2.2, 3.1])
        expected = None
        for amplitude, ratio in _EXPONENTIAL_GAUSSIAN_FITS[3]:
            component = fast_gaussian_filter(image, ratio * decay)
            if expected is None:
                expected = amplitude * component
            else:
                expected += amplitude * component
        actual = fast_exponential_filter(image, decay)
        np.testing.assert_array_equal(actual, expected)

    def test_dir_coupler_correction_matches_original_expression(self):
        rng = np.random.default_rng(451)
        density = rng.uniform(0.1, 1.8, (31, 27, 3))
        original_density = density.copy()
        log_raw = rng.uniform(-2, 0, density.shape)
        matrix = rng.uniform(0, 0.4, (3, 3))
        density_max = np.array([1.7, 1.8, 1.9])

        for positive in (False, True):
            for high_shift in (0.0, 0.13):
                silver = density_max - density if positive else density.copy()
                silver += high_shift * silver**2
                correction = contract("ijk, km->ijm", silver, matrix)
                expected = log_raw - (
                    0.94 * fast_gaussian_filter(correction, 1.5)
                    + 0.06 * fast_exponential_filter(correction, 2.7)
                )
                actual = compute_exposure_correction_dir_couplers(
                    log_raw, density, density_max, matrix, 1.5, 2.7,
                    0.06, high_exposure_couplers_shift=high_shift,
                    positive=positive,
                )
                np.testing.assert_array_equal(actual, expected)
                np.testing.assert_array_equal(density, original_density)


if __name__ == "__main__":
    unittest.main()
