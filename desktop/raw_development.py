"""Native scene-linear RAW sources; display proxies never become export data.

LibRaw remains an independent decoder, not a Capture One/Adobe implementation.
Metadata probing does not initialise the GPU or unpack the sensor. Conventional
Bayer uses the expanded float output path; other layouts explicitly identify
the compatible16 route in their source metadata.
"""
from __future__ import annotations

import ctypes as ct
from collections import OrderedDict
import json
from pathlib import Path
import threading
import weakref

import numpy as np

from desktop.raw_source import display_image, file_token, quantize_display, resize_pixels


class RawDevelopmentError(RuntimeError):
    pass


class _Result(ct.Structure):
    _fields_ = [('rgb', ct.POINTER(ct.c_float)), ('width', ct.c_uint32),
                ('height', ct.c_uint32), ('owner', ct.c_void_p), ('metadata_json', ct.c_char_p)]


_LIBRARY = None
_LOCK = threading.RLock()
_SOURCE_POLICY = 'auto'
_BASELINE_CACHE = OrderedDict()
_LIVE_SOURCES = {}


def memory_info():
    """Owned RAW bytes, excluding the caller's derived/display buffers.

    No decoder/GPU is initialised by this query. Live source views cannot be
    forcibly freed: their owners release them when the last NumPy view dies.
    """
    with _LOCK:
        return {'live_sources': len(_LIVE_SOURCES),
                'live_source_bytes': sum(_LIVE_SOURCES.values()),
                'baseline_entries': len(_BASELINE_CACHE), 'baseline_limit': 256}


def clear_cache():
    """Clear small starting-exposure metadata; never invalidate live pixels."""
    with _LOCK:
        _BASELINE_CACHE.clear()


def _release_source(library, result, key):
    # Finalizers may execute on any Python thread. The library and structure
    # are retained by this callback, independently of module shutdown order.
    with _LOCK:
        library.spk_raw_free(ct.byref(result))
        _LIVE_SOURCES.pop(key, None)


def _library():
    global _LIBRARY
    if _LIBRARY is None:
        from desktop.native_spectral import _RUNTIME
        library = ct.CDLL(str(_RUNTIME / 'spektrafilm_raw.dll'))
        library.spk_raw_probe.argtypes = [ct.c_char_p]
        library.spk_raw_probe.restype = ct.c_char_p
        library.spk_raw_decode.argtypes = [ct.c_char_p, ct.c_char_p, ct.c_int32, ct.POINTER(_Result)]
        library.spk_raw_decode.restype = ct.c_int32
        library.spk_raw_free.argtypes = [ct.POINTER(_Result)]
        library.spk_raw_free.restype = None
        library.spk_raw_last_error.argtypes = []
        library.spk_raw_last_error.restype = ct.c_char_p
        _LIBRARY = library
    return _LIBRARY


def available():
    try:
        with _LOCK:
            _library()
        return True
    except (OSError, AttributeError):
        return False


def _error(library):
    message = library.spk_raw_last_error()
    return RawDevelopmentError(message.decode('utf-8', errors='replace') if message else 'RAW development failed')


def probe_raw(path):
    """Read camera/geometry/headroom capability without sensor demosaicing."""
    with _LOCK:
        library = _library()
        response = library.spk_raw_probe(str(Path(path)).encode('utf-8'))
        if not response:
            raise _error(library)
        return json.loads(response)


def decode_raw(path, *, preview=False, policy='auto'):
    """Return native-owned float RGB and metadata; no full source copy.

    The ndarray owns a ctypes view whose finalizer releases the native vector.
    Keeping an ndarray view therefore also keeps the original native owner.
    Serialize this operation at the queue level: only a selected image should
    be developed, never every RAW added to the filmstrip.
    """
    if policy not in ('auto', 'headroom', 'compatible16'):
        raise ValueError('unknown RAW development policy')
    with _LOCK:
        library = _library()
        result = _Result()
        status = library.spk_raw_decode(str(Path(path)).encode('utf-8'), policy.encode('ascii'),
                                        int(preview), ct.byref(result))
        if status:
            raise _error(library)
        try:
            metadata = json.loads(result.metadata_json)
            pixels = np.ctypeslib.as_array(result.rgb, shape=(result.height*result.width*3,)).reshape(result.height,result.width,3)
            # The numpy/ctypes owner chain holds this root view until every
            # derived view dies. Do not finalise just the temporary reshape.
            root = pixels
            while isinstance(getattr(root, 'base', None), np.ndarray):
                root = root.base
            pixels.setflags(write=False)
            key = int(result.owner)
            _LIVE_SOURCES[key] = pixels.nbytes
            weakref.finalize(root, _release_source, library, result, key)
            return pixels, metadata
        except BaseException:
            library.spk_raw_free(ct.byref(result))
            raise


def _srgb_luminance_samples(prophoto):
    # D50 ProPhoto -> D65 sRGB, CAT02. This small analysis proxy only chooses
    # a neutral starting exposure; the actual transform uses native colour data.
    matrix = np.array([[2.034075, -0.727334, -0.306741],
                       [-0.228813, 1.231731, -0.002918],
                       [-0.008569, -0.153286, 1.161855]], dtype=np.float64)
    h, w = prophoto.shape[:2]
    step = max(1, int(np.sqrt(h*w/262144)))
    sample = np.asarray(prophoto[::step, ::step], dtype=np.float64) @ matrix.T
    return np.maximum(sample, 0).max(axis=-1)


def baseline_exposure(pixels):
    """Robust RAW starting exposure, preserving the scene-linear source.

    Use the same one-percent highlight intent as the previous LibRaw baseline,
    bounded to protect dark scenes. It is a display/development gain, never
    baked into or clipped against the stored source samples.
    """
    samples = _srgb_luminance_samples(pixels)
    finite = samples[np.isfinite(samples) & (samples > 1e-8)]
    if not finite.size:
        return 0.
    white = float(np.percentile(finite, 99))
    return max(-2., min(3., float(np.log2(1./max(white, 1e-8)))))


def read_developed_raw(path, max_edge=None, *, policy='auto'):
    """Create a display image carrying unquantised scene-linear source data.

    Only preview requests use half-size demosaic and a bounded display proxy.
    Final import/export keeps every decoded source pixel. A starting exposure
    lives in metadata so resetting UI exposure does not recreate a dark RAW.
    """
    pixels, metadata = decode_raw(path, preview=bool(max_edge), policy=policy)
    full_size = (metadata['source_width'], metadata['source_height'])
    if max_edge and max(pixels.shape[:2]) > max_edge:
        ratio = max_edge / max(pixels.shape[:2])
        pixels = resize_pixels(pixels, (max(1, round(pixels.shape[1]*ratio)), max(1, round(pixels.shape[0]*ratio))))
    token = file_token(path, full_size)
    with _LOCK:
        ev = _BASELINE_CACHE.get(token)
        if ev is not None:
            _BASELINE_CACHE.move_to_end(token)
    if ev is None:
        measured = baseline_exposure(pixels)
        with _LOCK:
            ev = _BASELINE_CACHE.setdefault(token, measured)
            while len(_BASELINE_CACHE) > 256:
                _BASELINE_CACHE.popitem(last=False)
    metadata.update(source_size=full_size, baseline_exposure_ev=ev,
                    source_color_space='ProPhoto RGB', source_linear=True)
    from desktop.native_spectral import process_editor
    # The Pillow surface is RGB8, so never materialise another full float
    # frame just to display it. Colour conversion is pointwise in the pre
    # stage; independent stripes have exactly the same source coordinates.
    visible = np.empty(pixels.shape, dtype=np.uint8)
    # A bounded preview fits in one dispatch. Repeated tiny GPU transfers add
    # latency at startup; full sources retain bounded conversion scratch.
    block_rows = pixels.shape[0] if max_edge and pixels.shape[0]*pixels.shape[1]<=4_194_304 else 256
    for top in range(0, pixels.shape[0], block_rows):
        block = process_editor(pixels[top:top + block_rows], {}, stage='pre',
                               source_color_space='ProPhoto RGB', source_linear=True,
                               source_size=(pixels.shape[1], pixels.shape[0]), origin=(0, top),
                               exposure_ev=ev, clamp_output=True)
        quantize_display(block, out=visible[top:top + len(block)])
        del block
    return display_image(pixels, full_size=full_size, token=token,
                         metadata=metadata, display_pixels=visible)
