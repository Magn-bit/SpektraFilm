"""Shared point/parametric curves, channel mixing and four-wheel colour grading.

Independent of film simulation; identical math for previews and export tiles.
No proprietary Lightroom or Capture One implementation is included.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from functools import lru_cache
import colorsys
import json
import math
import numpy as np

IDENTITY = ((0., 0.), (1., 1.))
CHANNELS = ('master', 'red', 'green', 'blue', 'luma')
ZONES = ('shadows', 'midtones', 'highlights')
GRADING_ZONES = (*ZONES, 'master')


@dataclass(frozen=True)
class ParametricCurve:
    shadows: float = 0.
    darks: float = 0.
    lights: float = 0.
    highlights: float = 0.
    shadow_split: float = .25
    midtone_split: float = .5
    highlight_split: float = .75


@dataclass(frozen=True)
class ParametricSet:
    master: ParametricCurve = ParametricCurve()
    red: ParametricCurve = ParametricCurve()
    green: ParametricCurve = ParametricCurve()
    blue: ParametricCurve = ParametricCurve()
    luma: ParametricCurve = ParametricCurve()


@dataclass(frozen=True)
class MixerRow:
    red: float = 0.
    green: float = 0.
    blue: float = 0.


@dataclass(frozen=True)
class ChannelMixer:
    red: MixerRow = MixerRow()
    green: MixerRow = MixerRow()
    blue: MixerRow = MixerRow()


@dataclass(frozen=True)
class CurveSet:
    master: tuple = IDENTITY
    red: tuple = IDENTITY
    green: tuple = IDENTITY
    blue: tuple = IDENTITY
    luma: tuple = IDENTITY
    parametric: ParametricSet = ParametricSet()


@dataclass(frozen=True)
class TonalGrade:
    hue: float = 0.
    saturation: float = 0.
    luminance: float = 0.


@dataclass(frozen=True)
class ColorGrading:
    shadows: TonalGrade = TonalGrade()
    midtones: TonalGrade = TonalGrade()
    highlights: TonalGrade = TonalGrade()
    balance: float = 0.
    blending: float = 50.
    # Appended to retain the positional constructor used by existing records/tests.
    master: TonalGrade = TonalGrade()


def _number(value, default, low, high):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return max(low, min(high, float(value)))
    return default


def normalize_parametric_curve(value):
    if isinstance(value, ParametricCurve): return value
    if not isinstance(value, dict): return ParametricCurve()
    amounts = {name: _number(value.get(name), 0., -100., 100.)
               for name in ('shadows', 'darks', 'lights', 'highlights')}
    # Three ordered dividers, with the same five-percent minimum region as Lab.
    a = _number(value.get('shadow_split', value.get('shadowSplit')), .25, .05, .85)
    b = min(.9, max(a+.05, _number(value.get('midtone_split', value.get('midtoneSplit')), .5, a+.05, .9)))
    c = min(.95, max(b+.05, _number(value.get('highlight_split', value.get('highlightSplit')), .75, b+.05, .95)))
    return ParametricCurve(**amounts, shadow_split=a, midtone_split=b, highlight_split=c)


def normalize_parametric(value):
    if isinstance(value, ParametricSet): return value
    if not isinstance(value, dict): return ParametricSet()
    return ParametricSet(**{name: normalize_parametric_curve(value.get(name, value.get('rgb')
                           if name == 'master' else None)) for name in CHANNELS})


def normalize_channel_mixer(value):
    if isinstance(value, ChannelMixer): return value
    if not isinstance(value, dict): return ChannelMixer()
    rows = {}
    for channel in ('red', 'green', 'blue'):
        row = value.get(channel, {})
        if isinstance(row, MixerRow): rows[channel] = row
        else:
            row = row if isinstance(row, dict) else {}
            rows[channel] = MixerRow(**{key: _number(row.get(key), 0., -100., 100.)
                                       for key in ('red', 'green', 'blue')})
    return ChannelMixer(**rows)


def channel_mixer_matrix(value):
    mixer = normalize_channel_mixer(value)
    return np.eye(3, dtype=np.float32) + np.asarray(
        [[getattr(getattr(mixer, row), channel) for channel in ('red', 'green', 'blue')]
         for row in ('red', 'green', 'blue')], dtype=np.float32) / np.float32(100)


def normalize_curves(value):
    if isinstance(value, CurveSet):
        return value
    if not isinstance(value, dict):
        return CurveSet()
    result = {}
    for name in CHANNELS:
        raw = value.get(name, value.get('rgb', IDENTITY) if name == 'master' else IDENTITY)
        if isinstance(raw, dict): raw = raw.get('points', IDENTITY)
        points = {}
        if isinstance(raw, (list, tuple)):
            for point in raw[:32]:
                if (isinstance(point, (list, tuple)) and len(point) >= 2
                        and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                and math.isfinite(v) for v in point[:2])):
                    points[round(max(0., min(1., float(point[0]))), 6)] = max(0., min(1., float(point[1])))
        if len(points) < 2:
            result[name] = IDENTITY
        else:
            ordered = sorted(points.items())
            # Endpoints define the actual domain. Do not add immovable ghost
            # points when a user moves an end horizontally.
            result[name] = tuple(ordered)
    return CurveSet(**result, parametric=normalize_parametric(value.get('parametric')))


def normalize_grading(value):
    if isinstance(value, ColorGrading):
        return value
    if not isinstance(value, dict):
        return ColorGrading()
    result = {}
    for zone in GRADING_ZONES:
        raw = value.get(zone, {})
        if isinstance(raw, TonalGrade):
            result[zone] = raw
        elif isinstance(raw, dict):
            result[zone] = TonalGrade(
                _number(raw.get('hue'), 0., 0., 360.),
                _number(raw.get('saturation'), 0., 0., 100.),
                _number(raw.get('luminance'), 0., -100., 100.))
    return ColorGrading(**result, balance=_number(value.get('balance'), 0., -100., 100.),
                        blending=_number(value.get('blending'), 50., 0., 100.))


def parse_color_tools(value):
    if isinstance(value, str):
        try: value = json.loads(value)
        except (TypeError, ValueError): value = {}
    if not isinstance(value, dict): value = {}
    return normalize_curves(value.get('curves')), normalize_grading(value.get('grading'))


def color_tools_json(curves, grading, hsl=None, channel_mixer=None):
    try:
        from .hsl import normalize_hsl
    except ImportError:
        from hsl import normalize_hsl
    return json.dumps(dict(curves=asdict(normalize_curves(curves)),
                           grading=asdict(normalize_grading(grading)),hsl=asdict(normalize_hsl(hsl)),
                           channel_mixer=asdict(normalize_channel_mixer(channel_mixer))),
                      ensure_ascii=False, separators=(',', ':'), allow_nan=False)


@lru_cache(maxsize=64)
def _curve(points):
    from scipy.interpolate import PchipInterpolator
    values = np.asarray(points, dtype=np.float64)
    return PchipInterpolator(values[:, 0], values[:, 1], extrapolate=False)


def _point_values(points, x):
    return _curve(points)(np.clip(x, points[0][0], points[-1][0]))


@lru_cache(maxsize=128)
def parametric_curve_points(value):
    """Lab's four-region construction, including monotonic tone-scale guard."""
    splits = (0., value.shadow_split, value.midtone_split, value.highlight_split, 1.)
    amounts = (value.shadows, value.darks, value.lights, value.highlights)
    offsets = [amounts[i]/100*(splits[i+1]-splits[i])/2 for i in range(4)]
    points = [(0., 0.)]
    for i in range(4):
        mid = (splits[i]+splits[i+1])/2
        points.append((mid, mid+offsets[i]))
        if i < 3: points.append((splits[i+1], splits[i+1]+(offsets[i]+offsets[i+1])/2))
    points.append((1., 1.))
    floor = 0.
    result = []
    for x, y in points:
        floor = max(floor, min(1., max(0., y)))
        result.append((x, floor))
    return tuple(result)


@lru_cache(maxsize=128)
def _fc_tangents(points):
    values = np.asarray(points, dtype=np.float64)
    h = np.diff(values[:, 0]); d = np.diff(values[:, 1])/h
    m = np.empty(len(points), dtype=np.float64); m[0] = d[0]; m[-1] = d[-1]
    m[1:-1] = np.where(d[:-1]*d[1:] <= 0, 0., (d[:-1]+d[1:])/2)
    for i in range(len(d)):
        if d[i] == 0: continue
        a, b = m[i]/d[i], m[i+1]/d[i]
        if a*a+b*b > 9:
            scale = 3/math.sqrt(a*a+b*b)
            m[i], m[i+1] = scale*a*d[i], scale*b*d[i]
    return values, h, m


def _fc_values(points, x):
    values, h, m = _fc_tangents(points)
    x = np.clip(x, values[0, 0], values[-1, 0])
    i = np.clip(np.searchsorted(values[:, 0], x, side='right')-1, 0, len(points)-2)
    t = (x-values[i, 0])/h[i]; t2 = t*t; t3 = t2*t
    result = ((2*t3-3*t2+1)*values[i, 1]+(t3-2*t2+t)*h[i]*m[i]
              +(-2*t3+3*t2)*values[i+1, 1]+(t3-t2)*h[i]*m[i+1])
    # Algebraically flat segments stay exactly flat; evaluating the two Hermite
    # endpoint terms separately can otherwise create sub-ulp downward steps.
    return np.clip(np.where(values[i, 1] == values[i+1, 1], values[i, 1], result), 0, 1)


def parametric_active(value):
    return any(getattr(value, key) != 0 for key in ('shadows', 'darks', 'lights', 'highlights'))


def curve_active(curves, channel):
    return getattr(curves, channel) != IDENTITY or parametric_active(getattr(curves.parametric, channel))


def evaluate_curve(curves, channel, x):
    """Composed point(parametric(x)); legacy point interpolation stays PCHIP."""
    curves = normalize_curves(curves)
    parametric = getattr(curves.parametric, channel)
    if parametric_active(parametric): x = _fc_values(parametric_curve_points(parametric), x)
    return _point_values(getattr(curves, channel), x)


def _decode(rgb):
    return np.where(rgb <= .04045, rgb/12.92, ((np.maximum(rgb, 0)+.055)/1.055)**2.4)


def _encode(rgb):
    return np.where(rgb <= .0031308, rgb*12.92, 1.055*np.maximum(rgb, 0)**(1/2.4)-.055)


def _oklab(linear):
    r, g, b = np.moveaxis(linear, -1, 0)
    l = np.cbrt(.4122214708*r+.5363325363*g+.0514459929*b)
    m = np.cbrt(.2119034982*r+.6806995451*g+.1073969566*b)
    s = np.cbrt(.0883024619*r+.2817188376*g+.6299787005*b)
    return np.stack((.2104542553*l+.7936177850*m-.0040720468*s,
                     1.9779984951*l-2.4285922050*m+.4505937099*s,
                     .0259040371*l+.7827717662*m-.8086757660*s), axis=-1)


def _linear_from_oklab(lab):
    L, a, b = np.moveaxis(lab, -1, 0)
    l = (L+.3963377774*a+.2158037573*b)**3
    m = (L-.1055613458*a-.0638541728*b)**3
    s = (L-.0894841775*a-1.2914855480*b)**3
    return np.stack((4.0767416621*l-3.3077115913*m+.2309699292*s,
                     -1.2684380046*l+2.6097574011*m-.3413193965*s,
                     -.0041960863*l-.7034186147*m+1.7076147010*s), axis=-1)


@lru_cache(maxsize=64)
def _grade_vectors(grading):
    vectors = []
    for zone in GRADING_ZONES:
        grade = getattr(grading, zone)
        wheel = np.array(colorsys.hsv_to_rgb((grade.hue % 360)/360, 1., 1.), dtype=np.float32)
        ab = _oklab(_decode(wheel))[1:]
        ab /= max(float(np.linalg.norm(ab)), 1e-6)
        vectors.append((grade.luminance*.0015, *(ab*grade.saturation*.0012)))
    return np.asarray(vectors, dtype=np.float32)


def apply_color_tools(rgb, curves=None, grading=None, channel_mixer=None):
    """In-place bounded colour operation. Neutral settings are bit-exact identity.

    Curves use shape-preserving cubic interpolation without ringing. Grading
    moves OKLab chroma with smoothly overlapping tonal weights, then compresses
    out-of-gamut chroma towards the same lightness before sRGB encoding.
    """
    curves, grading = normalize_curves(curves), normalize_grading(grading)
    active_curves = [(index, name) for index, name in enumerate(CHANNELS[:4]) if curve_active(curves, name)]
    active_luma = curve_active(curves, 'luma')
    active_grade = any(getattr(grading, zone).saturation or getattr(grading, zone).luminance for zone in GRADING_ZONES)
    mixer = normalize_channel_mixer(channel_mixer)
    active_mixer = mixer != ChannelMixer()
    matrix = channel_mixer_matrix(mixer) if active_mixer else None
    if not active_curves and not active_grade and not active_luma and not active_mixer:
        return rgb
    # rgb may be a strided spatial region; avoid a reshape copy swallowing edits.
    height, width = rgb.shape[:2]
    rows = max(1, min(128, 65536//max(1, width)))
    for top in range(0, height, rows):
        block = rgb[top:top+rows]
        if active_mixer: block[:] = block @ matrix.T
        for index, name in active_curves:
            if index == 0:
                block[:] = evaluate_curve(curves, name, np.clip(block, 0, 1))
            else:
                block[..., index-1] = evaluate_curve(curves, name, np.clip(block[..., index-1], 0, 1))
        np.clip(block, 0, 1, out=block)
        if not active_grade and not active_luma: continue
        lab = _oklab(_decode(block)).astype(np.float32)
        if active_luma:
            lab[..., 0] = evaluate_curve(curves, 'luma', np.clip(lab[..., 0], 0, 1))
        lightness = lab[..., 0].copy()
        t = np.clip(lightness+grading.balance*.0025, 0, 1)
        sigma = .16+.24*grading.blending/100
        weights = np.exp(-.5*((t[..., None]-np.array([0., .5, 1.], dtype=np.float32))/sigma)**2)
        weights /= np.sum(weights, axis=-1, keepdims=True)
        vectors = _grade_vectors(grading)
        delta = (weights[..., 0, None]*vectors[0]+weights[..., 1, None]*vectors[1]
                 +weights[..., 2, None]*vectors[2]+vectors[3])
        # Preserve endpoint blacks/whites and avoid coloured rings in extremes.
        taper = np.sqrt(np.clip(4*lightness*(1-lightness), 0, 1))
        lab += delta*taper[..., None]
        lab[..., 0] = np.clip(lab[..., 0], 0, 1)
        # Compress chroma into gamut while retaining hue/lightness. Eight binary
        # refinements suffice for a soft look; valid pixels keep full chroma.
        linear = _linear_from_oklab(lab)
        invalid = np.any((linear < -1e-6) | (linear > 1.000001), axis=-1)
        if np.any(invalid):
            bad = lab[invalid].copy()
            low = np.zeros(len(bad), dtype=np.float32)
            high = np.ones(len(bad), dtype=np.float32)
            for _ in range(8):
                scale = (low+high)*.5
                candidate = bad.copy();candidate[:, 1:] *= scale[:, None]
                test = _linear_from_oklab(candidate)
                fits = np.all((test >= 0) & (test <= 1), axis=-1)
                low = np.where(fits, scale, low);high = np.where(fits, high, scale)
            bad[:, 1:] *= low[:, None]
            linear[invalid] = _linear_from_oklab(bad)
        block[:] = _encode(np.clip(linear, 0, 1))
    return rgb
