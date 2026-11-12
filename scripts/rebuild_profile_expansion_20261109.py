"""Rebuild Pro160S/Pro160C/Reala spectral resources from retained MIT literals.

Run with the workspace Python, then verify_new_spectral_materials.py --install.
No downloaded module is executed, and no hash tests are performed.
"""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
from scripts import import_additional_profiles as converter
REVISION='a15043f6fe2d365d0c359d22e0868076800916d9'
FILES={'fujifilm_pro_160s':'fuji_pro_160s.py','fujifilm_pro_160c':'fuji_pro_160c.py','fujifilm_superia_reala':'fuji_superia_reala.py'}
converter.COMMIT=REVISION;converter.STOCKS={stock:('negative_film/'+name,'') for stock,name in FILES.items()}
source=ROOT/'licenses/additional-spectral-data/source-20261109'
out=ROOT/'output/film-profile-research/pro160-reala-candidates';out.mkdir(parents=True,exist_ok=True)
manifest_file=ROOT/'vendor/spektrafilm/data/profile_extensions/manifest.json';manifest=json.loads(manifest_file.read_text(encoding='utf-8'))
for stock,name in FILES.items():
 profile,provenance=converter.convert(stock,source/name,source/'densiometry.py')
 profile['metadata'].update(version='extension-2',created='2026-11-09')
 profile['metadata']['datasource']=profile['metadata']['datasource'].replace('Modeled research candidate converted','Converted')
 provenance.pop('source_sha256',None);provenance.pop('density_source_sha256',None)
 provenance['verification']=converter.verification(profile,out)
 converter.write_json(out/(stock+'.json'),profile);converter.write_json(out/(stock+'.provenance.json'),provenance)
 for target in (ROOT/'vendor/spektrafilm/data/profiles',ROOT/'native/engine/runtime/resources/profiles'):
  converter.write_json(target/(stock+'.json'),profile)
 converter.write_json(manifest_file.parent/(stock+'.provenance.json'),provenance)
 neutral=provenance['verification']['neutral_print']
 manifest['profiles'][stock]=dict(paper=neutral['paper'],neutral_filters_cmy=neutral['cmy_cc'],illuminant=neutral['illuminant'],source_revision=REVISION,provenance_file=stock+'.provenance.json',model_status='estimated')
 print(stock,'converted, finite, neutral calibrated',flush=True)
converter.write_json(manifest_file,manifest)
