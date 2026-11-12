"""Conservative, offline adjustment proposals. Never mutates image or edits.

These are independent statistical/line-detection tools, not private LR/C1 code.
The caller applies returned changes in one undo transaction after generation
and photo-identity checks. Geometry reports no change when evidence is weak.
"""
from dataclasses import asdict, replace
import math

import numpy as np

from shared.color_management import conversion_matrix, decode, encode
from shared.geometry import normalize_geometry
from shared.levels import LevelChannel, normalize_levels


def _get(settings, name, default):
    return settings.get(name, default) if isinstance(settings, dict) else getattr(settings, name, default)


def _proxy(pixels, source_color_space, source_linear):
    source = np.asarray(pixels)
    if source.ndim != 3 or source.shape[2] != 3 or min(source.shape[:2]) < 2:
        raise ValueError('自动调整需要 RGB 图像')
    step = max(1, math.ceil(max(source.shape[:2]) / 640))
    values = np.array(source[::step, ::step], dtype=np.float32, copy=True)
    if source.dtype == np.uint8:
        values /= 255.
    elif source.dtype == np.uint16:
        values /= 65535.
    if not np.isfinite(values).all():
        raise ValueError('自动调整输入包含无效像素')
    linear = values if source_linear else decode(values, source_color_space)
    if source_color_space != 'sRGB':
        linear = linear @ conversion_matrix(source_color_space, 'sRGB').T
    return np.asarray(linear, np.float32)


def _wb_matrix(temperature, tint):
    def white(t, g=0.):
        x = (-3.0258469e9/t**3+2.1070379e6/t**2+.2226347e3/t+.240390) if t>4000 else (-.2661239e9/t**3-.2343580e6/t**2+.8776956e3/t+.179910)
        y = (-1.1063814*x**3-1.34811020*x*x+2.18555832*x-.20219683) if t<=2222 else (-.9549476*x**3-1.37418593*x*x+2.09137015*x-.16748867) if t<=4000 else (3.081758*x**3-5.8733867*x*x+3.75112997*x-.37001483)
        y = np.clip(y+g*.000045, .30, .36)
        return np.array([x/y, 1., (1-x-y)/y])
    b = np.array([[.8951,.2664,-.1614],[-.7502,1.7135,.0367],[.0389,-.0685,1.0296]])
    xyz = np.array([[.4124564,.3575761,.1804375],[.2126729,.7151522,.072175],[.0193339,.119192,.9503041]])
    return np.linalg.solve(xyz, np.linalg.solve(b, np.diag((b@white(temperature,tint))/(b@white(6500)))@b)@xyz)


def _estimate_white_balance(linear):
    """Estimate a source white from spatially distributed, unsaturated neutrals."""
    height, width = linear.shape[:2]
    flat = linear.reshape(-1, 3)
    luminance = flat @ np.array([.2126, .7152, .0722])
    peak = flat.max(axis=1)
    chroma = (peak-flat.min(axis=1))/np.maximum(peak, 1e-6)
    valid = ((luminance > .008) & (luminance < .84) &
             (flat.min(axis=1) > .002) & (peak < .985) & (chroma < .72))
    if int(valid.sum()) < 24:
        return {}, .1, '缺少可置信的中性区域，保留白平衡'

    log_ratio = np.log(np.maximum(flat, 1e-6)/np.maximum(luminance[:, None], 1e-6))
    tile_estimates = []
    y_edges = np.linspace(0, height, 9, dtype=int)
    x_edges = np.linspace(0, width, 9, dtype=int)
    for y0, y1 in zip(y_edges[:-1], y_edges[1:]):
        for x0, x1 in zip(x_edges[:-1], x_edges[1:]):
            ys, xs = np.mgrid[y0:y1, x0:x1]
            indices = (ys*width+xs).ravel()
            selected = indices[valid[indices]]
            if len(selected) >= 4:
                tile_estimates.append(np.median(log_ratio[selected], axis=0))
    if not tile_estimates:
        return {}, .1, '中性区域分布不足，保留白平衡'

    tile_estimates = np.asarray(tile_estimates, dtype=np.float64)
    neutral_log = np.median(tile_estimates, axis=0)
    neutral = np.exp(neutral_log)
    neutral /= max(float(neutral.mean()), 1e-8)

    from scipy.optimize import least_squares

    def residual(q):
        corrected = _wb_matrix(q[0]*1000, q[1]) @ neutral
        corrected /= max(float(corrected.mean()), 1e-8)
        return np.log(np.maximum(corrected, 1e-6))

    fits = [least_squares(residual, [start, 0.], bounds=([2., -100.], [10., 100.]),
                          loss='soft_l1', f_scale=.025, x_scale=[2., 25.], max_nfev=55)
            for start in (3.2, 6.5, 9.2)]
    fit = min(fits, key=lambda item: float(np.linalg.norm(item.fun)))
    spread = float(np.median(np.linalg.norm(tile_estimates-neutral_log, axis=1)))
    coverage = min(1., float(valid.sum())/(len(flat)*.05))
    distribution = min(1., len(tile_estimates)/10.)
    consistency = math.exp(-spread/.12)
    fit_quality = math.exp(-float(np.linalg.norm(fit.fun))/.15)
    # Weak evidence must lower confidence, rather than being compensated by
    # plentiful pixels elsewhere. Mixed illumination or a poorly fitted cast
    # is not a reason to force a global correction.
    confidence = min(.98, coverage**.5 * distribution**.5 * consistency**.5 * fit_quality)
    if confidence < .4 or len(tile_estimates) < 6 or np.linalg.norm(fit.fun) > .12:
        return {}, confidence, '中性区域分布不足，保留白平衡'
    return ({'temperature': round(float(fit.x[0]*1000), 1),
             'tint': round(float(fit.x[1]), 2)}, confidence,
            '按分布式中性区域估计色温与色调')


def _geometry(linear, settings):
    from skimage.feature import canny
    from skimage.transform import hough_line, hough_line_peaks
    grey = np.clip(encode(linear) @ np.array([.2126,.7152,.0722]), 0., 1.)
    edges = canny(grey, sigma=1.3)
    if edges.mean() < .002:
        return {}, 0., '未检测到足够的直线'
    # Search only lines close to horizontal or vertical; arbitrary object
    # diagonals are not evidence that the camera is tilted.
    theta = np.deg2rad(np.r_[np.arange(-90., -78., .1), np.arange(-12., 12., .1), np.arange(78., 90., .1)])
    accumulator, angles, distances = hough_line(edges, theta=theta)
    strength, normal, _ = hough_line_peaks(accumulator, angles, distances,
        min_distance=12, min_angle=8, threshold=max(24., min(grey.shape)*.12), num_peaks=24)
    if len(strength) < 3:
        return {}, .15, '可靠直线不足，保留当前几何'
    deviation = (np.rad2deg(normal)+45.) % 90. - 45.
    best = max(range(len(strength)), key=lambda i: float(strength[np.abs(deviation-deviation[i]) < 1.0].sum()))
    keep = np.abs(deviation-deviation[best]) < 1.
    support = float(strength[keep].sum()/strength.sum())
    estimate = float(np.average(deviation[keep], weights=strength[keep]))
    spread = float(np.sqrt(np.average((deviation[keep]-estimate)**2, weights=strength[keep])))
    confidence = min(.98, support * min(1., int(keep.sum())/5.) * max(0.,1.-spread/1.2))
    if keep.sum() < 3 or support < .65 or confidence < .5 or abs(estimate)>10.:
        return {}, confidence, '直线方向不一致，未强行拉直'
    g = normalize_geometry(_get(settings, 'geometry', None))
    if g.flip_horizontal != g.flip_vertical:
        estimate = -estimate
    return {'geometry': asdict(replace(g, rotation=round(-estimate, 3)))}, confidence, '依据一致的水平与垂直直线估计倾斜'


def _line_segments(linear):
    """Return a bounded set of long, near-axis line segments.

    This deliberately uses a proxy and only treats repeated architectural
    lines as evidence. A single diagonal edge or a dense natural texture must
    never cause a large perspective correction.
    """
    from skimage.feature import canny
    from skimage.transform import probabilistic_hough_line
    grey = np.clip(encode(linear) @ np.array([.2126, .7152, .0722]), 0., 1.)
    edges = canny(grey, sigma=1.25)
    h, w = edges.shape
    if float(edges.mean()) < .002:
        return [], (h, w)
    length = max(32, int(min(h, w) * .18))
    segments = probabilistic_hough_line(edges, threshold=max(8, length // 4),
        line_length=length, line_gap=max(7, length // 8),
        theta=np.linspace(-np.pi / 2, np.pi / 2, 360, endpoint=False), rng=0)
    result = []
    for (x0, y0), (x1, y1) in segments:
        dx, dy = float(x1 - x0), float(y1 - y0)
        segment_length = math.hypot(dx, dy)
        if segment_length < length:
            continue
        angle = math.atan2(dy, dx)
        # Undirected line angle in [-pi/2, pi/2).
        angle = (angle + math.pi / 2) % math.pi - math.pi / 2
        horizontal = abs(angle) <= math.radians(14)
        vertical = abs(abs(angle) - math.pi / 2) <= math.radians(14)
        if not (horizontal or vertical):
            continue
        family = 'horizontal' if horizontal else 'vertical'
        result.append((np.array([x0, y0], dtype=np.float64),
                       np.array([x1, y1], dtype=np.float64),
                       segment_length, family))
    # Avoid a dense texture dominating the solve. Keep the strongest line per
    # coarse cell and family, while retaining spatially separated evidence.
    cells = {}
    cell_w, cell_h = max(24, w // 8), max(24, h // 8)
    for item in sorted(result, key=lambda value: value[2], reverse=True):
        midpoint = (item[0] + item[1]) * .5
        key = (item[3], int(midpoint[0] // cell_w), int(midpoint[1] // cell_h))
        if key not in cells:
            cells[key] = item
    return list(cells.values())[:96], (h, w)


def _perspective(linear, settings, mode):
    """Estimate absolute vertical/full perspective from repeated line families.

    The solve minimizes line direction error after the same homography used by
    preview/export. It is bounded, conservative, and returns no edits when the
    evidence does not improve enough. This is an estimator, not a proprietary
    camera or LR/C1 algorithm.
    """
    from scipy.optimize import minimize
    from shared.geometry import geometry_matrix

    segments, shape = _line_segments(linear)
    h, w = shape
    families = {'vertical': [item for item in segments if item[3] == 'vertical'],
                'horizontal': [item for item in segments if item[3] == 'horizontal']}
    required = 3 if mode == 'vertical' else 5
    if len(families['vertical']) < required:
        return {}, .1, '可靠的垂直线不足，保留当前透视'
    if mode == 'full' and len(families['horizontal']) < 2:
        return {}, .12, '缺少水平线组，未强行校正完整透视'
    # Full mode needs lines distributed across the frame to establish a
    # vanishing direction; a tight cluster is not enough evidence.
    all_lines = families['vertical'] + (families['horizontal'] if mode == 'full' else [])
    xs = [(a[0] + b[0]) * .5 for a, b, _, _ in all_lines]
    ys = [(a[1] + b[1]) * .5 for a, b, _, _ in all_lines]
    if (max(xs) - min(xs) < w * .28 or max(ys) - min(ys) < h * .28):
        return {}, .16, '直线空间分布不足，保留当前透视'

    current = normalize_geometry(_get(settings, 'geometry', None))
    # The source sent to this estimator has no user geometry applied. Keep
    # crop/scale/flip/quarter-turn semantics, but solve absolute correction
    # fields from the source in one pass.
    # The worker receives the source before user geometry. Solve only the
    # requested absolute correction from that source; untouched horizontal
    # perspective is copied back for vertical-only mode below.
    base = replace(current, rotation=0., vertical=0., horizontal=0., auto_crop=False)
    points = np.asarray([[*item[0], 1., *item[1], 1.] for item in all_lines],
                        dtype=np.float64).reshape(-1, 2, 3)
    weights = np.asarray([item[2] for item in all_lines], dtype=np.float64)
    vertical = np.asarray([item[3] == 'vertical' for item in all_lines])
    if current.quarter_turns % 2:
        vertical = ~vertical

    def errors(values):
        v, q = values
        g = replace(base, vertical=float(v), horizontal=float(q))
        mapped = points @ geometry_matrix(w, h, g).T
        mapped = mapped[..., :2] / mapped[..., 2:3]
        delta = mapped[:, 1] - mapped[:, 0]
        directions = np.arctan2(delta[:, 1], delta[:, 0])
        desired = np.where(vertical, math.pi / 2, 0.)
        return (directions - desired + math.pi / 2) % math.pi - math.pi / 2

    def residual(values):
        e = errors(values)
        # Huber loss permits a few mistaken edges without letting them
        # dictate a visibly wrong vanishing point.
        limit = math.radians(1.2)
        loss = np.where(np.abs(e) <= limit, e * e,
                        2 * limit * np.abs(e) - limit * limit)
        return float(np.average(loss, weights=weights))

    initial = (0., base.horizontal)
    before = residual(initial)
    bounds = [(-100., 100.),
              (base.horizontal, base.horizontal) if mode == 'vertical' else (-100., 100.)]
    result = minimize(residual, initial,
                      method='Powell', bounds=bounds,
                      options={'maxiter': 45, 'xtol': .08, 'ftol': 1e-7})
    values = np.asarray(result.x, dtype=np.float64)
    after = residual(values)
    improvement = (before - after) / max(before, 1e-9)
    final_errors = np.abs(errors(values))
    support = float(weights[final_errors < math.radians(1.2)].sum() / weights.sum())
    # Reject boundary solutions and tiny improvements: these are typical of
    # foliage, brick texture, and weak line detections.
    if not result.success or not np.isfinite(after) or improvement < .30 or support < .72:
        return {}, .22, '透视线索不足，未强行校正'
    if abs(values[0]) > 95. or (mode == 'full' and abs(values[1]) > 95.):
        return {}, .2, '透视估计超出安全范围，保留当前透视'
    confidence = min(.96, .42 + .34 * min(1., len(families['vertical']) / 8.)
                     + (.18 * min(1., len(families['horizontal']) / 5.) if mode == 'full' else .1))
    confidence *= support * float(np.clip(improvement / .7, 0., 1.))
    if confidence < .45:
        return {}, round(confidence, 4), '透视改善证据不足，保留当前透视'
    vertical_value = float(round(float(values[0]), 2))
    horizontal_value = float(round(float(values[1]), 2))
    geometry = replace(current, vertical=vertical_value,
                       horizontal=horizontal_value if mode == 'full' else current.horizontal)
    reason = '依据分布式垂直线估计透视' if mode == 'vertical' else '依据水平与垂直线组估计完整透视'
    return {'geometry': asdict(geometry)}, round(float(confidence), 4), reason


def analyze_auto(pixels, kind, settings, source_color_space='sRGB', source_linear=False):
    """Return ``{kind, changes, confidence, reason}`` without applying edits.

    Input is original or bounded RGB, with the stated source transfer/primaries.
    RAW baseline exposure should be included by the caller when requesting
    tone/levels, without baking the user's exposure or these edits into it.
    White balance and tone return absolute temperature/tint/exposure for this source;
    levels and geometry return full nested records, preserving untouched fields.
    """
    if kind not in ('white_balance', 'levels', 'tone', 'geometry', 'geometry_vertical', 'geometry_full'):
        raise ValueError('未知自动调整类型')
    linear = _proxy(pixels, source_color_space, source_linear)
    if kind == 'geometry':
        changes, confidence, reason = _geometry(linear, settings)
    elif kind == 'geometry_vertical':
        changes, confidence, reason = _perspective(linear, settings, 'vertical')
    elif kind == 'geometry_full':
        changes, confidence, reason = _perspective(linear, settings, 'full')
    elif kind == 'white_balance':
        changes, confidence, reason = _estimate_white_balance(linear)
    else:
        encoded = encode(linear)
        y = encoded @ np.array([.2126,.7152,.0722])
        low, median, high = np.percentile(y, [.2,50,99.8])
        dynamic = float(high-low)
        confidence = min(.95,max(0.,dynamic/.35))
        if dynamic<.015:
            changes, reason = {}, '画面层次不足，保留当前调整'
        elif kind == 'levels':
            black, white = float(np.clip(low,0,.18)), float(np.clip(high,.55,1.))
            mid = float(np.clip((median-black)/(white-black),.03,.97))
            gamma = float(np.clip(np.log(mid)/np.log(.46),.65,1.6))
            levels = normalize_levels(_get(settings,'levels',None))
            levels = replace(levels, master=replace(levels.master,black=round(black,5),white=round(white,5),gamma=round(gamma,4)))
            changes, reason = {'levels':asdict(levels)}, '以稳健端点与中间调建立主色阶，保留各色通道'
        else:
            yl = np.maximum(linear @ np.array([.2126,.7152,.0722]),0)
            mid, top = np.percentile(yl,[50,99.5])
            correction = float(np.clip(np.log2(.18/max(mid,1e-5)),-1.25,1.25))
            exposure = float(np.clip(correction,-3,3))
            highlight = float(np.clip(-(top*2**correction-.88)*75,-70,0))
            changes = {'exposure':round(exposure,3),'highlights':round(highlight,2),
                       'shadows':round(float(np.clip((.07-np.percentile(yl,10))*220,0,35)),2)}
            reason = '按中间调测光，并保守保护高光与阴影'
    return {'kind':kind,'changes':changes,'confidence':round(float(confidence),4),'reason':reason}
