"""Independent reconstruction of a verified subset of C1's ICGC scalar curve.

The shipped x64 implementation and a local runtime oracle establish quadratic
interpolation for three knots, natural cubic for four or more knots, and linear
endpoint extrapolation. This file contains no C1 code or resources and never
loads C1. It is a research reference, not a complete RAW tone-curve pipeline.

Only finite, ordered, well-separated knots are supported. C1's point sorting,
near-duplicate policy, FCRV composition and profile input domain are not modeled.
"""
from bisect import bisect_right
import math
import struct


def float32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


class RecoveredCurve:
    def __init__(self, points):
        points = [(float32(x), float32(y)) for x, y in points]
        if not 2 <= len(points) <= 18:
            raise ValueError('Verified curve boundary is 2 to 18 knots')
        if not all(math.isfinite(v) for p in points for v in p):
            raise ValueError('Finite knots are required')
        self.x, self.y = map(list, zip(*points))
        h = [b-a for a,b in zip(self.x,self.x[1:])]
        if any(v <= 1e-4 for v in h):
            raise ValueError('Only ordered knots separated by more than 1e-4 are verified')
        slopes = [(b-a)/step for a,b,step in zip(self.y,self.y[1:],h)]
        n = len(points)
        if n == 2:
            self.d = [slopes[0],slopes[0]]
        elif n == 3:
            quadratic = (slopes[1]-slopes[0])/(self.x[2]-self.x[0])
            self.d = [slopes[0]+quadratic*(2*x-self.x[0]-self.x[1]) for x in self.x]
        else:
            # Solve the natural spline's tridiagonal system for second
            # derivatives; derive first derivatives for Hermite evaluation.
            diagonal = [2*(h[i-1]+h[i]) for i in range(1,n-1)]
            rhs = [6*(slopes[i]-slopes[i-1]) for i in range(1,n-1)]
            for i in range(1,n-2):
                factor = h[i]/diagonal[i-1]
                diagonal[i] -= factor*h[i]
                rhs[i] -= factor*rhs[i-1]
            second = [0.0]*n
            second[n-2] = rhs[-1]/diagonal[-1]
            for i in range(n-4,-1,-1):
                second[i+1] = (rhs[i]-h[i+1]*second[i+2])/diagonal[i]
            self.d = [slopes[i]-h[i]*(2*second[i]+second[i+1])/6 for i in range(n-1)]
            self.d.append(slopes[-1]+h[-1]*(second[-2]+2*second[-1])/6)

    def __call__(self, value):
        x = float32(value)
        if not math.isfinite(x):
            raise ValueError('Finite scalar input is required')
        if x < self.x[0]:
            return float32(self.y[0]+(x-self.x[0])*self.d[0])
        if x > self.x[-1]:
            return float32(self.y[-1]+(x-self.x[-1])*self.d[-1])
        i = max(0,min(len(self.x)-2,bisect_right(self.x,x)-1))
        h = self.x[i+1]-self.x[i]
        t = (x-self.x[i])/h
        y0,y1 = self.y[i:i+2]
        d0,d1 = self.d[i:i+2]
        return float32(y0+(3-2*t)*t*t*(y1-y0)
            +h*t*(t-1)*((t-1)*d0+t*d1))
