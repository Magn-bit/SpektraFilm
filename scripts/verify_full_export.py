"""Measure a complete, unscaled RAW -> native spectrum -> TIFF16 export once."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'vendor')]


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def peak_mib():
    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in
            ('PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage',
             'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
             'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]
    counts = Counters()
    counts.cb = ctypes.sizeof(counts)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    query = ctypes.WinDLL('psapi').GetProcessMemoryInfo
    query.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    if not query(kernel.GetCurrentProcess(), ctypes.byref(counts), counts.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return counts.PeakWorkingSetSize / 1024 ** 2


def one(source, folder):
    import numpy as np
    import tifffile
    from desktop import imaging, native_spectral
    from dataclasses import asdict
    folder.mkdir(parents=True, exist_ok=True)
    output = folder / (source.stem + '_Portra 400.tif')
    before = digest(source)
    dimensions = list(imaging.photo_dimensions(str(source)))
    timings = {}
    for name in ('read_photo', 'render_pixels'):
        original = getattr(imaging, name)
        def timed(*args, _name=name, _original=original, **kwargs):
            start = time.perf_counter()
            try:
                return _original(*args, **kwargs)
            finally:
                timings[_name + '_seconds'] = time.perf_counter() - start
        setattr(imaging, name, timed)
    settings = imaging.film_settings(imaging.Settings())
    started = time.perf_counter()
    size = list(imaging.export_preset(str(source), str(output), settings, 'TIFF'))
    seconds = time.perf_counter() - started
    timings['encode_write_seconds'] = max(0., seconds - sum(timings.values()))
    backend = native_spectral.backend_info()
    assert backend['available'] and backend['backend']['render_core'] == 'native-vulkan', backend
    assert size == dimensions, (size, dimensions)
    with tifffile.TiffFile(output) as tiff:
        page = tiff.pages[0]
        assert [page.imagewidth, page.imagelength] == dimensions
        assert page.dtype == np.dtype('uint16') and page.samplesperpixel == 3
        assert page.bitspersample == 16 and page.compression == 32946
        assert page.tags.get(34675) is not None, 'Missing ICC profile'
        first_strip = next(page.segments())[0]
        unique_levels = int(np.unique(first_strip).size)
        assert unique_levels > 256, unique_levels
        assert np.ptp(first_strip) > 1024, 'Unexpected flat or dark output'
    unchanged = digest(source) == before
    assert unchanged, 'Source file changed'
    case = dict(source=str(source), source_sha256=before, source_unchanged=unchanged,
                dimensions=dimensions, settings=asdict(settings),
                decode_seconds=timings['read_photo_seconds'],
                process_peak_working_set_mib=peak_mib(),
                exports=[dict(preset='TIFF', path=str(output), sha256=digest(output),
                              dimensions=size, seconds=seconds, bits_per_sample=16,
                              bytes=output.stat().st_size, first_strip_levels=unique_levels,
                              backend='native-vulkan', timings=timings, native=backend)])
    return case


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', action='append', required=True)
    parser.add_argument('--output', default='output/full-export-0.4.0')
    parser.add_argument('--child', action='store_true')
    args = parser.parse_args()
    folder = (ROOT / args.output).resolve()
    if args.child:
        source = Path(args.source[0]).resolve()
        result = one(source, folder)
        (folder / 'case.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({k: result[k] for k in ('source', 'dimensions', 'decode_seconds', 'process_peak_working_set_mib')}, ensure_ascii=False), flush=True)
        print('EXPORT_SECONDS', result['exports'][0]['seconds'], flush=True)
        return
    folder.mkdir(parents=True, exist_ok=True)
    cases = []
    for index, value in enumerate(args.source):
        target = folder / ('case-' + str(index + 1))
        subprocess.run([sys.executable, '-X', 'utf8', __file__, '--child', '--source', value,
                        '--output', str(target)], cwd=ROOT, check=True)
        cases.append(json.loads((target / 'case.json').read_text(encoding='utf-8')))
        report = dict(ok=True, version='0.4.0', backend='native-vulkan',
                      scope='Current Windows source: full RAW decode, complete native spectral processing, TIFF16 Deflate encoding, fsync and atomic publication; first render per process',
                      cases=cases)
        (folder / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
