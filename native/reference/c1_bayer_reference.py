"""Readable research reference for four recovered Bayer interpolation steps.

This module is intentionally outside the application. It models the observed
green-refinement and chroma-completion equations, not a RAW developer. Callers
must supply the observed RGGB layout and explicit synthetic/observed weights.
There is no camera default, sensor scaling, boundary extension or color render.
"""
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ChromaParameters:
    green_to_color_threshold: float
    ratio_offset: float
    regularizer: float
    direction_floor: float

    def values(self):
        values = np.asarray((self.green_to_color_threshold, self.ratio_offset,
                             self.regularizer, self.direction_floor), np.float32)
        if not np.isfinite(values).all() or np.any(values < 0) or np.any(values[2:] <= 0):
            raise ValueError('finite nonnegative weights, positive regularizer/floor required')
        return values


@dataclass(frozen=True)
class InitialGreenParameters:
    red_row_gain: float
    blue_row_gain: float
    regularizer: float
    reference_bias: float

    def values(self):
        values = np.asarray((self.red_row_gain, self.blue_row_gain,
                             self.regularizer, self.reference_bias), np.float32)
        if (not np.isfinite(values).all() or np.any(values[:2] <= 0)
                or np.any(values[:2] > 16) or values[2] <= 0
                or not 0 <= values[3] <= 65535):
            raise ValueError('positive gains <=16, positive regularizer and bias in 0..65535 required')
        return values


def initial_green(raw, region, parameters, *, auxiliary_stride=0,
                  auxiliary=None, local_memory=False, cfa='RGGB'):
    """Recover green at R/B sites from ushort CFA, with explicit limitations.

    This implements only the observed global-memory/no-auxiliary-map branch.
    Unsupported layouts, local-memory and auxiliary variants are rejected.
    Direction evidence uses fixed-point integer scores and a 5x5 ambiguity
    recheck. The selected color/green ratio is regularized around a supplied
    bias; original CFA samples are retained, missing R/B remain zero.
    """
    return _initial_green_impl(raw, region, parameters,
        auxiliary_stride=auxiliary_stride, auxiliary=auxiliary,
        local_memory=local_memory, cfa=cfa, arithmetic='gpu')


def initial_green_cpu(raw, region, parameters, *, auxiliary_stride=0,
                      auxiliary=None, local_memory=False, cfa='RGGB',
                      diagnostics=False):
    """Research reference for the observed native scalar CPU stage1 workers.

    This is a separate arithmetic contract from ``initial_green`` (OpenCL).
    It uses fixed-point center classification, floor integer midpoints and
    symmetric east interpolation weights. Only an auxiliary difference of
    zero and RGGB are supported; this is not a complete CPU RAW developer.
    Diagnostics expose compact H x (W/2) chroma-site decisions/candidates.
    """
    return _initial_green_impl(raw, region, parameters,
        auxiliary_stride=auxiliary_stride, auxiliary=auxiliary,
        local_memory=local_memory, cfa=cfa, arithmetic='cpu',
        diagnostics=diagnostics)


def _initial_green_impl(raw, region, parameters, *, auxiliary_stride=0,
                        auxiliary=None, local_memory=False, cfa='RGGB',
                        arithmetic, diagnostics=False):
    if auxiliary_stride != 0 or auxiliary is not None or local_memory or cfa != 'RGGB':
        raise NotImplementedError('only global-memory RGGB with auxiliary_stride=0 is implemented')
    raw = np.asarray(raw)
    if raw.ndim != 2 or raw.dtype != np.uint16:
        raise ValueError('2D uint16 sensor samples required')
    x, y, width, height = map(int, region)
    if min(width, height) <= 0 or any(v & 1 for v in (x, y, width, height)):
        raise ValueError('positive even extent and even RGGB origin required')
    if min(x, y) < 6 or x+width+6 > raw.shape[1] or y+height+6 > raw.shape[0]:
        raise ValueError('six-pixel sensor halo required')
    red_gain, blue_gain, epsilon, bias = parameters.values()
    rows = y+np.arange(height, dtype=np.intp)[:, None]
    columns = x+np.arange(0, width, 2, dtype=np.intp)[None, :]+(rows & 1)
    gain = np.where(rows & 1, blue_gain, red_gain).astype(np.float32)

    def s(dy=0, dx=0):
        return raw[rows+dy, columns+dx].astype(np.int32)

    # OpenCL int arithmetic is 32 bit on the measured backend. Explicit
    # truncation preserves signed division toward zero, including overflowed
    # products; it must not turn into Python floor division for negatives.
    def divide(values, denominator):
        return np.trunc(values.astype(np.float64)/denominator).astype(np.int32)

    gain_fixed = np.floor(gain*np.float32(1024)).astype(np.int32)
    curvature_fixed = np.floor(gain*np.float32(1024)*np.float32(1.6)).astype(np.int32)
    offset = np.trunc(bias-bias*gain).astype(np.int32)
    center = s()
    scaled_center = (((center*gain_fixed) >> np.int32(10))+offset
        if arithmetic == 'cpu' else
        np.floor(center.astype(np.float32)*gain).astype(np.int32)+offset)
    north, south, west, east = s(-1, 0), s(1, 0), s(0, -1), s(0, 1)
    differences = [north-scaled_center, south-scaled_center,
                   west-scaled_center, east-scaled_center]

    def score_grid(coordinates):
        scores = [np.zeros(center.shape, np.int32) for _ in range(4)]
        horizontal_variation = np.zeros_like(center)
        vertical_variation = np.zeros_like(center)
        for dy, dx in coordinates:
            scaled = divide(s(dy, dx)*gain_fixed, 1024)+offset
            neighbors = [s(dy-1, dx), s(dy+1, dx), s(dy, dx-1), s(dy, dx+1)]
            for i in range(4):
                scores[i] += abs(neighbors[i]-scaled-differences[i])
            horizontal_variation += abs(neighbors[2]-neighbors[3])
            vertical_variation += abs(neighbors[0]-neighbors[1])
        return scores, horizontal_variation, vertical_variation

    score, horizontal_variation, vertical_variation = score_grid(
        [(dy, dx) for dy in (-2, 0, 2) for dx in (-2, 0, 2)])
    # Far axial evidence is not a full cross grid: only the corresponding
    # directional pair and pairwise variation are accumulated at each point.
    for distance in (-4, 4):
        scaled = divide(s(distance, 0)*gain_fixed, 1024)+offset
        score[0] += abs(s(distance-1, 0)-scaled-differences[0])
        score[1] += abs(s(distance+1, 0)-scaled-differences[1])
        vertical_variation += abs(s(distance-1, 0)-s(distance+1, 0))
        scaled = divide(s(0, distance)*gain_fixed, 1024)+offset
        score[2] += abs(s(0, distance-1)-scaled-differences[2])
        score[3] += abs(s(0, distance+1)-scaled-differences[3])
        horizontal_variation += abs(s(0, distance-1)-s(0, distance+1))
    vertical_penalty = (abs(west-s(-2, -1))+abs(west-s(2, -1))
        +abs(east-s(-2, 1))+abs(east-s(2, 1)))
    vertical_penalty += divide(abs(s(-2, 0)+s(2, 0)-2*center)*curvature_fixed, 1024)
    horizontal_penalty = (abs(north-s(-1, -2))+abs(north-s(-1, 2))
        +abs(south-s(1, -2))+abs(south-s(1, 2)))
    horizontal_penalty += divide(abs(s(0, -2)+s(0, 2)-2*center)*curvature_fixed, 1024)
    score[0] += vertical_penalty
    score[1] += vertical_penalty
    vertical_variation += vertical_penalty
    score[2] += horizontal_penalty
    score[3] += horizontal_penalty
    horizontal_variation += horizontal_penalty

    def choose(scores):
        sn, ss, sw, se = scores
        horizontal = np.maximum(sw, se) < np.minimum(sn, ss)
        vertical = np.maximum(sn, ss) < np.minimum(sw, se)
        return horizontal, vertical

    horizontal, vertical = choose(score)
    horizontal &= horizontal_variation < vertical_variation
    vertical &= vertical_variation < horizontal_variation
    direction = np.where(horizontal, 1, np.where(vertical, 2, 3))
    half_imbalance = divide(abs(west+east-north-south), 2)
    square = half_imbalance*half_imbalance  # observed int32 wrap retained
    neighbor_sum = west+east+north+south-np.int32(np.trunc(bias*np.float32(4)))
    recheck = (direction == 3) & ~(square < neighbor_sum)
    wide, _, _ = score_grid([(dy, dx) for dy in (-4, -2, 0, 2, 4) for dx in (-4, -2, 0, 2, 4)])
    wide_horizontal, wide_vertical = choose(wide)
    direction = np.where(recheck & wide_horizontal, 1,
                         np.where(recheck & wide_vertical, 2, direction))

    # Local one-sided variation measures. Mixed interpolation uses the
    # products of the other three variations (inverse-weight equivalent),
    # retaining the measured float32 arithmetic instead of reciprocal sums.
    wn = (1+abs(s(-3, 0)-north)+abs(s(-2, -1)-west)
          +abs(s(-2, 1)-east)+abs(north-south)).astype(np.float32)+abs(s(-2, 0)-center).astype(np.float32)*gain
    ws = (1+abs(s(3, 0)-south)+abs(s(2, -1)-west)
          +abs(s(2, 1)-east)+abs(north-south)).astype(np.float32)+abs(s(2, 0)-center).astype(np.float32)*gain
    ww = (1+abs(s(0, -3)-west)+abs(west-east)+abs(s(-1, -2)-north)
          +abs(s(1, -2)-south)).astype(np.float32)+abs(s(0, -2)-center).astype(np.float32)*gain
    east_variation = 1+abs(s(0, 3)-east)+abs(west-east)+abs(s(-1, 2)-north)+abs(s(1, 2)-south)
    we = east_variation.astype(np.float32)+abs(s(0, 2)-center).astype(np.float32)*gain
    # The horizontal-only branch uniquely scales its entire east variation.
    horizontal_east = (east_variation+abs(s(0, 2)-center)).astype(np.float32)*gain
    if arithmetic == 'cpu':
        horizontal_east = we
    midpoint_rounding = 0 if arithmetic == 'cpu' else 1
    midpoint = [divide(center+s(dy, dx)+midpoint_rounding, 2).astype(np.float32)
                for dy, dx in ((-2, 0), (2, 0), (0, -2), (0, 2))]
    north, south, west, east = [value.astype(np.float32) for value in (north, south, west, east)]
    center_float = center.astype(np.float32)

    def ratio_result(total, numerator, denominator):
        regularization = total*epsilon
        reference = total*bias
        numerator = np.maximum(numerator+regularization-reference, regularization)
        denominator = np.maximum(denominator+regularization-reference, regularization)
        return (numerator/denominator)*(center_float-bias+epsilon)

    hg = ratio_result(horizontal_east+ww, horizontal_east*west+ww*east,
                      horizontal_east*midpoint[2]+ww*midpoint[3])
    vg = ratio_result(wn+ws, ws*north+wn*south, ws*midpoint[0]+wn*midpoint[1])
    mn, ms, mw, me = ws*(we*ww), wn*(we*ww), (ws*wn)*we, (ws*wn)*ww
    mg = ratio_result(mw+me+mn+ms, mn*north+ms*south+mw*west+me*east,
                      mn*midpoint[0]+ms*midpoint[1]+mw*midpoint[2]+me*midpoint[3])
    green = np.where(direction == 1, hg, np.where(direction == 2, vg, mg))-epsilon+bias
    output = np.zeros((height, width, 4), np.float32)
    local_rows = np.arange(height)[:, None]
    local_chroma_columns = np.arange(0, width, 2)[None, :]+(local_rows & 1)
    local_green_columns = np.arange(0, width, 2)[None, :]+1-(local_rows & 1)
    output[local_rows, local_chroma_columns, 1] = green
    output[local_rows, local_green_columns, 1] = raw[y:y+height, x:x+width][local_rows, local_green_columns]
    output[local_rows, local_chroma_columns, np.where(local_rows & 1, 2, 0)] = center
    statistics = {'direction_counts_at_chroma': _counts(direction),
        'wide_recheck': int(np.count_nonzero(recheck)),
        'mixed_without_recheck': int(np.count_nonzero((~recheck) & (direction == 3))),
        'wide_horizontal': int(np.count_nonzero(recheck & (direction == 1))),
        'wide_vertical': int(np.count_nonzero(recheck & (direction == 2))),
        'wide_mixed': int(np.count_nonzero(recheck & (direction == 3))),
        'wrapped_ambiguity_square': int(np.count_nonzero(square < 0))}
    if diagnostics:
        statistics.update(chroma_direction_map=direction.copy(),
            chroma_forced_green=np.stack([hg, vg, mg], axis=-1)-epsilon+bias)
    return output, statistics


def _region(image, region):
    image = np.asarray(image, dtype=np.float32)
    if image.ndim != 3 or image.shape[2] != 4 or not np.isfinite(image).all():
        raise ValueError('finite float4 image required')
    x, y, width, height = map(int, region)
    if any(value & 1 for value in (x, y, width, height)) or min(width, height) <= 0:
        raise ValueError('positive even extent and even RGGB origin required')
    if min(x, y) < 2 or x+width+2 > image.shape[1] or y+height+2 > image.shape[0]:
        raise ValueError('two-pixel input halo required')
    yy, xx = np.indices((height, width))

    def sample(dy=0, dx=0):
        return image[y+dy:y+dy+height, x+dx:x+dx+width]

    return image, sample, (yy & 1) == 0, (xx & 1) == 0


def _counts(values):
    keys, counts = np.unique(values, return_counts=True)
    return {str(int(key)): int(count) for key, count in zip(keys, counts)}


def refine_green(image, region, *, diagnostics=False):
    """Eight-direction green refinement at R/B sites; return ROI and counts.

    The best of eight variation scores selects a candidate. Axial winners
    retain the existing green; oblique winners average their candidate with
    the better axial candidate. Original green samples and CFA colors survive.
    """
    return _refine_green_impl(image, region, diagnostics=diagnostics, arithmetic='gpu')


def refine_green_cpu(image, region, *, diagnostics=False, auxiliary=None):
    """Observed CPU no-auxiliary stage2 scalar, accepting packed float3.

    CPU retains every input R/B component, including the negative placeholder
    produced by black subtraction. Its one-third constants are float32(1/3).
    This does not implement the alternative auxiliary-map refinement branch.
    """
    if auxiliary is not None:
        raise NotImplementedError('CPU auxiliary refinement is not reconstructed')
    image = np.asarray(image)
    if image.dtype != np.float32 or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError('packed float32 RGB required')
    expanded = np.concatenate([image, np.zeros((*image.shape[:2], 1), np.float32)], -1)
    output, decisions = _refine_green_impl(expanded, region,
        diagnostics=diagnostics, arithmetic='cpu')
    return output[..., :3], decisions


def _refine_green_impl(image, region, *, diagnostics, arithmetic):
    _, sample, even_y, even_x = _region(image, region)
    center = sample()
    chroma_site = even_y == even_x
    red_site = even_y & even_x
    known = np.where(red_site, center[..., 0], center[..., 2])
    green = center[..., 1]

    def g(dy, dx):
        return sample(dy, dx)[..., 1]

    def same(dy, dx):
        neighbor = sample(dy, dx)
        return np.where(red_site, neighbor[..., 0], neighbor[..., 2])

    def opposite(dy, dx):
        neighbor = sample(dy, dx)
        return np.where(red_site, neighbor[..., 2], neighbor[..., 0])

    north, south, west, east = g(-1, 0), g(1, 0), g(0, -1), g(0, 1)
    nw, ne, sw, se = g(-1, -1), g(-1, 1), g(1, -1), g(1, 1)
    third = np.float32(1/3 if arithmetic == 'cpu' else .3333333)
    candidates = [
        (north+green+south)*np.float32(1/3),
        (west+green+east)*np.float32(1/3),
        (ne+np.float32(2)*green+sw)*np.float32(.25),
        (nw+np.float32(2)*green+se)*np.float32(.25),
        (g(2, -1)+green+g(-2, 1))*third,
        (g(1, -2)+green+g(-1, 2))*third,
        (g(-2, -1)+green+g(2, 1))*third,
        (g(-1, -2)+green+g(1, 2))*third,
    ]
    scores = [
        abs(north-green)+abs(south-green),
        abs(west-green)+abs(east-green),
        abs(same(-2, 2)-known)+abs(same(2, -2)-known)
        +abs(opposite(1, -1)-opposite(-1, 1))+abs(north-west)+abs(south-east),
        abs(same(-2, -2)-known)+abs(same(2, 2)-known)
        +abs(opposite(-1, -1)-opposite(1, 1))+abs(north-east)+abs(south-west),
        abs(g(2, -1)-green)+abs(g(-2, 1)-green)+abs(north-sw)+abs(south-ne),
        abs(g(1, -2)-green)+abs(g(-1, 2)-green)+abs(west-ne)+abs(east-sw),
        abs(g(-2, -1)-green)+abs(g(2, 1)-green)+abs(south-nw)+abs(north-se),
        abs(g(-1, -2)-green)+abs(g(1, 2)-green)+abs(east-nw)+abs(west-se),
    ]
    # argmin preserves the earliest candidate on equal scores; the axial
    # comparison deliberately chooses horizontal for an equal pair.
    direction = np.argmin(np.stack(scores), axis=0)
    axial = np.where(scores[0] < scores[1], 0, 1)
    stack = np.stack(candidates)
    chosen = np.take_along_axis(stack, direction[None], axis=0)[0]
    axial_green = np.take_along_axis(stack, axial[None], axis=0)[0]
    refined = np.where(direction < 2, green, (chosen+axial_green)*np.float32(.5))
    output = center.copy()
    if arithmetic == 'gpu':
        output[..., 0] = np.where(red_site, center[..., 0], np.float32(0))
        output[..., 2] = np.where(chroma_site & ~red_site, center[..., 2], np.float32(0))
    output[..., 1] = np.where(chroma_site, refined, green)
    output[..., 3] = np.where(chroma_site, center[..., 3], np.float32(0))
    decisions = {'direction_counts_at_chroma': _counts(direction[chroma_site]),
                 'axial_preserved': int(np.count_nonzero(chroma_site & (direction < 2))),
                 'oblique_refined': int(np.count_nonzero(chroma_site & (direction >= 2)))}
    if diagnostics:
        score_array = np.stack(scores)
        ordered = np.sort(score_array, axis=0)
        decisions.update(direction_map=direction, score_margin=ordered[1]-ordered[0], scores=score_array)
    return output, decisions


def fill_opposite_chroma(image, region, parameters):
    """Fill B at R sites and R at B sites from diagonal color/green ratios."""
    threshold, ratio_offset, epsilon, floor = parameters.values()
    _, sample, even_y, even_x = _region(image, region)
    center = sample()
    chroma_site = even_y == even_x
    red_site = even_y & even_x
    green = center[..., 1]
    known = np.where(red_site, center[..., 0], center[..., 2])

    def c(dy, dx):
        neighbor = sample(dy, dx)
        return np.where(red_site, neighbor[..., 2], neighbor[..., 0])

    def g(dy, dx):
        return sample(dy, dx)[..., 1]

    def own(dy, dx):
        neighbor = sample(dy, dx)
        return np.where(red_site, neighbor[..., 0], neighbor[..., 2])

    diagonal_a = abs(c(-1, -1)-c(1, 1)) < abs(c(1, -1)-c(-1, 1))
    adapt = (g(-1, -1)+g(1, 1)+g(-1, 1)+g(1, -1)
             > (c(-1, -1)+c(-1, 1)+c(1, -1)+c(1, 1))*threshold)

    def estimate(first, second):
        y0, x0 = first
        y1, x1 = second
        g0, g1, c0, c1 = g(y0, x0), g(y1, x1), c(y0, x0), c(y1, x1)
        w0 = floor+abs(g0-green)+abs(own(2*y0, 2*x0)-known)
        w1 = floor+abs(g1-green)+abs(own(2*y1, 2*x1)-known)
        w0 = np.where(adapt, w0*(ratio_offset+abs(c0-g0)/np.maximum(np.float32(1), np.float32(1)+c0+g0)), w0)
        w1 = np.where(adapt, w1*(ratio_offset+abs(c1-g1)/np.maximum(np.float32(1), np.float32(1)+c1+g1)), w1)
        regularization = (w1+w0)*epsilon
        ratio = (w1*c0+w0*c1+regularization)/np.maximum(regularization, w1*g0+w0*g1+regularization)
        return ratio*(green+epsilon)-epsilon

    missing = np.where(diagonal_a, estimate((-1, -1), (1, 1)), estimate((1, -1), (-1, 1)))
    output = center.copy()
    output[..., 2] = np.where(red_site, missing, output[..., 2])
    output[..., 0] = np.where(chroma_site & ~red_site, missing, output[..., 0])
    return output, {'diagonal_nw_se': int(np.count_nonzero(chroma_site & diagonal_a)),
                    'diagonal_sw_ne': int(np.count_nonzero(chroma_site & ~diagonal_a)),
                    'adaptive_weights': int(np.count_nonzero(chroma_site & adapt)),
                    'unadapted_weights': int(np.count_nonzero(chroma_site & ~adapt))}


def fill_chroma_at_green(image, region, parameters):
    """Fill R/B at both G sites with inverse variation color/green ratios."""
    threshold, ratio_offset, epsilon, _ = parameters.values()
    _, sample, even_y, even_x = _region(image, region)
    center = sample()
    green_site = even_y != even_x
    green = center[..., 1]
    offsets = ((-1, 0), (1, 0), (0, -1), (0, 1))
    neighbors = [sample(dy, dx) for dy, dx in offsets]
    greens = [neighbor[..., 1] for neighbor in neighbors]
    far_greens = [sample(2*dy, 2*dx)[..., 1] for dy, dx in offsets]
    variations = [np.float32(1)+abs(greens[0]-greens[1])+abs(far_greens[i]-green) for i in (0, 1)]
    variations += [np.float32(1)+abs(greens[2]-greens[3])+abs(far_greens[i]-green) for i in (2, 3)]
    output = center.copy()
    counts = {}
    for channel, label in ((0, 'red'), (2, 'blue')):
        colors = [neighbor[..., channel] for neighbor in neighbors]
        # Reproduce the observed arithmetic association, which can differ by
        # a few ULP from an algebraically reordered four-way float sum.
        sum_green = greens[0]+greens[1]+greens[3]+greens[2]
        sum_color = (colors[0]+colors[2]+colors[3]+colors[1])*threshold
        adapt = sum_green > sum_color
        weights = []
        for variation, color, neighbor_green in zip(variations, colors, greens):
            adjustment = ratio_offset+abs(neighbor_green-color)/np.maximum(np.float32(1), np.float32(1)+neighbor_green+color)
            weights.append(np.float32(1)/np.where(adapt, variation*adjustment, variation))
        north, south, west, east = weights
        total = north+south+east+west
        numerator = north*colors[0]+south*colors[1]+west*colors[2]+east*colors[3]+total*epsilon
        denominator = np.maximum(total*epsilon,
            north*greens[0]+south*greens[1]+west*greens[2]+east*greens[3]+total*epsilon)
        missing = numerator/denominator*(green+epsilon)-epsilon
        output[..., channel] = np.where(green_site, missing, output[..., channel])
        counts[label+'_adaptive_weights'] = int(np.count_nonzero(green_site & adapt))
        counts[label+'_unadapted_weights'] = int(np.count_nonzero(green_site & ~adapt))
    return output, counts


def fill_opposite_chroma_cpu(image, region, *, regularizer, direction_floor=1):
    """Inspected CPU scalar diagonal worker, explicit packed float3 input.

    This is only chroma interpolation. The Run method's white balance,
    SIMD dispatch and subsequent noise/detail passes are separate operations.
    """
    image = _packed_cpu_chroma(image)
    output, decisions = fill_opposite_chroma(image, region,
        ChromaParameters(.75, .03, regularizer, direction_floor))
    return output[..., :3], decisions


def fill_chroma_at_green_cpu(image, region, *, regularizer):
    """Inspected CPU scalar axial worker, requiring completed diagonal chroma."""
    image = _packed_cpu_chroma(image)
    output, decisions = fill_chroma_at_green(image, region,
        ChromaParameters(.75, .03, regularizer, 1))
    return output[..., :3], decisions


def _packed_cpu_chroma(image):
    image = np.asarray(image)
    if image.dtype != np.float32 or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError('packed float32 RGB required')
    return np.concatenate([image, np.zeros((*image.shape[:2], 1), np.float32)], -1)
