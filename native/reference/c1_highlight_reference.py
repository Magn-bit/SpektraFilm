"""Independent, research-only reconstruction of one observed clipping operator.

This module never loads Capture One or its resources. Its parameter contract is
explicit: no camera defaults, white balance, normalization or complete RAW
pipeline is implied. Finite RGBA float32 inputs, positive thresholds/ranges and
finite nonnegative strengths/scales are the supported numerical domain.
"""
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class HighlightParameters:
    thresholds: tuple[float, float, float]
    recovery_strength: float
    excess_ranges: tuple[float, float, float]
    channel_scales: tuple[float, float, float]
    desaturation_strength: float

    def values(self):
        if any(len(group) != 3 for group in (
                self.thresholds, self.excess_ranges, self.channel_scales)):
            raise ValueError('three threshold, range and scale values required')
        values = np.asarray((*self.thresholds, self.recovery_strength,
                             *self.excess_ranges, *self.channel_scales,
                             self.desaturation_strength), np.float32)
        if (not np.isfinite(values).all() or np.any(values[:3] <= 0)
                or np.any(values[4:7] <= 0) or values[3] < 0
                or np.any(values[7:] < 0)):
            raise ValueError('finite positive thresholds/ranges and nonnegative strengths/scales required')
        return values


def recover_highlights(pixels, parameters):
    """Return a new float32 RGBA array, preserving alpha and unclipped pixels.

    Each channel reads the *original* RGB for its recovery weight. The second
    operation desaturates the corrected triple by its squared excess. Neither
    operation adds a lower clamp; negative finite source channels are retained
    in the observed equations. The input array is never modified.
    """
    source = np.asarray(pixels)
    if source.dtype != np.float32 or source.ndim < 1 or source.shape[-1] != 4:
        raise ValueError('RGBA float32 array required')
    if not np.isfinite(source).all():
        raise ValueError('finite pixels required')
    p = parameters.values()
    rgb = source[..., :3]
    corrected = rgb.copy()
    for channel in range(3):
        other = [index for index in range(3) if index != channel]
        active = rgb[..., channel] > p[channel]
        weight = np.zeros(rgb.shape[:-1], np.float32)
        # Division is evaluated only for positive, clipped source samples.
        weight[active] = np.minimum(
            (rgb[..., channel][active]-p[channel])*(p[3]/p[channel])
            * np.minimum(rgb[..., other[0]][active], rgb[..., other[1]][active])
            / rgb[..., channel][active], np.float32(1))
        corrected[..., channel] = (
            rgb[..., channel]*(np.float32(1)-weight)
            + (rgb[..., other[0]]+rgb[..., other[1]])*np.float32(.5)*weight)

    active = np.any(corrected > p[:3], axis=-1)
    excess = np.maximum(corrected-p[:3], np.float32(0))/p[4:7]
    weight = ((excess[..., 0]+excess[..., 1])+excess[..., 2])
    weight *= np.minimum(np.minimum(corrected[..., 0]*p[7],
                                    corrected[..., 1]*p[8]), corrected[..., 2]*p[9])
    weight *= p[10]
    weight = np.where(active, np.minimum(weight*weight, np.float32(1)), np.float32(0))
    luminance = (corrected[..., 0]*np.float32(.299)
                 + corrected[..., 1]*np.float32(.587)
                 + corrected[..., 2]*np.float32(.114))
    result = source.copy()
    result[..., :3] = (corrected*(np.float32(1)-weight[..., None])
                       + luminance[..., None]*weight[..., None])
    return result
