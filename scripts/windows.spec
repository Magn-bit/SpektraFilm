# Both launchers share one analysis, module archive and dependency directory.
from pathlib import Path
import importlib.util
from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata

root=Path(SPECPATH).parent
datas=[(str(root/path),str(Path(path).parent)) for path in ('LICENSE',)]
datas += [(str(root/path),path) for path in (
    'desktop/qml','desktop/translations','assets','licenses','native/engine/runtime','native/library/runtime','native/color/runtime','native/metadata/runtime','native/hdr/runtime')]
datas += [(str(root/source),target) for source,target in (
    ('native/library/LICENSE','licenses/SpektraLab_library'),
    ('native/library/UPSTREAM.json','licenses/SpektraLab_library'),
    ('native/library/third_party/nlohmann/LICENSE.MIT','licenses/SpektraLab_library/nlohmann'),
    ('native/library/third_party/sqlite/README.md','licenses/SpektraLab_library/sqlite'))]
vendor_data,vendor_binaries,vendor_hidden=collect_all('spektrafilm')
datas += vendor_data+collect_data_files('colour')+copy_metadata('wgpu')
heif_location=Path(importlib.util.find_spec('pillow_heif').origin).parent.parent
binaries=vendor_binaries+[(str(path),'.') for path in heif_location.glob('libheif*.dll')]
analysis=Analysis([str(root/'desktop/main.py')],
    pathex=[str(root),str(root/'vendor')],binaries=binaries,datas=datas,
    hiddenimports=vendor_hidden+['desktop.automation','desktop.ai_editor','desktop.ai_contract','desktop.ai_prompts','desktop.ai_providers','PySide6.QtSvg','wgpu.backends.wgpu_native','rawpy','tifffile',
        'imagecodecs','pillow_heif','_pillow_heif','matplotlib.backends.backend_agg'],
    hookspath=[],hooksconfig={},runtime_hooks=[],
    excludes=['tkinter','IPython','pytest'],noarchive=False)
pyz=PYZ(analysis.pure)
common=dict(exclude_binaries=True,debug=False,bootloader_ignore_signals=False,strip=False,upx=False,
            icon=str(root/'assets/icons/spektrafilm.ico'),version=str(root/'scripts/windows-version.txt'))
gui=EXE(pyz,analysis.scripts,[],name='SpektraFilm',console=False,**common)
cli=EXE(pyz,analysis.scripts,[],name='SpektraFilmCLI',console=True,**common)
collect=COLLECT(gui,cli,analysis.binaries,analysis.datas,strip=False,upx=False,name='SpektraFilm')
