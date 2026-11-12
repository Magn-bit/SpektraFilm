"""Export installed additional films through the canonical product entry point.

Actual JPEG/TIFF exports retain source resolution. Only the comparison sheet is
resized. This does not change production settings, data, or tests.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import platform
import sys
import time

import numpy as np
from PIL import Image, ImageCms, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'vendor'))
from desktop.imaging import export_photo, film_settings, photo_dimensions, read_photo, SRGB
from shared.film_profiles import extension_profiles

STOCKS = [('fujifilm_velvia_50', 'Fujifilm Velvia 50'),
          ('agfa_vista_100', 'Agfa Vista 100'),
          ('fujifilm_natura_1600', 'Fujifilm Natura 1600')]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_report(path, report):
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def comparison(images, path, dimensions):
    margin, gap, tile_width = 24, 24, 344
    tile_height = round(tile_width * dimensions[1] / dimensions[0])
    row_height = tile_height + 48
    sheet = Image.new('RGB', (margin * 2 + tile_width * 2 + gap,
                              100 + row_height * 2 + margin), '#F3F4F0')
    draw = ImageDraw.Draw(sheet)
    font_path = ROOT / 'assets/fonts/SpektraBilingualSerif-Regular.ttf'
    font = ImageFont.truetype(str(font_path), 20)
    small = ImageFont.truetype(str(font_path), 15)
    draw.text((margin, 18), 'Original and additional film profiles', fill='#253127', font=font)
    draw.text((margin, 49), f'Comparison thumbnails only; actual exports: {dimensions[0]} x {dimensions[1]}', fill='#596259', font=small)
    for index, (label, image) in enumerate(images):
        x = margin + (index % 2) * (tile_width + gap)
        y = 90 + (index // 2) * row_height
        thumb = image.resize((tile_width, tile_height), Image.Resampling.LANCZOS)
        sheet.paste(thumb, (x, y))
        draw.text((x, y + tile_height + 10), label, fill='#253127', font=font)
    sheet.save(path, icc_profile=SRGB)
    return list(sheet.size)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'output/mask-reference/source-windsock.jpg')
    parser.add_argument('--output', type=Path, default=ROOT / 'output/film-profile-research/exports-final')
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    if not output.is_relative_to((ROOT / 'output/film-profile-research').resolve()):
        parser.error('Choose an output directory inside output/film-profile-research/.')
    if source.is_relative_to(output):
        parser.error('The source must remain outside the output directory.')
    output.mkdir(parents=True, exist_ok=False)
    source_hash = digest(source)
    dimensions = photo_dimensions(str(source))
    original = read_photo(str(source))
    assert original.size == dimensions
    original_pixels = np.array(original)
    installed = extension_profiles()
    report = {'ok': False, 'checked_utc': datetime.now(timezone.utc).isoformat(),
              'source': str(source), 'source_sha256_before': source_hash,
              'source_dimensions': list(dimensions), 'source_bytes': source.stat().st_size,
              'entry_points': ['desktop.imaging.film_settings', 'desktop.imaging.export_photo'],
              'max_edge': 0, 'preview': False, 'jpeg_quality': 100,
              'platform': platform.platform(), 'exports': [], 'pairwise_differences': [],
              'scope': 'Current installed Windows CPU spectral product path, canonical settings, full source dimensions. One photograph; no measured film fidelity or Android runtime claim.'}
    report_path = output / 'report.json'
    previews = [('Original', original)]
    arrays = {}
    try:
        for stock, label in STOCKS:
            settings = film_settings({'stock': stock})
            assert settings.stock == stock and settings.spectral and settings.film_enabled
            profile = ROOT / 'vendor/spektrafilm/data/profiles' / (stock + '.json')
            assert digest(profile) == installed[stock]['profile_sha256']
            formats = ['jpg', 'tif'] if stock == 'fujifilm_velvia_50' else ['jpg']
            for suffix in formats:
                destination = output / f'{stock}.{suffix}'
                print(f'Exporting {stock} {suffix}: {dimensions[0]}x{dimensions[1]}', flush=True)
                start = time.perf_counter()
                actual_size = export_photo(str(source), str(destination), settings, max_edge=0, quality=100)
                seconds = time.perf_counter() - start
                assert tuple(actual_size) == dimensions
                with Image.open(destination) as image:
                    image.load()
                    assert image.size == dimensions and image.mode == 'RGB'
                    icc = image.info.get('icc_profile')
                    assert icc == SRGB
                    pixel_array = np.array(image)
                    entry = {'stock': stock, 'label': label, 'format': image.format,
                             'path': str(destination), 'dimensions': list(image.size),
                             'mode': image.mode, 'decoded_dtype': str(pixel_array.dtype),
                             'icc_present': True, 'icc_matches_product_srgb': True,
                             'icc_profile_name': ImageCms.getProfileName(ImageCms.ImageCmsProfile(io.BytesIO(icc))).strip(),
                             'icc_sha256': hashlib.sha256(icc).hexdigest(),
                             'bytes': destination.stat().st_size, 'sha256': digest(destination),
                             'export_seconds': round(seconds, 4), 'canonical_settings': asdict(settings),
                             'installed_profile_sha256': digest(profile), 'installed_calibration': installed[stock],
                             'mean_absolute_rgb_difference_from_original_8bit': float(np.abs(pixel_array.astype(float) - original_pixels).mean())}
                    if suffix == 'tif':
                        entry['bits_per_sample'] = list(image.tag_v2.get(258, ()))
                        entry['compression_tag'] = image.tag_v2.get(259)
                    else:
                        arrays[stock] = pixel_array
                        previews.append((label, image.copy()))
                    report['exports'].append(entry)
                assert digest(source) == source_hash
                write_report(report_path, report)
        hashes = [entry['sha256'] for entry in report['exports'] if entry['format'] == 'JPEG']
        assert len(set(hashes)) == 3
        for i, (a, _) in enumerate(STOCKS):
            for b, _ in STOCKS[i + 1:]:
                difference = np.abs(arrays[a].astype(np.int16) - arrays[b].astype(np.int16))
                assert np.any(difference)
                report['pairwise_differences'].append({'a': a, 'b': b,
                    'mean_absolute_rgb_difference_8bit': float(difference.mean()),
                    'max_absolute_rgb_difference_8bit': int(difference.max()),
                    'fraction_pixels_different': float(np.any(difference > 0, axis=2).mean())})
        sheet_path = output / 'comparison.png'
        report['comparison'] = {'path': str(sheet_path), 'dimensions': comparison(previews, sheet_path, dimensions), 'sha256': digest(sheet_path), 'resized_thumbnails_only': True}
        report.update(ok=True, source_unchanged=True, all_outputs_source_resolution=True,
                      all_outputs_product_srgb=True, all_three_jpegs_different=True)
    finally:
        report['source_sha256_after'] = digest(source)
        report['source_unchanged'] = report['source_sha256_after'] == source_hash
        write_report(report_path, report)
        original.close()
        for _, image in previews[1:]:
            image.close()
    print(json.dumps({'ok': report['ok'], 'source_unchanged': report['source_unchanged'],
                      'exports': len(report['exports']), 'report': str(report_path),
                      'comparison': report.get('comparison')}, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
