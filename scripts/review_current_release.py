"""Review exact 0.5 candidates: running Windows smoke and Android metadata/signature."""
from pathlib import Path
import argparse
import ctypes as ct
import json
import os
import shutil
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def identity(path):
    value=path.stat();return dict(bytes=value.st_size,mtime_ns=value.st_mtime_ns)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--windows',type=Path,required=True)
    parser.add_argument('--apk',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    candidate=args.windows.resolve();exe=candidate/'SpektraFilm.exe'
    version=ct.WinDLL('version')
    version.GetFileVersionInfoSizeW.argtypes=[ct.c_wchar_p,ct.c_void_p]
    version.GetFileVersionInfoW.argtypes=[ct.c_wchar_p,ct.c_uint32,ct.c_uint32,ct.c_void_p]
    version.VerQueryValueW.argtypes=[ct.c_void_p,ct.c_wchar_p,ct.c_void_p,ct.c_void_p]
    size=version.GetFileVersionInfoSizeW(str(exe),None)
    assert size>0
    buffer=ct.create_string_buffer(size);assert version.GetFileVersionInfoW(str(exe),0,size,buffer)
    pointer=ct.c_void_p();length=ct.c_uint32()
    assert version.VerQueryValueW(buffer,'\\',ct.byref(pointer),ct.byref(length))
    fixed=ct.cast(pointer,ct.POINTER(ct.c_uint32))
    assert (fixed[2]>>16,fixed[2]&65535,fixed[3]>>16,fixed[3]&65535)==(0,5,0,0)
    env=dict(os.environ)
    # Keep host DLL search paths out of a bundled Qt/scientific runtime.
    system_root=os.environ.get('SystemRoot','C:/Windows')
    env['PATH']=os.pathsep.join([str(Path(system_root)/'System32'),system_root])
    log=args.output/'windows-smoke.log';report=args.output/'windows-smoke.json'
    with log.open('w',encoding='utf-8') as stream:
        result=subprocess.run([str(exe),'--smoke-test','--smoke-spectral','--verify-export',
            str((args.output/'candidate.tif').resolve()),'--verification-report',str(report.resolve()),
            '--screenshot',str((args.output/'candidate.png').resolve())],cwd=ROOT,env=env,
            stdout=stream,stderr=subprocess.STDOUT,timeout=100)
    if result.returncode:raise RuntimeError('Windows candidate failed: '+log.read_text(encoding='utf-8',errors='replace')[-2000:])
    smoke=read(report);assert smoke['ok'] and smoke['settings']['film_enabled']
    assert smoke['native_spectral']['backend']['render_core']=='native-vulkan'
    internal=candidate/'_internal'
    for name in ('native/engine/runtime/spektrafilm_raw.dll','native/engine/runtime/resources/vulkan/spk_editor_restore.spv',
        'desktop/qml/components/OutputRecipeDialog.qml','desktop/qml/components/SyncSettingsDialog.qml',
        'assets/fonts/SpektraBilingualSerif-Regular.ttf','licenses/THIRD-PARTY.md'):
        assert (internal/name).is_file(),name
    metadata=read(args.apk.parent/'output-metadata.json')
    assert any(item['versionName']=='0.5.0' and item['versionCode']==23 for item in metadata['elements'])
    with zipfile.ZipFile(args.apk) as package:
        names=set(package.namelist())
        for name in ('classes.dex','lib/arm64-v8a/libspektra_spectral.so','lib/arm64-v8a/libspektra_raw.so',
            'assets/native_engine/vulkan/spk_editor_restore.spv','assets/fonts/SpektraBilingualSerif-Regular.ttf',
            'assets/color/sRGB.icc','assets/color/DisplayP3.icc','assets/color/ProPhotoRGB.icc'):
            assert name in names,name
        assert not any('libpython' in name or 'chaquopy' in name for name in names)
        assert not any(name.startswith('assets/') and name.lower().endswith(('.jpg','.jpeg','.png','.heic')) for name in names)
    dev=Path(os.environ['LOCALAPPDATA'])/'SpektraFilmDev/android-sdk/build-tools/35.0.0'
    java=Path('C:/Program Files/Eclipse Adoptium/jdk-21.0.12.101-hotspot/bin/java.exe')
    signature=subprocess.run([str(java),'-jar',str(dev/'lib/apksigner.jar'),'verify','--verbose',str(args.apk)],
        capture_output=True,text=True,check=True)
    (args.output/'android-signature.txt').write_text(signature.stdout,encoding='utf-8')
    assert 'Verified using v2 scheme (APK Signature Scheme v2): true' in signature.stdout
    # Evidence is copied explicitly; historical full-size products are excluded.
    evidence={
        'bulk-raw.json':ROOT/'output/editor-full/bulk-raw.json',
        'full-export.json':ROOT/'output/editor-full/final-0.5-memory/report.json',
        'workspace.json':ROOT/'output/editor-workspace/verification.json',
        'sync-output.json':ROOT/'output/editor-workspace/secondary-verification.json',
        'quarter-turn.json':ROOT/'output/editor-workspace/quarter-turn-verification.json',
        'natural-raw.png':ROOT/'output/editor-workspace/raw-natural-1440x900.png',
        'calibration.png':ROOT/'output/editor-workspace/calibration-track-1366x768.png',
        'crop.png':ROOT/'output/editor-workspace/crop-xpan-selected-1366x768.png',
        'crop-menu.png':ROOT/'output/editor-workspace/crop-ratio-menu-1366x768.png',
        'crop-controls.json':ROOT/'output/editor-workspace/crop-menu-verification.json',
        'slider-before.json':ROOT/'output/slider-interaction/before.json',
        'slider-current.json':ROOT/'output/slider-interaction/candidate.json',
        'recipe.png':ROOT/'output/editor-workspace/recipe-1366x768.png'}
    for name,path in evidence.items():shutil.copy2(path,args.output/name)
    review=dict(ok=True,version='0.5.0',windows=dict(artifact=identity(exe),smoke_ok=True),
        android=dict(artifact=identity(args.apk),package_ok=True,device_runtime_verified=False),
        changes=['Windows control fix: field notifications, coalesced drag, background preview images; crop menu and gradient tracks',
            'Restoration cache invalidation, single restoration pass and bounded pre-processing request',
            'Natural RAW plus optional complete spectral darkroom','Native full editor, calibration/HSL/curves/wheels and masks',
            'Source-space sharpening/noise reduction before film','Inline crop/XPan and exact quarter-turn geometry',
            'Classified per-photo batch history, bounded lazy RAW ingestion and caches',
            'Real high-depth output recipes, wide RGB ICC and processed linear DNG',
            'Task workspaces retain approved typography; Android preview/tools remain visible together'],
        checks=dict(windows_candidate_smoke=smoke['checks'],
            source_milestone='8 core editing/output integration checks passed; native optics/restoration/lifecycle targeted checks passed',
            bulk='256 separate same-source RAW paths, selected photo only decoded; see bulk-raw.json',
            desktop='1366x768/1440x900 UI, first drag, crop, quarter turn, per-photo sync undo and saved output recipes',
            controls='Current bundled QML under development Qt runtime: actual pointer drags, final values, single undo, Shift fine step, double-click reset; real crop menu clicks and Escape',
            latency='1366x768 Windows, 640px native interactive preview: exposure pointer median 30.113ms to 0.305ms; see slider-current.json; not a guarantee of zero dropped frames or an Android measurement',
            android='assembleDebug/lintDebug/test source compilation; host state/encoder/LibRaw/native color checks; v2 signature',
            tests='Key milestones only; no hash tests or repeated historical full RAW tests'),
        limitations=['No ADB device: Android current UI, touch, permissions and full-size export wall time remain unverified',
            '256-path import uses hard links to the same actual RAW, not 256 different cameras/content',
            'Full-size 61MP measurement is source process on RTX3070Ti Laptop, not Android or a universal speed guarantee',
            'No proprietary LR/C1 algorithm restoration; non-Bayer/unsupported RAW limitations are explicit',
            'Spectral result retains UNORM16 boundary; monitor ICC proof/EDR, DI, physical borders/datebacks and paired frames remain pending',
            'No macOS/iOS builds; no full language/update/CLI-MCP product API'])
    (args.output/'review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(ok=True,version='0.5.0',windows=identity(exe),android=identity(args.apk),device_runtime_verified=False)),flush=True)


if __name__=='__main__':main()
