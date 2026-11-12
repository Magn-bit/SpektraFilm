"""Install and verify three pinned spectral datasets; never execute downloaded code.

The converter reads literal dictionaries with AST. No hashes or full RAW reruns.
"""
import argparse,json,sys,time
from dataclasses import replace
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
from desktop.imaging import Settings,read_photo
from desktop.raw_source import source_pixels,normalized_pixels,quantize_display
from desktop import native_spectral
from shared.film_profiles import extension_profiles
STOCKS=[('fujifilm_pro_160s','Pro 160S','#B0BBA0'),('fujifilm_pro_160c','Pro 160C','#A5B7AA'),('fujifilm_superia_reala','Superia Reala','#9DAD90')]
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--install',action='store_true');args=parser.parse_args()
out=ROOT/'output/lab-frames-papers-review';out.mkdir(parents=True,exist_ok=True)
source=read_photo(str(ROOT/'output/current-ui/source-preview.jpg'),384);samples=normalized_pixels(source_pixels(source))
manifest_path=ROOT/'assets/luts/manifest.json';manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
base=replace(Settings(),film_enabled=True,grain=0,halation=0,lens_correction=False,defringe=False)
records=[];images=[]
for stock,name,color in STOCKS:
 settings=replace(base,stock=stock);values=native_spectral.parameters(settings);ext=extension_profiles()[stock]
 assert values['print_stock']==ext['paper']
 assert abs(values['m_filter_neutral']-ext['neutral_filters_cmy'][1])<1e-9
 assert not values['dir_couplers_active']
 start=time.perf_counter();pixels=native_spectral.render_spectral(samples,settings,preview=True)
 assert pixels.shape==samples.shape and np.isfinite(pixels).all()
 images.append((name,Image.fromarray(quantize_display(pixels))))
 # Explicit compatibility LUT generated from THIS spectral material, not a borrowed stock.
 axis=np.linspace(0,1,33,dtype=np.float32);b,g,r=np.meshgrid(axis,axis,axis,indexing='ij')
 grid=np.stack((r,g,b),axis=-1).reshape(33,1089,3)
 lut=native_spectral.render_spectral(grid,settings,preview=True).reshape(33,33,33,3)
 assert np.isfinite(lut).all()
 if args.install:
  np.asarray(lut,dtype='<f4').tofile(ROOT/'assets/luts'/(stock+'.f32'))
  if not any(v['id']==stock for v in manifest['stocks']):manifest['stocks'].append(dict(id=stock,name=name,maker='Fujifilm',description='',color=color,type='negative',category='negative',file=stock+'.f32'))
 records.append(dict(id=stock,neutral_filters=ext['neutral_filters_cmy'],paper=values['print_stock'],source_revision=ext['source_revision'],mean_rgb=pixels.mean(axis=(0,1)).tolist(),milliseconds=round((time.perf_counter()-start)*1000,2),compatibility_lut_from_own_spectral_material=True))
if args.install:manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
arrays=[np.asarray(image).astype(float) for _,image in images]
differences=[dict(a=STOCKS[i][0],b=STOCKS[j][0],mean_rgb8_difference=float(abs(arrays[i]-arrays[j]).mean())) for i in range(3) for j in range(i+1,3)]
assert min(v['mean_rgb8_difference'] for v in differences)>.5,differences
font=ImageFont.truetype(str(ROOT/'assets/fonts/SpektraBilingualSerif-Regular.ttf'),18)
sheet=Image.new('RGB',(3*400,330),'#F4F5EF');draw=ImageDraw.Draw(sheet)
for i,(name,image) in enumerate(images):
 image.thumbnail((384,270));sheet.paste(image,(i*400+8,8));draw.text((i*400+12,288),name,font=font,fill='#283025')
sheet.save(out/'three-additional-materials.png')
report=dict(ok=True,materials=records,pairwise=differences,scope='True finite spectral profiles with neutral print calibration; runtime uses full spectra. No laboratory stock-match claim; optional LUT is explicitly generated from same material.')
(out/'additional-materials.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False),flush=True)
