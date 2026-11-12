"""In-process float32 -> Vulkan spectral model -> genuine RGBA16 bridge.

Preview proxies and final-size sources have separate identities. A session owns
its source and developed negative; print-only deltas reuse the negative. A GPU
failure is raised, never replaced here by a LUT or a reduced-resolution image.
"""
from __future__ import annotations

import atexit
from collections import OrderedDict
import ctypes as ct
from dataclasses import asdict, is_dataclass, replace
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import secrets
import shutil
import sys
import tempfile
import threading
import time
import weakref

import numpy as np


class NativeSpectralError(RuntimeError):
    pass


class _Image(ct.Structure):
    _fields_ = [('data', ct.POINTER(ct.c_float)), ('width', ct.c_uint32),
                ('height', ct.c_uint32), ('channels', ct.c_uint32)]


class _Result(ct.Structure):
    _fields_ = [('rgba16', ct.POINTER(ct.c_uint16)), ('texture', ct.c_void_p),
                ('width', ct.c_uint32), ('height', ct.c_uint32),
                ('row_stride_px', ct.c_uint32), ('elapsed_ms', ct.c_double),
                ('reprint', ct.c_int32), ('negative_was_cached', ct.c_int32),
                ('progress_id', ct.c_char * 40)]


_LOCK = threading.RLock()
_ACTIVE_LOCK = threading.Lock()
_BUFFER_LOCK = threading.Lock()
_RUNTIME = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'native' / 'engine' / 'runtime'
_VENDOR = _RUNTIME.parents[2] / 'vendor'
if _VENDOR.is_dir() and str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))
_ENGINE = None
_INITIALIZATION_ERROR = None
_LAST_RENDER = {}
_LARGE_FRAME_PIXELS = 80_000_000
_CACHE_LIMITS = {'max_entries': 2, 'source_bytes': 192 * 1024 ** 2,
                 'retained_bytes': 512 * 1024 ** 2}
_MAPPED_RESULTS = {}
# editor_process.cpp::pre_matrix and capture-side restoration are the only
# settings consumed by stage=pre. Levels/HDR/curves/masks remain post-only.
# Exposure/coordinates/source transfer belong
# to the request itself. Never traverse display curves or mask strokes here.
_PRE_EDITOR_FIELDS = ('temperature', 'tint',
    'calibration_red_hue', 'calibration_red_saturation',
    'calibration_green_hue', 'calibration_green_saturation',
    'calibration_blue_hue', 'calibration_blue_saturation',
    'sharpening', 'noise_luminance', 'noise_color')
# Texture, physical area scale and texture pitch in micrometres. Amount is
# separate: dragging strength must not also move the particle boundaries.
# Morphology changes distribution/spatial correlation, not just grain RMS.
_GRAIN = {'fine': (1, .42, 2.2), 'classic': (2, 1., 4.),
          'coarse': (3, 2.1, 6.), 'clustered': (4, 1.35, 4.5)}


def _json_bytes(values):
    return json.dumps(values, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')


@lru_cache(maxsize=1)
def _neutral_database():
    values = json.loads((_RUNTIME / 'resources' / 'neutral_print_filters.json').read_text(encoding='utf-8'))
    product = _RUNTIME / 'resources' / 'product-neutral-print-filters.json'
    if product.is_file():
        for paper, illuminants in json.loads(product.read_text(encoding='utf-8')).items():
            for light, films in illuminants.items():
                values.setdefault(paper, {}).setdefault(light, {}).update(films)
    return values


@lru_cache(maxsize=32)
def paper_supports_edr(paper):
    """Packaged material data is immutable during an application session."""
    try:
        data=json.loads((_RUNTIME/'resources/profiles'/(paper+'.json')).read_text(encoding='utf-8'))
        return bool(data.get('data',{}).get('edr_tone_map'))
    except (OSError,ValueError):
        return False


def parameters(settings):
    """The common product contract, also documented for the Android bridge."""
    from shared.darkroom import BLACK_AND_WHITE, resolve_paper, scans_directly
    from shared.film_profiles import extension_profiles
    stock = settings.stock
    paper = resolve_paper(stock, getattr(settings, 'paper', 'auto'))
    extension = extension_profiles().get(stock)
    illuminant = 'TH-KG3'
    neutral = _neutral_database().get(paper, {}).get(illuminant, {}).get(stock, [0., 65., 55.])
    if extension and paper == extension.get('paper') and extension.get('neutral_filters_cmy') is not None:
        neutral = extension['neutral_filters_cmy']
        illuminant = extension['illuminant']
    bw = stock in BLACK_AND_WHITE
    if bw:
        neutral = [0., 0., 68.]
    texture, scale, pitch_um = _GRAIN.get(settings.grain_type, _GRAIN['classic'])
    grain_area = .8 * settings.grain_size ** 2 * scale
    glare = float(getattr(settings, 'glare', 0.))
    values = {
        'film_stock': stock, 'print_stock': paper,
        'input_color_space': 'sRGB', 'input_cctf_decoding': True,
        'output_color_space': 'sRGB', 'output_cctf_encoding': True,
        'auto_exposure': False, 'exposure_baseline_ev': 0.,
        'exposure_compensation_ev': float(settings.exposure),
        'film_format_mm': float(getattr(settings, 'film_format_mm', 35.)),
        'scan_film': scans_directly(stock) or bool(settings.scan_film),
        'extended_dynamic_range': bool(settings.extended_dynamic_range and not settings.scan_film
            and not scans_directly(stock) and paper_supports_edr(paper)),
        'grain_active': settings.grain_enabled and settings.grain > 0, 'grain_sublayers_active': bool(settings.grain_layered),
        'grain_amount': float(settings.grain) / 50., 'grain_particle_area_um2': max(.000001, grain_area),
        'grain_texture': texture, 'grain_texture_scale_um': pitch_um * settings.grain_size,
        'grain_uniformity_r': .992, 'grain_uniformity_g': .992,
        'grain_uniformity_b': .992, 'grain_blur': 0., 'grain_cloud_blur_um': 0.,
        'halation_active': settings.halation > 0,
        'halation_amount': float(settings.halation / 25.),
        'halation_scatter_amount': min(1., float(settings.halation / 25.)),
        'halation_headroom_ev': 0.,
        'dir_couplers_active': not (bw or extension),
        'neutral_filters_from_database': False,
        'c_filter_neutral': float(neutral[0]), 'm_filter_neutral': float(neutral[1]),
        'y_filter_neutral': float(neutral[2]), 'enlarger_illuminant': illuminant,
        'print_exposure': 2. ** float(getattr(settings, 'print_exposure', 0.)),
        'preflash_exposure': float(getattr(settings,'preflash_exposure',0.)) if settings.print_effects else 0.,
        'minilab_active': bool(getattr(settings,'minilab_active',False)) and not settings.scan_film,
        'scene_curve': scene_curve_samples(getattr(settings,'scene_curves',None)),
        'm_filter_shift': float(getattr(settings, 'print_m', 0.)) / 100.,
        'y_filter_shift': float(getattr(settings, 'print_y', 0.)) / 100.,
        'filter_shift_scale': 60.,
        'glare_active': glare > 0. and settings.print_effects, 'glare_amount': 1., 'glare_percent': glare,
        'scanner_white_correction': False, 'scanner_black_correction': False,
    }
    # These are existing physical controls in the native model. Keeping their
    # former values when absent preserves edits made before the editor update.
    scatter = getattr(settings, 'halation_scatter_amount', None)
    if scatter is not None:
        values['halation_scatter_amount'] = float(scatter)
        values['halation_active'] = values['halation_active'] or float(scatter) > 0
    if not settings.halation_enabled:
        values['halation_active'] = False
        values['halation_scatter_amount'] = 0.
    for key, default in (('halation_scatter_scale', 1.), ('halation_spatial_scale', 1.),
                         ('halation_boost_ev', 0.), ('halation_protect_ev', 4.),
                         ('dir_couplers_amount', 1.), ('density_curve_gamma', 1.),
                         ('halation_headroom_ev', 0.)):
        values[key] = float(getattr(settings, key, default))
    values['antihalation_removed'] = bool(getattr(settings, 'antihalation_removed', False))
    values['auto_exposure_method'] = str(getattr(settings, 'metering_method', 'balanced'))
    values['scene_latitude_active'] = bool(getattr(settings, 'scene_latitude_active', False))
    values['scene_latitude_norm'] = str(getattr(settings, 'scene_latitude_norm', 'power'))
    for key, default in (('scene_latitude_highlight_knee', 2.), ('scene_latitude_highlight_room', 0.),
                         ('scene_latitude_shadow_knee', -2.), ('scene_latitude_shadow_room', 0.),
                         ('scene_latitude_rolloff', 2.), ('scene_latitude_max_lift', 4.)):
        values[key] = float(getattr(settings, key, default))
    if scans_directly(stock) and getattr(settings,'hdr_enabled',False):
        # Match the slide SDR/HDR realisation, including custom textures.
        values.update(scan_hdr_stretch=True,grain_seed=743)
    return values


@lru_cache(maxsize=32)
def scene_curve_samples(curves):
    from shared.color_tools import CurveSet, evaluate_curve
    if curves is None or curves==CurveSet():return ''
    x=np.linspace(0,1,129)
    return ','.join(format(float(value),'.8g') for channel in ('master','luma','red','green','blue')
                    for value in np.clip(evaluate_curve(curves,channel,x),0,1))


def _physical_settings(settings,pixels):
    if getattr(settings,'film_format_axis','long')!='short':return settings
    height,width=pixels.shape[:2]
    return replace(settings,film_format_mm=float(settings.film_format_mm)*max(width,height)/min(width,height),film_format_axis='long')


def _normalized(pixels):
    values = np.asarray(pixels)
    if values.dtype == np.uint8:
        result = np.ascontiguousarray(values, dtype=np.float32)
        result *= np.float32(1. / 255.)
        return result
    if values.dtype == np.uint16:
        result = np.ascontiguousarray(values, dtype=np.float32)
        result *= np.float32(1. / 65535.)
        return result
    return np.ascontiguousarray(values, dtype=np.float32)


def _close_mapped_result(mapping, filename):
    try:
        mapping.close()
    finally:
        try:
            Path(filename).unlink(missing_ok=True)
        except OSError:
            pass
        with _BUFFER_LOCK:
            _MAPPED_RESULTS.pop(filename, None)


def _mapped_result(shape,dtype=np.float32):
    needed = math.prod(shape) * np.dtype(dtype).itemsize
    folder = Path(tempfile.gettempdir())
    if shutil.disk_usage(folder).free < needed + 512 * 1024 ** 2:
        raise NativeSpectralError('临时磁盘空间不足，无法保存原尺寸高位深显影缓冲')
    handle, filename = tempfile.mkstemp(prefix='spektrafilm-render-', suffix='.f32', dir=folder)
    os.close(handle)
    try:
        output = np.memmap(filename, dtype=dtype, mode='w+', shape=shape, order='C')
    except BaseException:
        Path(filename).unlink(missing_ok=True)
        raise
    with _BUFFER_LOCK:
        _MAPPED_RESULTS[filename] = needed
    # All NumPy/memmap views retain this root in their base chain. Anchoring
    # deletion here keeps a view alive after the original result is dropped.
    weakref.finalize(output, _close_mapped_result, output._mmap, filename)
    return output


def _region_halo(settings, width, height):
    """Compose serial effects; mixture components share their widest support.

    The native IIR PSFs have infinite mathematical support. Six sigma plus
    grain/scanner context is a finite region boundary, checked against the
    whole-frame implementation. It is not described as bit-exact IIR tiling.
    """
    px_um = float(settings.film_format_mm) * 1000. / max(width, height)
    scatter = bounce = 0.
    values = parameters(settings)
    if values['halation_active']:
        if values['halation_scatter_amount'] > 0:
            scatter = 9.7 * 2.7684 * values.get('halation_scatter_scale', 1.) / px_um
        # Gaussian N=3 for ordinary films; removed-remjet base PSF is wider.
        if settings.stock == 'cinestill_800t':
            bounce = 120. * 9.448921 * math.sqrt(settings.halation / 25.) / px_um
        else:
            bounce = 65. * math.sqrt(3. * settings.halation / 25.) / px_um
        bounce *= values.get('halation_spatial_scale', 1.)
    couplers = 200. * 2.7684 / px_um if values['dir_couplers_active'] else 0.
    grain = max(float(values['grain_blur']), float(values['grain_cloud_blur_um']) *
                math.sqrt(float(values['grain_particle_area_um2']) * 3.2 * 2. / (px_um * px_um)))
    return max(16, math.ceil(6. * (scatter + bounce + couplers + grain) + 8.))


def _render_regions(engine, source, settings, values, *, core_edge=None, seed=None):
    """Bound GPU/CPU scratch while writing every source pixel to file storage."""
    height, width = source.shape[:2]
    halo = _region_halo(settings, width, height)
    # ~48MP maximum region: below the proven 61MP direct path, regardless of
    # frame size. Core never shrinks away to hide an unsupported wide PSF.
    max_edge = int(math.sqrt(48_000_000))
    core = min(core_edge or 3072, max_edge - 2 * halo)
    if core < 128:
        raise NativeSpectralError('当前片幅和空间光晕需要的邻域过大，超过有界显影内存预算；请增大片幅或降低光晕')
    seed = seed or (743 if values.get('grain_texture',0)>0 else secrets.randbelow(2147483646)+1)
    clear_sessions()
    output = _mapped_result(source.shape)
    native_ms, regions = 0., 0
    peak_region_pixels = 0
    started = time.perf_counter()
    try:
        # Boost and clipped-lamp headroom are normalized by the WHOLE frame's
        # spectral exposure maxima. Measuring per haloed region produces
        # visible bands on medium-format exports. Preserve those two global
        # reductions with a bounded exact prepass, only when they are used.
        needs_peaks = (float(values.get('halation_boost_ev', 0.)) != 0. or
                       (values.get('halation_active') and
                        float(values.get('halation_headroom_ev', 0.)) > 0. and
                        float(values.get('halation_amount', 0.)) > 0.))
        peaks, peak_prepass_ms, peak_prepass_regions = {}, 0., 0
        if needs_peaks:
            measured = time.perf_counter()
            peaks = dict(frame_exposure_peak=0., frame_boosted_peak=0.)
            # Full-width strips remain contiguous and cover every source
            # pixel once. No halo is needed before the optical operators.
            measure_rows = max(1, min(512, 4_000_000 // width))
            for top in range(0, height, measure_rows):
                tile = _normalized(source[top:top+measure_rows])
                region = dict(values, striped=False, tile_full_width=width, tile_full_height=height,
                              tile_origin_x=0, tile_origin_y=top, tile_seed=seed)
                measured_peaks = engine.analyze(tile, region, 'exposure_peaks')
                for name in peaks:
                    value = measured_peaks.get(name)
                    if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                        raise NativeSpectralError('全图光学峰值无效，已阻止分块产生不一致的高光')
                    peaks[name] = max(peaks[name], value)
                peak_prepass_regions += 1
                del tile
            peak_prepass_ms = (time.perf_counter() - measured) * 1000.
        for top in range(0, height, core):
            bottom = min(height, top + core)
            y0, y1 = max(0, top - halo), min(height, bottom + halo)
            for left in range(0, width, core):
                right = min(width, left + core)
                x0, x1 = max(0, left - halo), min(width, right + halo)
                tile = _normalized(source[y0:y1, x0:x1])
                region = dict(values, striped=False, tile_full_width=width, tile_full_height=height,
                              tile_origin_x=x0, tile_origin_y=y0, tile_seed=seed, **peaks)
                rendered = engine.render(tile, region, None)
                output[top:bottom, left:right] = rendered[top-y0:bottom-y0, left-x0:right-x0]
                native_ms += _LAST_RENDER.get('native_ms', 0.)
                peak_region_pixels = max(peak_region_pixels, tile.shape[0] * tile.shape[1])
                regions += 1
                del rendered, tile
        output.flush()
        _LAST_RENDER.update(native_ms=native_ms, negative_cached=False, reprint=False,
            width=width, height=height, input_dtype=str(source.dtype), output_bits=16,
            bounded_regions=regions, region_halo=halo, region_core=core,
            max_region_pixels=peak_region_pixels, file_backed_output=True,
            optical_peaks=peaks, optical_peak_prepass_ms=peak_prepass_ms,
            optical_peak_prepass_regions=peak_prepass_regions,
            region_seconds=time.perf_counter()-started)
        return output
    except BaseException:
        # The finalizer owns deletion and closes its mapping once views die.
        del output
        raise


class _Engine:
    def __init__(self):
        self.lib = ct.CDLL(str(_RUNTIME / 'spektrafilm_engine.dll'))
        specs = {
            'spk_engine_create': ([ct.c_char_p, ct.c_void_p], ct.c_void_p),
            'spk_engine_destroy': ([ct.c_void_p], None),
            'spk_open': ([ct.c_void_p, ct.POINTER(_Image), ct.c_char_p, ct.POINTER(ct.c_void_p)], ct.c_void_p),
            'spk_set_params': ([ct.c_void_p, ct.c_char_p, ct.POINTER(ct.c_void_p)], ct.c_int32),
            'spk_render': ([ct.c_void_p, ct.c_char_p, ct.POINTER(_Result)], ct.c_int32),
            'spk_reprint': ([ct.c_void_p, ct.c_char_p, ct.POINTER(_Result)], ct.c_int32),
            'spk_result_free': ([ct.POINTER(_Result)], None),
            'spk_session_release': ([ct.c_void_p], None),
            'spk_string_free': ([ct.c_void_p], None),
            'spk_last_error': ([ct.c_void_p], ct.c_char_p),
            'spk_capabilities': ([ct.c_void_p], ct.c_char_p),
            'spk_memory_report': ([ct.c_void_p], ct.c_char_p),
            'spk_trim_memory': ([ct.c_void_p, ct.c_uint64, ct.POINTER(ct.c_uint64)], ct.c_int32),
            'spk_cancel': ([ct.c_void_p, ct.c_char_p], None),
            'spk_progress': ([ct.c_void_p,ct.c_char_p,ct.POINTER(ct.c_void_p)],ct.c_int32),
            'spk_canvas_size': ([ct.c_void_p,ct.POINTER(ct.c_uint32),ct.POINTER(ct.c_uint32),ct.POINTER(ct.c_void_p)],ct.c_int32),
            'spk_render_canvas': ([ct.c_void_p,ct.c_char_p,ct.POINTER(ct.c_uint16),ct.c_uint32,ct.c_uint32,ct.POINTER(ct.c_void_p)],ct.c_int32),
            'spk_editor_process': ([ct.c_void_p, ct.POINTER(_Image), ct.c_char_p,
                                   ct.POINTER(ct.c_float), ct.POINTER(ct.c_double)], ct.c_int32),
            'spk_editor_process_with_tone_base': ([ct.c_void_p,ct.POINTER(_Image),ct.POINTER(_Image),ct.c_char_p,
                                   ct.POINTER(ct.c_float),ct.POINTER(ct.c_double)],ct.c_int32),
            'spk_solve': ([ct.c_void_p, ct.c_char_p, ct.POINTER(ct.c_void_p)], ct.c_int32),
            'spk_scene_latitude': ([ct.c_void_p, ct.c_char_p, ct.POINTER(ct.c_void_p)], ct.c_int32),
            'spk_session_hdr_curve': ([ct.c_void_p,ct.c_char_p,ct.POINTER(ct.c_void_p)],ct.c_int32),
            'spk_color_transform_rgb': ([ct.c_void_p,ct.POINTER(ct.c_float),ct.c_uint32,ct.c_uint32,
                ct.c_char_p,ct.c_char_p,ct.POINTER(ct.c_float),ct.c_char_p],ct.c_int32),
            'spk_overscan_geometry': ([ct.c_void_p, ct.POINTER(ct.c_void_p)], ct.c_int32),
            'spk_output_transform': ([ct.c_void_p,ct.c_char_p,ct.c_char_p,ct.c_char_p,ct.POINTER(ct.c_void_p),
                                      ct.POINTER(ct.POINTER(ct.c_float)),ct.POINTER(ct.c_uint32)],ct.c_int32),
        }
        for name, (args, result) in specs.items():
            function = getattr(self.lib, name)
            function.argtypes, function.restype = args, result
        pair_function = getattr(self.lib, 'spk_render_pair', None)
        if pair_function is not None:
            pair_function.argtypes = [ct.c_void_p, ct.c_char_p, ct.POINTER(_Result)]
            pair_function.restype = ct.c_int32
        self.handle = self.lib.spk_engine_create(str(_RUNTIME / 'resources').encode('utf-8'), None)
        if not self.handle:
            raise NativeSpectralError(self.error())
        self.sessions = OrderedDict()
        self.active_session = None
        self.capabilities = json.loads(self.lib.spk_capabilities(self.handle))

    def error(self):
        message = self.lib.spk_last_error(getattr(self, 'handle', None))
        return message.decode('utf-8', errors='replace') if message else '原生光谱引擎初始化或渲染失败'

    def _free_reply(self, reply):
        if reply.value:
            self.lib.spk_string_free(reply)

    def render(self, pixels, values, key, *, film_canvas=False, pair_request=None,bounded_canvas=False,progress=None):
        height, width = pixels.shape[:2]
        # Full-frame sources and negatives dominate memory. Retain a small
        # proxy pair, or one large source, rather than an unbounded image list.
        source_bytes = pixels.nbytes
        existing = self.sessions.get(key) if key is not None else None
        if existing is None:
            while self.sessions and (len(self.sessions) >= _CACHE_LIMITS['max_entries'] or
                    source_bytes + sum(item[2] for item in self.sessions.values()) > _CACHE_LIMITS['source_bytes']):
                _, old = self.sessions.popitem(last=False)
                self.lib.spk_session_release(old[0])
            image = _Image(pixels.ctypes.data_as(ct.POINTER(ct.c_float)), width, height, 3)
            reply = ct.c_void_p()
            try:
                handle = self.lib.spk_open(self.handle, ct.byref(image),
                                           _json_bytes(dict(values, product_defaults=True)), ct.byref(reply))
            finally:
                self._free_reply(reply)
            if not handle:
                raise NativeSpectralError(self.error())
            existing = [handle, values, source_bytes]
            if key is not None:
                self.sessions[key] = existing
        else:
            self.sessions.move_to_end(key)
            delta = {name: value for name, value in values.items() if existing[1].get(name) != value}
            if delta:
                reply = ct.c_void_p()
                try:
                    status = self.lib.spk_set_params(existing[0], _json_bytes(delta), ct.byref(reply))
                finally:
                    self._free_reply(reply)
                if status:
                    raise NativeSpectralError(self.error())
                existing[1] = values
        result = _Result()
        with _ACTIVE_LOCK:
            self.active_session = existing[0]
        try:
            if bounded_canvas:
                return self.render_canvas(existing[0],pair_request,progress)
            # reprint computes a missing/invalidated negative, but preserves a
            # valid one. spk_render intentionally forces film redevelopment.
            if pair_request is not None:
                function = getattr(self.lib, 'spk_render_pair', None)
                if function is None:
                    raise NativeSpectralError('当前引擎尚未包含独立半格印放接口，请重新构建引擎')
                status = function(existing[0], _json_bytes(pair_request), ct.byref(result))
            else:
                status = self.lib.spk_reprint(existing[0], b'full', ct.byref(result))
            if status:
                raise NativeSpectralError(self.error())
            geometry = None
            if film_canvas:
                reply = ct.c_void_p()
                try:
                    status = self.lib.spk_overscan_geometry(existing[0], ct.byref(reply))
                    if status:
                        raise NativeSpectralError(self.error())
                    geometry = json.loads(ct.string_at(reply)) if reply.value else {'valid': False}
                finally:
                    self._free_reply(reply)
                if values.get('overscan_active'):
                    if not geometry.get('valid') or (result.width, result.height) != (geometry.get('canvas_w'), geometry.get('canvas_h')):
                        raise NativeSpectralError('胶片画布与原生片门几何不一致')
                elif (result.width, result.height) != (width, height):
                    raise NativeSpectralError('日期曝光返回尺寸不匹配')
            elif (result.width, result.height) != (width, height):
                raise NativeSpectralError('原生光谱返回尺寸不匹配，已阻止缩小的导出')
            out_width, out_height = int(result.width), int(result.height)
            if min(out_width, out_height) < 1 or result.row_stride_px < out_width or not result.rgba16:
                raise NativeSpectralError('原生光谱返回无效画布')
            view = np.ctypeslib.as_array(result.rgba16,
                    shape=(out_height * result.row_stride_px * 4,)).reshape(out_height, result.row_stride_px, 4)
            output = view[:, :out_width, :3].astype(np.float32)
            output *= np.float32(1. / 65535.)
            _LAST_RENDER.update(native_ms=result.elapsed_ms, negative_cached=bool(result.negative_was_cached),
                                reprint=bool(result.reprint), width=out_width, height=out_height,
                                input_dtype='float32', output_bits=16)
            return (output, geometry) if film_canvas else output
        finally:
            with _ACTIVE_LOCK:
                self.active_session = None
            self.lib.spk_result_free(ct.byref(result))
            if key is None:
                self.lib.spk_session_release(existing[0])
            self.enforce_cache_limits()

    def render_canvas(self,session,pair_request,progress):
        width,height=ct.c_uint32(),ct.c_uint32();reply=ct.c_void_p()
        try:
            status=self.lib.spk_canvas_size(session,ct.byref(width),ct.byref(height),ct.byref(reply))
            if status:raise NativeSpectralError(self.error())
            size=json.loads(ct.string_at(reply))
        finally:self._free_reply(reply)
        if not width.value or not height.value:raise NativeSpectralError('原生片边画布尺寸无效')
        raw=_mapped_result((height.value,width.value,4),np.uint16)
        request=dict(region_edge=1024)
        if pair_request:request['pair']=pair_request['pair']
        finished=threading.Event();poller=None
        if progress is not None:
            def poll():
                previous=0.
                while not finished.wait(.1):
                    state=ct.c_void_p()
                    try:
                        if self.lib.spk_progress(session,None,ct.byref(state)) or not state.value:continue
                        value=json.loads(ct.string_at(state))
                        if not str(value.get('progress_id','')).startswith('c'):continue
                        current=max(previous,min(100.,float(value.get('pct',0))))
                        if current>previous:progress(current/100);previous=current
                    except (ValueError,OSError):pass
                    finally:self._free_reply(state)
            poller=threading.Thread(target=poll,daemon=True);poller.start()
        reply=ct.c_void_p();started=time.perf_counter()
        try:
            status=self.lib.spk_render_canvas(session,_json_bytes(request),raw.ctypes.data_as(ct.POINTER(ct.c_uint16)),width,height,ct.byref(reply))
            report=json.loads(ct.string_at(reply)) if reply.value else {}
            if status or not report.get('success'):raise NativeSpectralError(self.error())
        finally:
            finished.set()
            if poller is not None:poller.join()
            self._free_reply(reply)
        geometry_reply=ct.c_void_p()
        try:
            status=self.lib.spk_overscan_geometry(session,ct.byref(geometry_reply))
            if status:raise NativeSpectralError(self.error())
            geometry=json.loads(ct.string_at(geometry_reply))
        finally:self._free_reply(geometry_reply)
        if geometry.get('valid') and (geometry['canvas_w'],geometry['canvas_h'])!=(width.value,height.value):
            raise NativeSpectralError('原生片边尺寸与片门几何不一致')
        output=_mapped_result((height.value,width.value,3))
        for top in range(0,height.value,64):
            output[top:top+64]=raw[top:top+64,:,:3]
            output[top:top+64]*=np.float32(1/65535.)
        output.flush();del raw
        geometry['bounded_report']=report
        _LAST_RENDER.update(native_ms=(time.perf_counter()-started)*1000,width=width.value,height=height.value,
            output_bits=16,file_backed_output=True,canvas=report,canvas_size=size)
        if progress is not None:progress(1.)
        return output,geometry

    def memory_report(self):
        return json.loads(self.lib.spk_memory_report(self.handle))

    def enforce_cache_limits(self):
        """Bound retained source + negative + view bytes, beyond entry count."""
        while self.sessions:
            persistent = self.memory_report().get('persistent', {})
            retained = sum(persistent.get(name, 0) for name in
                           ('source_bytes', 'cached_negative_bytes', 'cached_view_bytes'))
            if (len(self.sessions) <= _CACHE_LIMITS['max_entries'] and
                sum(item[2] for item in self.sessions.values()) <= _CACHE_LIMITS['source_bytes'] and
                retained <= _CACHE_LIMITS['retained_bytes']):
                break
            _, old = self.sessions.popitem(last=False)
            self.lib.spk_session_release(old[0])

    def trim_memory(self, keep_free_bytes=0):
        released = ct.c_uint64()
        status = self.lib.spk_trim_memory(self.handle, max(0, int(keep_free_bytes)), ct.byref(released))
        if status:
            raise NativeSpectralError(self.error())
        return released.value

    def close(self):
        for handle, _, _ in self.sessions.values():
            self.lib.spk_session_release(handle)
        self.sessions.clear()
        self.lib.spk_engine_destroy(self.handle)

    def editor(self, pixels, request, output, tone_base=None):
        height, width = pixels.shape[:2]
        image = _Image(pixels.ctypes.data_as(ct.POINTER(ct.c_float)), width, height, 3)
        elapsed = ct.c_double()
        if tone_base is None:
            status = self.lib.spk_editor_process(self.handle, ct.byref(image), _json_bytes(request),
                        output.ctypes.data_as(ct.POINTER(ct.c_float)), ct.byref(elapsed))
        else:
            base=_Image(tone_base.ctypes.data_as(ct.POINTER(ct.c_float)),width,height,1)
            status=self.lib.spk_editor_process_with_tone_base(self.handle,ct.byref(image),ct.byref(base),
                        _json_bytes(request),output.ctypes.data_as(ct.POINTER(ct.c_float)),ct.byref(elapsed))
        if status:
            raise NativeSpectralError(self.error())
        _LAST_RENDER['editor_ms'] = elapsed.value
        return output

    def analyze(self, pixels, values, target, request=None):
        height, width = pixels.shape[:2]
        image = _Image(pixels.ctypes.data_as(ct.POINTER(ct.c_float)), width, height, 3)
        reply = ct.c_void_p()
        handle = None
        try:
            handle = self.lib.spk_open(self.handle, ct.byref(image),
                                      _json_bytes(dict(values, product_defaults=True)), ct.byref(reply))
            self._free_reply(reply)
            reply = ct.c_void_p()
            if not handle:
                raise NativeSpectralError(self.error())
            if target == 'hdr_curve':
                status=self.lib.spk_session_hdr_curve(handle,_json_bytes(request or {}),ct.byref(reply))
            elif target == 'scene_latitude':
                status = self.lib.spk_scene_latitude(handle, _json_bytes(request or {}), ct.byref(reply))
            else:
                if target == 'exposure_peaks':
                    with _ACTIVE_LOCK:
                        self.active_session = handle
                try:
                    status = self.lib.spk_solve(handle, target.encode('ascii'), ct.byref(reply))
                finally:
                    if target == 'exposure_peaks':
                        with _ACTIVE_LOCK:
                            self.active_session = None
            if status:
                raise NativeSpectralError(self.error())
            return json.loads(ct.string_at(reply)) if reply.value else {}
        finally:
            self._free_reply(reply)
            if handle:
                self.lib.spk_session_release(handle)


def _get_engine():
    global _ENGINE, _INITIALIZATION_ERROR
    if _ENGINE is None and _INITIALIZATION_ERROR is None:
        try:
            if sys.platform != 'win32':
                raise NativeSpectralError('此运行时是 Windows Vulkan 引擎')
            _ENGINE = _Engine()
        except (OSError, ValueError, AttributeError, NativeSpectralError) as error:
            _INITIALIZATION_ERROR = str(error)
    return _ENGINE


def available():
    with _LOCK:
        return _get_engine() is not None


def backend_info():
    with _LOCK:
        engine = _get_engine()
        if engine is None:
            return {'available': False, 'error': _INITIALIZATION_ERROR}
        return {'available': True, 'backend': engine.capabilities.get('backend', {}),
                'last_render': dict(_LAST_RENDER),
                'bridge_session_cache': {'entries': len(engine.sessions),
                    'source_bytes': sum(item[2] for item in engine.sessions.values()),
                    'limits': dict(_CACHE_LIMITS)},
                'memory': json.loads(engine.lib.spk_memory_report(engine.handle))}


def memory_info():
    """Engine/cache/scratch ownership, without starting the GPU.

    Native totals exclude caller-owned NumPy sources and mapped results.
    The scratch byte count describes live temporary disk mappings; these are
    not persistent caches and must not be deleted while an export owns them.
    Invoke on the engine worker lane, never synchronously in a UI timer.
    """
    with _BUFFER_LOCK:
        scratch = {'live_mappings': len(_MAPPED_RESULTS),
                   'live_bytes': sum(_MAPPED_RESULTS.values())}
    with _LOCK:
        engine = _ENGINE
        return {'initialized': engine is not None,
                'session_cache': {'entries': len(engine.sessions) if engine else 0,
                    'source_bytes': sum(item[2] for item in engine.sessions.values()) if engine else 0,
                    'limits': dict(_CACHE_LIMITS)},
                'temporary_scratch': scratch,
                'native': engine.memory_report() if engine else {}}


def set_cache_limits(*, max_entries=None, source_bytes=None, retained_bytes=None):
    """Set nonnegative preview budgets and evict older sessions immediately.

    `retained_bytes` covers native sources, negatives and cached print views;
    idle pool storage is controlled separately by trim_memory. A zero budget
    disables retained sessions. Full export sessions are always transient.
    """
    requested = {'max_entries': max_entries, 'source_bytes': source_bytes,
                 'retained_bytes': retained_bytes}
    for name, value in requested.items():
        if value is not None and (isinstance(value, bool) or int(value) < 0):
            raise ValueError(f'{name} must be a nonnegative integer')
    with _LOCK:
        _CACHE_LIMITS.update({name: int(value) for name, value in requested.items() if value is not None})
        if _ENGINE is not None:
            _ENGINE.enforce_cache_limits()
        return dict(_CACHE_LIMITS)


def trim_memory(*, keep_free_bytes=0):
    """Trim idle GPU pool storage between jobs; preserve all live sessions."""
    if int(keep_free_bytes) < 0:
        raise ValueError('keep_free_bytes must be nonnegative')
    with _LOCK:
        return _ENGINE.trim_memory(keep_free_bytes) if _ENGINE is not None else 0


def render_spectral(encoded_srgb_float32, settings, *, preview=False, source_token=None,
                    output_color_space='sRGB', digital_intermediate=False,di_blue_compensation=False,
                    scan_hdr_overrides=None):
    started = time.perf_counter()
    pixels = np.asarray(encoded_srgb_float32)
    if pixels.ndim != 3 or pixels.shape[2] != 3 or min(pixels.shape[:2]) < 1:
        raise NativeSpectralError('原生光谱需要 H×W×3 源像素')
    settings = _physical_settings(settings,pixels)
    values = parameters(settings)
    values.update(output_color_space=str(output_color_space),
                  digital_intermediate=bool(digital_intermediate),
                  digital_intermediate_blue_compensation=bool(di_blue_compensation))
    if digital_intermediate:
        from shared.darkroom import scans_directly
        if scans_directly(settings.stock):raise NativeSpectralError('反转片不能输出负片中间片')
        values.update(scan_film=False,minilab_active=False,extended_dynamic_range=False)
    if scan_hdr_overrides is not None:
        allowed={'scan_hdr_stretch','scan_hdr_headroom','scan_hdr_output_scale','grain_seed'}
        if not isinstance(scan_hdr_overrides,dict) or set(scan_hdr_overrides)-allowed:
            raise NativeSpectralError('无效 HDR 扫描参数')
        values.update(scan_hdr_overrides)
    values.update(striped=pixels.shape[0] * pixels.shape[1] > 8_000_000,
                  strip_rows=512, strip_budget_bytes=512 * 1024 ** 2)
    try:
        hash(source_token)
        token = source_token
    except TypeError:
        token = repr(source_token)
    # Final sources/negatives can each exceed a gigabyte. Only small preview
    # sessions belong in the retained UI cache; exports must release theirs.
    cacheable = (preview and _CACHE_LIMITS['max_entries'] > 0 and _CACHE_LIMITS['retained_bytes'] > 0
                 and pixels.size * np.dtype(np.float32).itemsize <= _CACHE_LIMITS['source_bytes'])
    overrides_key=tuple(sorted((scan_hdr_overrides or {}).items()))
    key = (token, pixels.shape, True, str(output_color_space), bool(digital_intermediate),bool(di_blue_compensation),overrides_key) if source_token is not None and cacheable else None
    with _LOCK:
        engine = _get_engine()
        if engine is None:
            raise NativeSpectralError(_INITIALIZATION_ERROR or '原生光谱不可用')
        if not preview and pixels.shape[0] * pixels.shape[1] > _LARGE_FRAME_PIXELS:
            result = _render_regions(engine, pixels, settings, values)
        else:
            result = engine.render(_normalized(pixels), values, key)
        _LAST_RENDER['bridge_ms'] = (time.perf_counter() - started) * 1000.
        return result


def render_film_canvas(pixels, settings, *, overrides, preview=False, source_token=None, pair=None,progress=None):
    """Expose a physical film canvas, including native edge/date illumination.

    The caller prepares the gate(s) before this boundary. Only this explicit
    API accepts an expanded output; ordinary render_spectral retains its
    strict source-size guarantee. No post-render border or thumbnail fallback.
    Input transfer/primaries must describe the supplied samples precisely.
    """
    started = time.perf_counter()
    source = _normalized(pixels)
    if source.ndim != 3 or source.shape[2] != 3 or min(source.shape[:2]) < 1:
        raise NativeSpectralError('胶片画布需要 H×W×3 源像素')
    values = parameters(settings)
    values.update(overrides)
    pair_request = None
    target = values.get('output_color_space', 'sRGB')
    if pair is not None:
        values.update(output_color_space='ProPhoto RGB', output_cctf_encoding=True)
        pair_request = dict(tier='full', target_space='ProPhoto RGB', pair=pair)
    if not (values.get('overscan_active') or values.get('date_imprint_active') or pair is not None):
        raise NativeSpectralError('胶片画布必须启用片边或日期曝光')
    # Upstream rejects striped+overscan: never feed physical millimetre
    # coordinates into the same-size region executor, which would repeat
    # film edges on every tile. Native allocation failures propagate.
    values.update(striped=False)
    cacheable = (preview and source_token is not None and _CACHE_LIMITS['max_entries'] > 0
                 and source.nbytes <= _CACHE_LIMITS['source_bytes'])
    try:
        hash(source_token)
        token = source_token
    except TypeError:
        token = repr(source_token)
    key = ('film_canvas', token, source.shape,
           values.get('input_color_space'), values.get('input_cctf_decoding')) if cacheable else None
    with _LOCK:
        engine = _get_engine()
        if engine is None:
            raise NativeSpectralError(_INITIALIZATION_ERROR or '原生光谱不可用')
        result = engine.render(source, values, key, film_canvas=True, pair_request=pair_request,
            bounded_canvas=not preview,progress=progress)
        if pair is not None and target!='ProPhoto RGB':
            if target!='sRGB':raise NativeSpectralError('独立半格画布当前输出支持 sRGB 或 ProPhoto RGB')
            output,geometry=result
            converted=process_editor(output,{},stage='pre',source_color_space='ProPhoto RGB',
                clamp_output=False,out=output)
            result=converted,dict(geometry,output_color_space=target)
        _LAST_RENDER['bridge_ms'] = (time.perf_counter() - started) * 1000.
        return result


@lru_cache(maxsize=16)
def source_color_matrix(source='sRGB',target='ProPhoto RGB'):
    """Use the engine's own row-major CAT02 matrix at source boundaries."""
    with _LOCK:
        engine=_get_engine()
        if engine is None:raise NativeSpectralError(_INITIALIZATION_ERROR or '原生光谱不可用')
        reply=ct.c_void_p();table=ct.POINTER(ct.c_float)();count=ct.c_uint32()
        try:
            status=engine.lib.spk_output_transform(engine.handle,str(source).encode('utf-8'),str(target).encode('utf-8'),
                b'{"lightness_compression_active":false}',ct.byref(reply),ct.byref(table),ct.byref(count))
            if status:raise NativeSpectralError(engine.error())
            document=json.loads(ct.string_at(reply))
            result=np.asarray(document['matrix'],dtype=np.float32).reshape(3,3)
            result.setflags(write=False)
            return result
        finally:engine._free_reply(reply)


def cancel_active():
    # Deliberately outside _LOCK: the render holds it, and spk_cancel is the
    # one C entry point expressly safe to call concurrently with a render.
    with _ACTIVE_LOCK:
        engine = _ENGINE
        if engine is not None and engine.active_session:
            engine.lib.spk_cancel(engine.active_session, None)


def editor_request(settings, *, stage='post', source_size=None, origin=(0, 0),
                   pixel_scale=(1., 1.), source_color_space='sRGB', source_linear=False,
                   exposure_ev=None, clamp_output=None):
    """Wire contract shared by the desktop and Android editor stages.

    Coordinates describe the oriented source before crop. A proxy covering the
    whole source uses pixel_scale=(full_width/proxy_width, full_height/proxy_height).
    A full-resolution tile instead uses origin=(source_x, source_y), scale=(1,1).
    """
    if stage == 'pre':
        if is_dataclass(settings):
            values = {name: getattr(settings, name) for name in _PRE_EDITOR_FIELDS
                      if hasattr(settings, name)}
        else:
            source = settings if isinstance(settings, dict) else dict(settings)
            values = {name: source[name] for name in _PRE_EDITOR_FIELDS if name in source}
    else:
        values = asdict(settings) if is_dataclass(settings) else dict(settings)
    request = dict(stage=stage, settings=values, origin_x=float(origin[0]), origin_y=float(origin[1]),
                   pixel_scale_x=float(pixel_scale[0]), pixel_scale_y=float(pixel_scale[1]),
                   source_color_space=str(source_color_space), source_linear=bool(source_linear))
    if source_size is not None:
        request.update(source_width=int(source_size[0]), source_height=int(source_size[1]))
    if exposure_ev is not None:
        request['exposure_ev'] = float(exposure_ev)
    if clamp_output is not None:
        request['clamp_output'] = bool(clamp_output)
    return request


def process_editor(pixels, settings, *, stage='post', source_size=None, origin=(0, 0),
                   pixel_scale=(1., 1.), source_color_space='sRGB', source_linear=False,
                   exposure_ev=None, clamp_output=None, out=None, tone_base=None):
    """Shared GPU adjustments without reducing resolution or quantising floats.

    ``out`` may be the same contiguous float32 input or a caller-owned memmap.
    Native scratch is striped; callers do not need to split large source frames.
    Geometry/crop belongs after this operation. No LUT or CPU substitute is used.
    """
    source = _normalized(pixels)
    if source.ndim != 3 or source.shape[2] != 3 or min(source.shape[:2]) < 1:
        raise NativeSpectralError('编辑引擎需要 H×W×3 源像素')
    if out is None:
        out = _mapped_result(source.shape) if source.shape[0]*source.shape[1] > _LARGE_FRAME_PIXELS else np.empty_like(source)
    if out.dtype != np.float32 or not out.flags.c_contiguous or out.shape != source.shape or not out.flags.writeable:
        raise NativeSpectralError('编辑输出需要同尺寸连续可写 float32 RGB 缓冲')
    if tone_base is not None:
        tone_base=np.ascontiguousarray(tone_base,dtype=np.float32)
        if tone_base.shape != source.shape[:2] or not np.isfinite(tone_base).all() or np.any(tone_base<0):
            raise NativeSpectralError('HDR基底需要同尺寸非负有限浮点亮度平面')
    request = editor_request(settings, stage=stage, source_size=source_size, origin=origin,
            pixel_scale=pixel_scale, source_color_space=source_color_space, source_linear=source_linear,
            exposure_ev=exposure_ev, clamp_output=clamp_output)
    with _LOCK:
        engine = _get_engine()
        if engine is None:
            raise NativeSpectralError(_INITIALIZATION_ERROR or '原生编辑引擎不可用')
        return engine.editor(source, request, out,tone_base)


def solve_spectral(pixels, settings, *, target='both', source_token=None):
    """Measure suggested exposure/filter pack; does not silently apply edits."""
    if target not in ('exposure', 'filter_pack', 'both'):
        raise ValueError('target must be exposure, filter_pack or both')
    settings=_physical_settings(settings,pixels)
    # The filter-pack solve is a material-neutral baseline, not a scene colour
    # solve.  Build it from the same product database (including stock-specific
    # overrides) that the renderer uses.  Calling the low-level reference
    # database here used to discard those overrides and could shift a correct
    # print when the user pressed Auto.
    if target == 'filter_pack':
        values = parameters(settings)
        return {'solved_params': {
            'c_filter_neutral': float(values.get('c_filter_neutral', 0.)),
            'm_filter_neutral': float(values.get('m_filter_neutral', 65.)),
            'y_filter_neutral': float(values.get('y_filter_neutral', 55.)),
        }, 'metered': False, 'filter_pack_source': 'product-neutral-database'}
    with _LOCK:
        engine = _get_engine()
        if engine is None:
            raise NativeSpectralError(_INITIALIZATION_ERROR or '原生光谱不可用')
        values = parameters(settings)
        reply = engine.analyze(_normalized(pixels), values, target)
        if target == 'both' and isinstance(reply, dict):
            solved = reply.get('solved_params')
            if isinstance(solved, dict):
                # Keep exposure from the scene meter, but use the exact same
                # stock/paper neutral values as rendering for the filter part.
                for key in ('c_filter_neutral', 'm_filter_neutral', 'y_filter_neutral'):
                    if key in values:
                        solved[key] = float(values[key])
                reply['solved_params'] = solved
                reply['filter_pack_source'] = 'product-neutral-database'
        return reply


def scene_latitude(pixels, settings, *, request=None, source_token=None):
    """Return measured latitude and suggested params_delta without rendering."""
    settings=_physical_settings(settings,pixels)
    with _LOCK:
        engine = _get_engine()
        if engine is None:
            raise NativeSpectralError(_INITIALIZATION_ERROR or '原生光谱不可用')
        return engine.analyze(_normalized(pixels), parameters(settings), 'scene_latitude', request)


def hdr_curve(pixels,settings,request=None,*,source_token=None):
    """Measured print-density HDR curve from the same physical parameters."""
    settings=_physical_settings(settings,pixels)
    with _LOCK:
        engine=_get_engine()
        if engine is None:raise NativeSpectralError(_INITIALIZATION_ERROR or '原生光谱不可用')
        return engine.analyze(_normalized(pixels),parameters(settings),'hdr_curve',request)


def transform_color(pixels,source='ProPhoto RGB',target='sRGB',*,compress=True):
    """GPU float32 CAT02/CAM16 conversion with the engine's cached setup."""
    source_pixels=_normalized(pixels)
    result=np.empty(source_pixels.shape,dtype=np.float32)
    with _LOCK:
        engine=_get_engine()
        if engine is None:raise NativeSpectralError(_INITIALIZATION_ERROR or '原生光谱不可用')
        status=engine.lib.spk_color_transform_rgb(engine.handle,
            source_pixels.ctypes.data_as(ct.POINTER(ct.c_float)),source_pixels.shape[1],source_pixels.shape[0],
            source.encode('utf-8'),target.encode('utf-8'),result.ctypes.data_as(ct.POINTER(ct.c_float)),
            _json_bytes(dict(algorithm='cam16ucs' if compress else 'off',lightness_compression_active=False)))
        if status:raise NativeSpectralError(engine.error())
    return result


def clear_sessions(*, keep_free_bytes=0):
    """Release retained previews and idle pool memory; leave caller results alive."""
    with _LOCK:
        if _ENGINE is not None:
            for handle, _, _ in _ENGINE.sessions.values():
                _ENGINE.lib.spk_session_release(handle)
            _ENGINE.sessions.clear()
            return _ENGINE.trim_memory(keep_free_bytes)
    return 0


def _shutdown():
    global _ENGINE
    with _LOCK:
        if _ENGINE is not None:
            _ENGINE.close()
            _ENGINE = None


atexit.register(_shutdown)
