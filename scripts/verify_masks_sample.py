"""Render a real user-selected sample and record local preview timings."""
from dataclasses import asdict, replace
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'vendor'))
from desktop.imaging import Settings, read_photo, render, SRGB
from shared.local_masks import MaskLayer, MaskStroke, apply_masks, rasterize_mask
from shared.color_tools import CurveSet, ColorGrading, TonalGrade


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'output/mask-sample')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    original_hash=hashlib.sha256(args.source.read_bytes()).hexdigest()
    image=read_photo(str(args.source))
    subject=MaskLayer('windsock','风向袋 · 径向',exposure=.22,temperature=4,saturation=8,
        shadows=6,kind='radial',center=(.686,.311),radius_x=.168,radius_y=.024,
        rotation=3,feather=.8)
    sky=MaskLayer('clouds','天空 · 线性渐变',exposure=-.16,temperature=-3,
        highlights=-12,kind='linear',start=(.5,.6),end=(.5,.03))
    settings=Settings(film_enabled=False,exposure=.2,contrast=3,saturation=0,vibrance=6,
        lens_correction=False,defringe=False,
        curves=CurveSet(master=((0.,0.),(.22,.2),(.65,.69),(1.,1.)),
                        luma=((0.,0.),(.45,.48),(1.,1.))),
        grading=ColorGrading(shadows=TonalGrade(220,5),midtones=TonalGrade(36,2),
                             highlights=TonalGrade(46,5)))
    global_only=render(image,settings)
    full=render(image,replace(settings,masks=(sky,subject)))
    full.save(args.output/'windsock-local.tif',compression='tiff_lzw',icc_profile=SRGB)
    full.save(args.output/'windsock-local.jpg',quality=100,subsampling=0,icc_profile=SRGB)
    alpha=rasterize_mask(subject,image.width,image.height)
    raw=np.asarray(global_only,dtype=np.float32)
    overlay=raw*(1-alpha[:,:,None]*.38)+np.array([198,75,65],dtype=np.float32)*alpha[:,:,None]*.38
    overlay=Image.fromarray(np.rint(overlay).clip(0,255).astype(np.uint8))
    overlay.save(args.output/'mask-coverage.png')
    panel_width=420
    panel_height=round(image.height*panel_width/image.width)
    sheet=Image.new('RGB',(panel_width*3+64,panel_height+78),'#f4f5f1')
    draw=ImageDraw.Draw(sheet)
    font=ImageFont.truetype(str(ROOT/'assets/fonts/SpektraBilingualSerif-Regular.ttf'),18)
    for index,(label,photo) in enumerate([('原片',image),('曲线与三向调色',global_only),('径向与线性蒙版',full)]):
        x=16+index*(panel_width+16)
        sheet.paste(photo.resize((panel_width,panel_height),Image.Resampling.LANCZOS),(x,16))
        draw.text((x,32+panel_height),label,font=font,fill='#29352c')
    sheet.save(args.output/'comparison.png')
    # Native pixel crop: do not enlarge a downsampled panel to suggest detail.
    crop=(650, 535, 1130, 775)
    details=Image.new('RGB', (480*3+64, 240+72), '#f4f5f1')
    labels=ImageDraw.Draw(details)
    for index,(label,photo) in enumerate([('原片 · 100%',image),('基础调整 · 100%',global_only),('局部蒙版 · 100%',full)]):
        x=16+index*(480+16)
        details.paste(photo.crop(crop),(x,16))
        labels.text((x,272),label,font=font,fill='#29352c')
    details.save(args.output/'details-100-percent.png')
    with Image.open(args.output/'windsock-local.tif') as exported:
        np.testing.assert_array_equal(np.asarray(exported),np.asarray(full))
        assert exported.size == image.size
    with Image.open(args.output/'windsock-local.jpg') as exported:
        assert exported.size == image.size
    # Keep the benchmark scoped to the expensive local operation alone. The
    # source has already been decoded and globally developed, as in the UI cache.
    preview=global_only.copy();preview.thumbnail((800,800),Image.Resampling.LANCZOS)
    rgb=np.asarray(preview,dtype=np.float32)/255
    timings=[]
    for index in range(31):
        started=time.perf_counter()
        apply_masks(rgb.copy(),(sky,replace(subject,exposure=.1+index*.015)))
        timings.append((time.perf_counter()-started)*1000)
    assert hashlib.sha256(args.source.read_bytes()).hexdigest()==original_hash
    report={'source':str(args.source),'source_sha256':original_hash,'source_unchanged':True,
            'source_size':list(image.size),'output_size':list(full.size),
            'global_settings':asdict(settings),'masks':[asdict(sky),asdict(subject)],
            'preview_size':list(preview.size),'local_only_cold_ms':round(timings[0],2),
            'local_only_warm_median_ms':round(float(np.median(timings[1:])),2),
            'local_only_warm_p95_ms':round(float(np.percentile(timings[1:],95)),2),
            'scope':'This host, cached global preview; local mask processing only. Not UI input latency or Android runtime.'}
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({key:value for key,value in report.items() if key not in ('masks','global_settings')},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
