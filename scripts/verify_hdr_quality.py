"""Same-RAW visual/tonal review for the independent detail-preserving HDR."""
from pathlib import Path
import json
import sys
import numpy as np
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from desktop.imaging import read_photo,Settings
from desktop.raw_source import source_pixels,source_metadata,quantize_display
from desktop.native_spectral import process_editor
from shared.levels import hdr_luminance_base


def main():
    photo=Path(sys.argv[1] if len(sys.argv)>1 else 'D:/Download/DSC09118.ARW')
    im=read_photo(str(photo),960);settings=Settings();meta=source_metadata(im)
    source=process_editor(source_pixels(im),settings,stage='pre',
        exposure_ev=float(meta.get('baseline_exposure_ev',0)),
        source_color_space=meta['source_color_space'],source_linear=meta['source_linear'],clamp_output=False)
    full=tuple(im.info['source_size']);scale=(full[0]/im.width,full[1]/im.height)
    base=hdr_luminance_base(source,scale)
    decode=lambda values:np.where(values<=.04045,values/12.92,np.maximum((values+.055)/1.055,0)**2.4)
    linear=decode(source);luma=np.maximum(linear@np.array([.2126,.7152,.0722],np.float32),0)
    # Previous release's point curve, retained here solely for this visual
    # comparison. It is not a second production rendering mode.
    previous=linear.copy();l=luma.copy();gain=np.ones_like(l)
    for amount,pivot,rolloff,stops,upper in ((75,.18,2.,2.4,False),(-75,.18,2.,3.5,True)):
        distance=np.log2(np.maximum(l,1e-8)/pivot)
        weight=1.-np.exp2(-np.maximum(distance if upper else -distance,0.)/rolloff)
        zone=np.exp2(amount*.01*stops*weight*weight);gain*=zone;l*=zone
    previous*=gain[...,None]
    previous=np.where(previous<=.0031308,previous*12.92,1.055*np.maximum(previous,0)**(1/2.4)-.055)
    current=process_editor(source,dict(highlights=-75,shadows=75),pixel_scale=scale,
                           tone_base=base,clamp_output=False)
    items=[('Source',source),('Previous HDR',previous),('Detail-preserving HDR',current)]
    canvas=Image.new('RGB',(im.width*3,im.height+38),'#eeeae2');draw=ImageDraw.Draw(canvas)
    font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',18)
    for i,(name,pixels) in enumerate(items):
        canvas.paste(Image.fromarray(quantize_display(pixels)),(i*im.width,38))
        draw.text((i*im.width+14,8),name,fill='#363c32',font=font)
    old_luma=decode(previous)@np.array([.2126,.7152,.0722],np.float32)
    newlinear=decode(current);new_luma=newlinear@np.array([.2126,.7152,.0722],np.float32)
    report=dict(source=photo.name,proxy_size=im.size,source_size=full,highlights=-75,shadows=75,
        reference='Previous product HDR; no proprietary C1 pixel equivalence is claimed')
    for label,mask in [('shadow',luma<.08),('highlight',luma>.55)]:
        report[label]=dict(pixels=int(mask.sum()),source_mean=float(np.mean(luma[mask])),
            previous_mean=float(np.mean(old_luma[mask])),current_mean=float(np.mean(new_luma[mask])))
    saturated=(np.max(linear,axis=-1)-np.min(linear,axis=-1)>.2)&(luma>.01)
    chroma=lambda values:values/np.maximum(np.sum(values,axis=-1,keepdims=True),1e-8)
    report['saturated_pixels']=int(saturated.sum())
    report['saturated_linear_chroma_max_error']=float(np.max(abs(chroma(newlinear)[saturated]-chroma(linear)[saturated])))
    assert report['saturated_linear_chroma_max_error']<2e-6
    assert report['shadow']['current_mean']>report['shadow']['previous_mean']
    assert report['highlight']['current_mean']<report['highlight']['previous_mean']
    out=ROOT/'output/hdr-interaction-review';out.mkdir(parents=True,exist_ok=True)
    canvas.save(out/'real-raw-hdr-comparison.jpg',quality=95)
    (out/'quality.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
