"""Numerical contracts for independently implemented curves, grading and masks.

OKLab checks use colour-science as an independent conversion reference. Its
D65/sRGB matrices differ slightly from the compact runtime matrices: measured
chroma drift for an in-gamut luma-only edit is below 8.1e-6, hence a 2e-5 bound.
No Lightroom/Capture One private interpolation or colour math is asserted.
"""
from dataclasses import replace
from pathlib import Path
import colorsys
import sys
import unittest

import numpy as np
import colour

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shared.color_tools import (
    ZONES, CurveSet, ColorGrading, TonalGrade, apply_color_tools,
)
from shared.local_masks import MaskLayer, apply_masks, rasterize_mask


def reference_lab(rgb):
    return colour.XYZ_to_Oklab(colour.sRGB_to_XYZ(rgb))


def gray(values):
    return np.repeat(np.asarray(values, dtype=np.float32)[None, :, None], 3, axis=2)


def arbitrary_regions(width, height):
    """Uneven cuts include narrow tiles and cross the runtime's 128-row strips."""
    xs = sorted(set((0, 1, 7, width // 3, width // 3 + 1, width - 2, width)))
    ys = sorted(set((0, 1, 13, height // 2, height - 1, height)))
    for top, bottom in zip(ys, ys[1:]):
        for left, right in zip(xs, xs[1:]):
            yield top, bottom, left, right


class CurveMathTests(unittest.TestCase):
    def test_neutral_curves_and_inactive_wheels_are_bit_exact_in_place(self):
        source = np.random.default_rng(120).random((19, 31, 3), dtype=np.float32)
        working = source.copy()
        neutral = ColorGrading(
            shadows=TonalGrade(170, 0, 0), midtones=TonalGrade(320, 0, 0),
            highlights=TonalGrade(85, 0, 0), balance=100, blending=0)
        self.assertIs(apply_color_tools(working, CurveSet(), neutral), working)
        np.testing.assert_array_equal(working, source)

    def test_master_curve_interpolates_knots_and_retains_lifted_endpoints(self):
        points = ((0., .12), (.2, .19), (.55, .61), (.8, .76), (1., .86))
        output = apply_color_tools(gray([p[0] for p in points]), CurveSet(master=points))
        np.testing.assert_allclose(output[0, :, 0], [p[1] for p in points], atol=5e-8, rtol=0)
        np.testing.assert_array_equal(output[..., 0], output[..., 1])
        np.testing.assert_array_equal(output[..., 1], output[..., 2])

    def test_shape_preservation_has_no_new_extrema_between_knots(self):
        for points in (
            ((0., 0.), (.08, .2), (.3, .21), (.75, .9), (1., 1.)),
            ((0., .1), (.17, .83), (.41, .27), (.8, .76), (1., .5)),
        ):
            with self.subTest(points=points):
                x = np.linspace(0, 1, 4097, dtype=np.float32)
                output = apply_color_tools(gray(x), CurveSet(master=points))[0, :, 0]
                for (x0, y0), (x1, y1) in zip(points, points[1:]):
                    segment = output[(x >= x0) & (x <= x1)]
                    self.assertGreaterEqual(float(segment.min()), min(y0, y1) - 1e-7)
                    self.assertLessEqual(float(segment.max()), max(y0, y1) + 1e-7)
                if all(b[1] >= a[1] for a, b in zip(points, points[1:])):
                    self.assertTrue(np.all(np.diff(output) >= 0))

    def test_each_rgb_channel_leaves_other_channels_bit_exact(self):
        source = np.random.default_rng(121).uniform(.05, .95, (17, 29, 3)).astype(np.float32)
        for channel, name in enumerate(('red', 'green', 'blue')):
            with self.subTest(channel=name):
                curves = CurveSet(**{name: ((0., .2), (1., .8))})
                output = apply_color_tools(source.copy(), curves)
                np.testing.assert_allclose(output[..., channel], .2 + .6 * source[..., channel],
                                           atol=6e-8, rtol=0)
                for other in set(range(3)) - {channel}:
                    np.testing.assert_array_equal(output[..., other], source[..., other])

    def test_master_and_channel_curves_compose_in_documented_order(self):
        source = np.random.default_rng(122).random((13, 23, 3), dtype=np.float32)
        curve = ((0., .1), (1., .9))
        output = apply_color_tools(source.copy(), CurveSet(master=curve, red=curve))
        expected = .1 + .8 * source
        expected[..., 0] = .1 + .8 * expected[..., 0]
        np.testing.assert_allclose(output, expected, atol=1.2e-7, rtol=0)

    def test_luma_curve_moves_lightness_and_preserves_in_gamut_chroma(self):
        source = np.array([[[.32, .44, .38], [.42, .3, .35], [.26, .34, .47]]], np.float32)
        before = reference_lab(source)
        output = apply_color_tools(source.copy(), CurveSet(luma=((0., .1), (1., .9))))
        after = reference_lab(output)
        np.testing.assert_allclose(after[..., 0], .1 + .8 * before[..., 0], atol=2e-5, rtol=0)
        np.testing.assert_allclose(after[..., 1:], before[..., 1:], atol=2e-5, rtol=0)
        self.assertGreater(float(np.max(np.abs(output - source))), .005)

    def test_luma_is_independent_of_master_rgb_mapping(self):
        source = np.array([[[.25, .4, .55], [.6, .35, .3]]], np.float32)
        curve = ((0., .1), (1., .9))
        master = apply_color_tools(source.copy(), CurveSet(master=curve))
        luma = apply_color_tools(source.copy(), CurveSet(luma=curve))
        self.assertGreater(float(np.max(np.abs(master - luma))), .01)
        original_ab = reference_lab(source)[..., 1:]
        luma_drift = float(np.max(np.abs(reference_lab(luma)[..., 1:] - original_ab)))
        master_drift = float(np.max(np.abs(reference_lab(master)[..., 1:] - original_ab)))
        self.assertLess(luma_drift, 2e-5)
        self.assertGreater(master_drift, luma_drift + .005)

    def test_strided_view_keeps_edits_and_does_not_touch_surrounding_pixels(self):
        base = np.random.default_rng(123).uniform(.1, .8, (39, 53, 3)).astype(np.float32)
        original = base.copy()
        region = base[1::2, 2::3]
        self.assertFalse(region.flags.c_contiguous)
        self.assertIs(apply_color_tools(region, CurveSet(green=((0., .15), (1., .85)))), region)
        untouched = np.ones(base.shape[:2], dtype=bool)
        untouched[1::2, 2::3] = False
        np.testing.assert_array_equal(base[untouched], original[untouched])
        np.testing.assert_array_equal(region[..., 0], original[1::2, 2::3, 0])
        np.testing.assert_allclose(region[..., 1], .15 + .7 * original[1::2, 2::3, 1],
                                   atol=6e-8, rtol=0)


class ThreeWayGradingTests(unittest.TestCase):
    def test_hue_follows_each_wheel_direction_and_wraps_at_360(self):
        source = gray([.45])
        before = reference_lab(source)
        for zone in ZONES:
            for hue in (0, 60, 120, 180, 240, 300):
                with self.subTest(zone=zone, hue=hue):
                    grading = ColorGrading(**{zone: TonalGrade(hue, 25)})
                    output = apply_color_tools(source.copy(), grading=grading)
                    delta = (reference_lab(output) - before)[0, 0]
                    target = reference_lab(np.asarray(colorsys.hsv_to_rgb(hue / 360, 1., 1.)))[1:]
                    direction = float(delta[1:] @ target / (np.linalg.norm(delta[1:]) * np.linalg.norm(target)))
                    self.assertGreater(direction, .99999)
                    self.assertLess(abs(float(delta[0])), 1e-5)
            zero = apply_color_tools(source.copy(), grading=ColorGrading(**{zone: TonalGrade(0, 25)}))
            wrapped = apply_color_tools(source.copy(), grading=ColorGrading(**{zone: TonalGrade(360, 25)}))
            np.testing.assert_array_equal(zero, wrapped)

    def test_saturation_scales_chroma_before_gamut_compression(self):
        source = gray([.45])
        before = reference_lab(source)
        first = apply_color_tools(source.copy(), grading=ColorGrading(midtones=TonalGrade(210, 15)))
        second = apply_color_tools(source.copy(), grading=ColorGrading(midtones=TonalGrade(210, 30)))
        a = (reference_lab(first) - before)[..., 1:]
        b = (reference_lab(second) - before)[..., 1:]
        np.testing.assert_allclose(b, 2 * a, atol=2e-6, rtol=0)

    def test_luminance_sign_and_tonal_zone_dominance(self):
        source = gray([.05, .4, .9])
        before = reference_lab(source)
        for index, zone in enumerate(ZONES):
            with self.subTest(zone=zone):
                positive = apply_color_tools(source.copy(), grading=ColorGrading(**{zone: TonalGrade(luminance=20)}))
                negative = apply_color_tools(source.copy(), grading=ColorGrading(**{zone: TonalGrade(luminance=-20)}))
                increase = reference_lab(positive) - before
                decrease = reference_lab(negative) - before
                self.assertTrue(np.all(increase[..., 0] > 0))
                self.assertTrue(np.all(decrease[..., 0] < 0))
                self.assertEqual(int(np.argmax(increase[0, :, 0])), index)
                np.testing.assert_allclose(increase[..., 1:], 0, atol=2e-5, rtol=0)
                np.testing.assert_allclose(decrease[..., 1:], 0, atol=2e-5, rtol=0)

    def test_balance_positive_favours_highlights_negative_favours_shadows(self):
        source = gray([.4])
        before = reference_lab(source)
        for zone, ascending in (('highlights', True), ('shadows', False)):
            amounts = []
            for balance in (-100, 0, 100):
                grading = ColorGrading(**{zone: TonalGrade(210, 30)}, balance=balance)
                output = apply_color_tools(source.copy(), grading=grading)
                amounts.append(float(np.linalg.norm((reference_lab(output) - before)[..., 1:])))
            with self.subTest(zone=zone):
                differences = np.diff(amounts)
                self.assertTrue(np.all(differences > 0) if ascending else np.all(differences < 0))

    def test_blending_broadens_overlap_into_other_tonal_zones(self):
        source = gray([.1])
        before = reference_lab(source)
        narrow = apply_color_tools(source.copy(), grading=ColorGrading(highlights=TonalGrade(210, 30), blending=0))
        broad = apply_color_tools(source.copy(), grading=ColorGrading(highlights=TonalGrade(210, 30), blending=100))
        narrow_amount = float(np.linalg.norm((reference_lab(narrow) - before)[..., 1:]))
        broad_amount = float(np.linalg.norm((reference_lab(broad) - before)[..., 1:]))
        self.assertGreater(broad_amount, .001)
        self.assertGreater(broad_amount, narrow_amount * 100)

    def test_extreme_grades_are_finite_bounded_and_preserve_black_white(self):
        random = np.random.default_rng(124).random((129, 137, 3), dtype=np.float32)
        random[0, :8] = np.array([[0, 0, 0], [1, 1, 1], [1, 0, 0], [0, 1, 0],
                                 [0, 0, 1], [1, 1, 0], [1, 0, 1], [0, 1, 1]])
        for balance, blending in ((-100, 0), (0, 50), (100, 100)):
            grading = ColorGrading(TonalGrade(210, 100, 100), TonalGrade(330, 100, -100),
                                   TonalGrade(60, 100, 100), balance, blending)
            output = apply_color_tools(random.copy(), grading=grading)
            with self.subTest(balance=balance, blending=blending):
                self.assertTrue(np.all(np.isfinite(output)))
                self.assertGreaterEqual(float(output.min()), 0)
                self.assertLessEqual(float(output.max()), 1)
                np.testing.assert_array_equal(output[0, 0], random[0, 0])
                np.testing.assert_allclose(output[0, 1], random[0, 1], atol=4e-7, rtol=0)

    def test_curves_luma_and_grading_match_arbitrary_strided_tiles_exactly(self):
        source = np.random.default_rng(125).random((259, 307, 3), dtype=np.float32)
        curves = CurveSet(master=((0., .03), (.2, .16), (.65, .77), (1., .97)),
                          red=((0., 0.), (.5, .58), (1., 1.)),
                          blue=((0., .04), (.75, .7), (1., .94)),
                          luma=((0., 0.), (.4, .48), (1., 1.)))
        grading = ColorGrading(TonalGrade(215, 73, 17), TonalGrade(35, 46, -13),
                               TonalGrade(312, 81, 9), 37, 72)
        whole = apply_color_tools(source.copy(), curves, grading)
        tiled = source.copy()
        for top, bottom, left, right in arbitrary_regions(307, 259):
            apply_color_tools(tiled[top:bottom, left:right], curves, grading)
        np.testing.assert_array_equal(tiled, whole)


class GradientMaskMathTests(unittest.TestCase):
    def test_linear_endpoints_midpoint_reverse_and_orientation(self):
        layer = MaskLayer(kind='linear', start=(.2, .5), end=(.8, .5))
        alpha = rasterize_mask(layer, 101, 101)
        self.assertEqual(float(alpha[50, 20]), 0)
        self.assertEqual(float(alpha[50, 50]), .5)
        self.assertEqual(float(alpha[50, 80]), 1)
        self.assertTrue(np.all(np.diff(alpha[50]) >= 0))
        reverse = rasterize_mask(replace(layer, start=layer.end, end=layer.start), 101, 101)
        np.testing.assert_allclose(reverse, 1 - alpha, atol=6e-8, rtol=0)
        vertical = rasterize_mask(replace(layer, start=(.5, .2), end=(.5, .8)), 101, 101)
        np.testing.assert_array_equal(vertical, alpha.T)

    def test_radial_rotation_changes_axes_and_full_turn_keeps_coverage(self):
        layer = MaskLayer(kind='radial', radius_x=.35, radius_y=.12, feather=.6)
        horizontal = rasterize_mask(layer, 101, 101)
        vertical = rasterize_mask(replace(layer, rotation=90), 101, 101)
        self.assertGreater(float(horizontal[50, 65]), .9)
        self.assertEqual(float(horizontal[65, 50]), 0)
        np.testing.assert_allclose(vertical, horizontal.T, atol=1e-7, rtol=0)
        a = rasterize_mask(replace(layer, rotation=-37), 101, 101)
        b = rasterize_mask(replace(layer, rotation=323), 101, 101)
        np.testing.assert_allclose(a, b, atol=1e-7, rtol=0)

    def test_radial_feather_softens_interior_without_moving_outer_boundary(self):
        layer = MaskLayer(kind='radial', radius_x=.4, radius_y=.4, feather=0)
        hard = rasterize_mask(layer, 101, 101)
        soft = rasterize_mask(replace(layer, feather=1), 101, 101)
        self.assertEqual(float(hard[50, 50]), 1)
        self.assertEqual(float(soft[50, 50]), 1)
        self.assertEqual(float(hard[50, 70]), 1)
        self.assertEqual(float(soft[50, 70]), .5)
        self.assertEqual(float(hard[50, 90]), 0)
        self.assertEqual(float(soft[50, 90]), 0)
        self.assertTrue(np.all(np.diff(soft[50, 50:]) <= 0))

    def test_gradient_alpha_and_inversion_match_whole_image_on_arbitrary_tiles(self):
        for layer in (
            MaskLayer(kind='linear', start=(.12, .87), end=(.92, .21)),
            MaskLayer(kind='radial', center=(.67, .24), radius_x=.41, radius_y=.13,
                      rotation=29, feather=.75),
        ):
            alpha = rasterize_mask(layer, 113, 87)
            inverted = rasterize_mask(replace(layer, inverted=True), 113, 87)
            with self.subTest(kind=layer.kind):
                np.testing.assert_array_equal(inverted, 1 - alpha)
                self.assertFalse(alpha.flags.writeable)
                for active, whole in ((layer, alpha), (replace(layer, inverted=True), inverted)):
                    for top, bottom, left, right in arbitrary_regions(113, 87):
                        tile = rasterize_mask(active, right - left, bottom - top, 113, 87, left, top)
                        np.testing.assert_array_equal(tile, whole[top:bottom, left:right])

    def test_gradient_compositing_matches_arbitrary_tiles_after_colour_tools(self):
        source = np.random.default_rng(126).uniform(.04, .92, (137, 181, 3)).astype(np.float32)
        curves = CurveSet(green=((0., 0.), (.4, .47), (1., 1.)),
                          luma=((0., 0.), (.6, .65), (1., 1.)))
        grading = ColorGrading(shadows=TonalGrade(210, 25), highlights=TonalGrade(40, 20))
        masks = (
            MaskLayer(kind='linear', start=(.1, .15), end=(.85, .75), exposure=.4, tint=-14),
            MaskLayer(kind='radial', center=(.61, .39), radius_x=.31, radius_y=.19,
                      rotation=-34, feather=.82, inverted=True, highlights=-20, saturation=18),
        )
        whole = apply_masks(apply_color_tools(source.copy(), curves, grading), masks)
        tiled = source.copy()
        for top, bottom, left, right in arbitrary_regions(181, 137):
            tile = tiled[top:bottom, left:right]
            apply_color_tools(tile, curves, grading)
            apply_masks(tile, masks, 181, 137, left, top)
        np.testing.assert_array_equal(tiled, whole)


if __name__ == '__main__':
    unittest.main()
