"""Exercise Android's actual TIFF encoder on a JVM and decode independently."""
from pathlib import Path
import json
import shutil
import subprocess
import numpy as np
import tifffile

root=Path(__file__).resolve().parents[1]
out=root/'output/android/tiff-verification'
out.mkdir(parents=True,exist_ok=True)
compiler=shutil.which('javac')
java=shutil.which('java')
assert compiler and java,'JDK required'
subprocess.run([compiler,'-d',str(out),str(root/'android/app/src/main/java/com/spektra/film/TiffEncoder.java'),str(root/'scripts/TiffRoundtrip.java')],check=True)
target=out/'roundtrip.tif'
profile=root/'assets/color/sRGB.icc'
subprocess.run([java,'-cp',str(out),'TiffRoundtrip',str(profile),str(target)],check=True)
expected=np.array([[[x*3711+y,y*5821+x,(x^y)*2001+11] for x in range(17)] for y in range(11)],dtype=np.uint16)
with tifffile.TiffFile(target) as tiff:
    image=tiff.pages[0]
    np.testing.assert_array_equal(image.asarray(),expected)
    assert image.shape==(11,17,3) and image.dtype==np.uint16
    assert image.tags['InterColorProfile'].value==profile.read_bytes()
    assert image.bitspersample==16 and int(image.compression)==8
    assert np.any(expected%257!=0), 'Reference must contain detail unavailable in RGB8'

report=dict(ok=True,scope='Actual Java TIFF encoder on host JVM; independent tifffile exact RGB16/ICC roundtrip; invalid-size and overflow guards. Not Android device execution.',file=str(target),size=[17,11],bits_per_channel=16)
(out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
