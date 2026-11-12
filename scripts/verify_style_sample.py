"""Render the eight real author Hald styles on one local, full-size sample.

The contact sheets are labelled comparison thumbnails/native crops. TIFFs
retain the decoded source dimensions; no photo data leaves this process.
"""
from dataclasses import asdict
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'vendor'))
from desktop.imaging import Settings, read_photo, render, SRGB
from shared.style_presets import catalog, apply_style


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_tiff(image, path):
    started = time.perf_counter()
    image.save(path, compression='tiff_lzw', icc_profile=SRGB)
    elapsed = (time.perf_counter()-started)*1000
    with Image.open(path) as exported:
        assert exported.size == image.size, (path, exported.size, image.size)
        assert exported.mode == 'RGB'
        assert exported.info.get('icc_profile') == SRGB
        np.testing.assert_array_equal(np.asarray(exported), np.asarray(image))
    return round(elapsed, 2)


def contact_sheet(images, rows, path, source_size, *, crop=None, attribution='t3mujinpack / João Almeida · MIT · 原始 Hald 144³ 采样'):
    width, margin, gap, tile_width = 1200, 32, 22, 364
    image_height = round(tile_width*source_size[1]/source_size[0]) if crop is None else 352
    row_height = image_height+76
    height = 124+row_height*3+72
    sheet = Image.new('RGB', (width, height), '#F4F5F1')
    draw = ImageDraw.Draw(sheet)
    font_file = str(ROOT/'assets/fonts/SpektraBilingualSerif-Regular.ttf')
    title = ImageFont.truetype(font_file, 34)
    label = ImageFont.truetype(font_file, 22)
    note = ImageFont.truetype(font_file, 18)
    ink, secondary = '#29352C', '#596357'
    draw.text((margin, 22), '原片与作者色彩风格' if crop is None else '作者色彩风格 · 原生像素局部', font=title, fill=ink)
    subtitle = (f'缩略对比图 · 各款完整 TIFF 均为 {source_size[0]} × {source_size[1]}'
                if crop is None else f'100% 局部裁切 · 同一源片区域 {crop} · 没有放大插值')
    draw.text((margin, 76), subtitle, font=note, fill=secondary)
    for index, (entry, photo) in enumerate(zip(rows, images)):
        x = margin+(index%3)*(tile_width+gap)
        y = 124+(index//3)*row_height
        panel = photo.resize((tile_width, image_height), Image.Resampling.LANCZOS) if crop is None else photo.crop(crop)
        panel_x = x+(tile_width-panel.width)//2
        sheet.paste(panel, (panel_x, y))
        draw.rectangle((panel_x, y, panel_x+panel.width-1, y+panel.height-1), outline='#CAD1C5', width=1)
        draw.text((x, y+image_height+12), entry['name'], font=label, fill=ink)
        description = '同一原片 · 中性设置' if index == 0 else f"平均 RGB 差异 {entry['mean_absolute_rgb_difference_8bit']:.2f} / 255"
        draw.text((x, y+image_height+44), description, font=note, fill=secondary)
    draw.text((margin, height-63), attribution, font=note, fill=secondary)
    draw.text((margin, height-34), '本图用于对照；色彩 LUT 不包含独立颗粒或完整光谱显影。', font=note, fill=secondary)
    sheet.save(path, icc_profile=SRGB)
    return list(sheet.size)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, nargs='?', default=ROOT/'output/mask-reference/source-windsock.jpg')
    parser.add_argument('--output', type=Path, default=ROOT/'output/style-sample')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    source = args.source.resolve()
    source_hash = digest(source)
    photo = read_photo(str(source))
    assert photo.size == (1280, 1920), ('Expected existing windsock sample', photo.size)
    base_settings = Settings(film_enabled=False, lens_correction=False, defringe=False, grain=0, halation=0)
    baseline = render(photo, base_settings)
    reference = np.asarray(photo, dtype=np.uint8)
    np.testing.assert_array_equal(np.asarray(baseline), reference)
    write_tiff(baseline, args.output/'source-srgb.tif')
    selected = [p for p in catalog() if p['kind'] == 'community-hald']
    assert len(selected) == 8
    manifest_path = ROOT/'assets/styles/luts/manifest.json'
    lut_manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    author_sources = {entry['id']:entry for entry in lut_manifest['luts']}
    entries = []
    images = [baseline]
    rows = [dict(name='原片 · sRGB')]
    arrays = {}
    for style in selected:
        settings = Settings.from_mapping(apply_style(asdict(base_settings), style))
        started = time.perf_counter()
        result = render(photo, settings)
        cold_ms = (time.perf_counter()-started)*1000
        started = time.perf_counter()
        warm = render(photo, settings)
        warm_ms = (time.perf_counter()-started)*1000
        np.testing.assert_array_equal(np.asarray(warm), np.asarray(result))
        assert result.size == photo.size
        path = args.output/(style['id']+'.tif')
        encode_ms = write_tiff(result, path)
        pixels = np.asarray(result, dtype=np.uint8)
        delta = pixels.astype(np.float32)-reference
        absolute = np.abs(delta)
        original = author_sources[style['id']]
        entry = dict(id=style['id'], name=style['name'], author=style['author'],
            source_name=original['source_name'], source_url=original['source'],
            source_sha256=original['source_sha256'], rgb8_sha256=original['sha256'],
            source_commit=original['commit'], license=original['license'],
            size=list(result.size), mode='RGB', bits_per_channel=8,
            tiff=str(path.resolve()), tiff_sha256=digest(path),
            mean_absolute_rgb_difference_8bit=round(float(np.mean(absolute)), 5),
            mean_rgb_delta_8bit=[round(float(x), 5) for x in np.mean(delta, axis=(0,1))],
            max_absolute_channel_difference_8bit=int(np.max(absolute)),
            changed_pixel_fraction=round(float(np.mean(np.any(pixels != reference, axis=-1))), 7),
            average_channel_spread_8bit=round(float(np.mean(pixels.max(axis=-1).astype(np.int16)-pixels.min(axis=-1))), 5),
            render_with_initial_lut_load_ms=round(cold_ms, 2), render_cached_lut_ms=round(warm_ms, 2),
            tiff_encode_write_ms=encode_ms, cold_warm_pixels_identical=True,
            tiff_pixels_roundtrip_identical=True, embedded_srgb_profile=True)
        assert entry['mean_absolute_rgb_difference_8bit'] > 0, style['id']
        entries.append(entry)
        rows.append(entry)
        images.append(result)
        arrays[style['id']] = pixels
        print(f"{style['name']}: RGB MAE {entry['mean_absolute_rgb_difference_8bit']}, cached render {warm_ms:.1f} ms", flush=True)
    pairwise = []
    for i, first in enumerate(entries):
        for second in entries[i+1:]:
            mae = float(np.mean(np.abs(arrays[first['id']].astype(np.int16)-arrays[second['id']].astype(np.int16))))
            pairwise.append(dict(first=first['id'], second=second['id'], mean_absolute_rgb_difference_8bit=round(mae, 5)))
    pairwise.sort(key=lambda entry: entry['mean_absolute_rgb_difference_8bit'])
    overview = args.output/'comparison-thumbnails.png'
    detail = args.output/'details-100-percent.png'
    overview_size = contact_sheet(images, rows, overview, photo.size)
    crop = (688, 440, 1040, 792)
    detail_size = contact_sheet(images, rows, detail, photo.size, crop=crop)
    assert digest(source) == source_hash
    report = dict(ok=True, checked_at=datetime.now(timezone.utc).isoformat(),
        source=str(source), source_sha256=source_hash, source_unchanged=True,
        source_size=list(photo.size), source_srgb_baseline_pixels_identical=True,
        baseline_settings=asdict(base_settings), author_styles=8, presets=entries,
        pairwise_rgb_mae=pairwise, manifest_sha256=digest(manifest_path),
        contact_sheet=str(overview.resolve()), contact_sheet_size=overview_size,
        contact_sheet_scope='Downsampled comparison only. Full TIFFs retain 1280x1920; not export-resolution evidence.',
        details=str(detail.resolve()), details_size=detail_size, native_detail_crop=list(crop),
        environment=dict(platform=platform.platform(), python=sys.version.split()[0], processor=platform.processor()),
        timing_scope='Local host, decoded in-memory 1280x1920 sRGB sample. First/cached application renders with film, geometry, masks and corrections disabled. Includes Hald and neutral finishing; excludes input decode, TIFF encoding/writes, UI event/display and Android runtime. One first/cached pair per style, not a statistical latency benchmark.',
        visual_scope='One blue-sky/red-windsock photograph. RGB MAE measures difference, not beauty, film accuracy or popularity. No skin/foliage/night-scene quality claim. Author-supplied Hald colour transforms; no physical grain or spectral equivalence.')
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n', encoding='utf-8')
    lines = ['# 8 款作者风格：本地实片筛选记录', '',
        f'源片：`{source}`；SHA256 `{source_hash}`。检查后源文件未变。', '',
        '所有结果均从同一张 1280×1920 sRGB 原片计算；胶片显影、镜头校正、几何、蒙版及额外调色关闭，仅应用真实作者 Hald。中性基线与解码原片逐像素相同。', '',
        '8 张 TIFF 均保持 1280×1920、RGB 8-bit，并嵌入 sRGB；重新读取后的像素与渲染结果完全一致。冷/缓存两次渲染结果完全一致。', '',
        '| 展示名称（原始文件名见 JSON） | 对原片平均 RGB 差异 /255 | 首次加载并渲染 ms | 缓存后渲染 ms | TIFF 编码写盘 ms |',
        '| --- | ---: | ---: | ---: | ---: |']
    for entry in entries:
        lines.append(f"| {entry['name']} | {entry['mean_absolute_rgb_difference_8bit']:.2f} | {entry['render_with_initial_lut_load_ms']:.2f} | {entry['render_cached_lut_ms']:.2f} | {entry['tiff_encode_write_ms']:.2f} |")
    lines += ['', 'Kodachrome 64 的作者源文件拼作 Kodak Kodakchrome 64；界面更正拼写，完整 source_name、固定 commit 与来源/hash 保存在 JSON。', '',
        '平均差异是对所有像素三个 RGB 通道的绝对差取均值；差异大不等于更好。耗时仅为本机、内存中解码样片的渲染，两次样本不构成中位数/P95 或界面响应测试，编码写盘单独计时。', '',
        f'缩略总览：`{overview.name}`，{overview_size[0]}×{overview_size[1]}，每张照片按比例缩为 364×546；不是最终输出分辨率。', '',
        f'原生像素局部：`{detail.name}`，使用同一源片区域 `{crop}`，每幅 352×352 原生像素，无放大插值。', '',
        '## 候选间差异', '', '以下为本样片中最接近的三对，不代表不同素材上的差异或全局重复：', '']
    names = {entry['id']:entry['name'] for entry in entries}
    for pair in pairwise[:3]:
        lines.append(f"- {names[pair['first']]} / {names[pair['second']]}：RGB MAE {pair['mean_absolute_rgb_difference_8bit']:.2f}/255。")
    lines += ['', '此样片只覆盖蓝天、云和红白风向袋；不得外推人像肤色、绿植或夜景效果。作者原名、MIT 许可、固定 commit、源 PNG 与派生 RGB8 的哈希在 assets/styles 资源清单中保留。公开仓库星数和下载量属于整个项目，不能当成八款单独的人气排名。', '']
    (args.output/'report.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(dict(ok=True,styles=8,source_unchanged=True,dimensions=list(photo.size),
        report=str(args.output/'report.json'),comparison=str(overview)), ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
