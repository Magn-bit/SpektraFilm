"""Reproduce RGB8 assets from pinned, original-author Hald PNGs (no resampling)."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import urllib.request

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, default=ROOT / 'output/preset-research/creative-source')
    args = parser.parse_args()
    source = args.source_dir.resolve()
    metadata_path = source / 'manifest.json'
    if not metadata_path.exists():
        metadata_path = ROOT / 'assets/styles/source-manifest.json'
    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    target = ROOT / 'assets/styles/luts'
    target.mkdir(parents=True, exist_ok=True)
    source.mkdir(parents=True, exist_ok=True)
    previous=json.loads((target/'manifest.json').read_text(encoding='utf-8'))['luts'] if (target/'manifest.json').exists() else []
    licenses=metadata.get('licenses',[])
    if not licenses and metadata.get('license_file'):
        licenses=[dict(file=metadata['license_file'],sha256=metadata['license_sha256'],source_url=metadata['license_source_url'])]
    for license in licenses:
        license_path=source/license['file']
        assert license_path.is_relative_to(source)
        if not license_path.exists():
            license_path.write_bytes(urllib.request.urlopen(license['source_url'], timeout=60).read())
        assert digest(license_path.read_bytes())==license['sha256'],'Changed author license'
        shutil.copy2(license_path,target/license['file'])
    entries = []
    for entry in metadata['presets']:
        png_path = source / entry['file']
        if not png_path.exists():
            png_path.write_bytes(urllib.request.urlopen(entry['source_url'], timeout=60).read())
        assert digest(png_path.read_bytes()) == entry['sha256'], entry['id']
        with Image.open(png_path) as image:
            assert image.mode == 'RGB' and list(image.size) == entry['png_size']
            if entry.get('embedded_icc_sha256'):
                assert digest(image.info['icc_profile']) == entry['embedded_icc_sha256']
            assert entry['input_encoding']=='sRGB' and entry['output_encoding']=='sRGB'
            # PIL's row-major bytes are exactly Hald's red-fastest cube samples.
            raw = image.tobytes()
        assert len(raw) == entry['cube_size'] ** 3 * 3
        filename = entry['id'] + '.rgb8'
        (target / filename).write_bytes(raw)
        source_page=entry['source_url']
        if source_page.startswith('https://raw.githubusercontent.com/'):
            parts=source_page.removeprefix('https://raw.githubusercontent.com/').split('/',3)
            source_page='https://github.com/'+parts[0]+'/'+parts[1]+'/blob/'+parts[2]+'/'+parts[3]
        entries.append(dict(id=entry['id'], name=entry['name'], file=filename,
            size=entry['cube_size'], sha256=digest(raw), bytes=len(raw),
            input_encoding='sRGB', output_encoding='sRGB', order='r-fastest', storage='uint8',
            author=entry['author'], source=entry['source_url'], source_page=source_page, source_name=entry['source_name'],
            source_sha256=entry['sha256'], source_file=entry['file'], category=entry['category'],
            commit=entry['commit'], license=entry['license'], license_file=entry['license_file'],
            conversion='Original RGB8 samples reordered as a cube without resampling; trilinear lookup.'))
    (target / 'manifest.json').write_text(json.dumps(dict(version=1, luts=entries), ensure_ascii=False, indent=2)+'\n',encoding='utf-8')
    (target.parent / 'source-manifest.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+'\n',encoding='utf-8')
    keep={entry['file'] for entry in entries}|{license['file'] for license in licenses}
    for old in previous:
        for name in (old['file'],old['license_file']):
            path=(target/name).resolve()
            assert path.is_relative_to(target.resolve()) and path.parent==target.resolve()
            if name not in keep:path.unlink(missing_ok=True)
    print(f'Created {len(entries)} author transforms; {sum(e["bytes"] for e in entries)} raw sample bytes')


if __name__ == '__main__':
    main()
