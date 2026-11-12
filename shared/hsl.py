"""Eight-band HSL mixer shared by desktop and Android.

This is our documented sRGB HSL operation, not Adobe's proprietary renderer.
Cosine interpolation gives continuous, overlapping hue selections; a chroma
taper keeps neutral objects neutral. Work is bounded to at most 65536 pixels.
"""
from dataclasses import asdict, dataclass
from functools import lru_cache
import math
import numpy as np

BANDS = ('red', 'orange', 'yellow', 'green', 'aqua', 'blue', 'purple', 'magenta')
ANCHORS = np.array((0., 30., 60., 120., 180., 240., 270., 300., 360.))


@dataclass(frozen=True)
class HslBand:
    hue: float = 0.
    saturation: float = 0.
    luminance: float = 0.


@dataclass(frozen=True)
class HslSettings:
    red: HslBand = HslBand()
    orange: HslBand = HslBand()
    yellow: HslBand = HslBand()
    green: HslBand = HslBand()
    aqua: HslBand = HslBand()
    blue: HslBand = HslBand()
    purple: HslBand = HslBand()
    magenta: HslBand = HslBand()


def normalize_hsl(value):
    if isinstance(value, HslSettings):
        value = asdict(value)
    if not isinstance(value, dict):
        return HslSettings()
    result = {}
    for name in BANDS:
        raw = value.get(name, {})
        if isinstance(raw, HslBand): raw = asdict(raw)
        fields = {}
        for key in ('hue', 'saturation', 'luminance'):
            v = raw.get(key, 0.) if isinstance(raw, dict) else 0.
            fields[key] = max(-100., min(100., float(v))) if (
                isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)) else 0.
        result[name] = HslBand(**fields)
    return HslSettings(**result)


@lru_cache(maxsize=128)
def _values(settings):
    values = np.array([[getattr(getattr(settings, band), key)
                        for key in ('hue', 'saturation', 'luminance')] for band in BANDS])
    return np.concatenate((values, values[:1]))


def apply_hsl(rgb, settings=None):
    """Edit sRGB floats in place, preserving dtype and neutral pixels.

    Hue range is +/-30 degrees, saturation moves toward zero/one, and
    lightness range is +/-0.30 tapered at black/white. Selections are measured
    before editing, so changing one band never changes another band's mask.
    Neutral settings are an exact no-op. Spatial tiles give identical results.
    """
    settings = normalize_hsl(settings)
    if settings == HslSettings(): return rgb
    values = _values(settings)
    width = rgb.shape[1]
    rows = max(1, min(128, 65536 // max(1, width)))
    for top in range(0, rgb.shape[0], rows):
        block = rgb[top:top+rows]
        source = np.clip(block, 0., 1.)
        r, g, b = np.moveaxis(source, -1, 0)
        maximum, minimum = source.max(axis=-1), source.min(axis=-1)
        chroma = maximum-minimum
        light = (maximum+minimum)*.5
        hue = np.zeros_like(light)
        nonzero = chroma > 1e-7
        red = nonzero & (maximum == r)
        green = nonzero & ~red & (maximum == g)
        blue = nonzero & ~red & ~green
        np.divide(g-b, chroma, out=hue, where=red)
        part = np.zeros_like(hue)
        np.divide(b-r, chroma, out=part, where=green)
        hue[green] = part[green]+2.
        np.divide(r-g, chroma, out=part, where=blue)
        hue[blue] = part[blue]+4.
        hue = (hue*60.) % 360.
        selection = np.searchsorted(ANCHORS, hue, side='right')-1
        t = (hue-ANCHORS[selection])/(ANCHORS[selection+1]-ANCHORS[selection])
        weight = (.5-.5*np.cos(t*np.pi)).astype(block.dtype)
        delta = (values[selection]*(1-weight[..., None])+values[selection+1]*weight[..., None]).astype(block.dtype)
        # Close-to-neutral colours have no stable hue. Smoothly protect them.
        protection = np.clip((chroma-.01)/.09, 0., 1.)
        protection *= protection*(3.-2.*protection)
        delta *= protection[..., None]
        changed = nonzero & np.any(delta != 0., axis=-1)
        if not np.any(changed): continue
        saturation = np.zeros_like(light)
        denominator = 1.-np.abs(2.*light-1.)
        np.divide(chroma, denominator, out=saturation, where=denominator > 1e-7)
        hue = (hue+delta[..., 0]*.3) % 360.
        sat_delta = delta[..., 1]*.01
        saturation += np.where(sat_delta >= 0., (1.-saturation)*sat_delta, saturation*sat_delta)
        light += delta[..., 2]*.003*denominator
        np.clip(light, 0., 1., out=light)
        c = (1.-np.abs(2.*light-1.))*np.clip(saturation, 0., 1.)
        x = c*(1.-np.abs((hue/60.) % 2.-1.))
        sector = (hue/60.).astype(np.int8)
        m = light-c*.5
        channels = (np.select((sector==0, sector==1, sector==2, sector==3, sector==4), (c,x,0.,0.,x), default=c),
                    np.select((sector==0, sector==1, sector==2, sector==3, sector==4), (x,c,c,x,0.), default=0.),
                    np.select((sector==0, sector==1, sector==2, sector==3, sector==4), (0.,0.,x,c,c), default=x))
        for index, channel in enumerate(channels):
            block[..., index][changed] = (channel+m)[changed]
    return rgb
