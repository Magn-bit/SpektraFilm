"""Shared settings semantics, actual LUT interpolation and optional spectral path."""
from __future__ import annotations
from dataclasses import dataclass, asdict, replace
from functools import lru_cache
from collections import OrderedDict
from pathlib import Path
import json
import math
import os
import sys
import tempfile
import shutil
import threading

import numpy as np
from PIL import Image, ImageOps, ImageCms, ImageFilter
from desktop.compute import compress_output_gamut
from shared.film_profiles import init_film_params, print_for_stock
from shared.local_masks import MaskLayer, normalize_masks, apply_masks
from shared.color_tools import (CurveSet, ColorGrading, ChannelMixer, normalize_curves,
                                normalize_grading, normalize_channel_mixer, apply_color_tools)
from shared.hsl import HslSettings, normalize_hsl, apply_hsl
from shared.levels import (LevelsSet, normalize_levels, apply_levels, apply_hdr_tone,
                           apply_hdr_endpoints, apply_brightness,hdr_luminance_base)
from shared.geometry import Geometry, normalize_geometry, apply_geometry_image, apply_geometry_pixels, crop_box
from shared.style_luts import known_lut, lut_for_id, apply_lut as apply_author_lut
from shared.photo_formats import RAW_EXTENSIONS
from desktop.raw_source import (source_pixels, normalized_pixels, display_image,
                                resize_pixels, read_high_precision_raster, file_token, source_metadata)

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
ASSETS = ROOT / 'assets'
EXPORT_PRESETS = {
    'JPG_HIGH': dict(label='高品质 JPG', folder='高品质 JPG', suffix='jpg', edge=0, quality=100),
    'JPG_SHARE': dict(label='分享 JPG', folder='分享 JPG', suffix='jpg', edge=0, quality=85),
    'TIFF': dict(label='无损 TIFF', folder='无损 TIFF', suffix='tif', edge=0, quality=100),
    'RAW': dict(label='RAW 原片', folder='RAW 原片', suffix=None, edge=0, quality=100),
}
SRGB = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
_SPECTRAL_CONTEXTS = OrderedDict()
_SPECTRAL_CONTEXT_SIGNATURES = {}
_SPECTRAL_CONTEXTS_LOCK = threading.RLock()


def _process_spectral_cached(values, params, key, signature=None):
    from spektrafilm import Simulator
    from spektrafilm.runtime.params_builder import digest_params

    with _SPECTRAL_CONTEXTS_LOCK:
        simulator = _SPECTRAL_CONTEXTS.pop(key, None)
        if simulator is None:
            simulator = Simulator(digest_params(params))
        elif signature is None or _SPECTRAL_CONTEXT_SIGNATURES.get(key) != signature:
            simulator.update_params(digest_params(params))
        if signature is not None:
            _SPECTRAL_CONTEXT_SIGNATURES[key] = signature
        else:
            _SPECTRAL_CONTEXT_SIGNATURES.pop(key, None)
        _SPECTRAL_CONTEXTS[key] = simulator
        while len(_SPECTRAL_CONTEXTS) > 3:
            evicted, _ = _SPECTRAL_CONTEXTS.popitem(last=False)
            _SPECTRAL_CONTEXT_SIGNATURES.pop(evicted, None)
        simulator.set_output_gamut_processor(compress_output_gamut)
        return simulator.process(values)


def _process_spectral_tap_cached(values, params, key, signature, stage_cache, stage_signature):
    from spektrafilm import Simulator
    from spektrafilm.runtime.params_builder import digest_params

    with _SPECTRAL_CONTEXTS_LOCK:
        simulator = _SPECTRAL_CONTEXTS.pop(key, None)
        if simulator is None:
            simulator = Simulator(digest_params(params))
        elif _SPECTRAL_CONTEXT_SIGNATURES.get(key) != signature:
            simulator.update_params(digest_params(params))
        _SPECTRAL_CONTEXT_SIGNATURES[key] = signature
        _SPECTRAL_CONTEXTS[key] = simulator
        while len(_SPECTRAL_CONTEXTS) > 3:
            evicted, _ = _SPECTRAL_CONTEXTS.popitem(last=False)
            _SPECTRAL_CONTEXT_SIGNATURES.pop(evicted, None)

        simulator.set_output_gamut_processor(compress_output_gamut)

        cached_exposure = stage_cache.get('log_e_film')
        if stage_cache.get('signature') == stage_signature and cached_exposure is not None:
            # Updating parameters rebuilds the resize service. Entering after
            # preprocess must still restore its physical pixel scale.
            simulator.process_tap(values, inject='rgb_in', collect='rgb_pre')
            exposure = cached_exposure
        else:
            exposure = simulator.process_tap(
                values, inject='rgb_in', collect='log_e_film'
            )
            stage_cache.clear()
            stage_cache['signature'] = stage_signature
            stage_cache['log_e_film'] = exposure
        return simulator.process_tap(
            exposure, inject='log_e_film', collect='rgb_out'
        )
PARAMETER_LIMITS = {
    'exposure':(-8,8), 'temperature':(2000,10000), 'tint':(-100,100),
    'contrast':(-100,100), 'brightness':(-100,100), 'warmth':(-50,50), 'saturation':(-100,100), 'vibrance':(-100,100),
    'highlights':(-100,100), 'shadows':(-100,100), 'whites':(-100,100), 'blacks':(-100,100), 'black_point':(0,20),
    'white_point':(80,100), 'gamma':(.5,2),
    'texture':(-100,100), 'clarity':(-100,100), 'dehaze':(-100,100),
    'sharpening':(0,100), 'noise_luminance':(0,100), 'noise_color':(0,100),
    'calibration_shadow_tint':(-100,100),
    'calibration_red_hue':(-100,100), 'calibration_red_saturation':(-100,100),
    'calibration_green_hue':(-100,100), 'calibration_green_saturation':(-100,100),
    'calibration_blue_hue':(-100,100), 'calibration_blue_saturation':(-100,100),
    'grain':(0,100), 'grain_size':(.25,2.5), 'halation':(0,100), 'vignette':(0,100), 'strength':(0,100),
    'look_strength':(0,100), 'film_format_mm':(4,200), 'glare':(0,30),
    'preflash_exposure':(0,.2),
    'hdr_peak_stops':(.5,4),
    'print_exposure':(-3,3), 'print_y':(-100,100), 'print_m':(-100,100),
    'halation_scatter_amount':(0,1), 'halation_scatter_scale':(.25,4),
    'halation_spatial_scale':(.25,4), 'halation_boost_ev':(0,8),
    'halation_protect_ev':(0,8), 'dir_couplers_amount':(0,4),
    'density_curve_gamma':(.2,4), 'halation_headroom_ev':(0,8),
    'scene_latitude_highlight_knee':(-24,24), 'scene_latitude_shadow_knee':(-24,24),
    'scene_latitude_highlight_room':(0,24), 'scene_latitude_shadow_room':(0,24),
    'scene_latitude_rolloff':(1,4), 'scene_latitude_max_lift':(.25,12),
}
GRAIN_TYPES = {'classic','fine','coarse','clustered'}
FILM_FIELDS = ('stock','exposure','grain','grain_size','grain_type','halation','vignette','strength',
               'paper','film_format_mm','glare','print_exposure','print_y','print_m','geometry')

@dataclass(frozen=True)
class Settings:
    stock: str = 'kodak_portra_400'
    exposure: float = 0.0
    temperature: float = 6500.0
    tint: float = 0.0
    contrast: float = 0.0
    brightness: float = 0.0
    warmth: float = 0.0
    saturation: float = 0.0
    vibrance: float = 0.0
    highlights: float = 0.0
    shadows: float = 0.0
    whites: float = 0.0
    blacks: float = 0.0
    black_point: float = 0.0
    white_point: float = 100.0
    gamma: float = 1.0
    texture: float = 0.0
    clarity: float = 0.0
    dehaze: float = 0.0
    sharpening: float = 0.0
    noise_luminance: float = 0.0
    noise_color: float = 0.0
    calibration_shadow_tint: float = 0.0
    calibration_red_hue: float = 0.0
    calibration_red_saturation: float = 0.0
    calibration_green_hue: float = 0.0
    calibration_green_saturation: float = 0.0
    calibration_blue_hue: float = 0.0
    calibration_blue_saturation: float = 0.0
    grain: float = 18.0
    grain_size: float = 1.0
    grain_type: str = 'classic'
    halation: float = 12.0
    vignette: float = 0.0
    strength: float = 100.0
    spectral: bool = True
    film_enabled: bool = False
    paper: str = 'auto'
    film_format_mm: float = 35.0
    film_format_axis: str = 'long'
    glare: float = 0.0
    print_exposure: float = 0.0
    print_y: float = 0.0
    print_m: float = 0.0
    preflash_exposure: float = 0.0
    hdr_enabled: bool = False
    hdr_peak_stops: float = 2.0
    digital_intermediate: bool = False
    minilab_active: bool = False
    scan_film: bool = False
    extended_dynamic_range: bool = False
    print_effects: bool = True
    grain_layered: bool = True
    grain_enabled: bool = True
    halation_enabled: bool = True
    scene_curves: CurveSet = CurveSet()
    halation_scatter_amount: float | None = None
    halation_scatter_scale: float = 1.0
    halation_spatial_scale: float = 1.0
    halation_boost_ev: float = 0.0
    halation_protect_ev: float = 4.0
    antihalation_removed: bool = False
    dir_couplers_amount: float = 1.0
    density_curve_gamma: float = 1.0
    halation_headroom_ev: float = 0.0
    metering_method: str = 'balanced'
    scene_latitude_active: bool = False
    scene_latitude_norm: str = 'power'
    scene_latitude_highlight_knee: float = 2.0
    scene_latitude_highlight_room: float = 0.0
    scene_latitude_shadow_knee: float = -2.0
    scene_latitude_shadow_room: float = 0.0
    scene_latitude_rolloff: float = 2.0
    scene_latitude_max_lift: float = 4.0
    lens_correction: bool = True
    defringe: bool = True
    masks: tuple = ()
    curves: CurveSet = CurveSet()
    grading: ColorGrading = ColorGrading()
    channel_mixer: ChannelMixer = ChannelMixer()
    hsl: HslSettings = HslSettings()
    levels: LevelsSet = LevelsSet()
    geometry: Geometry = Geometry()
    look_lut: str = ''
    look_strength: float = 100.0

    @classmethod
    def from_mapping(cls, data):
        """Treat persisted edits as untrusted data, not constructor arguments."""
        if not isinstance(data, dict):
            return cls()
        valid = {}
        for key, (low, high) in PARAMETER_LIMITS.items():
            value = data.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                valid[key] = max(low, min(high, float(value)))
        if isinstance(data.get('stock'),str) and data['stock'] in {s['id'] for s in catalog()}:
            valid['stock'] = data['stock']
        if isinstance(data.get('spectral'), bool):
            valid['spectral'] = data['spectral']
        if isinstance(data.get('film_enabled'), bool):
            valid['film_enabled'] = data['film_enabled']
        if data.get('grain_type') in GRAIN_TYPES:
            valid['grain_type'] = data['grain_type']
        if isinstance(data.get('paper'), str):
            from shared.darkroom import paper_choices
            stock = valid.get('stock', cls.stock)
            choices = {item['id'] for item in paper_choices(stock)} | {'auto'}
            if data['paper'] in choices:
                valid['paper'] = data['paper']
        valid['masks'] = normalize_masks(data.get('masks', ()))
        valid['curves'] = normalize_curves(data.get('curves'))
        valid['scene_curves'] = normalize_curves(data.get('scene_curves'))
        if data.get('film_format_axis') in ('long','short'):valid['film_format_axis']=data['film_format_axis']
        valid['grading'] = normalize_grading(data.get('grading'))
        valid['channel_mixer'] = normalize_channel_mixer(data.get('channel_mixer'))
        valid['hsl'] = normalize_hsl(data.get('hsl'))
        valid['levels'] = normalize_levels(data.get('levels'))
        valid['geometry'] = normalize_geometry(data.get('geometry'))
        if isinstance(data.get('look_lut'),str) and known_lut(data['look_lut']):
            valid['look_lut'] = data['look_lut']
        if data.get('metering_method') in ('balanced','center','protect_highlights','protect_shadows'):
            valid['metering_method']=data['metering_method']
        if data.get('scene_latitude_norm') in ('power','y','max'):
            valid['scene_latitude_norm']=data['scene_latitude_norm']
        for key in ('lens_correction','defringe','antihalation_removed','scene_latitude_active','minilab_active',
                    'scan_film','extended_dynamic_range','print_effects','grain_layered','grain_enabled','halation_enabled','hdr_enabled','digital_intermediate'):
            if isinstance(data.get(key),bool): valid[key]=data[key]
        from shared.darkroom import resolve_paper
        if valid.get('minilab_active') and (valid.get('stock',cls.stock)!='kodak_portra_400' or
                resolve_paper(valid.get('stock',cls.stock),valid.get('paper','auto'))!='kodak_portra_endura'):
            valid['minilab_active']=False
        return cls(**valid)


def film_settings(value=None):
    """Canonical editor settings; retained name for existing export callers.

    Immutable settings are already validated by controller setters. Avoid
    serializing every mask point on each slider frame. Untrusted mappings
    still go through the complete bounded parser.
    """
    if isinstance(value, Settings):
        return value if value.spectral else replace(value,spectral=True)
    data=dict(value) if isinstance(value,dict) else {}
    return Settings.from_mapping(dict(data,spectral=True))


def settings_from_record(record):
    """Migrate saved scopes without resurrecting previously hidden edits."""
    if not isinstance(record,dict): return film_settings()
    raw=record.get('settings',{})
    if not isinstance(raw,dict): return film_settings()
    version=record.get('version',1)
    if isinstance(version,int) and version>=4:
        return film_settings(raw)
    # 0.4.x saved only these film fields and always rendered film enabled.
    # Earlier retired general edits must stay neutral when reopened.
    data={key:raw[key] for key in FILM_FIELDS if key in raw}
    data['geometry']=asdict(Geometry(crop=normalize_geometry(data.get('geometry')).crop)) if version==3 else {}
    return film_settings(dict(data,film_enabled=True,lens_correction=False,defringe=False))

@lru_cache(maxsize=1)
def catalog():
    return json.loads((ASSETS/'luts/manifest.json').read_text(encoding='utf-8'))['stocks']

def read_photo(path: str, max_edge: int | None = None) -> Image.Image:
    if Path(path).suffix.lower() in RAW_EXTENSIONS:
        from .raw_development import available as raw_available,read_developed_raw
        if raw_available() and os.environ.get('SPEKTRAFILM_COMPUTE','auto').lower()!='cpu':
            return read_developed_raw(path,max_edge)
        import rawpy
        with rawpy.imread(path) as raw:
            # postprocess(half_size=True) mutates LibRaw's width/height; capture
            # full source geometry before decoding a bounded preview.
            full_size = (raw.sizes.width, raw.sizes.height)
            if raw.sizes.flip in (5, 6): full_size = full_size[::-1]
            # Match Android's LibRaw development policy. LibRaw's default
            # output curve is BT.709, which is not the sRGB curve our tools
            # expect. Half-size is confined to the editing preview.
            pixels = raw.postprocess(
                use_camera_wb=True, output_color=rawpy.ColorSpace.sRGB,
                # LibRaw reconstruct modes (3+) bypass histogram brightness
                # even when no_auto_bright=False. Blend retains highlight
                # handling while permitting the intended baseline normalization.
                gamma=(2.4, 12.92), highlight_mode=rawpy.HighlightMode.Blend,
                demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,
                no_auto_bright=False, auto_bright_thr=.01,
                output_bps=16, half_size=bool(max_edge))
            image = display_image(pixels, full_size=full_size)
    else:
        precision = (read_high_precision_raster(path)
                     if Path(path).suffix.lower() in {'.tif','.tiff','.png','.heic','.heif','.avif'} else None)
        if precision is not None:
            image = display_image(precision)
            full_size = image.size
        else:
            image = _read_display_photo(path)
            full_size = image.size
    image.info['source_size'] = full_size
    image.info['_spektrafilm_source_token'] = file_token(path, full_size)
    if max_edge:
        precision = getattr(image, '_spektrafilm_source_pixels', None)
        image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        if precision is not None and precision.shape[:2] != (image.height, image.width):
            image._spektrafilm_source_pixels = resize_pixels(precision, image.size)
            image.info['_spektrafilm_source_pixels'] = image._spektrafilm_source_pixels
    return image


def _read_display_photo(path):
    if Path(path).suffix.lower() in ('.heif','.heic'):
        import pillow_heif
        pillow_heif.register_heif_opener()
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source)
        icc = source.info.get('icc_profile')
        if icc:
            try:
                import io
                image = ImageCms.profileToProfile(image.convert('RGB'), ImageCms.ImageCmsProfile(io.BytesIO(icc)), ImageCms.createProfile('sRGB'), outputMode='RGB')
            except (OSError, ValueError, ImageCms.PyCMSError):
                image = image.convert('RGB')
        else:
            image = image.convert('RGB')
        image.load()
    return image


def prepare_photo_source(image,path,settings):
    """Optical corrections use scene RGB precision and are cached by callers."""
    if not (settings.lens_correction or settings.defringe):return image,{}
    metadata=source_metadata(image)
    if metadata['source_linear'] or metadata['source_color_space']!='sRGB' or metadata.get('baseline_exposure_ev',0):
        from .native_spectral import process_editor
        values=process_editor(source_pixels(image),{},stage='pre',
            source_color_space=metadata['source_color_space'],source_linear=metadata['source_linear'],
            exposure_ev=metadata.get('baseline_exposure_ev',0),clamp_output=False)
        # Keep the natural display but attach the converted, unclipped float
        # source. The baseline is consumed exactly once before optical work.
        original=image
        metadata=dict(metadata,source_color_space='sRGB',source_linear=False,baseline_exposure_ev=0)
        image=display_image(values,full_size=image.info.get('source_size',image.size),metadata=metadata,
            token=(original.info.get('_spektrafilm_source_token',id(original)),'optical-input'),
            display_pixels=np.asarray(original,dtype=np.uint8))
    from .lens import prepare_photo
    return prepare_photo(image,path,correction=settings.lens_correction,defringe=settings.defringe)

def read_thumbnail(path: str, max_edge: int = 180) -> Image.Image:
    """Decode only a bounded filmstrip image; selected photos use read_photo()."""
    suffix=Path(path).suffix.lower()
    if suffix in ('.heif','.heic'):
        import pillow_heif
        pillow_heif.register_heif_opener()
    if suffix in RAW_EXTENSIONS:
        import rawpy
        try:
            with rawpy.RawPy() as raw:
                raw.open_file(path)
                full_size=(raw.sizes.width,raw.sizes.height)
                if raw.sizes.flip in (5,6): full_size=full_size[::-1]
                thumb=raw.extract_thumb()
                if thumb.format == rawpy.ThumbFormat.JPEG:
                    import io
                    with Image.open(io.BytesIO(thumb.data)) as source:
                        image=ImageOps.exif_transpose(source).convert('RGB')
                        image.load()
                else:
                    image=Image.fromarray(thumb.data).convert('RGB')
        except (rawpy.LibRawError, ValueError):
            image=read_photo(path,max_edge)
            full_size=image.info.get('source_size',image.size)
        image.thumbnail((max_edge,max_edge),Image.Resampling.LANCZOS)
        image.info['source_size']=full_size
        return image
    with Image.open(path) as source:
        full_size=source.size
        orientation=source.getexif().get(274,1)
        source.draft('RGB',(max_edge*2,max_edge*2))
        image=ImageOps.exif_transpose(source).convert('RGB')
        icc=source.info.get('icc_profile')
        if icc:
            try:
                import io
                image=ImageCms.profileToProfile(image,ImageCms.ImageCmsProfile(io.BytesIO(icc)),ImageCms.createProfile('sRGB'),outputMode='RGB')
            except (OSError,ValueError,ImageCms.PyCMSError): pass
        image.thumbnail((max_edge,max_edge),Image.Resampling.LANCZOS)
        image.load()
    if orientation in (5,6,7,8): full_size=full_size[::-1]
    image.info['source_size']=full_size
    return image

def photo_dimensions(path: str):
    """Read oriented dimensions without decoding photo pixels or RAW thumbnails."""
    if Path(path).suffix.lower() in ('.heif','.heic'):
        import pillow_heif
        pillow_heif.register_heif_opener()
    if Path(path).suffix.lower() in RAW_EXTENSIONS:
        import rawpy
        with rawpy.RawPy() as raw:
            # Metadata import must not unpack the sensor plane for every
            # queued file. Selected-photo development owns unpack/postprocess.
            raw.open_file(path)
            width,height=raw.sizes.width,raw.sizes.height
            if raw.sizes.flip in (5,6): width,height=height,width
            return width,height
    with Image.open(path) as source:
        width,height=source.size
        if source.getexif().get(274,1) in (5,6,7,8): width,height=height,width
        return width,height

def srgb_decode(x):
    return np.where(x <= .04045, x/12.92, ((x+.055)/1.055)**2.4)

def srgb_encode(x):
    x = np.maximum(x, 0)
    return np.where(x <= .0031308, x*12.92, 1.055*x**(1/2.4)-.055)


@lru_cache(maxsize=256)
def _color_matrix(temperature, tint, primary_adjustments):
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

    # Treat 6500 K as the neutral point for the encoded sRGB source.
    source_white = whitepoint(6500.0)
    target_white = whitepoint(temperature, tint)
    bradford = np.array([[.8951,.2664,-.1614],[-.7502,1.7135,.0367],[.0389,-.0685,1.0296]])
    scale = (bradford @ target_white)/(bradford @ source_white)
    adaptation = np.linalg.inv(bradford) @ np.diag(scale) @ bradford
    rgb_to_xyz = np.array([[.4124564,.3575761,.1804375],[.2126729,.7151522,.0721750],[.0193339,.1191920,.9503041]])
    matrix = np.linalg.inv(rgb_to_xyz) @ adaptation @ rgb_to_xyz

    # Rotate camera primaries around the neutral axis without tinting grey pixels.
    axis = np.ones(3, dtype=np.float64)/np.sqrt(3.0)
    columns = []
    for index, (hue, saturation) in enumerate(zip(primary_adjustments[::2], primary_adjustments[1::2])):
        primary = np.eye(3, dtype=np.float64)[:,index]
        neutral = np.full(3, primary.sum()/3.0)
        chroma = primary-neutral
        angle = float(hue)*.006283185307179586
        rotated = chroma*np.cos(angle) + np.cross(axis,chroma)*np.sin(angle) + axis*np.dot(axis,chroma)*(1-np.cos(angle))
        columns.append(neutral + rotated*(1+float(saturation)/100.0))
    return tuple(float(value) for value in (np.column_stack(columns) @ matrix).reshape(-1))


def _prepare_source(pixels, settings):
    adjustments = (settings.calibration_red_hue, settings.calibration_red_saturation,
                  settings.calibration_green_hue, settings.calibration_green_saturation,
                  settings.calibration_blue_hue, settings.calibration_blue_saturation)
    if settings.temperature == 6500 and settings.tint == 0 and not any(adjustments):
        return pixels
    matrix = np.asarray(_color_matrix(settings.temperature, settings.tint, adjustments), dtype=np.float64).reshape(3,3)
    source = pixels.reshape(-1,3)
    high_precision = pixels.dtype != np.uint8
    output = np.empty(source.shape, dtype=np.float32 if high_precision else np.uint8)
    for start in range(0, len(source), 262144):
        block = srgb_decode(normalized_pixels(source[start:start+262144]).astype(np.float64))
        block = block @ matrix.T
        np.clip(block, 0, 1, out=block)
        encoded = srgb_encode(block)
        if high_precision:
            output[start:start+len(block)] = encoded
        else:
            np.clip(encoded*255.0+.5, 0, 255, out=encoded)
            output[start:start+len(block)] = encoded.astype(np.uint8)
    return output.reshape(pixels.shape)

def _apply_exposure_pixels(pixels, exposure):
    if pixels.dtype != np.uint8:
        values = normalized_pixels(pixels)
        return values if exposure == 0 else np.clip(srgb_encode(srgb_decode(values) * 2**exposure), 0, 1)
    if exposure == 0:
        return pixels
    curve=srgb_encode(srgb_decode(np.arange(256,dtype=np.float32)/255)*2**exposure)
    np.clip(curve*255+.5,0,255,out=curve)
    return curve[pixels].astype(np.uint8)

@lru_cache(maxsize=16)
def load_lut(stock: str):
    manifest = json.loads((ASSETS/'luts/manifest.json').read_text(encoding='utf-8'))
    entry = next(s for s in manifest['stocks'] if s['id'] == stock)
    n = manifest['size']
    return np.fromfile(ASSETS/'luts'/entry['file'], dtype='<f4').reshape(n,n,n,3)

def apply_lut(rgb, lut, chunk_pixels=65536):
    """Float32 trilinear interpolation with bounded temporary allocations."""
    rgb = np.asarray(rgb, dtype=np.float32)
    lut = np.asarray(lut, dtype=np.float32)
    if rgb.shape[-1:] != (3,) or lut.ndim != 4 or lut.shape[3] != 3:
        raise ValueError('RGB pixels and an RGB cube are required.')
    n = lut.shape[0]
    if n < 2 or lut.shape[:3] != (n,n,n) or chunk_pixels < 1:
        raise ValueError('Invalid LUT dimensions or chunk size.')
    pixels = rgb.reshape(-1,3)
    output = np.empty(pixels.shape, dtype=np.float32)
    for start in range(0,len(pixels),chunk_pixels):
        pos = np.clip(pixels[start:start+chunk_pixels],0,1)*(n-1)
        lo = np.minimum(pos.astype(np.int32),n-2)
        f = pos-lo.astype(np.float32)
        r,g,b = [lo[:,c] for c in range(3)]
        fr,fg,fb = [f[:,c,None] for c in range(3)]
        a = lut[b,g,r]*(1-fr)+lut[b,g,r+1]*fr
        c = lut[b,g+1,r]*(1-fr)+lut[b,g+1,r+1]*fr
        d = lut[b+1,g,r]*(1-fr)+lut[b+1,g,r+1]*fr
        e = lut[b+1,g+1,r]*(1-fr)+lut[b+1,g+1,r+1]*fr
        output[start:start+chunk_pixels] = (a*(1-fg)+c*fg)*(1-fb)+(d*(1-fg)+e*fg)*fb
    return output.reshape(rgb.shape)

def _spectral(rgb, s, preview=False, stage_cache=None, source_token=None,output_color_space='sRGB',digital_intermediate=False):
    # The native renderer executes the whole spectral model, never an export
    # LUT. Explicit CPU mode remains available for compatibility/reference.
    if sys.platform == 'win32' and os.environ.get('SPEKTRAFILM_COMPUTE', 'auto').lower() != 'cpu':
        try:
            from desktop import native_spectral
        except ImportError:
            native_spectral = None
        if native_spectral is not None and native_spectral.available():
            return native_spectral.render_spectral(rgb, s,
                    preview=preview,source_token=source_token,output_color_space=output_color_space,
                    digital_intermediate=digital_intermediate)
    sys.path.insert(0, str(ROOT/'vendor'))
    from spektrafilm import init_params
    values=np.asarray(rgb)
    if values.dtype==np.uint8:
        values=values.astype(np.float64)
        values/=255
    elif values.dtype == np.uint16:
        values=values.astype(np.float64)/65535
    else:
        values=values.astype(np.float64,copy=False)
    key=(s.stock,print_for_stock(s.stock,s.paper))
    signature=(s.exposure,s.grain,s.grain_size,s.grain_type,s.halation,bool(preview),rgb.shape[:2],
               s.film_format_mm,s.glare,s.print_exposure,s.print_y,s.print_m,
               s.scan_film,s.extended_dynamic_range,s.print_effects,s.grain_layered,s.grain_enabled,s.halation_enabled)
    with _SPECTRAL_CONTEXTS_LOCK:
        simulator=_SPECTRAL_CONTEXTS.get(key)
        if (simulator is not None and _SPECTRAL_CONTEXT_SIGNATURES.get(key)==signature
                and not (preview and stage_cache is not None)):
            _SPECTRAL_CONTEXTS.move_to_end(key)
            simulator.set_output_gamut_processor(compress_output_gamut)
            developed=simulator.process(values)
        else:
            developed=None
    if developed is None:
        p = init_film_params(s.stock, s.paper)
        p.io.input_color_space='sRGB'
        p.io.input_cctf_decoding=True
        p.io.scan_film=p.film.is_positive or s.scan_film
        if s.extended_dynamic_range and not p.io.scan_film:
            raise ValueError('相纸扩展范围需要原生光谱引擎')
        p.camera.auto_exposure=False
        p.camera.exposure_compensation_ev=s.exposure
        p.camera.film_format_mm=s.film_format_mm
        p.enlarger.print_exposure=2**s.print_exposure
        # Product filter sliders span +/-60 CC, matching the native bridge's
        # normalised shift * filter_shift_scale=60 contract.
        p.enlarger.y_filter_shift=s.print_y*.6
        p.enlarger.m_filter_shift=s.print_m*.6
        p.print_render.glare.active=s.glare>0 and s.print_effects
        p.print_render.glare.percent=s.glare
        p.settings.use_enlarger_lut=True
        p.settings.use_scanner_lut=True
        # The caller already supplies a bounded proxy. Upstream preview_mode
        # disables grain and DIR diffusion, so it cannot represent the user's
        # actual grain controls. Keep the full model at the proxy's pixel pitch.
        p.settings.preview_mode=False
        p.settings.preview_max_size=max(rgb.shape[:2])
        p.film_render.grain.active=s.grain_enabled and s.grain>0
        p.film_render.grain.sublayers_active=s.grain_layered
        p.enlarger.preflash_exposure=s.preflash_exposure if s.print_effects else 0.
        from shared.grain_texture import PROFILES
        texture,area_scale,pitch_um=PROFILES[s.grain_type]
        p.film_render.grain.texture=texture
        p.film_render.grain.texture_scale_um=pitch_um*s.grain_size
        p.film_render.grain.amount=s.grain/50
        p.film_render.grain.particle_area_um2=.8*s.grain_size**2*area_scale
        p.film_render.grain.uniformity=(.992,.992,.992)
        p.film_render.grain.blur=0
        p.film_render.grain.blur_dye_clouds_um=0
        p.film_render.halation.active=s.halation_enabled and s.halation>0
        p.film_render.halation.halation_amount=s.halation/25
        p.film_render.halation.scatter_amount=s.halation/25
        if preview and stage_cache is not None:
            stage_signature=(key,s.exposure,s.halation,s.halation_enabled,s.film_format_mm,bool(preview),rgb.shape[:2],
                s.temperature,s.tint,
                s.calibration_red_hue,s.calibration_red_saturation,
                s.calibration_green_hue,s.calibration_green_saturation,
                s.calibration_blue_hue,s.calibration_blue_saturation)
            developed=_process_spectral_tap_cached(
                values,p,key,signature,stage_cache,stage_signature
            )
        else:
            developed=_process_spectral_cached(values,p,key,signature)
    np.clip(developed,0,1,out=developed)
    return developed.astype(np.float32,copy=False)

def render(image: Image.Image, s: Settings, *, preview=False, high_precision=False) -> Image.Image:
    pixels=render_pixels(image,s,preview=preview)
    # Display/8-bit encoders need one RGB8 frame, but not several full-size
    # floating-point temporaries for clip, multiply, round and conversion.
    display=np.empty(pixels.shape,dtype=np.uint8)
    for top in range(0,pixels.shape[0],128):
        display[top:top+128]=np.rint(np.clip(pixels[top:top+128],0,1)*255).astype(np.uint8)
    result=Image.fromarray(display)
    if high_precision:
        result._spektrafilm_render_pixels=pixels
    return result


def render_pixels(image: Image.Image, s: Settings, *, preview=False,output_color_space='sRGB',preserve_headroom=False):
    """Process source precision; return encoded sRGB float32 before encoding."""
    if image.mode != 'RGB': image=image.convert('RGB')
    pixels=source_pixels(image)
    # Both no-film and spectral development use the same GPU editor. Source
    # RGB remains immutable; output stays floating point until its encoder.
    from . import native_spectral
    if os.environ.get('SPEKTRAFILM_COMPUTE','auto').lower()!='cpu' and native_spectral.available():
        full_size=tuple(image.info.get('source_size',image.size))
        coordinate=dict(source_size=full_size,pixel_scale=(full_size[0]/image.width,full_size[1]/image.height))
        info=source_metadata(image)
        metadata=dict(source_color_space=info['source_color_space'],source_linear=bool(info['source_linear']))
        baseline=float(info.get('baseline_exposure_ev',0))
        # A standard-display preview still needs unclipped film/editor values
        # until its last display quantisation. It can return encoded sRGB
        # directly instead of making a redundant ProPhoto -> sRGB round trip.
        wide=output_color_space!='sRGB' or preserve_headroom
        if not s.film_enabled or s.strength<=0:
            cache=getattr(image,'_spektrafilm_preview_cache',None)
            if cache is None:
                out=native_spectral.process_editor(pixels,s,stage='all',exposure_ev=baseline+s.exposure,
                    clamp_output=not wide,**coordinate,**metadata)
            else:
                fields=native_spectral._PRE_EDITOR_FIELDS
                pre_key=(tuple(getattr(s,name) for name in fields),baseline+s.exposure,
                         info['source_color_space'],bool(info['source_linear']))
                saved=getattr(image,'_spektrafilm_prepared_editor',None)
                if saved is not None and saved[0]==pre_key:prepared=saved[1]
                else:
                    prepared=native_spectral.process_editor(pixels,s,stage='pre',exposure_ev=baseline+s.exposure,
                        clamp_output=False,**coordinate,**metadata)
                    image._spektrafilm_prepared_editor=(pre_key,prepared)
                tone_base=None
                if s.highlights or s.shadows:
                    tone_key=('no-film',pre_key,s.contrast,s.warmth,s.saturation,s.vibrance)
                    saved=getattr(image,'_spektrafilm_hdr_base',None)
                    if saved is not None and saved[0]==tone_key:tone_base=saved[1]
                    else:
                        tone_base=hdr_luminance_base(prepared,coordinate['pixel_scale'],contrast=s.contrast,
                            warmth=s.warmth,saturation=s.saturation,vibrance=s.vibrance)
                        image._spektrafilm_hdr_base=(tone_key,tone_base)
                out=native_spectral.process_editor(prepared,s,stage='post',tone_base=tone_base,
                    clamp_output=not wide,**coordinate)
        else:
            from shared.darkroom import BLACK_AND_WHITE, scans_directly
            di=bool(s.digital_intermediate and s.stock not in BLACK_AND_WHITE and not scans_directly(s.stock))
            adjustments=(s.temperature,s.tint,s.calibration_red_hue,s.calibration_red_saturation,
                         s.calibration_green_hue,s.calibration_green_saturation,
                         s.calibration_blue_hue,s.calibration_blue_saturation,
                         s.sharpening,s.noise_luminance,s.noise_color)
            cache=getattr(image,'_spektrafilm_preview_cache',None)
            prepared=None
            def prepare():
                nonlocal prepared
                if prepared is None:
                    pre_key=(adjustments,baseline,info['source_color_space'],bool(info['source_linear']))
                    saved=getattr(image,'_spektrafilm_prepared_editor',None) if cache is not None else None
                    if saved is not None and saved[0] == pre_key:
                        prepared=saved[1]
                    else:
                        prepared=native_spectral.process_editor(pixels,s,stage='pre',exposure_ev=baseline,**coordinate,**metadata)
                        if cache is not None:image._spektrafilm_prepared_editor=(pre_key,prepared)
                return prepared
            optical=tuple(getattr(s,key) for key in ('halation_scatter_amount','halation_scatter_scale',
                'halation_spatial_scale','halation_boost_ev','halation_protect_ev','antihalation_removed',
                'dir_couplers_amount','density_curve_gamma','halation_headroom_ev'))
            latitude=tuple(getattr(s,key) for key in ('scene_latitude_active','scene_latitude_norm',
                'scene_latitude_highlight_knee','scene_latitude_highlight_room','scene_latitude_shadow_knee',
                'scene_latitude_shadow_room','scene_latitude_rolloff','scene_latitude_max_lift'))
            key=(s.stock,s.paper,s.exposure,s.halation,s.grain,s.grain_size,s.grain_type,
                 s.film_format_mm,s.film_format_axis,s.glare,s.print_exposure,s.print_y,s.print_m,
                 s.preflash_exposure,s.minilab_active,s.scene_curves,adjustments,optical,latitude,bool(wide),
                 s.scan_film,s.extended_dynamic_range,s.print_effects,s.grain_layered,s.grain_enabled,s.halation_enabled,
                 di,bool(s.hdr_enabled))
            if cache is not None and key in cache:
                out=cache[key].copy()
            else:
                out=_spectral(prepare(),s,preview=preview,
                    source_token=(image.info.get('_spektrafilm_source_token',id(image)),image.size,adjustments),
                    output_color_space='ProPhoto RGB' if wide or di else 'sRGB',digital_intermediate=di)
                if di:
                    from .digital_intermediate import view_codes
                    out=view_codes(out)
                if wide or di:
                    out=native_spectral.process_editor(out,{},stage='pre',source_color_space='ProPhoto RGB',
                        clamp_output=False,out=out)
                if cache is not None:cache.clear();cache[key]=out.copy()
            if s.strength<100:
                base=native_spectral.process_editor(prepare(),replace(s,temperature=6500,tint=0,
                    calibration_red_hue=0,calibration_red_saturation=0,
                    calibration_green_hue=0,calibration_green_saturation=0,
                    calibration_blue_hue=0,calibration_blue_saturation=0,
                    sharpening=0,noise_luminance=0,noise_color=0),stage='pre',exposure_ev=s.exposure,**coordinate)
                for top in range(0,image.height,128):
                    out[top:top+128]=(out[top:top+128]-base[top:top+128])*(s.strength/100)+base[top:top+128]
            tone_base=None
            if s.highlights or s.shadows:
                tone_key=(key,s.strength,s.contrast,s.warmth,s.saturation,s.vibrance)
                saved=getattr(image,'_spektrafilm_hdr_base',None) if cache is not None else None
                if saved is not None and saved[0]==tone_key:
                    tone_base=saved[1]
                elif cache is not None:
                    tone_base=hdr_luminance_base(out,coordinate['pixel_scale'],contrast=s.contrast,
                        warmth=s.warmth,saturation=s.saturation,vibrance=s.vibrance)
                    image._spektrafilm_hdr_base=(tone_key,tone_base)
            out=native_spectral.process_editor(out,s,stage='post',out=out,clamp_output=not wide,
                tone_base=tone_base,**coordinate)
        if s.look_lut:
            look=lut_for_id(s.look_lut)
            for top in range(0,image.height,128):apply_author_lut(out[top:top+128],look,strength=s.look_strength/100)
        out=apply_geometry_pixels(out,s.geometry)
        if output_color_space!='sRGB':
            from shared.color_management import convert_pixels
            out=convert_pixels(out,'sRGB',output_color_space,out=out)
        return out
    if s.digital_intermediate:raise ValueError('Cineon DI 需要原生光谱引擎')
    if output_color_space!='sRGB':raise ValueError('宽色域输出需要原生编辑引擎')
    prepared=_prepare_source(pixels,s)
    apply_film=s.film_enabled and s.strength>0
    if not apply_film:
        base=_apply_exposure_pixels(prepared,s.exposure)
        return _finish_render(pixels,normalized_pixels(base),s,as_pixels=True)
    preview_cache=getattr(image,'_spektrafilm_preview_cache',None)
    cache_key=(s.spectral,s.stock,s.paper,s.exposure,s.temperature,s.tint,s.halation,
               s.grain,s.grain_size,s.grain_type,bool(preview),
               s.calibration_red_hue,s.calibration_red_saturation,
               s.calibration_green_hue,s.calibration_green_saturation,
               s.calibration_blue_hue,s.calibration_blue_saturation,
               s.film_format_mm,s.glare,s.print_exposure,s.print_y,s.print_m,
               s.scan_film,s.extended_dynamic_range,s.print_effects,s.grain_layered,s.grain_enabled,s.halation_enabled)
    if preview_cache is not None and cache_key in preview_cache:
        out=preview_cache[cache_key].copy()
    elif s.spectral:
        stage_cache=None
        if preview and max(image.size)<=2560:
            stage_cache=getattr(image,'_spektrafilm_spectral_stage_cache',None)
            if stage_cache is None:
                stage_cache={}
                image._spektrafilm_spectral_stage_cache=stage_cache
        out=_spectral(prepared,s,preview=preview,stage_cache=stage_cache,
                      source_token=(image.info.get('_spektrafilm_source_token',id(image)),image.size,
                                    s.temperature,s.tint,s.calibration_red_hue,s.calibration_red_saturation,
                                    s.calibration_green_hue,s.calibration_green_saturation,
                                    s.calibration_blue_hue,s.calibration_blue_saturation))
        if preview_cache is not None:
            preview_cache.clear()
            preview_cache[cache_key]=out.copy()
    else:
        lut=load_lut(s.stock)
        out=np.empty(pixels.shape,dtype=np.float32)
        flat=out.reshape(-1,3)
        source=prepared.reshape(-1,3)
        chunk=65536
        # Every input channel is an eight-bit integer. Compute its exact
        # transfer/exposure curve once instead of repeating powers per pixel.
        exposure_curve=srgb_encode(srgb_decode(np.arange(256,dtype=np.float32)/255)*2**s.exposure)
        for start in range(0,len(source),chunk):
            values=source[start:start+chunk]
            exposed=(exposure_curve[values] if values.dtype==np.uint8 else
                     srgb_encode(srgb_decode(normalized_pixels(values))*2**s.exposure))
            flat[start:start+chunk]=apply_lut(exposed,lut)
        _halation(out,image.width,s)
        if preview_cache is not None:
            preview_cache.clear()
            preview_cache[cache_key]=out.copy()
    if s.strength<100:
        base=normalized_pixels(_apply_exposure_pixels(prepared,s.exposure))
        out-=base
        out*=s.strength/100
        out+=base
    return _finish_render(pixels,out,s,as_pixels=True)

def _halation(out,width,s):
    from scipy.ndimage import gaussian_filter
    if s.halation_enabled and s.halation>0:
        sigma=max(width/450,1.2)
        for channel,gain in enumerate((.32,.09,.025)):
            bright=np.maximum(out[...,channel]-.72,0)
            halo=gaussian_filter(bright,sigma)
            out[...,channel]+=halo*(gain*s.halation/25)

def _grain_noise_chunk(start, stop, width, grain_size, grain_type='classic', pixel_size_um=4.):
    from shared.grain_texture import noise_chunk
    return noise_chunk(start,stop,width,grain_size,grain_type,pixel_size_um)

@lru_cache(maxsize=20)
def _interactive_filter(stock):
    # Pillow's native C interpolator keeps interaction outside Python loops.
    # Eight-bit intermediate rounding is confined to this labelled fast path.
    table=load_lut(stock)
    return ImageFilter.Color3DLUT(table.shape[0],table.reshape(-1).tolist(),channels=3)

def render_interactive(image: Image.Image,s: Settings) -> Image.Image:
    if image.mode!='RGB': image=image.convert('RGB')
    pixels=np.asarray(image,dtype=np.uint8)
    source_pixels=_prepare_source(pixels,s)
    if not s.film_enabled or s.strength<=0:
        base=_apply_exposure_pixels(source_pixels,s.exposure)
        return _finish_render(pixels,base.astype(np.float32)/255,s)
    source=Image.fromarray(source_pixels) if source_pixels is not pixels else image
    if s.exposure:
        curve=np.clip(srgb_encode(srgb_decode(np.arange(256,dtype=np.float32)/255)*2**s.exposure),0,1)
        source=source.point(np.rint(curve*255).astype(np.uint8).tolist()*3)
    output=source.filter(_interactive_filter(s.stock))
    out=np.asarray(output,dtype=np.float32)/255
    _halation(out,image.width,s)
    if s.strength<100:
        base=_apply_exposure_pixels(source_pixels,s.exposure).astype(np.float32)/255
        out-=base
        out*=s.strength/100
        out+=base
    return _finish_render(pixels,out,s)

def _finish_render(pixels,out,s,*,as_pixels=False):
    look=lut_for_id(s.look_lut) if s.look_lut else None
    height,width=pixels.shape[:2]
    chunk=max(width,(65536//width)*width)
    if as_pixels:
        # A freshly rendered float frame can be finished in place. A source
        # frame (film disabled) remains immutable for later edits/cache reuse.
        if out.dtype!=np.float32 or not out.flags.c_contiguous or np.shares_memory(out,pixels):
            out=np.array(out,dtype=np.float32,copy=True,order='C')
        output=out
    else:
        output=np.empty(pixels.shape,dtype=np.uint8)
    flat=out.reshape(-1,3)
    target=output.reshape(-1,3)
    hdr_base=(hdr_luminance_base(out,contrast=s.contrast,warmth=s.warmth,
                saturation=s.saturation,vibrance=s.vibrance).reshape(-1)
              if s.highlights or s.shadows else None)
    weights=np.array([.2126,.7152,.0722],dtype=np.float32)
    warmth=np.array([1+s.warmth*.0025,1,1-s.warmth*.0025],dtype=np.float32)
    for start in range(0,len(flat),chunk):
        stop=min(start+chunk,len(flat))
        block=flat[start:stop]
        if s.film_enabled and s.strength>0 and not s.spectral and s.grain_enabled and s.grain>0:
            noise=_grain_noise_chunk(start,stop,width,s.grain_size,s.grain_type,
                                    s.film_format_mm*1000/max(width,height))[:,None]
            grain_scale={'classic':1.0,'fine':.65,'coarse':1.45,'clustered':1.16}[s.grain_type]
            block+=noise*(s.grain/100)*.055*grain_scale*(s.strength/100)*np.sqrt(np.clip(block,.01,1))
        if s.contrast:
            block-=.5;block*=1+s.contrast/100;block+=.5
        if s.warmth: block*=warmth
        if s.saturation:
            lum=np.sum(block*weights,axis=-1,keepdims=True)
            block[:]=lum+(block-lum)*(1+s.saturation/100)
        if s.vibrance:
            maximum=np.max(block,axis=-1,keepdims=True)
            minimum=np.min(block,axis=-1,keepdims=True)
            chroma=np.clip(maximum-minimum,0,1)
            factor=1+(s.vibrance/100)*(1-chroma)
            lum=np.sum(block*weights,axis=-1,keepdims=True)
            block[:]=lum+(block-lum)*factor
        apply_hdr_tone(block,s.highlights,s.shadows,
            detail_base=hdr_base[start:stop] if hdr_base is not None else None)
        if s.black_point or s.white_point!=100 or s.gamma!=1:
            linear=srgb_decode(np.maximum(block,0))
            lower=s.black_point/100*.12
            upper=1-(100-s.white_point)/100*.12
            linear=np.clip((linear-lower)/max(.05,upper-lower),0,1)
            if s.gamma!=1: np.power(linear,1/s.gamma,out=linear)
            block[:]=srgb_encode(linear)
        apply_brightness(block,s.brightness)
        apply_hdr_endpoints(block,s.whites,s.blacks)
        apply_levels(block,s.levels)
        if s.vignette:
            positions=np.arange(start,stop)
            y=(positions//width).astype(np.float32)*(2/max(1,height-1))-1
            x=(positions%width).astype(np.float32)*(2/max(1,width-1))-1
            block*=1-np.clip((x*x+y*y)*.4,0,.8)[:,None]*(s.vignette/100)
        apply_author_lut(block,look,strength=s.look_strength/100)
        apply_hsl(block.reshape(-1,width,3),s.hsl)
        apply_color_tools(block.reshape(-1,width,3),s.curves,s.grading,s.channel_mixer)
        if s.masks:
            apply_masks(block.reshape(-1,width,3),s.masks,width,height,0,start//width,clamp_output=False)
        np.clip(block,0,1,out=block)
        if as_pixels:
            target[start:stop]=block
        else:
            block*=255;block+=.5
            target[start:stop]=block.astype(np.uint8)
    # Develop the whole source first so grain size and optical effects keep
    # their source-film scale. Crop without resampling at the final boundary.
    output=apply_geometry_pixels(output,s.geometry)
    return output if as_pixels else Image.fromarray(output)

def _publish_export(destination: Path, encode, *, postprocess=None):
    if destination.exists():
        raise FileExistsError('目标文件已存在，请选择一个新文件名。')
    fd,temporary=tempfile.mkstemp(prefix='.spektrafilm-',suffix='.tmp',dir=destination.parent)
    try:
        with os.fdopen(fd,'wb') as target:
            result=encode(target)
            target.flush()
            os.fsync(target.fileno())
        if postprocess is not None:postprocess(Path(temporary),result)
        if os.name=='nt':
            os.rename(temporary,destination)
        else:
            os.link(temporary,destination)
        return result
    finally:
        Path(temporary).unlink(missing_ok=True)


def _tiff_strips(pixels, *, workers=None, compression_level=1, window_bytes=48*1024**2):
    """Return strip rows and an ordered, bounded lossless encoder iterator."""
    from concurrent.futures import ThreadPoolExecutor
    import zlib

    height,width=pixels.shape[:2]
    row_bytes=max(1,width*3*2)
    workers=max(1,min(4,workers or os.cpu_count() or 1))
    workers=min(workers,max(1,window_bytes//(row_bytes*4)))
    # Per job: float scratch + uint16 conversion, then compression bytes.
    # Four times the raw strip size reserves that peak plus queued output.
    rows=max(1,min(128,window_bytes//(workers*4*row_bytes)))

    def encode(top):
        block=np.array(pixels[top:top+rows],dtype=np.float32,copy=True,order='C')
        np.clip(block,0,1,out=block)
        block*=65535
        np.rint(block,out=block)
        samples=block.astype(np.uint16)
        del block
        data=samples.tobytes(order='C')
        del samples
        return zlib.compress(data,compression_level)

    def strips():
        from collections import deque
        tops=iter(range(0,height,rows))
        with ThreadPoolExecutor(max_workers=workers,thread_name_prefix='tiff-strip') as executor:
            pending=deque(executor.submit(encode,top) for _,top in zip(range(workers),tops))
            while pending:
                # Do not executor.map or submit the entire image: completed
                # strips must not accumulate while tifffile writes to disk.
                yield pending.popleft().result()
                top=next(tops,None)
                if top is not None:pending.append(executor.submit(encode,top))
    return rows,strips()


def export_photo(path: str, dest: str, s: Settings, max_edge=0, quality=95):
    s=film_settings(s)
    if s.hdr_enabled:
        from .output import export_recipe
        from shared.output_recipes import OutputRecipe
        if Path(dest).suffix.lower() not in ('.jpg','.jpeg'):
            raise ValueError('HDR 增益图输出需要 JPEG 配方')
        return export_recipe(path,dest,s,OutputRecipe(format='jpeg',quality=quality,long_edge=max_edge))
    destination=Path(dest)
    fmt={'.png':'PNG','.jpg':'JPEG','.jpeg':'JPEG','.tif':'TIFF','.tiff':'TIFF'}.get(destination.suffix.lower())
    if not fmt:
        raise ValueError('请选择 PNG、JPEG 或 TIFF 格式。')
    if not isinstance(max_edge,int) or max_edge<0 or not 1<=quality<=100:
        raise ValueError('无效的输出尺寸或 JPEG 质量。')
    def encode(target):
        with read_photo(path,max_edge or None) as original:
            if s.lens_correction or s.defringe:
                original,_=prepare_photo_source(original,path,s)
            if fmt=='TIFF':
                # TIFF16 consumes float samples directly; do not build an
                # unused full-resolution RGB8 display before strip encoding.
                pixels=render_pixels(original,s)
            else:
                result=render(original,s,high_precision=True)
                pixels=getattr(result,'_spektrafilm_render_pixels',None)
                if pixels is None:
                    pixels=normalized_pixels(np.asarray(result))
            height,width=pixels.shape[:2]
            if fmt=='TIFF':
                import tifffile
                rows,strips=_tiff_strips(pixels)
                handle=tifffile.FileHandle(target,mode='wb',name='SpektraFilm.tif')
                # Bytes iterator items are precompressed strips; ndarray
                # iterator items would incorrectly be treated as full frames.
                tifffile.imwrite(handle,data=strips,shape=pixels.shape,dtype=np.uint16,
                                 photometric='rgb',compression='deflate',rowsperstrip=rows,
                                 metadata=None,iccprofile=SRGB)
            else:
                options={'quality':quality,'subsampling':0} if fmt=='JPEG' else {}
                result.save(target,format=fmt,icc_profile=SRGB,**options)
            return width,height
    return _publish_export(destination,encode)

def export_preset(path: str, dest: str, s: Settings, preset: str, *, encoded_proof=None, cancel=None):
    if preset not in EXPORT_PRESETS:
        raise ValueError('未知导出预设。')
    source,destination=Path(path),Path(dest)
    if preset=='RAW':
        if source.suffix.lower() not in RAW_EXTENSIONS:
            raise ValueError('RAW 原片仅适用于导入的相机 RAW 文件；不能将普通图片转换为 RAW。')
        if destination.suffix.lower()!=source.suffix.lower():
            raise ValueError('RAW 原片必须保留原始文件扩展名。')
        def copy_original(target):
            with source.open('rb') as original:
                shutil.copyfileobj(original,target,1024*1024)
        return _publish_export(destination,copy_original)
    expected={'.jpg','.jpeg'} if preset.startswith('JPG_') else {'.tif','.tiff'}
    if destination.suffix.lower() not in expected:
        raise ValueError('文件扩展名与所选导出格式不一致。')
    option=EXPORT_PRESETS[preset]
    from .output import export_recipe
    from shared.output_recipes import OutputRecipe
    return export_recipe(path,dest,s,OutputRecipe(format='tiff' if preset=='TIFF' else 'jpeg',
        bit_depth=16 if preset=='TIFF' else 8,quality=option['quality'],long_edge=option['edge']),
        encoded_proof=encoded_proof,cancel=cancel)
