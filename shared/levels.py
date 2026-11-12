"""Independent RGB input/output levels, shared by preview and final output."""
from dataclasses import dataclass
import math

import numpy as np

CHANNELS = ('master', 'red', 'green', 'blue')
FIELDS = ('black', 'white', 'gamma', 'output_black', 'output_white')


@dataclass(frozen=True)
class LevelChannel:
    black: float = 0.
    white: float = 1.
    gamma: float = 1.
    output_black: float = 0.
    output_white: float = 1.


@dataclass(frozen=True)
class LevelsSet:
    master: LevelChannel = LevelChannel()
    red: LevelChannel = LevelChannel()
    green: LevelChannel = LevelChannel()
    blue: LevelChannel = LevelChannel()


def normalize_channel(value):
    if isinstance(value, LevelChannel):
        return value
    if not isinstance(value, dict):
        return LevelChannel()
    defaults = LevelChannel()
    result = {}
    for key in FIELDS:
        number = value.get(key, getattr(defaults, key))
        low, high = (.1, 10.) if key == 'gamma' else (0., 1.)
        result[key] = max(low, min(high, float(number))) if (
            isinstance(number, (float, int)) and not isinstance(number, bool) and math.isfinite(number)) else getattr(defaults, key)
    # Input handles cannot cross. Output endpoints may cross deliberately to
    # invert the selected channel, as in an ordinary input/output levels tool.
    result['black'] = min(result['black'], 1. - 1e-4)
    result['white'] = max(result['black'] + 1e-4, result['white'])
    return LevelChannel(**result)


def normalize_levels(value):
    if isinstance(value, LevelsSet):
        return value
    return LevelsSet(**{key: normalize_channel(value.get(key)) for key in CHANNELS}) if isinstance(value, dict) else LevelsSet()


def apply_channel(values, channel):
    """Identity preserves float headroom; an edited input range sets endpoints."""
    channel = normalize_channel(channel)
    if channel == LevelChannel():
        return values
    scaled = np.clip((values - channel.black) / (channel.white - channel.black), 0., 1.)
    if channel.gamma != 1.:
        scaled = np.power(scaled, 1. / channel.gamma)
    return channel.output_black + scaled * (channel.output_white - channel.output_black)


def apply_levels(pixels, levels):
    """Edit writable float RGB in place: individual R/G/B, then master RGB."""
    levels = normalize_levels(levels)
    for index, key in enumerate(CHANNELS[1:]):
        channel = getattr(levels, key)
        if channel != LevelChannel():
            pixels[..., index] = apply_channel(pixels[..., index], channel)
    if levels.master != LevelChannel():
        pixels[...] = apply_channel(pixels, levels.master)
    return pixels


def hdr_luminance_base(pixels, pixel_scale=(1.,1.), *, contrast=0., warmth=0.,
                       saturation=0., vibrance=0.):
    """Edge-preserving log-luminance base; RGB detail is never blurred.

    Nine sparse Gaussian taps span 48 oriented source pixels. A fourth-power
    range weight suppresses mixing across exposure edges; 65% of the filtered
    log base separates fine texture from the tone mapping. This independent
    model is shared with spk_editor_color, not a recovered C1 implementation.
    Only a scalar plane is retained; conversion scratch is bounded by rows.
    """
    values=np.asarray(pixels,dtype=np.float32)
    if values.ndim!=3 or values.shape[-1]!=3:raise ValueError('HDR base requires H×W×3 RGB')
    height,width=values.shape[:2]
    logs=np.empty((height,width),np.float32)
    weights=np.array([.2126,.7152,.0722],np.float32)
    for top in range(0,height,128):
        block=values[top:top+128].copy()
        if contrast:block=(block-.5)*(1.+contrast/100.)+.5
        if warmth:block*=np.array([1.+warmth*.0025,1.,1.-warmth*.0025],np.float32)
        if saturation:
            luma=np.sum(block*weights,axis=-1,keepdims=True)
            block=luma+(block-luma)*(1.+saturation/100.)
        if vibrance:
            chroma=np.clip(block.max(axis=-1,keepdims=True)-block.min(axis=-1,keepdims=True),0,1)
            luma=np.sum(block*weights,axis=-1,keepdims=True)
            block=luma+(block-luma)*(1.+vibrance/100.*(1.-chroma))
        linear=np.where(block<=.04045,block/12.92,np.maximum((block+.055)/1.055,0.)**2.4)
        logs[top:top+len(block)]=np.log2(np.maximum(np.sum(linear*weights,axis=-1),1e-8))
    result=np.empty_like(logs)
    rx=max(1,int(np.floor(48./max(float(pixel_scale[0]),1e-6)+.5)))
    ry=max(1,int(np.floor(48./max(float(pixel_scale[1]),1e-6)+.5)))
    xs=np.arange(width)
    for top in range(0,height,128):
        end=min(height,top+128);center=logs[top:end]
        total=np.zeros_like(center);normal=np.zeros_like(center)
        for dy,wy in ((-ry,1.),(0,2.),(ry,1.)):
            ys=np.clip(np.arange(top,end)+dy,0,height-1)
            for dx,wx in ((-rx,1.),(0,2.),(rx,1.)):
                sample=logs[ys[:,None],np.clip(xs+dx,0,width-1)]
                delta=(sample-center)/np.float32(.7)
                square=delta*delta
                weight=np.float32(wx*wy)/(1.+square*square)
                total+=sample*weight;normal+=weight
        result[top:end]=np.exp2(center+(total/normal-center)*np.float32(.65))
    return result


def apply_hdr_linear(linear, highlights=0., shadows=0., whites=0., blacks=0., *, detail_base=None):
    """Remap scene-linear luminance without gray offsets or channel clipping.

    Each zone is a smooth exposure change measured in stops from its anchor.
    Shadows/highlights meet at 18% gray; blacks/whites have narrower support.
    The bounded slope stays positive even at +/-100, so combinations cannot
    reverse a gray ramp. One RGB gain retains linear chromatic ratios, true
    black and unclipped source headroom. This is an independent tonal model,
    not a sensor-clipping reconstruction or a proprietary HDR implementation.

    Keep these four zone constants in sync with the native editor shaders.
    """
    if not any((highlights, shadows, whites, blacks)):
        return linear
    luminance = (np.asarray(detail_base,dtype=np.float32).copy() if detail_base is not None
                 else np.maximum(linear @ np.array([.2126, .7152, .0722], np.float32), 0.))
    gain = np.ones_like(luminance)
    for amount, pivot, rolloff, stops, upper in (
            (shadows, .18, 1.7, 3.3, False),
            (highlights, .18, 1.7, 4.3, True),
            (blacks, .04, 1.4, 1.8, False),
            (whites, .45, 1.4, 2.2, True)):
        if not amount:
            continue
        distance = np.log2(np.maximum(luminance, 1e-8)/pivot)
        distance = np.maximum(distance if upper else -distance, 0.)
        weight = 1. - np.exp2(-distance/rolloff)
        zone_gain = np.exp2(max(-100., min(100., float(amount)))*(.01*stops)*weight*weight)
        gain *= zone_gain
        luminance *= zone_gain
    linear *= gain[..., None]
    return linear


def apply_hdr_tone(pixels, highlights=0., shadows=0., whites=0., blacks=0., *, detail_base=None,
                   pixel_scale=(1.,1.)):
    """Apply HDR zones to writable encoded sRGB; zero is an exact bypass."""
    if not any((highlights, shadows, whites, blacks)):
        return pixels
    if detail_base is None and (highlights or shadows) and pixels.ndim==3:
        detail_base=hdr_luminance_base(pixels,pixel_scale)
    linear = np.where(pixels <= .04045, pixels/12.92,
                      np.maximum((pixels+.055)/1.055, 0.)**2.4)
    apply_hdr_linear(linear, highlights, shadows, whites, blacks,detail_base=detail_base)
    pixels[...] = np.where(linear <= .0031308, linear*12.92,
                           1.055*np.maximum(linear, 0.)**(1./2.4)-.055)
    return pixels


def apply_hdr_endpoints(pixels, whites=0., blacks=0.):
    """Endpoint-selective zones, separate from input/output levels."""
    return apply_hdr_tone(pixels, whites=whites, blacks=blacks)


def apply_brightness(pixels, amount=0.):
    """Midtone-weighted linear gain; brightness does not replace exposure EV."""
    if not amount:
        return pixels
    linear = np.where(pixels <= .04045, pixels/12.92,
                      np.maximum((pixels+.055)/1.055,0.)**2.4)
    luma = np.maximum(linear @ np.array([.2126,.7152,.0722],np.float32),0.)
    perceptual = np.where(luma <= .0031308,luma*12.92,1.055*np.maximum(luma,0.)**(1./2.4)-.055)
    q = np.clip(perceptual,0.,1.)
    weight = np.maximum(4.*q*(1.-q),0.)**1.5
    linear *= np.exp2(float(amount)*.012*weight)[...,None]
    pixels[...] = np.where(linear <= .0031308,linear*12.92,
                           1.055*np.maximum(linear,0.)**(1./2.4)-.055)
    return pixels
