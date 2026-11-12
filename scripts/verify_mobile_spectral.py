"""Compare Android's portable mathematical backend against upstream on the host.

This is a scientific parity test, not evidence of Android device execution.
"""
from pathlib import Path
import json, os, subprocess, sys, time
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/android/spectral-parity'
OUT.mkdir(parents=True,exist_ok=True)
if len(sys.argv)==1:
    for mode,path in [('upstream',ROOT/'vendor'),('mobile',ROOT/'android/app/src/main/python')]:
        env=os.environ.copy();env['PYTHONPATH']=str(path)
        subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).resolve()),mode],cwd=ROOT,env=env,check=True,timeout=180)
    import numpy as np
    source=np.load(OUT/'upstream.npz');mobile=np.load(OUT/'mobile.npz')
    errors={key:float(np.max(abs(source[key]-mobile[key]))) for key in source.files}
    assert all(error<1e-8 for error in errors.values()),errors
    report=dict(ok=True,max_absolute_errors=errors,scope='Host scientific parity; no Android runtime claim',
                random_backend='NumPy distribution draws; model retained, random sequences differ')
    (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2));raise SystemExit()

import numpy as np
import spektrafilm
from spektrafilm.utils.fast_interp_lut import apply_lut_3d,apply_lut_cubic_2d
from spektrafilm.utils.fast_gaussian_filter import fast_gaussian_filter
from spektrafilm.utils.fast_interp import fast_interp
from spektrafilm import init_params,simulate
rng=np.random.default_rng(914)
image=rng.uniform(-.1,1.1,(19,23,3));lut=rng.random((7,7,7,3))
results={}
results['pchip']=apply_lut_3d(lut,image)
results['mitchell_3d']=apply_lut_3d(lut,image,method='mitchell')
results['mitchell_2d']=apply_lut_cubic_2d(rng.random((6,6,9)),image[...,:2])
for sigma in [.4,2.4,3.,12.]:results['gaussian_'+str(sigma)]=fast_gaussian_filter(image,sigma)
results['curve']=fast_interp(image,np.linspace(0,1,12),rng.random((12,3)))
for stock in ['kodak_portra_400','fujifilm_provia_100f']:
    for halo in [0.,.8]:
        p=init_params(stock,'kodak_portra_endura')
        p.io.input_color_space='sRGB';p.io.input_cctf_decoding=True;p.io.scan_film=p.film.is_positive
        p.camera.auto_exposure=False;p.camera.exposure_compensation_ev=.4
        p.settings.use_enlarger_lut=True;p.settings.use_scanner_lut=True
        p.film_render.grain.active=False
        # Paper glare is stochastic even when film grain is disabled.
        p.print_render.glare.active=False
        p.film_render.halation.active=halo>0;p.film_render.halation.halation_amount=halo;p.film_render.halation.scatter_amount=halo
        results[stock+str(halo)]=simulate(np.clip(image,0,1),p)
np.savez(OUT/(sys.argv[1]+'.npz'),**results)
if sys.argv[1]=='mobile':
    from studio_spectral import render_argb
    pixels=np.full((18,24),0xff706050,dtype='<u4')
    clean=render_argb(bytearray(pixels.tobytes()),24,18,'kodak_portra_400',0,0,0,1)
    grain=render_argb(pixels.tobytes(),24,18,'kodak_portra_400',0,.5,0,1)
    assert len(clean)==24*18*4 and clean!=grain
    tile_a=render_argb(pixels.tobytes(),24,18,'kodak_portra_400',0,.5,.2,1,False,2400,1800,101)
    tile_b=render_argb(pixels.tobytes(),24,18,'kodak_portra_400',0,.5,.2,1,False,2400,1800,102)
    assert len(tile_a)==len(tile_b)==24*18*4 and tile_a!=tile_b
    print('Mobile bridge keeps tile pixel dimensions and varies film grain per tile')
