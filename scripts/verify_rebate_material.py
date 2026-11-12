"""Small native scan-material milestone: preserve photograph, seed and canvas regions."""
from dataclasses import replace
from pathlib import Path
import argparse,json,sys,time
import numpy as np
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
from desktop.imaging import Settings,read_photo
from desktop.film_canvas import render_film_edge

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',action='store_true')
    args=parser.parse_args()
    out=ROOT/'output/rebate-material-084';out.mkdir(parents=True,exist_ok=True)
    photo=ROOT/'output/product-screenshots/DSC09118-preview.jpg'
    image=read_photo(str(photo),max_edge=1600)
    settings=replace(Settings(),film_enabled=True,grain=0,halation=0,lens_correction=False,defringe=False)
    rows=[]
    for stock,fmt in [('kodak_portra_400','135'),('kodak_vision3_500t','135'),('kodak_portra_400','120_6x6')]:
        name=stock+'-'+fmt
        options=dict(style='film',frame_format=fmt,frame_seed=20261112,camera_seed=1,
            fog=1.,leaks=0.,edge_print=True,frame_number=12,holes='light',
            placements=[dict(path=str(photo),metadata={})])
        started=time.monotonic()
        pixels,geometry=render_film_edge(image,replace(settings,stock=stock),options,preview=True)
        def save(suffix,values):
            Image.fromarray(np.rint(np.clip(values,0,1)*255).astype(np.uint8)).save(out/(name+suffix+'.png'))
        if args.baseline:
            np.save(out/(name+'-baseline.npy'),pixels)
            save('-before',pixels)
            (out/(name+'-geometry.json')).write_text(json.dumps(geometry),encoding='utf-8')
            continue
        before=np.load(out/(name+'-baseline.npy'))
        assert before.shape==pixels.shape
        mask=Image.new('1',(pixels.shape[1],pixels.shape[0]))
        draw=ImageDraw.Draw(mask)
        for gate in geometry['gates']:
            points=np.asarray(gate).reshape(4,2)*[pixels.shape[1],pixels.shape[0]]
            center=points.mean(axis=0)
            points=center+(points-center)*.94
            draw.polygon([tuple(p) for p in points],fill=1)
        core=np.asarray(mask,dtype=bool)
        assert np.array_equal(before[core],pixels[core]),'Scan material affected photograph interior'
        delta=np.abs(pixels-before)
        assert float(delta[~core].max())>0.005,'Rebate material did not change'
        repeated,_=render_film_edge(image,replace(settings,stock=stock),options,preview=True)
        assert np.array_equal(pixels,repeated),'Same seed moved the scan material'
        exported,export_geometry=render_film_edge(image,replace(settings,stock=stock),options,preview=False)
        residual=float(np.abs(exported-pixels).max())
        assert residual<6e-5,(name,residual)
        assert export_geometry['gates']==geometry['gates']
        save('-after',pixels)
        # Keep the actual native pixel view, rather than an AI replacement.
        save('-top-detail',pixels[:max(1,round(pixels.shape[0]*.18)),:])
        rows.append(dict(stock=stock,format=fmt,shape=list(pixels.shape),
            photograph_exact=True,seed_exact=True,preview_export_max_error=residual,
            seconds=round(time.monotonic()-started,3)))
    if not args.baseline:
        report=dict(ok=True,checks=rows,scope=__doc__)
        (out/'review.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report),flush=True)

if __name__=='__main__':main()
