"""Android bridge into the upstream spectral filming/printing/scanning model."""
from collections import OrderedDict
from functools import lru_cache
import threading
import hashlib
import json

import numpy as np
from spektrafilm import init_params, Simulator
from film_profiles import init_film_params, print_for_stock
from spektrafilm.runtime.params_builder import digest_params
from spektrafilm.runtime.topology import Tap
from spektrafilm.model.grain import set_grain_seed_offset

_SIMULATORS = OrderedDict()
_SIMULATOR_SIGNATURES = {}
_SIMULATOR_LOCK = threading.RLock()
_MAX_SIMULATORS = 1
_PREVIEW_FILM_BASES = OrderedDict()
_PREVIEW_EXPOSURES = OrderedDict()
_MAX_PREVIEW_CACHE_PIXELS = 1048576
_MAX_PREVIEW_CACHE_BYTES = 24*1024**2


def _remember_preview(cache, key, values):
    """Retain owned, immutable preview planes within one shared byte budget."""
    if values.nbytes > _MAX_PREVIEW_CACHE_BYTES:
        return
    owned = np.array(values, dtype=np.float64, order='C', copy=True)
    owned.flags.writeable = False
    cache.pop(key, None)
    cache[key] = owned
    # One current exposure and at most two developed looks. Prefer preserving
    # the exposure tap when a large proxy leaves room for only one plane.
    while len(_PREVIEW_EXPOSURES) > 1:
        _PREVIEW_EXPOSURES.popitem(last=False)
    while len(_PREVIEW_FILM_BASES) > 2:
        _PREVIEW_FILM_BASES.popitem(last=False)
    while sum(v.nbytes for c in (_PREVIEW_EXPOSURES, _PREVIEW_FILM_BASES)
              for v in c.values()) > _MAX_PREVIEW_CACHE_BYTES:
        victim = _PREVIEW_FILM_BASES or _PREVIEW_EXPOSURES
        victim.popitem(last=False)


def _process_preview_tap(simulator, values, inject, collect):
    # The bundled Android Simulator wrapper exposes only final processing;
    # its existing pipeline supports the same named taps used by desktop.
    return simulator._pipeline.process(values, inject=inject, collect=collect)


def _make_params(stock, width, height, source_width, source_height,
                 exposure, grain, grain_size, grain_type, halation, preview_mode,
                 paper='auto',film_format_mm=35,glare=0,print_exposure=0,print_y=0,print_m=0):
    p = init_film_params(stock,paper)
    # A whole-image proxy spans the full film frame; an export tile spans only
    # its share of that frame. Do not assign a proxy the full-source pixel pitch.
    p.camera.film_format_mm = (float(film_format_mm) if preview_mode else
                              float(film_format_mm) * max(width, height) / max(source_width, source_height))
    p.io.input_color_space = 'sRGB'
    p.io.input_cctf_decoding = True
    p.io.scan_film = p.film.is_positive
    p.camera.auto_exposure = False
    p.camera.exposure_compensation_ev = float(exposure)
    p.settings.use_enlarger_lut = True
    p.settings.use_scanner_lut = True
    # Input is already a bounded proxy. The upstream fast-preview preset turns
    # grain off entirely and would hide changes to these controls.
    p.settings.preview_mode = False
    p.settings.preview_max_size = max(width, height)
    p.film_render.grain.active = grain>0
    grain_profiles = {'classic':(1.0,.97,.65,1.0), 'fine':(.42,.99,.32,.45),
                      'coarse':(2.35,.95,.95,1.25), 'clustered':(1.45,.88,.72,1.8)}
    particle_scale, uniformity, blur, cloud_blur = grain_profiles.get(str(grain_type), grain_profiles['classic'])
    p.film_render.grain.particle_area_um2 = .2*(float(grain)*4)**2*float(grain_size)**2*particle_scale
    p.film_render.grain.uniformity = (uniformity, uniformity, uniformity)
    p.film_render.grain.blur = blur
    p.film_render.grain.blur_dye_clouds_um = cloud_blur
    p.film_render.halation.active = halation>0
    p.film_render.halation.halation_amount = float(halation)*4
    p.film_render.halation.scatter_amount = float(halation)*4
    p.print_render.glare.active = float(glare)>0
    p.print_render.glare.percent = float(glare)
    p.enlarger.print_exposure = 2.**float(print_exposure)
    p.enlarger.y_filter_shift = float(print_y)*.6
    p.enlarger.m_filter_shift = float(print_m)*.6
    return digest_params(p)


@lru_cache(maxsize=256)
def _color_matrix(temperature, tint, primaries):
    def whitepoint(kelvin, green_magenta=0.0):
        t = min(10000.0, max(2000.0, float(kelvin)))
        x = (-3.0258469e9/t**3 + 2.1070379e6/t**2 + .2226347e3/t + .240390) if t > 4000 else (-.2661239e9/t**3 - .2343580e6/t**2 + .8776956e3/t + .179910)
        if t <= 2222:
            y = -1.1063814*x**3 - 1.34811020*x**2 + 2.18555832*x - .20219683
        elif t <= 4000:
            y = -.9549476*x**3 - 1.37418593*x**2 + 2.09137015*x - .16748867
        else:
            y = 3.0817580*x**3 - 5.87338670*x**2 + 3.75112997*x - .37001483
        y = min(.36, max(.30, y + float(green_magenta)*.000045))
        return np.array([x/y, 1.0, (1-x-y)/y], dtype=np.float64)

    source_white = whitepoint(6500.0)
    target_white = whitepoint(temperature, tint)
    bradford = np.array([[.8951,.2664,-.1614],[-.7502,1.7135,.0367],[.0389,-.0685,1.0296]])
    scale = (bradford @ target_white)/(bradford @ source_white)
    adaptation = np.linalg.inv(bradford) @ np.diag(scale) @ bradford
    rgb_to_xyz = np.array([[.4124564,.3575761,.1804375],[.2126729,.7151522,.0721750],[.0193339,.1191920,.9503041]])
    matrix = np.linalg.inv(rgb_to_xyz) @ adaptation @ rgb_to_xyz
    axis = np.ones(3, dtype=np.float64)/np.sqrt(3.0)
    columns = []
    for index, (hue, saturation) in enumerate(zip(primaries[::2], primaries[1::2])):
        primary = np.eye(3, dtype=np.float64)[:,index]
        neutral = np.full(3, primary.sum()/3.0)
        chroma = primary-neutral
        angle = float(hue)*.006283185307179586
        rotated = chroma*np.cos(angle) + np.cross(axis,chroma)*np.sin(angle) + axis*np.dot(axis,chroma)*(1-np.cos(angle))
        columns.append(neutral + rotated*(1+float(saturation)/100.0))
    return (np.column_stack(columns) @ matrix).astype(np.float64)


def _prepare_rgb(rgb, temperature, tint, primaries):
    if float(temperature) == 6500 and float(tint) == 0 and not any(primaries):
        return rgb
    matrix = _color_matrix(float(temperature), float(tint), tuple(float(x) for x in primaries))
    flat = rgb.reshape(-1, 3)
    for start in range(0, len(flat), 65536):
        block = flat[start:start+65536]
        linear = np.where(block <= .04045, block/12.92, ((block+.055)/1.055)**2.4)
        linear = linear @ matrix.T
        np.clip(linear, 0, 1, out=linear)
        encoded = np.where(linear <= .0031308, linear*12.92, 1.055*np.maximum(linear,0)**(1/2.4)-.055)
        block[:] = np.clip(encoded, 0, 1)
    return rgb


def _grain_noise_chunk(start, stop, width, grain_size):
    positions = np.arange(start, stop, dtype=np.uint32)
    x = (positions % np.uint32(width)).astype(np.float32)
    y = (positions // np.uint32(width)).astype(np.float32)
    scale = max(1.0, float(grain_size))
    gx = x/scale; gy = y/scale
    x0 = np.floor(gx).astype(np.uint32); y0 = np.floor(gy).astype(np.uint32)
    fx = (gx-x0).astype(np.float32); fy = (gy-y0).astype(np.float32)
    def noise(ix, iy):
        value = ix*np.uint32(374761393)+iy*np.uint32(668265263)+np.uint32(1442695041)
        value = (value^(value>>np.uint32(13)))*np.uint32(1274126177)
        value ^= value>>np.uint32(16)
        return (value&np.uint32(65535)).astype(np.float32)/32767.5-1.0
    top = noise(x0,y0)*(1-fx)+noise(x0+np.uint32(1),y0)*fx
    bottom = noise(x0,y0+np.uint32(1))*(1-fx)+noise(x0+np.uint32(1),y0+np.uint32(1))*fx
    return (top*(1-fy)+bottom*fy)*np.sqrt(min(1.0,max(.25,float(grain_size))))


def _apply_exposure(rgb, exposure):
    if float(exposure)==0:
        return rgb
    flat=rgb.reshape(-1,3)
    gain=2.0**float(exposure)
    for start in range(0,len(flat),65536):
        block=flat[start:start+65536]
        linear=np.where(block<=.04045,block/12.92,((block+.055)/1.055)**2.4)
        linear*=gain
        block[:]=np.clip(np.where(linear<=.0031308,linear*12.92,
                                  1.055*np.maximum(linear,0)**(1/2.4)-.055),0,1)


def _apply_tone(rgb, contrast, warmth, saturation, highlights, shadows,
                black_point, white_point, gamma, vignette, vibrance=0):
    h, w = rgb.shape[:2]
    flat = rgb.reshape(-1, 3)
    weights = np.array([.2126,.7152,.0722], dtype=np.float64)
    warmth_gain = np.array([1+float(warmth)*.0025, 1, 1-float(warmth)*.0025], dtype=np.float64)
    for start in range(0, len(flat), 65536):
        stop = min(start+65536, len(flat))
        block = flat[start:stop]
        if contrast:
            block -= .5; block *= 1+float(contrast)/100; block += .5
        if warmth:
            block *= warmth_gain
        if saturation:
            luminance = np.sum(block*weights, axis=-1, keepdims=True)
            block[:] = luminance+(block-luminance)*(1+float(saturation)/100)
        if vibrance:
            chroma=np.clip(np.max(block,axis=-1,keepdims=True)-np.min(block,axis=-1,keepdims=True),0,1)
            factor=1+(float(vibrance)/100)*(1-chroma)
            luminance=np.sum(block*weights,axis=-1,keepdims=True)
            block[:]=luminance+(block-luminance)*factor
        if highlights or shadows or black_point or white_point != 100 or gamma != 1:
            linear = np.where(block <= .04045, block/12.92, ((block+.055)/1.055)**2.4)
            luminance = np.sum(linear*weights, axis=-1, keepdims=True)
            if shadows:
                linear += (float(shadows)/100)*.24*np.square(1-luminance)
            if highlights:
                linear += (float(highlights)/100)*.24*np.square(luminance)
            lower = float(black_point)/100*.12
            upper = 1-(100-float(white_point))/100*.12
            linear = np.clip((linear-lower)/max(.05,upper-lower),0,1)
            if gamma != 1:
                np.power(linear, 1/float(gamma), out=linear)
            block[:] = np.where(linear <= .0031308, linear*12.92, 1.055*np.maximum(linear,0)**(1/2.4)-.055)
        if vignette:
            positions = np.arange(start,stop)
            y = (positions//w).astype(np.float32)*(2/max(1,h-1))-1
            x = (positions%w).astype(np.float32)*(2/max(1,w-1))-1
            block *= 1-np.clip((x*x+y*y)*.4,0,.8)[:,None]*(float(vignette)/100)
        np.clip(block,0,1,out=block)


def _apply_color_tools(rgb, color_json):
    from color_tools import apply_color_tools, parse_color_tools
    from hsl import apply_hsl
    from style_luts import load_lut, apply_lut
    document = json.loads(color_json) if isinstance(color_json,str) and color_json else (color_json or {})
    look_path = document.get('look_lut_path','')
    if look_path:
        apply_lut(rgb, load_lut(look_path),strength=float(document.get('look_strength',100))/100)
    apply_hsl(rgb, document.get('hsl'))
    curves, grading = parse_color_tools(color_json)
    return apply_color_tools(rgb, curves, grading)


def render_argb(data, width, height, stock, exposure, grain, halation, strength,
                preview_mode=False, source_width=None, source_height=None, seed_offset=0,
                temperature=6500, tint=0, contrast=0, warmth=0, saturation=0,
                highlights=0, shadows=0, black_point=0, white_point=100, gamma=1,
                red_hue=0, red_saturation=0, green_hue=0, green_saturation=0,
                blue_hue=0, blue_saturation=0, grain_size=1, grain_type='classic', vignette=0,
                vibrance=0, film_enabled=True, masks_json='[]', origin_x=0, origin_y=0, color_json='{}'):
    # Java packs 0xAARRGGBB explicitly as little-endian Int32 (not Bitmap byte order).
    packed = np.frombuffer(data, dtype='<u4').reshape(height,width)
    rgb = np.empty((height,width,3),dtype=np.float64)
    scratch = np.empty((height,width),dtype=np.uint32)
    for channel,shift in enumerate((16,8,0)):
        np.right_shift(packed,shift,out=scratch)
        np.bitwise_and(scratch,255,out=scratch)
        np.multiply(scratch,1.0/255,out=rgb[:,:,channel])
    primaries=(red_hue,red_saturation,green_hue,green_saturation,blue_hue,blue_saturation)
    active_film=bool(film_enabled) and float(strength)>0
    if active_film:
        film_input=rgb.copy()
        _prepare_rgb(film_input,temperature,tint,primaries)
        _prepare_rgb(rgb,temperature,tint,primaries)
        _apply_exposure(rgb,exposure)
    else:
        _prepare_rgb(rgb,temperature,tint,primaries)
        _apply_exposure(rgb,exposure)
    source_width = int(source_width or width)
    source_height = int(source_height or height)
    if active_film:
        key = (stock, print_for_stock(stock))
        signature = (width, height, source_width, source_height, float(exposure),
                     float(grain), float(grain_size), str(grain_type), float(halation), bool(preview_mode))
        # Post-development curves, colour wheels and tone controls do not change
        # the spectral film stage. Keep only bounded preview intermediates;
        # exports always compute from the original source and never use these.
        preview_key = exposure_key = None
        if (preview_mode and width*height <= _MAX_PREVIEW_CACHE_PIXELS
                and int(seed_offset) == 0 and int(origin_x) == 0 and int(origin_y) == 0):
            # Hash every input byte, not a few sampled pixels or Bitmap identity.
            # Only a whole preview is eligible; full-resolution export tiles
            # never read or populate these caches, even when small enough.
            source_key=(hashlib.blake2b(data,digest_size=16).digest(),key,
                        width,height,source_width,source_height,
                        float(exposure),float(halation),float(temperature),
                        float(tint),tuple(float(v) for v in primaries))
            exposure_key=source_key
            preview_key=(source_key,signature)
        with _SIMULATOR_LOCK:
            cached = _PREVIEW_FILM_BASES.get(preview_key) if preview_key is not None else None
            simulator = _SIMULATORS.get(key)
            if simulator is None:
                simulator = Simulator(_make_params(stock,width,height,source_width,source_height,
                                                    exposure,grain,grain_size,grain_type,halation,preview_mode))
            elif _SIMULATOR_SIGNATURES.get(key) != signature:
                simulator.update_params(_make_params(stock,width,height,source_width,source_height,
                                                       exposure,grain,grain_size,grain_type,halation,preview_mode))
            _SIMULATOR_SIGNATURES[key] = signature
            _SIMULATORS.pop(key, None)
            _SIMULATORS[key] = simulator
            while len(_SIMULATORS) > _MAX_SIMULATORS:
                evicted, _ = _SIMULATORS.popitem(last=False)
                _SIMULATOR_SIGNATURES.pop(evicted, None)
            set_grain_seed_offset(int(seed_offset))
            try:
                if cached is not None:
                    developed = cached.copy()
                elif exposure_key is not None:
                    exposed = _PREVIEW_EXPOSURES.get(exposure_key)
                    if exposed is None:
                        exposed = np.asarray(_process_preview_tap(
                            simulator,film_input,Tap.RGB_IN,Tap.LOG_E_FILM),dtype=np.float64)
                        _remember_preview(_PREVIEW_EXPOSURES,exposure_key,exposed)
                    else:
                        # update_params reconstructs ResizingService. Its pixel
                        # size is initialized by preprocessing, and development
                        # (grain/coupler spatial scale) still needs that state.
                        _process_preview_tap(simulator,film_input,Tap.RGB_IN,Tap.RGB_PRE)
                        exposed = exposed.copy()
                    developed = np.asarray(_process_preview_tap(
                        simulator,exposed,Tap.LOG_E_FILM,Tap.RGB_OUT),dtype=np.float64)
                else:
                    developed = np.asarray(simulator.process(film_input),dtype=np.float64)
            finally:
                set_grain_seed_offset(0)
            if preview_key is not None and cached is None:
                _remember_preview(_PREVIEW_FILM_BASES,preview_key,developed)
        np.clip(developed,0,1,out=developed)
        np.subtract(developed,rgb,out=developed)
        np.multiply(developed,strength,out=developed)
        np.add(developed,rgb,out=developed)
    else:
        developed=rgb
    _apply_tone(developed,contrast,warmth,saturation,highlights,shadows,
                black_point,white_point,gamma,vignette,vibrance)
    _apply_color_tools(developed,color_json)
    from local_masks import apply_masks
    apply_masks(developed,masks_json,source_width,source_height,origin_x,origin_y)
    np.clip(developed,0,1,out=developed)
    np.multiply(developed,255,out=developed)
    np.rint(developed,out=developed)
    result=developed.astype(np.uint32)
    np.left_shift(result[:,:,0],16,out=result[:,:,0])
    np.left_shift(result[:,:,1],8,out=result[:,:,1])
    np.bitwise_or(result[:,:,0],result[:,:,1],out=result[:,:,0])
    np.bitwise_or(result[:,:,0],result[:,:,2],out=result[:,:,0])
    np.bitwise_or(result[:,:,0],0xff000000,out=result[:,:,0])
    return result[:,:,0].astype('<u4',copy=False).tobytes()


def render_lut_argb(data, width, height, lut_data, lut_size, exposure, grain,
                    halation, strength, origin_x=0, origin_y=0,
                    temperature=6500, tint=0, contrast=0, warmth=0, saturation=0,
                    highlights=0, shadows=0, black_point=0, white_point=100, gamma=1,
                    red_hue=0, red_saturation=0, green_hue=0, green_saturation=0,
                    blue_hue=0, blue_saturation=0, grain_size=1, grain_type='classic', vignette=0,
                    vibrance=0, film_enabled=True, masks_json='[]', source_width=0, source_height=0, color_json='{}'):
    """Vectorized approximate export path using the packaged trilinear LUT."""
    width = int(width)
    height = int(height)
    lut_size = int(lut_size)
    source = np.frombuffer(data, dtype='<u4').reshape(height, width)
    original = np.empty((height, width, 3), dtype=np.float32)
    for channel, shift in enumerate((16, 8, 0)):
        original[:, :, channel] = ((source >> shift) & 255) / 255.0
    primaries = (red_hue,red_saturation,green_hue,green_saturation,blue_hue,blue_saturation)
    _prepare_rgb(original,temperature,tint,primaries)
    _apply_exposure(original,exposure)
    if not bool(film_enabled) or float(strength)<=0:
        developed=original
        _apply_tone(developed,contrast,warmth,saturation,highlights,shadows,
                    black_point,white_point,gamma,vignette,vibrance)
        _apply_color_tools(developed,color_json)
        from local_masks import apply_masks
        apply_masks(developed,masks_json,source_width,source_height,origin_x,origin_y)
        np.clip(developed,0,1,out=developed)
        packed=np.rint(developed*255).astype(np.uint32)
        result=(packed[:,:,0]<<16)|(packed[:,:,1]<<8)|packed[:,:,2]|np.uint32(0xff000000)
        return result.astype('<u4',copy=False).tobytes()

    lut = np.frombuffer(lut_data, dtype='<f4').reshape(lut_size, lut_size, lut_size, 3)
    r,g,b=(original[:,:,i] for i in range(3))
    maximum = lut_size - 1
    rf = r * maximum
    gf = g * maximum
    bf = b * maximum
    ri = np.minimum(rf.astype(np.int32), maximum - 1)
    gi = np.minimum(gf.astype(np.int32), maximum - 1)
    bi = np.minimum(bf.astype(np.int32), maximum - 1)
    fr = rf - ri
    fg = gf - gi
    fb = bf - bi
    table = lut.reshape(-1)

    # The LUT is R-fastest, matching FilmEngine.renderInteractive's packed table layout.
    base = ((bi * lut_size + gi) * lut_size + ri) * 3
    converted = np.empty((height, width, 3), dtype=np.float32)
    for channel in range(3):
        c00 = table[base + channel] * (1 - fr) + table[base + 3 + channel] * fr
        c10 = table[base + lut_size * 3 + channel] * (1 - fr) + table[base + lut_size * 3 + 3 + channel] * fr
        c01 = table[base + lut_size * lut_size * 3 + channel] * (1 - fr) + table[base + lut_size * lut_size * 3 + 3 + channel] * fr
        c11 = table[base + lut_size * (lut_size + 1) * 3 + channel] * (1 - fr) + table[base + lut_size * (lut_size + 1) * 3 + 3 + channel] * fr
        converted[:, :, channel] = ((c00 * (1 - fg) + c10 * fg) * (1 - fb)
                                     + (c01 * (1 - fg) + c11 * fg) * fb)

    luminance = .2126 * r + .7152 * g + .0722 * b

    # Approximate halation locally; this path intentionally omits the full spatial film model.
    halo = np.maximum((luminance - .70) / .30, 0) ** 2 * float(halation)
    gain = np.asarray((.18, .055, .01), dtype=np.float32)[None, None, :]
    developed = original + (converted + halo[:, :, None] * gain - original) * float(strength)
    grain_profiles = {'classic':1.0,'fine':.68,'coarse':1.2,'clustered':1.05}
    profile_scale=grain_profiles.get(str(grain_type),1.0)
    developed_flat=developed.reshape(-1,3)
    luminance_flat=luminance.reshape(-1)
    for start in range(0,len(developed_flat),65536):
        stop=min(start+65536,len(developed_flat))
        noise=_grain_noise_chunk(start,stop,width,float(grain_size)*profile_scale)
        signal=(noise*float(grain)*.052*profile_scale
                *(.42+.58*(1-np.abs(luminance_flat[start:stop]*2-1))))
        developed_flat[start:stop]+=signal[:,None]*float(strength)
    _apply_tone(developed,contrast,warmth,saturation,highlights,shadows,
                black_point,white_point,gamma,vignette,vibrance)
    _apply_color_tools(developed,color_json)
    from local_masks import apply_masks
    apply_masks(developed,masks_json,source_width,source_height,origin_x,origin_y)
    np.clip(developed, 0, 1, out=developed)
    packed = (np.rint(developed * 255).astype(np.uint32))
    result = (packed[:, :, 0] << 16) | (packed[:, :, 1] << 8) | packed[:, :, 2] | np.uint32(0xff000000)
    return result.astype('<u4', copy=False).tobytes()


def apply_masks_argb(data, width, height, masks_json='[]', source_width=0,
                     source_height=0, origin_x=0, origin_y=0):
    """Reuse a developed preview while editing only local mask parameters."""
    from local_masks import apply_masks
    width,height=int(width),int(height)
    source=np.frombuffer(data,dtype='<u4').reshape(height,width)
    rgb=np.empty((height,width,3),dtype=np.float32)
    for channel,shift in enumerate((16,8,0)):
        rgb[:,:,channel]=((source>>shift)&255)/255.0
    apply_masks(rgb,masks_json,source_width,source_height,origin_x,origin_y)
    packed=np.rint(np.clip(rgb,0,1)*255).astype(np.uint32)
    result=(packed[:,:,0]<<16)|(packed[:,:,1]<<8)|packed[:,:,2]|np.uint32(0xff000000)
    return result.astype('<u4',copy=False).tobytes()
