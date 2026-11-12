"""Utility helpers for the spektrafilm runtime package."""

def load_and_process_raw_file(*args, **kwargs):
    # Keep optional Exiv2 / Lensfun camera metadata dependencies out of the
    # numerical spectral runtime. This shell decodes RAW through rawpy.
    from spektrafilm.utils.raw_file_processor import load_and_process_raw_file as impl
    return impl(*args, **kwargs)

__all__ = ['load_and_process_raw_file']
