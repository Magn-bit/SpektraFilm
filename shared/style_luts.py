"""Author Hald transforms: original RGB8 samples, bounded trilinear lookup.

The flattened Hald has red varying fastest, then green, then blue. It is
stored as [b,g,r,channel] without resampling or converting all samples to
float32. Only bounded pixel coordinates and interpolated outputs become floats.
"""
from __future__ import annotations

from collections import OrderedDict
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import sys
import threading

import numpy as np

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
LUT_ROOT = ROOT / 'assets/styles/luts'
_CACHE = OrderedDict()
_LOCK = threading.RLock()
CHUNK_PIXELS = 32768


@lru_cache(maxsize=1)
def manifest():
    return json.loads((LUT_ROOT / 'manifest.json').read_text(encoding='utf-8'))


def known_lut(ident):
    if not ident:
        return None
    return next((item for item in manifest()['luts'] if item['id'] == ident), None)


def lut_for_id(ident):
    entry = known_lut(ident)
    if entry is None:
        if ident:
            raise ValueError('未知的作者色彩预设：' + str(ident))
        return None
    path = (LUT_ROOT / entry['file']).resolve()
    if not path.is_relative_to(LUT_ROOT.resolve()):
        raise ValueError('预设资源路径无效')
    return load_lut(path, int(entry['size']), entry['sha256'])


def load_lut(path, size=None, sha256=None):
    """Load a validated RGB8 cube. Android supplies its checked private path."""
    path = Path(path).resolve()
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size, size, sha256)
    with _LOCK:
        result = _CACHE.pop(key, None)
        if result is not None:
            _CACHE[key] = result
            return result
        count = stat.st_size // 3
        side = int(round(count ** (1 / 3))) if size is None else int(size)
        if not 2 <= side <= 256 or stat.st_size != side ** 3 * 3:
            raise ValueError('作者色彩资源尺寸无效')
        raw = np.fromfile(path, dtype=np.uint8)
        if sha256 is not None and hashlib.sha256(raw).hexdigest() != sha256:
            raise ValueError('作者色彩资源校验失败')
        result = raw.reshape(side, side, side, 3)
        result.flags.writeable = False
        _CACHE[key] = result
        while len(_CACHE) > 2:
            _CACHE.popitem(last=False)
        return result


def apply_lut(rgb, cube, chunk_pixels=CHUNK_PIXELS, strength=1.):
    """Transform float RGB in place in encoded sRGB; return the same array."""
    if cube is None or strength<=0:
        return rgb
    from scipy.ndimage import map_coordinates
    if not isinstance(rgb, np.ndarray) or rgb.dtype not in (np.dtype('float32'),np.dtype('float64')) or rgb.shape[-1] != 3:
        raise ValueError('色彩预设输入必须为浮点 RGB')
    n = cube.shape[0]
    if cube.shape != (n, n, n, 3) or cube.dtype != np.uint8 or n < 2:
        raise ValueError('色彩预设必须为 RGB8 立方体')
    if chunk_pixels < 1:
        raise ValueError('无效的色彩处理块大小')
    # The renderers supply contiguous row strips; reject a silent reshape copy.
    if not rgb.flags.c_contiguous:
        raise ValueError('色彩预设输入必须连续')
    flat = rgb.reshape(-1, 3)
    strength=max(0.,min(1.,float(strength)))
    for start in range(0, len(flat), chunk_pixels):
        target = flat[start:start + chunk_pixels]
        original=target.copy() if strength<1 else None
        positions = np.clip(target, 0, 1).astype(np.float32,copy=False) * (n - 1)
        coordinates = positions[:, ::-1].T
        # Compiled first-order lookup reads original uint8 corners directly.
        # Float output prevents intermediate 8-bit rounding; prefilter=False
        # avoids allocating a whole floating-point/spline copy of the LUT.
        for channel in range(3):
            target[:,channel] = map_coordinates(cube[:,:,:,channel],coordinates,
                output=np.float32,order=1,mode='nearest',prefilter=False) / 255
        if original is not None:
            target-=original;target*=strength;target+=original
    return rgb


def apply_style_lut(rgb, ident=''):
    return apply_lut(rgb, lut_for_id(ident)) if ident else rgb

