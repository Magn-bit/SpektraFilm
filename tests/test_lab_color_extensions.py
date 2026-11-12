"""One focused integration node for newly connected Lab colour capabilities."""
from dataclasses import asdict, replace
import unittest

import numpy as np

from desktop.imaging import Settings
from desktop.native_spectral import available, process_editor, scene_curve_samples
from shared.color_tools import (
    ChannelMixer, MixerRow, ColorGrading, TonalGrade, CurveSet, ParametricCurve,
    ParametricSet, apply_color_tools, evaluate_curve, normalize_curves,
    normalize_parametric, parametric_curve_points,
)
from shared.style_presets import normalize_style


class ColourExtensions(unittest.TestCase):
    def test_mixer_uses_output_rows_without_grey_normalisation(self):
        source = np.array([[[.2, .4, .6], [.5, .5, .5]]], np.float32)
        mixer = ChannelMixer(red=MixerRow(red=-25, green=50, blue=10))
        result = apply_color_tools(source.copy(), channel_mixer=mixer)
        expected = source.copy()
        expected[..., 0] = source[..., 0]*.75 + source[..., 1]*.5 + source[..., 2]*.1
        np.testing.assert_allclose(result, expected, atol=6e-8, rtol=0)
        self.assertNotEqual(float(result[0, 1, 0]), .5)

    def test_parametric_lab_knots_composition_and_extreme_monotonicity(self):
        parameter = ParametricCurve(shadows=100)
        expected = ((0., 0.), (.125, .25), (.25, .3125), (.375, .375),
                    (.5, .5), (.625, .625), (.75, .75), (.875, .875), (1., 1.))
        self.assertEqual(parametric_curve_points(parameter), expected)
        x = np.linspace(0, 1, 4097)
        for amounts in ((100, -100, 100, -100), (-100, 100, -100, 100), (100, 100, 100, 100)):
            parameter = ParametricCurve(*amounts, .17, .46, .79)
            parametric = CurveSet(parametric=ParametricSet(master=parameter))
            y = evaluate_curve(parametric, 'master', x)
            self.assertTrue(np.all(np.diff(y) >= 0))
            self.assertEqual((float(y[0]), float(y[-1])), (0., 1.))
            composed = replace(parametric, master=((0., .1), (1., .9)))
            np.testing.assert_allclose(evaluate_curve(composed, 'master', x), .1+.8*y, atol=3e-16)

    def test_endpoint_domain_is_retained_and_outside_is_constant(self):
        curves = normalize_curves({'master': [[.18, .1], [.5, .6], [.88, .9]]})
        self.assertEqual(curves.master[0], (.18, .1))
        self.assertEqual(curves.master[-1], (.88, .9))
        values = evaluate_curve(curves, 'master', np.array([0, .1, .18, .88, .99, 1.]))
        np.testing.assert_array_equal(values, [.1, .1, .1, .9, .9, .9])

    def test_new_settings_style_and_scene_roundtrip_preserve_defaults(self):
        old = Settings.from_mapping({'curves': {'master': [[0, .1], [1, .9]]},
                                     'grading': {'shadows': {'hue': 210, 'saturation': 12}}})
        self.assertEqual(old.channel_mixer, ChannelMixer())
        self.assertEqual(old.curves.parametric, ParametricSet())
        self.assertEqual(old.grading.master, TonalGrade())
        curve = CurveSet(parametric=ParametricSet(master=ParametricCurve(lights=63)))
        settings = Settings(curves=curve, scene_curves=curve,
                            grading=ColorGrading(master=TonalGrade(37, 17, -8)),
                            channel_mixer=ChannelMixer(blue=MixerRow(red=12, green=-5)))
        self.assertEqual(Settings.from_mapping(asdict(settings)), settings)
        style = normalize_style({'settings': asdict(settings)})['settings']
        self.assertEqual(style['channel_mixer'], asdict(settings.channel_mixer))
        table = np.fromstring(scene_curve_samples(curve), sep=',').reshape(5, 129)
        np.testing.assert_allclose(table[0], evaluate_curve(curve, 'master', np.linspace(0, 1, 129)), atol=5e-9)
        self.assertGreater(float(np.max(np.abs(table[0]-np.linspace(0, 1, 129)))), .01)
        bounded = normalize_parametric({'master': {'shadow_split': .85, 'highlights': 150}}).master
        self.assertGreaterEqual(bounded.midtone_split-bounded.shadow_split, .049999)
        self.assertGreaterEqual(bounded.highlight_split-bounded.midtone_split, .049999)
        self.assertLessEqual(bounded.highlight_split, .95)
        self.assertEqual(bounded.highlights, 100)

    @unittest.skipUnless(available(), 'Windows Vulkan editor runtime required')
    def test_native_mixer_master_parametric_and_endpoint_chain_matches_cpu(self):
        source = np.random.default_rng(229).uniform(.05, .95, (61, 79, 3)).astype(np.float32)
        curves = CurveSet(master=((.08, .03), (.48, .55), (.94, .97)),
                          luma=((0., 0.), (.43, .47), (1., 1.)),
                          parametric=ParametricSet(master=ParametricCurve(-18, 43, -12, 27),
                                                  red=ParametricCurve(lights=41),
                                                  luma=ParametricCurve(darks=-32)))
        grading = ColorGrading(shadows=TonalGrade(215, 13, 4),
                               highlights=TonalGrade(43, 7), master=TonalGrade(31, 9, -3))
        mixer = ChannelMixer(red=MixerRow(green=13, blue=-7), blue=MixerRow(red=8, blue=-4))
        edits = dict(curves=asdict(curves), grading=asdict(grading), channel_mixer=asdict(mixer))
        expected = apply_color_tools(source.copy(), curves, grading, mixer)
        actual = process_editor(source, edits)
        np.testing.assert_allclose(actual, expected, atol=9e-5, rtol=1e-4)
        # The master is real global grading, independent of split weights.
        plain = process_editor(source, {})
        global_grade = process_editor(source, {'grading': {'master': {'hue': 210, 'saturation': 18}}})
        self.assertGreater(float(np.mean(np.abs(global_grade-plain))), .005)


if __name__ == '__main__':
    unittest.main()
