"""One bounded real JPEG/ISO21496/Adobe gain-map encode+independent decode node.

The synthetic curve is an explicit codec fixture, never a production fallback.
An actual engine-session export is validated separately by the integration node.
"""
from pathlib import Path
from dataclasses import replace
import io,json,sys,threading,time
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import numpy as np
from PIL import Image
from desktop.hdr_output import HDRRendition,HDROutputError,gain_map,base_jpeg,encode_jpeg,decode_jpeg
from desktop.output import ExportCancelled
from desktop.export_metadata import copy_capture_metadata
from shared.output_recipes import OutputRecipe
from shared.color_management import icc_profile

out=ROOT/'output/hdr-container-review';out.mkdir(parents=True,exist_ok=True)
start=time.perf_counter();report={'scope':'320x192 synthetic codec fixture, not RAW or film-session benchmark','checks':[]}
y,x=np.mgrid[:192,:320]
ramp=np.clip((x-8)/303,0,1).astype(np.float32)
noise=np.random.default_rng(324).normal(0,.0015,ramp.shape).astype(np.float32)
pixels=np.repeat(np.clip(ramp+noise,0,1)[:,:,None],3,axis=2)
pixels[:,:8]=0;pixels[:,-8:]=1
# Include colour without weakening the grey ramp's per-pixel gain comparison.
pixels[144:168,:,1]*=.7;pixels[168:,:,2]*=.6
domain=np.linspace(-12,0,256)
g=np.clip((domain+3)/3,0,1)*2
curve=dict(headroom=4,top=2,domain_log2_y=[-12,0],log2_gain=g.tolist(),ks=g.tolist(),
           rho=np.gradient(g,domain).tolist(),kappa=1,rho_max=2,detail_clamp=.10)
codes=gain_map(pixels,curve,rows=31)
assert np.array_equal(codes,gain_map(pixels,curve,rows=256)),'strip halos must preserve exact map codes'
report['checks'].append('bounded row bands equal whole-image grain-aware gain codes')
for color_space in ('sRGB','Display P3'):
    recipe=OutputRecipe(color_space=color_space);profile=icc_profile(color_space)
    current=gain_map(pixels,curve,color_space)
    rendition=HDRRendition(pixels,current,4,color_space=color_space)
    base=base_jpeg(pixels,recipe,profile)
    stream=io.BytesIO();encode_jpeg(stream,rendition,recipe,profile)
    encoded=stream.getvalue();path=out/(color_space.replace(' ','-')+'-gainmap.jpg');path.write_bytes(encoded)
    assert b'http://ns.adobe.com/hdr-gain-map/1.0/' in encoded
    assert b'urn:iso:std:iso:ts:21496:-1' in encoded
    a=base.find(b'\xff\xda');b=encoded.find(b'\xff\xda');e=encoded.find(b'\xff\xd9',b)+2
    assert a>=0 and b>=0 and base[a:]==encoded[b:e],'ordinary SDR entropy-coded scan must stay byte-for-byte identical'
    with Image.open(io.BytesIO(base)) as plain,Image.open(io.BytesIO(encoded)) as file:
        assert plain.size==file.size==(320,192)
        assert np.array_equal(np.asarray(plain.convert('RGB')),np.asarray(file.convert('RGB')))
        assert file.info.get('icc_profile')==profile
    sdr,info=decode_jpeg(encoded,display_boost=1)
    half,_=decode_jpeg(encoded,display_boost=2)
    hdr,_=decode_jpeg(encoded,display_boost=4)
    assert info['width']==info['map_width']==320 and info['height']==info['map_height']==192 and info['headroom']==4
    assert np.isfinite(hdr).all() and float(hdr[:144,-8:,:3].mean())>3.9
    assert float(hdr[:,:8,:3].max())==0,'zero offsets preserve black'
    valid=(sdr[:,:,:3].mean(2)>.025)&(np.arange(192)[:,None]<140)
    actual=np.log2(hdr[:,:,:3].astype(np.float32).mean(2)[valid]/sdr[:,:,:3].astype(np.float32).mean(2)[valid])
    expected=current.astype(np.float32)[valid]*(2/255)
    delta=float(np.quantile(np.abs(actual-expected),.99))
    assert delta<.035,(color_space,delta)
    assert np.all(half[:,:,:3].astype(np.float32)<=hdr[:,:,:3].astype(np.float32)+.002)
    report[color_space]=dict(file=str(path),dimensions=[320,192],gain_dimensions=[320,192],peak=float(hdr[:,:,:3].max()),gain_error_p99_stops=delta)
    # Production's capture metadata postpass must preserve a valid MPF index.
    source=out/'capture-metadata.png'
    if not source.exists():
        exif=Image.Exif();exif[271]='SpektraFilm fixture';exif[272]='readback';exif[306]='2026:11:11 12:00:00'
        Image.fromarray((pixels*255).astype(np.uint8)).save(source,exif=exif)
    copy_capture_metadata(source,path,(320,192))
    after,after_info=decode_jpeg(path,display_boost=4)
    assert after_info==info and np.array_equal(after,hdr),'Exif postpass must not change HDR picture or metadata'
    report['checks'].append(color_space+': ISO+Adobe declarations, full-size map, unchanged SDR scan/ICC, independent HDR readback and EXIF preservation')
# A wide but tiny raster proves the library's default 8192 cap was removed;
# no full-RAW performance rerun or automatic resize can conceal that boundary.
wide=np.full((8,9564,3),.8,np.float32)
wide_codes=np.full((8,9564),255,np.uint8)
stream=io.BytesIO();encode_jpeg(stream,HDRRendition(wide,wide_codes,4),OutputRecipe(),icc_profile('sRGB'))
decoded,info=decode_jpeg(stream.getvalue(),display_boost=4)
assert decoded.shape==(8,9564,4) and info['map_width']==9564
report['checks'].append('9564x8 boundary fixture preserves >8192 source width and gain width')
stop=threading.Event();stop.set()
try:gain_map(pixels,curve,cancel=stop)
except ExportCancelled:pass
else:raise AssertionError('cancelled generation must stop')
report['checks'].append('cancellation produces no gain-map result')
report.update(ok=True,elapsed_seconds=round(time.perf_counter()-start,3))
(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
