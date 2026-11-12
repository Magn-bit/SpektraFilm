"""One small real-photo/session HDR export integration node, never a RAW benchmark."""
from pathlib import Path
from dataclasses import replace
import io,json,sys,threading,time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import numpy as np
from PIL import Image
from desktop.imaging import Settings
from desktop.output import render_recipe_pixels,export_pixels,export_recipe,ExportCancelled
from desktop.hdr_output import HDRRendition,HDROutputError,decode_jpeg,prepare_rendition,encode_jpeg
from desktop.disk_cache import configure_cache
from shared.output_recipes import OutputRecipe,recipe_size
from shared.geometry import Geometry,output_size,apply_geometry_pixels
from shared.color_management import icc_profile

start=time.perf_counter()
out=ROOT/'output/hdr-session-review';out.mkdir(parents=True,exist_ok=True)
configure_cache(out/'cache',dict(working=32<<20,preview=32<<20,full=32<<20))
source=out/'真实照片 HDR 源.png'
reference=ROOT/'output/hdr-container-review/real-session-source.png'
assert reference.is_file(),'bounded real-photo reference is required, not a generated scene'
with Image.open(reference) as picture:
    exif=Image.Exif();exif[271]='SpektraFilm real-photo fixture';exif[272]='bounded integration'
    exif[36867]='2026:11:11 14:30:00';exif[33434]=(1,125);exif[33437]=(4,1)
    picture.convert('RGB').save(source,exif=exif)
original_bytes=source.read_bytes();original_stat=source.stat()
with Image.open(source) as picture:source_size=picture.size
assert max(source_size)<=320
base=Settings(film_enabled=True,hdr_enabled=True,grain=0,halation=0,lens_correction=False,defringe=False)
recipe=OutputRecipe()
report={'scope':'actual Windows Vulkan spectral sessions using one bounded real-photo PNG; not a large RAW speed/memory benchmark',
        'source_dimensions':source_size,'checks':[],'renditions':[]}

def check_rendition(name,settings,recipe=recipe,*,max_edge=None,mode=None):
    began=time.perf_counter()
    result=render_recipe_pixels(source,settings,recipe,max_edge=max_edge)
    assert isinstance(result,HDRRendition)
    assert result.gain_map.dtype==np.uint8 and result.gain_map.shape==result.shape[:2]
    assert np.isfinite(result).all() and np.isfinite(result.gain_map).all()
    if mode=='slide':assert result.hdr_curve.get('mode')=='slide-rendition'
    if mode=='curve':assert 'log2_gain' in result.hdr_curve and 'mode' not in result.hdr_curve
    path=out/(name+'.jpg')
    export_pixels(result,path,recipe,metadata_source=source)
    decoded,info=decode_jpeg(path,display_boost=16.8)
    assert decoded.shape==(*result.shape[:2],4)
    assert info['map_width']==result.shape[1] and info['map_height']==result.shape[0]
    assert abs(info['headroom']-result.headroom)<1e-4 and np.isfinite(decoded).all()
    with Image.open(path) as file:
        assert file.size==(result.shape[1],result.shape[0])
        assert file.info.get('icc_profile')==icc_profile(recipe.color_space)
        assert file.getexif()[271]=='SpektraFilm real-photo fixture'
        assert file.getexif()[274]==1
    report['renditions'].append(dict(name=name,path=str(path),dimensions=list(result.shape[1::-1]),
        gain_dimensions=[info['map_width'],info['map_height']],headroom=result.headroom,
        gain_code_min=int(result.gain_map.min()),gain_code_max=int(result.gain_map.max()),
        gain_method='slide-rendition' if result.hdr_curve.get('mode') else 'current-medium-session-curve',
        seconds=round(time.perf_counter()-began,3)))
    return result

negative=check_rendition('negative-print',base,mode='curve')
plain=render_recipe_pixels(source,replace(base,hdr_enabled=False),recipe)
assert np.array_equal(plain,np.asarray(negative)),'negative HDR must not change any ordinary SDR pixel'
report['checks'].append('negative HDR retains every ordinary developed SDR float pixel')
paper=check_rendition('negative-different-print',replace(base,print_exposure=.75,print_y=.12),mode='curve')
assert not np.array_equal(paper.gain_map,negative.gain_map)
assert not np.array_equal(paper,negative)
report['checks'].append('actual print change updates both current SDR pixels and its own session-derived map')

slide_settings=replace(base,stock='fujifilm_provia_100f',grain=18)
slide=check_rendition('slide-pair',slide_settings,mode='slide')
assert slide.hdr_curve['grain_seed']==743
assert slide.gain_map.max()>0
edited=check_rendition('slide-edited',replace(slide_settings,brightness=-25),mode='curve')
assert not np.array_equal(edited,slide)
report['checks'].append('unedited positive uses real same-seed SDR/HDR renditions; edited positive uses the final-picture session curve')

geometry=Geometry(quarter_turns=1,crop=(.08,.16,.9,.88),rotation=1.2)
sized_recipe=replace(recipe,long_edge=160,color_space='Display P3')
cropped=check_rendition('slide-crop-resize',replace(slide_settings,geometry=geometry),sized_recipe,mode='slide')
expected=recipe_size(*output_size(*source_size,geometry),sized_recipe)
assert (cropped.shape[1],cropped.shape[0])==expected
# The mono map's source-centre transform agrees with the production geometry.
from desktop.hdr_output import _map_geometry
codes=np.arange(source_size[0]*source_size[1],dtype=np.uint32).reshape(source_size[1],source_size[0])%256
codes=codes.astype(np.uint8)
mapped=_map_geometry(codes,geometry,output_size(*source_size,geometry)[::-1])
rgb=apply_geometry_pixels(np.repeat(codes[:,:,None],3,axis=2),geometry)
assert np.array_equal(mapped,rgb[:,:,0])
report['checks'].append('quarter-turn, crop, projective correction and explicit output resize keep gain and base canvases aligned; P3 ICC survives')

# Max-edge is an explicit proof request; final callers above never set it.
proof=check_rendition('negative-proof-proxy',base,max_edge=128,mode='curve')
assert max(proof.shape[:2])==128 and proof.hdr_identity[3]==128
assert negative.shape[1::-1]==source_size
report['checks'].append('explicit proof proxy is bounded, while final unresized output keeps original source dimensions')

for invalid_recipe,invalid_settings in (
    (replace(recipe,format='png'),base),
    (replace(recipe,color_space='ProPhoto RGB'),base),
    (recipe,replace(base,extended_dynamic_range=True)),
    (recipe,replace(base,film_enabled=False)),
    (recipe,replace(base,scan_film=True)),
    (recipe,replace(base,digital_intermediate=True)),
    (recipe,replace(base,stock='kodak_tri_x_400')),
    (recipe,replace(base,hdr_peak_stops=.1))):
    try:render_recipe_pixels(source,invalid_settings,invalid_recipe)
    except HDROutputError:pass
    else:raise AssertionError('unsupported HDR mode must fail explicitly, never silently output SDR')
report['checks'].append('PNG, unsupported gamut, EDR, film-off, scan, DI, black-and-white and invalid peaks explicitly refuse HDR instead of silently writing SDR')
stop=threading.Event();stop.set()
cancelled=out/'cancelled.jpg'
try:export_recipe(source,cancelled,base,recipe,cancel=stop)
except ExportCancelled:pass
else:raise AssertionError('cancelled export must stop')
assert not cancelled.exists()
assert source.read_bytes()==original_bytes
assert source.stat().st_mtime_ns==original_stat.st_mtime_ns
report['checks'].append('cancel before processing leaves no published output; all exports leave original bytes and modification time unchanged')

# The positive peak cap may be 1.05*16; cover this real codec boundary cheaply.
peak_fixture=HDRRendition(np.full((8,12,3),.8,np.float32),np.full((8,12),255,np.uint8),16.8)
stream=io.BytesIO();encode_jpeg(stream,peak_fixture,recipe,icc_profile('sRGB'))
pixels,metadata=decode_jpeg(stream.getvalue(),display_boost=16.8)
assert abs(metadata['headroom']-16.8)<1e-4 and np.isfinite(pixels).all()
report['checks'].append('codec accepts the positive rendition 4 EV plus 5 percent quantisation-guard peak boundary')
report.update(ok=True,elapsed_seconds=round(time.perf_counter()-start,3))
(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
