"""Verify the final original portrait/landscape styles on local real photos.

No uploads. NASA astronaut is used only as a local test fixture, not bundled
with the product. One subject is not a skin-tone-diversity quality audit.
"""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import skimage
from skimage.data import astronaut
from skimage.data._fetchers import data_dir

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from desktop.imaging import Settings, read_photo, render, SRGB
from shared.style_presets import catalog, apply_style

OUT = ROOT/'output/practical-style-sample'
FONT = ROOT/'assets/fonts/SpektraBilingualSerif-Regular.ttf'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_verified_tiff(image, path):
    started = time.perf_counter()
    image.save(path, compression='tiff_lzw', icc_profile=SRGB)
    elapsed = (time.perf_counter()-started)*1000
    with Image.open(path) as loaded:
        assert loaded.size == image.size
        assert loaded.mode == 'RGB'
        assert loaded.info.get('icc_profile') == SRGB
        np.testing.assert_array_equal(np.asarray(loaded), np.asarray(image))
    return round(elapsed, 2)


def comparison(images, rows, category, path):
    # No crop or synthetic reconstruction: all photographs keep their aspect.
    columns = 4 if category == 'landscape' else 5
    tile_width = 330 if category == 'landscape' else 260
    image_height = round(images[0].height*tile_width/images[0].width)
    margin, gap, top, footer, captions = 32, 20, 114, 80, 70
    row_count = math.ceil(len(images)/columns)
    row_height = image_height+captions
    width = margin*2+columns*tile_width+(columns-1)*gap
    height = top+row_count*row_height+footer
    sheet = Image.new('RGB', (width,height), '#F4F5F1')
    draw = ImageDraw.Draw(sheet)
    title_font = ImageFont.truetype(str(FONT),32)
    label_font = ImageFont.truetype(str(FONT),22)
    note_font = ImageFont.truetype(str(FONT),17)
    ink, muted = '#29352C', '#596357'
    title = '原创实用风格 · 风光' if category == 'landscape' else '原创实用风格 · 人像'
    draw.text((margin,22),title,font=title_font,fill=ink)
    source_size = f'{images[0].width} × {images[0].height}'
    draw.text((margin,72),f'缩略对比 · 原尺寸 TIFF {source_size} · 仅套用参数风格，胶片关闭',font=note_font,fill=muted)
    for i,(photo,row) in enumerate(zip(images,rows)):
        x = margin+(i%columns)*(tile_width+gap)
        y = top+(i//columns)*row_height
        panel = photo.resize((tile_width,image_height),Image.Resampling.LANCZOS)
        sheet.paste(panel,(x,y))
        draw.rectangle((x,y,x+tile_width-1,y+image_height-1),outline='#D0D6CA')
        draw.text((x,y+image_height+12),row['name'],font=label_font,fill=ink)
        caption = '原片 · sRGB' if i == 0 else f"RGB 平均差异 {row['rgb_mae_8bit']:.2f} /255"
        draw.text((x,y+image_height+42),caption,font=note_font,fill=muted)
    draw.text((margin,height-66),'SpektraFilm 原创参数 · 非外部作者预设，不宣称还原商业软件',font=note_font,fill=muted)
    caveat = ('样片仅有蓝天、云与红白风向袋，不能验证森林、海水、城市或夜景的全面效果。'
              if category == 'landscape' else 'NASA Eileen Collins / Public Domain · 单人样片，不代表专业肤色多样性验收。')
    draw.text((margin,height-37),caveat,font=note_font,fill=muted)
    sheet.save(path,icc_profile=SRGB)
    return list(sheet.size)


def verify_group(photo, presets, category):
    base = Settings(film_enabled=False, grain=0, halation=0,
                    lens_correction=False, defringe=False)
    original = np.asarray(photo,dtype=np.uint8)
    baseline = render(photo,base)
    np.testing.assert_array_equal(np.asarray(baseline),original)
    save_verified_tiff(photo,OUT/(category+'-original.tif'))
    images = [photo]
    rows = [dict(name='原片')]
    records = []
    for preset in presets:
        assert preset['kind'] == 'original' and preset['author'] == 'SpektraFilm'
        assert not preset['settings'].get('look_lut')
        settings = Settings.from_mapping(apply_style(asdict(base),preset))
        assert not settings.film_enabled and not settings.look_lut
        started = time.perf_counter()
        output = render(photo,settings)
        elapsed = (time.perf_counter()-started)*1000
        pixels = np.asarray(output,dtype=np.uint8)
        assert output.size == photo.size
        delta = np.abs(pixels.astype(np.float32)-original)
        path = OUT/(preset['id']+'.tif')
        encode_ms = save_verified_tiff(output,path)
        record = dict(id=preset['id'],name=preset['name'],category=category,
            author=preset['author'],kind=preset['kind'],description=preset['description'],
            settings=asdict(settings),source_size=list(photo.size),output_size=list(output.size),
            rgb_mae_8bit=round(float(delta.mean()),5),
            mean_rgb_delta_8bit=[round(float(v),5) for v in (pixels.astype(np.float32)-original).mean(axis=(0,1))],
            white_clipped_pixel_fraction=round(float(np.mean(np.all(pixels==255,axis=-1))),7),
            black_clipped_pixel_fraction=round(float(np.mean(np.all(pixels==0,axis=-1))),7),
            changed_pixel_fraction=round(float(np.mean(np.any(pixels!=original,axis=-1))),7),
            render_ms=round(elapsed,2),tiff_encode_write_ms=encode_ms,
            tiff=str(path),tiff_sha256=digest(path),tiff_roundtrip_pixels_identical=True,
            embedded_srgb=True,bits_per_channel=8)
        assert record['rgb_mae_8bit'] > 0
        records.append(record)
        images.append(output)
        rows.append(record)
        print(f"{category}/{preset['name']}: {elapsed:.1f}ms / MAE {record['rgb_mae_8bit']:.2f}",flush=True)
    shot=OUT/(category+'-comparison.png')
    size=comparison(images,rows,category,shot)
    return dict(styles=records,comparison=str(shot),comparison_size=size,
                baseline_pixels_identical=True,source_size=list(photo.size))


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    all_presets = catalog()
    assert all_presets[0]['id']=='none'
    presets=[item for item in all_presets if item['kind']=='original']
    assert len(presets)==18
    portrait = [p for p in presets if p.get('category')=='portrait']
    landscape = [p for p in presets if p.get('category')=='landscape']
    assert len(portrait)==8 and len(landscape)==10
    actual_catalog_hash = digest(ROOT/'assets/styles/presets.json')
    landscape_source = ROOT/'output/mask-reference/source-windsock.jpg'
    landscape_hash = digest(landscape_source)
    landscape_photo = read_photo(str(landscape_source))
    assert landscape_photo.size==(1280,1920)
    astronaut_source = Path(data_dir)/'astronaut.png'
    astronaut_hash = digest(astronaut_source)
    astronaut_pixels = astronaut()
    assert astronaut_pixels.shape==(512,512,3)
    portrait_photo = Image.fromarray(astronaut_pixels)
    # This local evidence copy is not added to product assets or a release.
    portrait_copy = OUT/'nasa-astronaut-local-fixture.png'
    portrait_photo.save(portrait_copy)
    results = dict(landscape=verify_group(landscape_photo,landscape,'landscape'),
                   portrait=verify_group(portrait_photo,portrait,'portrait'))
    assert digest(landscape_source)==landscape_hash
    assert digest(astronaut_source)==astronaut_hash
    assert digest(ROOT/'assets/styles/presets.json')==actual_catalog_hash
    report = dict(ok=True,checked_at=datetime.now(timezone.utc).isoformat(),
        preset_catalog_sha256=actual_catalog_hash,total_styles=19,original_styles=18,
        sources=dict(landscape=dict(path=str(landscape_source),sha256=landscape_hash,unchanged=True),
            portrait=dict(path=str(astronaut_source),sha256=astronaut_hash,unchanged=True,
                local_fixture=str(portrait_copy),person='Eileen Collins',
                source='https://flic.kr/p/r9qvLn',license='Public Domain; no known copyright restrictions',
                provenance='scikit-image data.astronaut documented NASA Great Images database photograph',
                not_bundled_with_product=True)),
        results=results,environment=dict(platform=platform.platform(),python=sys.version.split()[0],
            skimage=skimage.__version__,processor=platform.processor()),
        scope='Current SpektraFilm ORIGINAL parameter styles, eight portrait/ten landscape plus a no-style row. Actual image dimensions retained in RGB8 TIFFs; comparison images are labelled thumbnails. No external author/film LUT, no film simulation, lens corrections, geometry or masks. Real local samples only; no network uploads.',
        limitation='One NASA astronaut image is not a professional skin-tone-diversity or beauty-retouch audit; no face/skin masking. The landscape sample has sky/cloud/red windsock only and cannot verify forest/coast/city/night scene quality. Soft-light presets alter global tonal relationships, not skin texture or selective skin smoothing.',
        timing_scope='One render per style on this host from decoded in-memory source; excludes decode, TIFF writes, input/display latency and Android runtime. These are not statistical benchmark results.')
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# 原创实用风格：当前目录实片验证', '',
        '本版当前目录为 **18 款 SpektraFilm 原创参数风格：8 人像 + 10 风光**，首项为不覆盖参数的“无预设”，不包含胶片型号 LUT、CreativePack 实验风格或部分转换的外部作者 XMP。', '',
        '所有结果由当前 catalog 与应用 render() 实际计算；关闭胶片和额外校正、蒙版、几何，原片/目录文件 hash 不变。不是静态命名展示。', '',
        '| 分类 | 风格 | 原尺寸 TIFF | RGB 平均绝对差 /255 | 渲染 ms | 编码写盘 ms |',
        '| --- | --- | --- | ---: | ---: | ---: |']
    for group in results.values():
        for p in group['styles']:
            dims='×'.join(map(str,p['output_size']))
            lines.append(f"| {p['category']} | {p['name']} | {dims} | {p['rgb_mae_8bit']:.2f} | {p['render_ms']:.2f} | {p['tiff_encode_write_ms']:.2f} |")
    lines += ['', '全部 TIFF 为 RGB 8-bit 并嵌入 sRGB，回读像素与结果逐像素相同；未把缩略对比图作为全尺寸输出，也不声称已核验16-bit输出。', '',
        '风光原图：现有用户样片 `output/mask-reference/source-windsock.jpg`，1280×1920，源 SHA256 `'+landscape_hash+'`。', '',
        '人像：本机 scikit-image data.astronaut()，NASA Eileen Collins，512×512。其文档声明公共领域、无已知版权限制，原始出处 https://flic.kr/p/r9qvLn 。仅用于本地研发测试，不放入软件 assets 或发布包。', '',
        '## 验证边界', '',
        '- 单人 NASA 样片不是专业肤色多样性或人像美化验收；不存在脸部识别、皮肤局部蒙版或磨皮。柔光名称表示全局明暗过渡，不伪称皮肤纹理处理。',
        '- 风向袋照片覆盖蓝天、云与红白主体，不含森林、海水、城市或夜景；只能确认六款参数真实起效、输出完整，不能对相应场景质量作全面结论。',
        '- RGB 差异只衡量变化，不能当作审美评分、人气或准确度。单次渲染记录不代表输入延迟、60fps、Android 性能或所有设备。',
        '- 缩略图 `landscape-comparison.png` / `portrait-comparison.png` 保留完整画面比例，无裁切主体、生成照片或重绘。', '']
    (OUT/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(dict(ok=True,total_styles=10,report=str(OUT/'report.json'),
        landscape_comparison=results['landscape']['comparison'],portrait_comparison=results['portrait']['comparison']),ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
