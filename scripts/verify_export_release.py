"""Log regression checks, validate the TIFF encoder, and capture QML exports."""
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from desktop.imaging import SRGB

profile=root/'assets/color/sRGB.icc'
profile.parent.mkdir(parents=True,exist_ok=True)
if not profile.exists():profile.write_bytes(SRGB)
result=subprocess.run([sys.executable,'-X','utf8','-m','unittest','discover','-s','tests','-v'],cwd=root,capture_output=True,text=True,encoding='utf-8')
(root/'output/test-final.log').write_text(result.stdout+result.stderr,encoding='utf-8')
print((result.stdout+result.stderr)[-350:],flush=True)
if result.returncode:raise SystemExit(result.returncode)
subprocess.run([sys.executable,'-X','utf8','scripts/verify_android_tiff.py'],cwd=root,check=True)
subprocess.run([sys.executable,'-X','utf8','-m','desktop.main','--capture-state','export','--screenshot','output/export-presets-source.png'],cwd=root,check=True)
