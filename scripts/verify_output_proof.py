"""One output integration node: real encoder, Unicode EXIF and proof lifecycle."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from dataclasses import replace,asdict

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from PySide6.QtWidgets import QApplication
from desktop.controller import Controller,PhotoProvider
from desktop.imaging import Settings
from desktop.output import export_recipe
from desktop.lens import _exiftool
from desktop.native_spectral import parameters,paper_supports_edr
from shared.output_recipes import OutputRecipe,recipe_json,recipe_size
from shared.settings_sync import make_clip
from shared.geometry import Geometry


def wait(app,condition,timeout=25):
    deadline=time.monotonic()+timeout
    while condition() and time.monotonic()<deadline:
        app.processEvents();time.sleep(.01)
    assert not condition(),'output proof did not finish'


def main():
    app=QApplication.instance() or QApplication([])
    root=Path('output/output-proof-review');root.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        source=Path(directory)/'原图 sample.jpg'
        with Image.open('output/current-ui/source-preview.jpg') as image:
            image.thumbnail((384,384));w,h=image.size
            exif=Image.Exif()
            for key,value in {271:'SONY',272:'ILCE-7CR',36867:'2026:11:09 10:11:12',34855:100}.items():exif[key]=value
            image.save(source,quality=98,exif=exif)
        ctrl=Controller(PhotoProvider(),Path(directory)/'state')
        try:
            settings=replace(Settings(),film_enabled=True,lens_correction=False,defringe=False,grain=0,halation=0)
            ctrl._photo_model.append([dict(path=str(source),name=source.name,width=w,height=h,
                dimensions=f'{w} x {h}',settings=asdict(settings))])
            ctrl._current=0;ctrl._selected={0};ctrl._settings=settings
            recipe=OutputRecipe(format='jpeg',quality=98)
            proof=ctrl.outputProof;proof.request(recipe_json(recipe),True,True,False)
            wait(app,lambda:proof.busy)
            assert not proof.error,proof.error
            assert proof.fullResolution and proof.dimensions==[w,h],proof.dimensions
            proof.viewTile(0,0,100,100)
            assert proof.tileSource and proof.tileRect==[0,0,100,100]
            artifact=proof.exportArtifact();assert artifact.matches(str(source),settings,recipe)
            destination=Path(directory)/'成片.jpg'
            export_recipe(str(source),destination,settings,recipe,encoded_proof=artifact)
            assert destination.read_bytes()==artifact.path.read_bytes(),'published file was re-encoded'
            # Query the Chinese file through the same UTF-8 boundary as writes.
            result=subprocess.run([_exiftool(),'-charset','filename=UTF8','-@','-'],
                input='\n'.join(['-json','-Make','-Model','-DateTimeOriginal','-ISO','-Orientation#',
                '-ExifImageWidth','-ExifImageHeight','-ICC_Profile:ProfileDescription',str(destination)])+'\n',
                capture_output=True,text=True,encoding='utf-8',check=True)
            tags=json.loads(result.stdout)[0]
            assert tags['Model']=='ILCE-7CR' and tags['Make']=='SONY' and tags['ISO']==100,tags
            assert tags['Orientation']==1 and (tags['ExifImageWidth'],tags['ExifImageHeight'])==(w,h),tags
            previous=proof.source
            proof.request(recipe_json(replace(recipe,quality=90)),False,True,False)
            assert proof.source==previous and not proof.fullResolution and proof.exportArtifact() is None
            proof.release();wait(app,lambda:proof._task is not None)
            assert not proof.source and proof.exportArtifact() is None
            ctrl._changed=lambda:ctrl.stateChanged.emit()
            original=replace(settings,geometry=Geometry(crop=(.1,.1,.9,.9)));ctrl._settings=original
            assert ctrl.applySettingsClip(make_clip(replace(settings,exposure=.8)))==1
            assert ctrl._settings.geometry==original.geometry and ctrl._settings.exposure==.8
            ctrl.undo();assert ctrl._settings==original
            assert recipe_size(6000,4000,replace(recipe,short_edge=1000))==(1500,1000)
            assert not parameters(replace(settings,stock='kodak_tri_x_400',extended_dynamic_range=True))['extended_dynamic_range']
            assert paper_supports_edr('kodak_portra_endura')
            report=dict(ok=True,source_dimensions=[w,h],
                proof='full actual JPEG encoder -> readback -> bounded 1:1 tile -> exact artifact publication',
                metadata=tags,states=['last valid fit view retained during update','cancelled proof cannot publish',
                    'named clip preserves geometry and undo','unsupported EDR safely gated'],
                size_modes=['original','short-edge'])
            (root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(dict(ok=True,dimensions=[w,h],metadata_model=tags['Model'],checks=8),ensure_ascii=False))
        finally:ctrl.close()


if __name__=='__main__':main()
