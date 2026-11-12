"""Stage Android output color data from the shared, tested color contract."""
from pathlib import Path
import json
import sys

root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root))
from shared.color_management import conversion_matrix,icc_profile

output=root/'android/app/src/main/assets/color'
output.mkdir(parents=True,exist_ok=True)
for space,name in [('Display P3','DisplayP3'),('ProPhoto RGB','ProPhotoRGB')]:
    (output/(name+'.icc')).write_bytes(icc_profile(space))
(output/'output-matrices.json').write_text(json.dumps({space:conversion_matrix('sRGB',space).reshape(-1).tolist()
    for space in ('Display P3','ProPhoto RGB')},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Staged actual Display P3/ProPhoto profiles and source-to-output matrices')
