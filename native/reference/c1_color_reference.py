"""Recovered neutral pre-ICC math, with no installed engine/profile dependency.

Only the observed method1300 A7CR neutral CPU path is modeled. Callers supply
curve knots. This is not sensor normalization, automatic exposure, a complete
ICC engine, or an independent full RAW developer.
"""
import math

from .captureone_curve import RecoveredCurve, float32


def normalize_demosaic(value):
    """Convert post-demosaic color-stage code values using observed float32 scale."""
    value=float32(value)
    if not math.isfinite(value):
        raise ValueError('finite post-demosaic code value required')
    return float32(value*float32(1/65535))


def pre_icc_transfer(value, toe_sqrt=True):
    """Observed color-state flag110=1 transfer, with explicit float32 association.

    The static flag0 gamma branch has no corresponding runtime oracle and is
    rejected here. Negative input clamps to zero; highlights are not clipped.
    """
    if not toe_sqrt:
        raise NotImplementedError('flag0 transfer has not been runtime validated')
    value=float32(value)
    if not math.isfinite(value):
        raise ValueError('finite scalar required')
    if value<=0:
        return 0.0
    if value<=float32(.01947):
        return float32(value*float32(3.8521))
    return float32(float32(float32(math.sqrt(value))*float32(1.075))
                   -float32(.07500004768371582))


class DefaultPreICC:
    """Only neutral normalize → caller-supplied primary curve → transfer."""
    def __init__(self, primary_knots):
        self.curve=RecoveredCurve(primary_knots)

    def __call__(self, value):
        return pre_icc_transfer(self.curve(normalize_demosaic(value)))
