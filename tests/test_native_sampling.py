import sys
import unittest
from pathlib import Path

import numpy as np
import scipy.stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vendor'))
from spektrafilm.model.grain import layer_particle_model


def legacy_particle(density, maximum=2.2, particles=10., uniformity=.98, seed=41):
    np.random.seed(seed)
    probability = np.clip(density/maximum, 1e-6, 1-1e-6)
    od = maximum/particles
    saturation = 1-probability*uniformity*(1-1e-6)
    sample = scipy.stats.poisson.rvs(particles*probability/saturation)
    sample = np.asarray(sample, dtype=np.float64)
    sample *= od
    sample *= saturation
    return sample


class NativeSamplingTests(unittest.TestCase):
    def setUp(self):
        self.old_random_state = scipy.stats.poisson.random_state
        scipy.stats.poisson.random_state = np.random.mtrand._rand
        self.addCleanup(setattr, scipy.stats.poisson, 'random_state', self.old_random_state)

    def assert_state_equal(self, first, second):
        for a, b in zip(first, second):
            np.testing.assert_array_equal(a, b)

    def test_exact_same_seed_samples_and_rng_state_across_density_regimes(self):
        rng = np.random.default_rng(7451)
        samples = [np.zeros((2, 3)), np.full((13, 17), 2.2),
                   rng.uniform(-1, 5, (31, 29)), np.empty((0, 3)),
                   rng.uniform(.01, 2, (19, 23))[:, ::2]]
        for density in samples:
            for particles in (.1, 12., 1e5):
                with self.subTest(shape=density.shape, particles=particles):
                    reference = legacy_particle(density, particles=particles, seed=92)
                    expected_state = np.random.get_state()
                    actual = layer_particle_model(density, n_particles_per_pixel=particles, seed=92)
                    np.testing.assert_array_equal(actual, reference)
                    self.assert_state_equal(np.random.get_state(), expected_state)
                    self.assertFalse(np.shares_memory(actual, density))

    def test_invalid_rates_raise_value_error_without_consuming_rng(self):
        for bad in (-1., np.nan, np.inf, -np.inf, 1e20):
            rates = np.array([0., bad, 1.])
            with self.subTest(rate=bad):
                for sampler in (scipy.stats.poisson.rvs, scipy.stats.poisson.random_state.poisson):
                    np.random.seed(711)
                    expected_state = np.random.get_state()
                    with self.assertRaises(ValueError):
                        sampler(rates)
                    self.assert_state_equal(np.random.get_state(), expected_state)

    def test_invalid_density_or_particle_count_retains_value_error(self):
        cases = [(np.array([[np.nan, .5]]), 10.), (np.ones((2, 3)), -2.),
                 (np.ones((2, 3)), 1e20)]
        for density, particles in cases:
            with self.subTest(particles=particles, density=density):
                with self.assertRaises(ValueError):
                    legacy_particle(density, particles=particles)
                expected_state = np.random.get_state()
                with self.assertRaises(ValueError):
                    layer_particle_model(density, n_particles_per_pixel=particles, seed=41)
                self.assert_state_equal(np.random.get_state(), expected_state)

    def test_explicit_scipy_randomstate_and_generator_are_preserved(self):
        density = np.linspace(.01, 2., 91).reshape(7, 13)
        for create in (lambda:np.random.RandomState(671), lambda:np.random.default_rng(671)):
            with self.subTest(generator=type(create()).__name__):
                scipy.stats.poisson.random_state = create()
                reference = legacy_particle(density)
                scipy.stats.poisson.random_state = create()
                actual = layer_particle_model(density, seed=41)
                np.testing.assert_array_equal(actual, reference)

    def test_single_row_or_pixel_keeps_the_input_geometry(self):
        # scipy.stats.rvs squeezes leading singleton axes when size is absent;
        # the native NumPy sampler preserves them for narrow export regions.
        for shape in ((1, 19), (19, 1), (1, 1)):
            density = np.full(shape, .7)
            actual = layer_particle_model(density, seed=41)
            self.assertEqual(actual.shape, shape)
            self.assertTrue(np.isfinite(actual).all())


if __name__ == '__main__':
    unittest.main()
