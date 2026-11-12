"""Behavioral contracts for the independently recovered scalar-curve subset."""
import unittest

import numpy as np
from scipy.interpolate import CubicSpline

from native.reference.captureone_curve import RecoveredCurve, float32


class RecoveredCurveTests(unittest.TestCase):
    def test_two_knots_are_linear_including_unclamped_extrapolation(self):
        curve=RecoveredCurve([(0,0),(1,1)])
        for x in (-1,-.01,0,.5,1,1.5):
            self.assertEqual(curve(x),float32(x))

    def test_three_knots_are_quadratic_and_extrapolate_endpoint_tangents(self):
        curve=RecoveredCurve([(0,0),(.5,.25),(1,1)])
        for x in (0,.125,.25,.5,.75,1):
            self.assertEqual(curve(x),float32(x*x))
        self.assertEqual(curve(-.25),0)
        self.assertEqual(curve(1.25),1.5)

    def test_natural_cubic_matches_independent_scientific_reference(self):
        rng=np.random.default_rng(791)
        for count in range(4,19):
            x=np.linspace(0,1,count,dtype=np.float32).astype(float)
            y=rng.uniform(-.5,1.5,count).astype(np.float32).astype(float)
            curve=RecoveredCurve(zip(x,y))
            reference=CubicSpline(x,y,bc_type='natural')
            for at in np.linspace(0,1,121,dtype=np.float32):
                self.assertLessEqual(abs(curve(at)-float32(reference(at))),2e-7)
            for at,index in ((-.1,0),(1.1,-1)):
                value=y[index]+(float32(at)-x[index])*reference(x[index],1)
                self.assertLessEqual(abs(curve(at)-float32(value)),2e-7)

    def test_unverified_input_domain_is_rejected(self):
        for points in ([(0,0)],[(1,1),(0,0)],[(0,0),(0,1)],
                       [(0,0),(1e-5,1)],[(0,float('nan')),(1,1)]):
            with self.assertRaises(ValueError):
                RecoveredCurve(points)
        with self.assertRaises(ValueError):
            RecoveredCurve([(0,0),(1,1)])(float('nan'))


if __name__=='__main__':
    unittest.main()
