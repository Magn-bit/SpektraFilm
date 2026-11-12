import unittest

import numpy as np

from spektrafilm.model.grain import (
    _apply_grain_from_density_curves,
    apply_grain_to_density_layers,
    interp_density_cmy_layers,
    layer_particle_model,
    set_grain_seed_offset,
)


class StreamedGrainTests(unittest.TestCase):
    def _compare(self, positive):
        rng = np.random.default_rng(321)
        points = 180
        base = np.linspace(0.0, 2.2, points)
        if positive:
            base = base[::-1].copy()
        density_curves = np.repeat(base[:, None], 3, axis=1)
        density_curves_layers = np.empty((points, 3, 3), dtype=np.float64)
        for layer in range(3):
            density_curves_layers[:, layer, :] = base[:, None] * (0.3 + 0.2 * layer)
        density = rng.uniform(0.15, 1.8, (43, 67, 3))
        maxima = np.nanmax(density_curves_layers, axis=0)

        set_grain_seed_offset(257)
        expanded = interp_density_cmy_layers(
            density, density_curves, density_curves_layers,
            positive_film=positive,
        )
        expected = apply_grain_to_density_layers(
            expanded.copy(), maxima, pixel_size_um=8.5,
            particle_area_um2=0.24, grain_blur=0.7,
            grain_blur_dye_clouds_um=0.35,
            grain_micro_structure=(0.1, 30),
        )

        set_grain_seed_offset(257)
        actual = _apply_grain_from_density_curves(
            density, maxima, density_curves, density_curves_layers,
            positive_film=positive, pixel_size_um=8.5,
            particle_area_um2=0.24, grain_blur=0.7,
            grain_blur_dye_clouds_um=0.35,
            grain_micro_structure=(0.1, 30),
        )
        np.testing.assert_allclose(actual, expected, rtol=0, atol=2e-14)
        set_grain_seed_offset(0)

    def test_negative_film_layers_match_expanded_reference(self):
        self._compare(False)

    def test_positive_film_layers_match_expanded_reference(self):
        self._compare(True)

    def test_poisson_thinning_preserves_expected_grain_distribution(self):
        density_value = 0.72
        density_max = 1.8
        particles = 12.0
        uniformity = 0.97
        image = np.full((360, 480), density_value)
        actual = layer_particle_model(
            image, density_max=density_max,
            n_particles_per_pixel=particles,
            grain_uniformity=uniformity, seed=913,
        )
        probability = density_value / density_max
        saturation = 1 - probability * uniformity * (1 - 1e-6)
        expected_mean = particles * probability / saturation * (density_max / particles) * saturation
        expected_variance = particles * probability / saturation * (density_max / particles) ** 2 * saturation**2
        self.assertAlmostEqual(float(actual.mean()), expected_mean, delta=expected_mean * 0.015)
        self.assertAlmostEqual(float(actual.var()), expected_variance, delta=expected_variance * 0.025)


if __name__ == "__main__":
    unittest.main()
