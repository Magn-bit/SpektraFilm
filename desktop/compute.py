"""Validated optional acceleration of the existing spectral output gamut stage."""
from __future__ import annotations

import atexit
import logging
import os
import sys
import threading

import numpy as np

_LOCK = threading.RLock()
_GPU = None
_UNAVAILABLE = False
_STATUS = {"gamut_backend": "CPU", "scope": "CAM16-UCS output gamut stage only"}


def status():
    with _LOCK:
        return dict(_STATUS)


def close():
    """Release the process-owned GPU after render workers have stopped."""
    global _GPU
    with _LOCK:
        if _GPU is not None:
            _GPU.close()
            _GPU = None


atexit.register(close)


def compress_output_gamut(rgb, spec, *, output_color_space=None):
    """Use the verified Vulkan implementation where its exact contract applies.

    CPU remains the full-precision reference for unverified spaces/specs/devices.
    An unavailable GPU never changes the spectral model or image dimensions.
    """
    from spektrafilm.utils.gamut_compression import compress_rgb

    global _GPU, _UNAVAILABLE
    mode = os.environ.get("SPEKTRAFILM_COMPUTE", "auto").lower()
    eligible = (sys.platform == "win32" and mode != "cpu"
                and output_color_space == "sRGB" and spec.algorithm == "cam16ucs"
                and tuple(spec.knee) == (0.0, 1.0, 6.0)
                and tuple(spec.lightness_compression or ()) == (0.7, 1.0, 2.2)
                and np.size(rgb) // 3 >= 65536)
    if not eligible:
        return compress_rgb(rgb, spec, output_color_space=output_color_space)
    with _LOCK:
        if not _UNAVAILABLE:
            try:
                if _GPU is None:
                    from desktop.gpu_gamut_prototype import GamutGpuPrototype
                    _GPU = GamutGpuPrototype(backend="Vulkan")
                    _STATUS.update(gamut_backend="Vulkan", adapter=dict(_GPU.adapter.info))
                return _GPU.compress_for_spec(rgb, spec, output_color_space=output_color_space)
            except Exception as error:
                if _GPU is not None:
                    try:
                        _GPU.close()
                    except Exception:
                        logging.getLogger(__name__).debug("GPU cleanup failed", exc_info=True)
                _GPU = None
                _UNAVAILABLE = True
                _STATUS.update(gamut_backend="CPU", gpu_error=str(error))
                logging.getLogger(__name__).warning(
                    "Output gamut GPU unavailable; retaining the CPU spectral formula: %s", error
                )
    return compress_rgb(rgb, spec, output_color_space=output_color_space)
