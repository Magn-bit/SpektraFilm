"""Real public RAW and HSL checks; never upload photos or bundle fixtures."""
from dataclasses import asdict, replace
from pathlib import Path
import hashlib
import json
import platform
import sys
import time
import numpy as np
from PIL import Image
import rawpy

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from desktop.imaging import Settings, read_photo, photo_dimensions, export_preset, render, SRGB
from shared.hsl import HslSettings, HslBand, apply_hsl
from shared.style_presets import import_style_json


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    out=ROOT/'output/offline-engine';out.mkdir(parents=True,exist_ok=True)
    fixture=out/'pixel4xl-raw-pixls-3502.dng'
    before=digest(fixture)
    assert before=='0c03a6c93b4b8593cd0e4426166e6389710007238b82eb23861ef191322f0c54'
    start=time.perf_counter();photo=read_photo(str(fixture));decode_seconds=time.perf_counter()-start
    dims=photo_dimensions(str(fixture));assert photo.size==dims
    preview=read_photo(str(fixture),960)
    assert max(preview.size)<=960 and preview.info['source_size']==dims and preview.size!=photo.size
    assert np.asarray(photo).std()>8
    settings=Settings(film_enabled=False,lens_correction=False,defringe=False,
        hsl=HslSettings(orange=HslBand(saturation=-15,luminance=18),blue=HslBand(saturation=20,luminance=-18)))
    exports=[]
    for preset,suffix in (('JPG_HIGH','.jpg'),('TIFF','.tif'),('RAW','.dng')):
        target=out/('fixture-export-'+preset+suffix)
        started=time.perf_counter();export_preset(str(fixture),str(target),settings,preset)
        elapsed=time.perf_counter()-started
        if preset=='RAW':assert digest(target)==before
        else:
            with Image.open(target) as check:
                assert check.size==dims and check.info.get('icc_profile')==SRGB
        exports.append(dict(preset=preset,dimensions=dims,bytes=target.stat().st_size,seconds=elapsed,
                            source_bytes_unchanged=preset=='RAW',path=str(target)))
    assert digest(fixture)==before
    # True author XMPs remain partial conversions; measure actual added HSL,
    # instead of assuming that accepting the XML implies profile compatibility.
    folder=ROOT/'output/preset-research/practical-xmp-source'
    imported=[]
    for file in folder.rglob('*.xmp'):
        preset=json.loads(import_style_json(file.read_bytes(),file.name))
        assert preset['kind']=='xmp-partial' and any('Adobe' in warning for warning in preset['warnings'])
        hsl=preset['settings']['hsl']
        if any(any(v for v in band.values()) for band in hsl.values()):
            edited=preview.copy()
            pixels=np.asarray(edited).astype(np.float32)/255
            apply_hsl(pixels,hsl)
            delta=np.abs(pixels-np.asarray(preview).astype(np.float32)/255)*255
            imported.append(dict(file=file.name,name=preset['name'],active_hsl=hsl,
                                 rgb_mae_8bit=float(delta.mean()),warnings=preset['warnings']))
    assert len(imported)>=6
    # A representative preview-sized HSL workload, excluding decode/render/UI.
    source=np.random.default_rng(79).random((768,1024,3),dtype=np.float32)
    times=[]
    for _ in range(5):
        pixels=source.copy();start=time.perf_counter();apply_hsl(pixels,settings.hsl);times.append((time.perf_counter()-start)*1000)
    report=dict(ok=True,source=dict(path=str(fixture),sha256=before,unchanged=True,dimensions=dims),
        libraw='.'.join(map(str,rawpy.libraw_version)),rawpy=rawpy.__version__,
        full_decode_seconds=decode_seconds,preview_size=preview.size,exports=exports,
        hsl_786432_pixels_ms=times,xmp_hsl_partial_conversions=imported,
        platform=platform.platform(),limitations=[
            'Public Pixel4XL DNG only; not an A7CR or medium-format runtime test.',
            'LibRaw supplies RAW decoding/camera-matrix development, not Adobe/Capture One editing algorithms.',
            'RGB16 native cache is not a claim of a 16-bit end-to-end editing/export pipeline.',
            'Timing excludes input/display and is not Android performance evidence.'])
    (out/'windows-engine-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(ok=True,dimensions=dims,full_decode_seconds=decode_seconds,
        exports=[dict(preset=e['preset'],seconds=e['seconds']) for e in exports],
        hsl_preview_median_ms=float(np.median(times)),xmp_count=len(imported)),ensure_ascii=False))


if __name__=='__main__':main()
