# Optional shared-dependency packaging template; build-windows.ps1 owns release orchestration.
# desktop/main.py must route SpektraFilmCLI to desktop.automation.main before Qt imports.
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata

root = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(root / 'vendor'))
datas = [(str(root / source), target) for source, target in (
    ('desktop/qml', 'desktop/qml'), ('assets', 'assets'), ('licenses', 'licenses'),
    ('LICENSE', '.'), ('native/engine/runtime', 'native/engine/runtime'),
    ('native/library/runtime', 'native/library/runtime'),
    ('native/library/LICENSE', 'licenses/SpektraLab_library'),
    ('native/library/UPSTREAM.json', 'licenses/SpektraLab_library'),
    ('native/library/third_party/nlohmann/LICENSE.MIT', 'licenses/SpektraLab_library/nlohmann'),
    ('native/library/third_party/sqlite/README.md', 'licenses/SpektraLab_library/sqlite'),
)]
binaries = []
hiddenimports = ['wgpu.backends.wgpu_native', 'rawpy', 'tifffile', 'imagecodecs',
                 'matplotlib.backends.backend_agg', 'desktop.automation', 'desktop.gui_automation']
datas += collect_data_files('colour')
datas += copy_metadata('wgpu')
package_data, package_binaries, package_imports = collect_all('spektrafilm')
datas += package_data
binaries += package_binaries
hiddenimports += package_imports

a = Analysis([str(root / 'desktop/main.py')], pathex=[str(root), str(root / 'vendor')],
             binaries=binaries, datas=datas, hiddenimports=hiddenimports,
             hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=['tkinter', 'IPython', 'pytest'], noarchive=False, optimize=0)
pyz = PYZ(a.pure)
common = dict(exclude_binaries=True, debug=False, bootloader_ignore_signals=False,
              strip=False, upx=False, argv_emulation=False, target_arch=None,
              codesign_identity=None, entitlements_file=None,
              version=str(root / 'scripts/windows-version.txt'),
              icon=[str(root / 'assets/icons/spektrafilm.ico')])
gui = EXE(pyz, a.scripts, [], name='SpektraFilm', console=False,
          disable_windowed_traceback=False, **common)
cli = EXE(pyz, a.scripts, [], name='SpektraFilmCLI', console=True,
          disable_windowed_traceback=False, **common)
# One directory, two entry points, exactly one collected _internal dependency tree.
coll = COLLECT(gui, cli, a.binaries, a.datas, strip=False, upx=False,
               upx_exclude=[], name='SpektraFilm')
