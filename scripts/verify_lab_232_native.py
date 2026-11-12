from pathlib import Path
import sys,json,ctypes as ct,time
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import numpy as np
from desktop import native_spectral as ns
from desktop.imaging import Settings
p=ROOT/'output/lab-232-native-review';p.mkdir(exist_ok=True)
e=ns._get_engine();assert e,ns._INITIALIZATION_ERROR
lib=e.lib;lib.spk_session_hdr_curve.argtypes=[ct.c_void_p,ct.c_char_p,ct.POINTER(ct.c_void_p)];lib.spk_session_hdr_curve.restype=ct.c_int32
ramp=np.geomspace(.0001,12,96,dtype=np.float32);source=np.broadcast_to(ramp[None,:,None],(64,96,3)).copy();source*=np.array([.82,1,1.17],dtype=np.float32)
base=ns.parameters(Settings(stock='kodak_portra_400',grain=0,halation=0,glare=0,dir_couplers_amount=0));base.update(input_cctf_decoding=False,dir_couplers_active=False,striped=False,print_stock='kodak_portra_endura',minilab_active=True)
result={};t=time.perf_counter()
def render(v):return e.render(source,dict(base,**v),None)
baseline=render({});assert np.isfinite(baseline).all()
for name,changes in [('brightness',dict(print_exposure=2.)),('yellow',dict(y_filter_shift=.25)),('magenta',dict(m_filter_shift=.25)),('preflash',dict(preflash_exposure=.2))]:
 out=render(changes);delta=float(np.max(np.abs(out-baseline)));assert np.isfinite(out).all() and delta>.005,(name,delta);result[name]={'max_delta':delta,'mean_delta':float(np.mean(np.abs(out-baseline)))}
np.testing.assert_array_equal(render({}),baseline)
result['minilab_restore_exact']=True
identity=np.tile(np.linspace(0,1,129),(5,1));curved=identity.copy();curved[1]=np.minimum(curved[1]+1/16,1)
wire=lambda rows:','.join(format(x,'.8g') for x in rows.ravel())
def analysis(values,request=None):return e.analyze(source,dict(base,**values),'scene_latitude',request)
a=analysis({});b=analysis({'scene_curve':wire(curved)})
ah=a['scene']['histogram'];bh=b['scene']['histogram'];assert 'curved_fractions' not in ah and len(bh['curved_fractions'])==128
np.testing.assert_allclose(ah['fractions'],bh['fractions'],atol=1e-12,rtol=0)
centers=np.arange(128)*.25-16+.125;shift=float(centers@(np.array(bh['curved_fractions'])-np.array(bh['fractions'])))
assert abs(shift-1)<.03,shift
assert all(len(bh['curved_fractions_'+c])==128 for c in 'rgb')
assert 'curved_fractions' not in analysis({'scene_curve':wire(curved)},dict(norm='y'))['scene']['histogram']
result['after_curve_histogram']={'mean_shift_stops':shift,'rgb_bins':128,'identity_omits_curved':True,'other_norm_omits_curved':True}
# Own one session for its curve and repeated-medium cache.
def query(values,request):
 img=ns._Image(source.ctypes.data_as(ct.POINTER(ct.c_float)),96,64,3);reply=ct.c_void_p();h=lib.spk_open(e.handle,ct.byref(img),ns._json_bytes(dict(base,product_defaults=True,**values)),ct.byref(reply));e._free_reply(reply);assert h,e.error()
 try:
  r=ct.c_void_p();status=lib.spk_session_hdr_curve(h,ns._json_bytes(request),ct.byref(r))
  try:return status,json.loads(ct.string_at(r)) if r.value else e.error()
  finally:e._free_reply(r)
 finally:lib.spk_session_release(h)
s,h=query({},dict(headroom=4));assert s==0,h
assert len(h['ks'])==256 and len(h['rho'])==256 and h['top']==2 and h['log2_gain'][-1]==2
assert np.isfinite(h['ks']).all() and min(np.diff(h['log2_gain']))>=0
s,h2=query(dict(exposure_compensation_ev=2),dict(headroom=4));assert s==0,h2
np.testing.assert_allclose(h2['log2_gain'],h['log2_gain'],atol=1e-12,rtol=0)
for values,request in [({},dict(headrom=4)),(dict(digital_intermediate=True),dict(headroom=4)),(dict(extended_dynamic_range=True),dict(headroom=4))]:
 code,why=query(values,request);assert code!=0,(values,why)
result['hdr_curve']={'samples':256,'exposure_invariant':True,'top_stops':h['top'],'detail_clamp':h['detail_clamp'],'invalid_requests_refused':True}
(p/'curve.json').write_text(json.dumps(h,indent=2),encoding='utf-8')
# Positive films have their own layer-density HDR scan, not the print curve.
slide=dict(base,film_stock='fujifilm_provia_100f',scan_film=True,minilab_active=False,grain_active=True,grain_amount=.25)
sdr=e.render(source,slide,None)
stretched=e.render(source,dict(slide,scan_hdr_stretch=True,grain_seed=12345),None)
hdr=e.render(source,dict(slide,scan_hdr_headroom=4.,scan_hdr_output_scale=.25,grain_seed=12345),None)
assert np.isfinite(stretched).all() and np.isfinite(hdr).all()
assert float(np.max(np.abs(stretched-sdr)))>.005
assert float(np.max(np.abs(hdr-sdr)))>.005
np.testing.assert_array_equal(hdr,e.render(source,dict(slide,scan_hdr_headroom=4.,scan_hdr_output_scale=.25,grain_seed=12345),None))
changed_seed=e.render(source,dict(slide,scan_hdr_headroom=4.,scan_hdr_output_scale=.25,grain_seed=54321),None)
assert float(np.max(np.abs(changed_seed-hdr)))>1e-5
result['slide_scan_hdr']={'different_seed_max_delta':float(np.max(np.abs(changed_seed-hdr))),'film':slide['film_stock'],'shape':list(hdr.shape),'stretch_max_delta':float(np.max(np.abs(stretched-sdr))),'hdr_max_delta':float(np.max(np.abs(hdr-sdr))),'fixed_seed_repeat_exact':True}
edr=[]
for paper in (ROOT/'native/engine/upstream/engine/resources/profiles').glob('*.json'):
 original=json.loads(paper.read_text(encoding='utf-8')).get('data',{}).get('edr_tone_map')
 if original:
  packaged=json.loads((ns._RUNTIME/'resources/profiles'/paper.name).read_text(encoding='utf-8')).get('data',{}).get('edr_tone_map')
  assert original==packaged,paper.stem
  edr.append(paper.stem)
assert len(edr)==8,edr
result['staged_paper_edr']=edr
result.update(ok=True,elapsed_seconds=time.perf_counter()-t,fixture='96x64 scene-linear coloured ramp; Windows Vulkan; not full RAW export timing')
(p/'report.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
ns._shutdown()
