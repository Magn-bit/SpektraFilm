"""Vector brush masks and bounded, linear-light local compositing.

Coordinates refer to the oriented, optically corrected image. A brush radius is
a fraction of the short image edge. No preview bitmap is stored as edit data.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict, dataclass
import json
import math
import threading

import numpy as np

from shared.levels import apply_hdr_linear


@dataclass(frozen=True)
class MaskStroke:
    points: tuple = ()
    radius: float = .06
    feather: float = .75
    flow: float = 1.0
    erase: bool = False


@dataclass(frozen=True)
class MaskLayer:
    id: str = ''
    name: str = '蒙版'
    enabled: bool = True
    inverted: bool = False
    opacity: float = 1.0
    exposure: float = 0.0
    temperature: float = 0.0
    tint: float = 0.0
    contrast: float = 0.0
    saturation: float = 0.0
    highlights: float = 0.0
    shadows: float = 0.0
    strokes: tuple = ()
    kind: str = 'brush'
    start: tuple = (.25, .5)
    end: tuple = (.75, .5)
    center: tuple = (.5, .5)
    radius_x: float = .25
    radius_y: float = .25
    rotation: float = 0.
    feather: float = .75


LOCAL_LIMITS = {'exposure': (-3., 3.), 'temperature': (-100., 100.),
                'tint': (-100., 100.), 'contrast': (-100., 100.),
                'saturation': (-100., 100.), 'highlights': (-100., 100.),
                'shadows': (-100., 100.), 'opacity': (0., 1.)}
_ALPHA_CACHE = OrderedDict()
_ALPHA_LOCK = threading.RLock()
_ALPHA_BUDGET = 24 * 1024**2


def _number(value, default, low, high):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return max(low, min(high, float(value)))
    return default


def normalize_masks(value):
    """Validate saved JSON or UI data and return immutable edit snapshots."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return ()
    if not isinstance(value, (tuple, list)):
        return ()
    result = []
    for index, item in enumerate(value[:32]):
        if isinstance(item, MaskLayer):
            result.append(item)
            continue
        if not isinstance(item, dict):
            continue
        strokes = []
        raw_strokes = item.get('strokes', ())
        if isinstance(raw_strokes, (tuple, list)):
            for stroke in raw_strokes[:4096]:
                if isinstance(stroke, MaskStroke):
                    strokes.append(stroke)
                    continue
                if not isinstance(stroke, dict):
                    continue
                points = []
                raw_points = stroke.get('points', ())
                if isinstance(raw_points, (tuple, list)):
                    for point in raw_points[:8192]:
                        if not isinstance(point, (tuple, list)) or len(point) < 2:
                            continue
                        if all(isinstance(v, (int, float)) and not isinstance(v, bool)
                               and math.isfinite(v) for v in point[:2]):
                            point = tuple(max(0., min(1., float(v))) for v in point[:2])
                            if not points or point != points[-1]:
                                points.append(point)
                if points:
                    strokes.append(MaskStroke(tuple(points),
                        _number(stroke.get('radius'), .06, .002, .5),
                        _number(stroke.get('feather'), .75, 0., 1.),
                        _number(stroke.get('flow'), 1., 0., 1.),
                        stroke.get('erase') is True))
        settings = {key: _number(item.get(key), 1. if key == 'opacity' else 0., *limits)
                    for key, limits in LOCAL_LIMITS.items()}
        geometry = {}
        for key, default in (('start', (.25,.5)), ('end', (.75,.5)), ('center', (.5,.5))):
            point = item.get(key, default)
            if not isinstance(point, (list, tuple)) or len(point) < 2: point = default
            geometry[key] = tuple(_number(v, d, 0., 1.) for v, d in zip(point[:2],default))
        geometry.update(radius_x=_number(item.get('radius_x'), .25, .002, 2.),
                        radius_y=_number(item.get('radius_y'), .25, .002, 2.),
                        rotation=_number(item.get('rotation'), 0., -360., 360.),
                        feather=_number(item.get('feather'), .75, 0., 1.))
        result.append(MaskLayer(
            id=str(item.get('id') or f'mask-{index+1}')[:80],
            name=str(item.get('name') or f'蒙版 {index+1}')[:80],
            enabled=item.get('enabled', True) is not False,
            inverted=item.get('inverted') is True,
            strokes=tuple(strokes), kind=item.get('kind') if item.get('kind') in ('brush','linear','radial') else 'brush',
            **geometry, **settings))
    return tuple(result)


def masks_to_json(masks):
    return json.dumps([asdict(mask) for mask in normalize_masks(masks)],
                      ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def rasterize_mask(layer, width, height, source_width=0, source_height=0,
                   origin_x=0, origin_y=0):
    """Render alpha at exact source pixel centers, including partial tiles.

    A stroke is the continuous union of its segments: collecting more pointer
    events cannot darken the same stroke. Separate strokes build up with flow.
    """
    width, height = int(width), int(height)
    fw, fh = int(source_width or width), int(source_height or height)
    ox, oy = int(origin_x), int(origin_y)
    if width < 1 or height < 1 or fw < 1 or fh < 1:
        raise ValueError('Mask dimensions must be positive')
    if not isinstance(layer, MaskLayer):
        valid = normalize_masks([layer])
        if not valid:
            return np.zeros((height, width), dtype=np.float32)
        layer = valid[0]
    key = (layer.strokes, layer.inverted, layer.kind, layer.start, layer.end,
           layer.center, layer.radius_x, layer.radius_y, layer.rotation, layer.feather,
           width, height, fw, fh, ox, oy)
    cacheable = max(fw, fh) <= 2048 and width*height <= 1048576
    if cacheable:
        with _ALPHA_LOCK:
            cached = _ALPHA_CACHE.get(key)
            if cached is not None:
                _ALPHA_CACHE.move_to_end(key)
                return cached
    alpha = np.zeros((height, width), dtype=np.float32)
    if layer.kind in ('linear','radial'):
        x = np.arange(ox, ox+width, dtype=np.float64)[None, :]
        y = np.arange(oy, oy+height, dtype=np.float64)[:, None]
        sx, sy = max(1, fw-1), max(1, fh-1)
        if layer.kind == 'linear':
            ax, ay = layer.start[0]*sx, layer.start[1]*sy
            dx, dy = (layer.end[0]-layer.start[0])*sx, (layer.end[1]-layer.start[1])*sy
            length2 = dx*dx+dy*dy
            if length2 > 1e-12:
                t = np.clip(((x-ax)*dx+(y-ay)*dy)/length2, 0, 1)
                alpha[:] = t*t*(3-2*t)
        else:
            x = x-layer.center[0]*sx;y = y-layer.center[1]*sy
            angle = math.radians(layer.rotation)
            c, s = math.cos(angle), math.sin(angle)
            distance = np.hypot((x*c+y*s)/max(.5, layer.radius_x*sx),
                                (-x*s+y*c)/max(.5, layer.radius_y*sy))
            feather = max(.001, layer.feather)
            t = np.clip((distance-(1-feather))/feather, 0, 1)
            alpha[:] = 1-t*t*(3-2*t)
    for stroke in layer.strokes if layer.kind == 'brush' else ():
        if not stroke.points or stroke.flow <= 0:
            continue
        points = np.asarray(stroke.points, dtype=np.float64)
        points *= np.array([max(1, fw-1), max(1, fh-1)], dtype=np.float64)
        radius = max(.5, stroke.radius*min(fw, fh))
        left = max(0, math.floor(points[:, 0].min()-radius-ox))
        right = min(width, math.ceil(points[:, 0].max()+radius-ox)+1)
        top = max(0, math.floor(points[:, 1].min()-radius-oy))
        bottom = min(height, math.ceil(points[:, 1].max()+radius-oy)+1)
        if left >= right or top >= bottom:
            continue
        coverage = np.zeros((bottom-top, right-left), dtype=np.float32)
        pairs = zip(points[:-1], points[1:]) if len(points) > 1 else [(points[0], points[0])]
        inner = radius*(1-stroke.feather)
        soft_width = max(.5, radius-inner)
        for first, last in pairs:
            x0 = max(left, math.floor(min(first[0], last[0])-radius-ox))
            x1 = min(right, math.ceil(max(first[0], last[0])+radius-ox)+1)
            y0 = max(top, math.floor(min(first[1], last[1])-radius-oy))
            y1 = min(bottom, math.ceil(max(first[1], last[1])+radius-oy)+1)
            if x0 >= x1 or y0 >= y1:
                continue
            x = np.arange(x0+ox, x1+ox, dtype=np.float64)[None, :]-first[0]
            y = np.arange(y0+oy, y1+oy, dtype=np.float64)[:, None]-first[1]
            delta = last-first
            length2 = float(delta@delta)
            if length2 > 1e-16:
                projection = np.clip((x*delta[0]+y*delta[1])/length2, 0, 1)
                distance = np.hypot(x-projection*delta[0], y-projection*delta[1])
            else:
                distance = np.hypot(x, y)
            t = np.clip((distance-inner)/soft_width, 0, 1)
            edge = (1-t*t*(3-2*t)).astype(np.float32)
            patch = coverage[y0-top:y1-top, x0-left:x1-left]
            np.maximum(patch, edge, out=patch)
        coverage *= stroke.flow
        area = alpha[top:bottom, left:right]
        if stroke.erase:
            area *= 1-coverage
        else:
            area += (1-area)*coverage
    if layer.inverted:
        np.subtract(1., alpha, out=alpha)
    alpha.setflags(write=False)
    if cacheable:
        with _ALPHA_LOCK:
            _ALPHA_CACHE[key] = alpha
            _ALPHA_CACHE.move_to_end(key)
            while _ALPHA_CACHE and sum(a.nbytes for a in _ALPHA_CACHE.values()) > _ALPHA_BUDGET:
                _ALPHA_CACHE.popitem(last=False)
    return alpha


def _decode(rgb):
    return np.where(rgb <= .04045, rgb/12.92, ((np.maximum(rgb, 0)+.055)/1.055)**2.4)


def _encode(rgb):
    return np.where(rgb <= .0031308, rgb*12.92, 1.055*np.maximum(rgb, 0)**(1/2.4)-.055)


def apply_masks(rgb, masks, source_width=0, source_height=0, origin_x=0, origin_y=0, *, clamp_output=True):
    """Apply local edits in-place with bounded scratch memory; return rgb.

    Global film rendering is not repeated. Only affected strips are converted
    to linear light, adjusted and blended. Layers retain float headroom until
    the optional final output clamp; zero-alpha in-range pixels remain exact.
    """
    masks = normalize_masks(masks)
    if not masks:
        return rgb
    h, w = rgb.shape[:2]
    fw, fh = int(source_width or w), int(source_height or h)
    rows = max(1, min(128, 131072//max(1, w)))
    weights = np.array([.2126, .7152, .0722], dtype=np.float32)
    for layer in masks:
        if not layer.enabled or layer.opacity <= 0 or not any(getattr(layer, key) for key in LOCAL_LIMITS if key != 'opacity'):
            continue
        for top in range(0, h, rows):
            bottom = min(h, top+rows)
            alpha = rasterize_mask(layer, w, bottom-top, fw, fh, origin_x, origin_y+top)
            occupied = np.any(alpha > 0, axis=0)
            if not np.any(occupied):
                continue
            # A small brush must not pay for colour conversion across the whole
            # image strip. Keep exact pixel centres and untouched pixels outside
            # this tight region, including in arbitrarily cut export tiles.
            left = int(np.argmax(occupied))
            right = w-int(np.argmax(occupied[::-1]))
            covered_rows = np.any(alpha[:, left:right] > 0, axis=1)
            first = int(np.argmax(covered_rows))
            last = len(covered_rows)-int(np.argmax(covered_rows[::-1]))
            alpha = alpha[first:last, left:right]
            block = rgb[top+first:top+last, left:right]
            base = _decode(block).astype(np.float32)
            edited = base.copy()
            if layer.exposure:
                edited *= 2**layer.exposure
            if layer.temperature or layer.tint:
                gain = np.exp2(np.array([
                    layer.temperature*.004+layer.tint*.0015,
                    -layer.tint*.0015,
                    -layer.temperature*.004+layer.tint*.0015], dtype=np.float32))
                # Keep a neutral patch's luminance stable when changing tint.
                gain /= float(gain@weights)
                edited *= gain
            apply_hdr_linear(edited, layer.highlights, layer.shadows)
            if layer.contrast or layer.saturation:
                encoded = _encode(edited)
                if layer.contrast:
                    encoded = (encoded-.5)*(1+layer.contrast/100)+.5
                if layer.saturation:
                    lum = np.sum(encoded*weights, axis=-1, keepdims=True)
                    encoded = lum+(encoded-lum)*(1+layer.saturation/100)
                edited = _decode(encoded)
            amount = (alpha*layer.opacity)[:, :, None]
            composited = _encode(base+(edited-base)*amount)
            np.copyto(block, composited, where=amount > 0)
    if clamp_output:
        np.clip(rgb, 0, 1, out=rgb)
    return rgb
