"""Validate an actual RAW through the current source-resolution film exporter.

This is a Windows host test, not Android runtime or Adobe visual equivalence.
The source is read only; reports and exports must stay in the project output/.
"""
import argparse
import hashlib
import json
import platform
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

from PIL import Image
import rawpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'vendor'))
from desktop.imaging import film_settings, photo_dimensions, read_photo, export_preset, SRGB
from benchmark_spectral_export import process_memory_mib


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--tiff', action='store_true')
    parser.add_argument('--compute', choices=('auto','cpu'), default='auto')
    args = parser.parse_args()
    os.environ['SPEKTRAFILM_COMPUTE']=args.compute
    source = args.source.resolve()
    output = args.output_dir.resolve()
    if not output.is_relative_to((ROOT / 'output').resolve()):
        parser.error('Output directory must be within this project output/.')
    if source.is_relative_to(output):
        parser.error('Keep the original outside the output directory.')
    output.mkdir(parents=True, exist_ok=False)
    before = digest(source)
    dimensions = photo_dimensions(str(source))
    preview = read_photo(str(source), 800)
    assert tuple(preview.info['source_size']) == dimensions
    assert max(preview.size) <= 800 and preview.size != dimensions
    preview_size = preview.size
    preview.close()
    settings = film_settings()
    report = dict(ok=False, source=str(source), source_sha256=before,
                  dimensions=dimensions, preview_size=preview_size,
                  settings=asdict(settings), exports=[], platform=platform.platform(),
                  rawpy=rawpy.__version__, libraw=rawpy.libraw_version,
                  compute_requested=args.compute,
                  scope='Current Windows source code, full spectral RAW export including full RAW decode, render, encode and write; not Android runtime or Adobe equivalence')
    report_path = output / 'report.json'
    try:
        formats = [('JPG_HIGH', 'jpg')]
        if args.tiff:
            formats.append(('TIFF', 'tif'))
        formats.append(('RAW', source.suffix.lstrip('.')))
        for preset, suffix in formats:
            destination = output / (source.stem + '_Portra 400.' + suffix)
            print(f'Exporting {preset}: {dimensions[0]}x{dimensions[1]}', flush=True)
            start = time.perf_counter()
            export_preset(str(source), str(destination), settings, preset)
            elapsed = time.perf_counter() - start
            if preset == 'RAW':
                assert digest(destination) == before
            else:
                with Image.open(destination) as image:
                    assert image.size == dimensions
                    assert image.info.get('icc_profile') == SRGB
                    image.verify()
            report['exports'].append(dict(preset=preset, path=str(destination),
                dimensions=dimensions, bytes=destination.stat().st_size,
                seconds=round(elapsed, 3), sha256=digest(destination)))
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        assert digest(source) == before
        report.update(ok=True, source_unchanged=True)
    finally:
        from desktop.compute import status
        report['compute']=status()
        _, report['process_peak_working_set_mib'] = process_memory_mib()
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
