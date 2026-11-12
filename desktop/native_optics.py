"""Bounded native high-precision LCP remapping and conservative GPU defringe."""
from __future__ import annotations
import ctypes as ct
import math
import os
import sys
import numpy as np

from .native_spectral import (_Image, _LOCK, _get_engine, _mapped_result,
                              _normalized, NativeSpectralError)
from .raw_development import _library as _raw_library

_LAST = {}


def available():
    if sys.platform!='win32' or os.environ.get('SPEKTRAFILM_COMPUTE','auto').lower()=='cpu':
        return False
    try:
        with _LOCK:
            engine=_get_engine()
            return (engine is not None and hasattr(engine.lib,'spk_editor_defringe')
                    and hasattr(_raw_library(),'spk_lens_correct'))
    except (OSError,AttributeError):
        return False


def _destination(shape):
    return _mapped_result(shape) if shape[0]*shape[1] > 80_000_000 else np.empty(shape, dtype=np.float32)


def _model_values(model, width, height, metadata, sensor):
    equivalent = metadata.get('focal_35mm') or metadata['focal_length']*sensor
    fallback = equivalent/35
    fx, fy = (model.fx or fallback)*max(width,height), (model.fy or fallback)*max(width,height)
    if min(fx,fy) <= 0 or not math.isfinite(fx+fy):
        raise ValueError('invalid_focal_scale')
    return [fx,fy,model.cx*width,model.cy*height,model.k1,model.k2,model.k3,
            model.p1,model.p2,model.scale]


def correct_lens(pixels, base, chrom, metadata, sensor, zoom, *, out=None):
    """Apply the existing LCP model to already EXIF-oriented source samples.

    Coordinates use float64 in native CPU code, all channels are remapped in
    one parallel pass, and no un-oriented whole-frame copy is allocated.
    uint8/uint16 samples are accepted directly; output is always float32 RGB.
    """
    source = np.asarray(pixels)
    if source.ndim != 3 or source.shape[2] != 3 or min(source.shape[:2]) < 2:
        raise ValueError('image_too_small')
    dtype = {np.dtype('uint8'):1,np.dtype('uint16'):2,np.dtype('float32'):3}.get(source.dtype)
    if dtype is None:
        source = np.asarray(source,dtype=np.float32);dtype=3
    source = np.ascontiguousarray(source)
    orientation = int(metadata.get('orientation',1))
    width,height=source.shape[1],source.shape[0]
    rw,rh=(height,width) if orientation>=5 else (width,height)
    green = chrom[1] if chrom else base
    red = chrom[0] if chrom else base
    blue = chrom[2] if chrom else base
    models=(ct.c_double*40)(*sum((_model_values(model,rw,rh,metadata,sensor) for model in (base,green,red,blue)),[]))
    if out is None:out=_destination(source.shape)
    if out.dtype!=np.float32 or out.shape!=source.shape or not out.flags.c_contiguous or np.shares_memory(source,out):
        raise ValueError('lens output must be a separate contiguous float32 RGB frame')
    elapsed=ct.c_double()
    with _LOCK:
        library=_raw_library();function=library.spk_lens_correct
        function.argtypes=[ct.c_void_p,ct.c_uint32,ct.c_uint32,ct.c_uint32,ct.c_uint32,
                           ct.POINTER(ct.c_double),ct.c_int32,ct.c_double,ct.POINTER(ct.c_float),ct.POINTER(ct.c_double)]
        function.restype=ct.c_int32
        status=function(ct.c_void_p(source.ctypes.data),width,height,dtype,orientation,models,int(chrom is not None),float(zoom),out.ctypes.data_as(ct.POINTER(ct.c_float)),ct.byref(elapsed))
        if status:raise NativeSpectralError('原生镜头映射参数或内存无效')
    _LAST['lens_ms']=elapsed.value
    return out


def defringe(pixels, *, out=None):
    """Return corrected float RGB and corrected-pixel count; four-row halo."""
    source=_normalized(pixels)
    if source.ndim!=3 or source.shape[2]!=3 or min(source.shape[:2])<1:
        raise ValueError('defringe requires H×W×3 pixels')
    if out is None:out=_destination(source.shape)
    if out.dtype!=np.float32 or out.shape!=source.shape or not out.flags.c_contiguous:
        raise ValueError('defringe output must be contiguous float32 RGB')
    height,width=source.shape[:2];image=_Image(source.ctypes.data_as(ct.POINTER(ct.c_float)),width,height,3)
    count=ct.c_uint64();elapsed=ct.c_double()
    with _LOCK:
        engine=_get_engine()
        if engine is None:raise NativeSpectralError('原生去紫边引擎不可用')
        function=engine.lib.spk_editor_defringe
        function.argtypes=[ct.c_void_p,ct.POINTER(_Image),ct.POINTER(ct.c_float),ct.POINTER(ct.c_uint64),ct.POINTER(ct.c_double)]
        function.restype=ct.c_int32
        status=function(engine.handle,ct.byref(image),out.ctypes.data_as(ct.POINTER(ct.c_float)),ct.byref(count),ct.byref(elapsed))
        if status:raise NativeSpectralError(engine.error())
    _LAST['defringe_ms']=elapsed.value
    return out,int(count.value)


def timings():
    return dict(_LAST)
