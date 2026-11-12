"""Record verified external QML resource updates without changing the executable."""
from datetime import datetime
from pathlib import Path
import hashlib
import json

root=Path(__file__).resolve().parents[1]
path=root/'output/release-verification.json'
report=json.loads(path.read_text(encoding='utf-8'))
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert digest(Path(report['windows_exe']))==report['windows_exe_sha256']
assert digest(Path(report['android_apk']))==report['android_sha256']
files=[p.relative_to(root/'desktop/qml').as_posix() for p in (root/'desktop/qml').rglob('*') if p.is_file()]
hashes={}
for name in files:
    source=root/'desktop/qml'/name;packaged=root/'dist/SpektraFilm/_internal/desktop/qml'/name
    assert source.read_bytes()==packaged.read_bytes(),name
    hashes[name]=digest(source)
states=[]
for scale in ['1','1.25','1.5','2','native']:
    proof=root/'output/scrollbar-verification'/('scale-'+scale+'.json')
    data=json.loads(proof.read_text(encoding='utf-8'))
    assert data['ok'];states.extend(data['checks'])
    if scale!='native':assert len(data['checks'])==12
assert len(states)==52
report.update(qml_sha256=hashes,ui_verified_at=datetime.now().astimezone().isoformat(),scrollbar_verification=dict(ok=True,combinations=52,min_content_track_gap=8,evidence=str(root/'output/scrollbar-verification'),native_screenshot=str(Path(report['evidence'])/'export.png')))
path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(ok=True,windows=report['windows_exe'],android=report['android_apk'],scrollbar_combinations=52,qml_sha256=hashes),ensure_ascii=False,indent=2))
