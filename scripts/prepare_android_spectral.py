"""Reproducible Android port: preserve upstream model, replace desktop accelerators.

Run after updating vendor/spektrafilm. No upstream desktop files are modified.
"""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / 'vendor/spektrafilm'
target = ROOT / 'android/app/src/main/python/spektrafilm'
target.mkdir(parents=True, exist_ok=True)
changed = []
shutil.copy2(ROOT / 'shared/film_profiles.py', target.parent / 'film_profiles.py')
shutil.copy2(ROOT / 'shared/darkroom.py', target.parent / 'darkroom.py')
shutil.copy2(ROOT / 'shared/local_masks.py', target.parent / 'local_masks.py')
shutil.copy2(ROOT / 'shared/color_tools.py', target.parent / 'color_tools.py')
shutil.copy2(ROOT / 'shared/hsl.py', target.parent / 'hsl.py')
shutil.copy2(ROOT / 'shared/geometry.py', target.parent / 'photo_geometry.py')
shutil.copy2(ROOT / 'shared/style_presets.py', target.parent / 'style_presets.py')
shutil.copy2(ROOT / 'shared/style_luts.py', target.parent / 'style_luts.py')
for path in source.rglob('*'):
    if not path.is_file() or '__pycache__' in path.parts or path.suffix in {'.pyc', '.nbc', '.nbi'}:
        continue
    relative = path.relative_to(source)
    destination = target / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == '.py':
        text = path.read_text(encoding='utf-8')
        text = text.replace('from numba import njit, prange', 'from mobile_accel import njit, prange')
        text = text.replace('import numba\n', 'import mobile_accel as numba\n')
        text = text.replace('import pyfftw.interfaces.numpy_fft as fft', 'from mobile_accel import fft')
        text = text.replace('import OpenImageIO as oiio', 'oiio = None  # Android ContentResolver performs image I/O')
        text = text.replace('from skimage.transform import rescale', 'from mobile_accel import rescale')
        if text != path.read_text(encoding='utf-8'):
            changed.append(relative.as_posix())
        destination.write_text(text, encoding='utf-8')
    else:
        shutil.copy2(path, destination)
resource_packages=[]
for directory in [target/'data',*(target/'data').rglob('*')]:
    if directory.is_dir() and '__pycache__' not in directory.parts:
        initializer=directory/'__init__.py'
        if not initializer.exists():
            initializer.write_text('# Android resource package (upstream data unchanged).\n',encoding='utf-8')
            resource_packages.append(directory.relative_to(target).as_posix())
report = dict(upstream='vendor/spektrafilm', port='android/app/src/main/python/spektrafilm',
              resource_packages=resource_packages,
              modified_files=changed, backend='NumPy/SciPy; no Numba/LLVM or desktop image I/O',
              upstream_sha256={p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in source.rglob('*.py') if '__pycache__' not in p.parts})
(target.parent / 'port-manifest.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
for cache in target.parent.rglob('__pycache__'):
    assert cache.resolve().is_relative_to(target.parent.resolve())
    shutil.rmtree(cache)
print(f'Prepared upstream spectral model; {len(changed)} portability patches')
