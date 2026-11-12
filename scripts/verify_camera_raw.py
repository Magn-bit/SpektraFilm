"""Reproducible multi-camera RAW checks. Never writes to an input file.

Downloads are opt-in, kept under output/, and SHA-256 checked against the saved
raw.pixls.us public-domain catalogue. Results describe tested files, not all
compression variants or subjective color accuracy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import itertools
from pathlib import Path
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'vendor')]

import numpy as np
import rawpy
from desktop.imaging import read_photo


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def samples(directory):
    catalogue = json.loads((ROOT / 'output/offline-engine/raw-pixls-repository.json').read_text(encoding='utf-8'))['data']
    for file_id, filename in ((3773, 'fujifilm-gfx100.raf'), (6565, 'hasselblad-x2d100c.3fr'), (3900, 'phaseone-iq4-150mp.iiq')):
        row = next(row for row in catalogue if f'/getfile.php/{file_id}/nice/' in row[7])
        assert 'publicdomain/zero' in row[5]
        url = re.search(r"href='([^']+)'", row[7]).group(1)
        expected = re.search(r"Checksum'>([a-f0-9]{64})", row[7]).group(1)
        destination = directory / filename
        if not destination.exists() or digest(destination) != expected:
            print(f'Downloading {row[0]} {row[1]}', flush=True)
            partial = destination.with_suffix(destination.suffix + '.part')
            try:
                request = urllib.request.Request(urllib.parse.quote(url, safe=':/'), headers={'User-Agent': 'SpektraFilm RAW validation'})
                with urllib.request.urlopen(request, timeout=60) as response, partial.open('wb') as output:
                    expected_length = int(response.headers.get('Content-Length', '0'))
                    while block := response.read(1024 * 1024):
                        output.write(block)
                actual = digest(partial)
                assert (not expected_length or partial.stat().st_size == expected_length) and actual == expected, (
                    f'Downloaded sample failed verification: {partial.stat().st_size}/{expected_length} bytes, '
                    f'SHA-256 {actual}, expected {expected}')
                partial.replace(destination)
            finally:
                partial.unlink(missing_ok=True)
        yield destination, {'url': url, 'sha256': expected, 'camera': f'{row[0]} {row[1]}', 'encoding': row[2], 'license': 'CC0'}


def verify(path, directory, full):
    before = digest(path)
    started = time.perf_counter()
    with rawpy.imread(str(path)) as raw:
        size = (raw.sizes.width, raw.sizes.height)
        if raw.sizes.flip in (5, 6):
            size = size[::-1]
        metadata = {'sensor': [raw.sizes.raw_width, raw.sizes.raw_height],
                    'source_size': list(size), 'wb': list(raw.camera_whitebalance),
                    'black': list(raw.black_level_per_channel), 'white': raw.white_level,
                    'colors': raw.num_colors}
    with read_photo(str(path), 1600) as preview:
        assert preview.info['source_size'] == size
        assert max(preview.size) <= 1600
        assert preview.width > 0 and preview.height > 0
        values = np.asarray(preview)
        metadata['preview_size'] = list(preview.size)
        metadata['preview_channel_mean'] = (values.mean(axis=(0, 1)) / 255).tolist()
        metadata['preview_seconds'] = time.perf_counter() - started
        preview.save(directory / (path.stem + '-preview.jpg'), quality=95, subsampling=0)
    if full:
        started = time.perf_counter()
        with read_photo(str(path)) as image:
            assert image.size == size, f'Full RAW was reduced: {image.size} != {size}'
            metadata['full_size'] = list(image.size)
            metadata['full_seconds'] = time.perf_counter() - started
    assert digest(path) == before, 'Source was modified'
    return {'path': str(path), 'sha256': before, **metadata}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--download-medium-format', action='store_true')
    parser.add_argument('--full', action='store_true')
    parser.add_argument('paths', nargs='*', type=Path)
    arguments = parser.parse_args()
    directory = ROOT / 'output/camera-raw-validation'
    directory.mkdir(parents=True, exist_ok=True)
    sources = [(path, {}) for path in arguments.paths]
    if arguments.download_medium_format:
        sources = itertools.chain(sources, samples(directory))
    results = []
    for path, origin in sources:
        print(f'Checking {path.name}', flush=True)
        result = {**verify(path.resolve(), directory, arguments.full), **origin}
        results.append(result)
        (directory / 'report.json').write_text(json.dumps({'rawpy': rawpy.__version__, 'libraw': rawpy.libraw_version, 'samples': results}, indent=2, ensure_ascii=False), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
