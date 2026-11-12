"""One targeted GPU acceptance pass for product grain morphology.

Uses a small original-pixel crop of a 61MP virtual film plane, not a 61MP
end-to-end benchmark. No file digests or duplicate legacy regressions.
"""
from __future__ import annotations
from dataclasses import replace
import json
from pathlib import Path
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from desktop.imaging import Settings
from desktop import native_spectral as native
from shared.grain_texture import PROFILES, apply_density_grain


def run(output):
    output.mkdir(parents=True,exist_ok=True)
    source=np.full((320,480,3),.45,dtype=np.float32)
    settings=Settings(spectral=True,grain=35,grain_size=1.,halation=0)
    spatial=dict(dir_couplers_active=False,tile_full_width=9504,tile_full_height=6336,
                 tile_origin_x=2048,tile_origin_y=3072,tile_seed=743)
    engine=native._get_engine()
    if engine is None:
        raise RuntimeError(native.backend_info())
    quiet=engine.render(source,dict(native.parameters(replace(settings,grain=0)),**spatial),None)
    report={'device':native.backend_info()['backend'],'fixture':{
        'rendered_crop':[480,320],'physical_plane':[9504,6336],'film_format_mm':35,
        'grain':35,'grain_size':1,'full_export_benchmark':False},'styles':{}}
    swatches=[]
    for kind in PROFILES:
        values=dict(native.parameters(replace(settings,grain_type=kind)),**spatial)
        start=time.perf_counter();rgb=engine.render(source,values,None)
        seconds=time.perf_counter()-start
        residual=rgb-quiet;y=residual.mean(axis=-1);std=float(y.std())
        # The identical original coordinates must produce the identical field
        # even when a sub-rectangle is a separate native render.
        subvalues=dict(values,tile_origin_x=2048+83,tile_origin_y=3072+57)
        sub=engine.render(source[57:247,83:383],subvalues,None)
        # Scanner blur/sharpening still needs a halo although the grain
        # generator itself is pointwise in the original film coordinates.
        region_error=float(np.max(np.abs(sub[16:-16,16:-16]-rgb[73:231,99:367])))
        data={'luminance_std':std,'kurtosis':float(np.mean((y-y.mean())**4)/max(std**4,1e-20)),
            'horizontal_correlation':float(np.corrcoef(y[:,:-1].ravel(),y[:,1:].ravel())[0,1]),
            'chroma_std':float((residual[...,0]-residual[...,1]).std()),
            'mean_delta':float(residual.mean()),'render_seconds':seconds,
            'independent_region_max_error':region_error}
        assert 0.<std<.07,data
        assert data['chroma_std']<std*.15,data
        assert abs(data['mean_delta'])<.003,data
        assert region_error<=2./65535.,data
        report['styles'][kind]=data
        swatch=Image.fromarray(np.rint(np.clip(rgb,0,1)*255).astype('uint8'))
        swatch.save(output/f'{kind}.png');swatches.append((kind,swatch))
    styles=report['styles']
    assert styles['coarse']['horizontal_correlation']>styles['classic']['horizontal_correlation']+.2,styles
    assert styles['clustered']['horizontal_correlation']>styles['classic']['horizontal_correlation']+.2,styles
    # Same model/pitch, different amount: exact density noise scales rather
    # than moving the particles. CPU hook is bounded to 64 rows.
    from types import SimpleNamespace
    grain=SimpleNamespace(active=True,amount=.5,texture=4,texture_scale_um=4.5,
        particle_area_um2=.8*1.35,uniformity=(.992,)*3)
    density=np.full((145,151,3),.6,dtype=np.float32)
    a=apply_density_grain(density,3.68,grain,np.array([2.2]*3))
    grain.amount=1.;b=apply_density_grain(density,3.68,grain,np.array([2.2]*3))
    scale_error=float(np.max(np.abs((a-density)*2-(b-density))))
    assert scale_error<2e-7,scale_error
    report['amount_scaling_density_max_error']=scale_error
    # Preserve a neutral detail sheet at 1:1. The same tone, amount, size,
    # physical film and seed are used for all four panels.
    sheet=Image.new('RGB',(1008,756),'#f3f1eb');draw=ImageDraw.Draw(sheet)
    font_path=ROOT/'assets/fonts/SpektraBilingualSerif-Regular.ttf'
    font=ImageFont.truetype(str(font_path),18) if font_path.is_file() else ImageFont.load_default()
    labels={'fine':'细腻','classic':'经典','coarse':'粗粝','clustered':'团簇'}
    for i,(kind,swatch) in enumerate(swatches):
        x=16+(i%2)*496;y=16+(i//2)*370
        draw.text((x,y),labels[kind],fill='#34382f',font=font)
        sheet.paste(swatch,(x,y+32))
    sheet.save(output/'grain-types-1to1.png')
    report['status']='passed'
    (output/'metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    native.clear_sessions()
    return report


if __name__=='__main__':
    folder=ROOT/'output/grain-refinement'
    if len(sys.argv)>1:folder=Path(sys.argv[1])
    print(json.dumps(run(folder),ensure_ascii=False,indent=2))
