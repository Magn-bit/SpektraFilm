"""Publish one reviewed local build without hashes or redundant benchmarks."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import argparse
import json
import re
import shutil
import uuid
import zipfile

ROOT=Path(__file__).resolve().parents[1]
RELEASE=ROOT/'release'
VERSION,VERSION_CODE='0.5.0',23
ITEMS=('Windows','Android','Source','Evidence','README.md','manifest.json','SHA256SUMS.txt')
EXCLUDED={'.git','.gradle','.kotlin','.cxx','__pycache__','build','CMakeFiles','node_modules'}
BINARY_SUFFIXES={'.pyc','.pyo','.nbc','.nbi','.dll','.exe','.so','.o','.obj','.a','.lib','.pdb','.log','.apk','.class'}
_EMBEDDED_CREDENTIAL=re.compile(rb'(?i)(?<![A-Za-z0-9])(?:sk-(?:proj-|ant-|svcacct-)?[A-Za-z0-9_-]{32,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|AKIA[A-Z0-9]{16}|AIza[0-9A-Za-z_-]{35})(?![A-Za-z0-9])')


def _scan_stream(stream):
    carry=b''
    while True:
        chunk=stream.read(1024*1024)
        if not chunk:return False
        data=carry+chunk
        if _EMBEDDED_CREDENTIAL.search(data):return True
        carry=data[-512:]


def _audit_zip(path_or_stream):
    try:
        with zipfile.ZipFile(path_or_stream) as archive:
            for info in archive.infolist():
                if info.is_dir():continue
                with archive.open(info) as member:
                    if _scan_stream(member):
                        raise ValueError('A packaged file appears to contain an API credential; public release was not created')
    except zipfile.BadZipFile:
        return False
    return True


def audit_public_artifacts(paths):
    """Scan every file, including binary strings and compressed archive entries."""
    for item in paths:
        path=Path(item)
        if path.is_symlink():raise ValueError('Cannot audit a linked public artifact')
        if path.is_dir():
            children=sorted(path.rglob('*'))
            for child in children:
                if child.is_symlink():raise ValueError('Cannot audit a linked public artifact')
                if child.is_file():audit_public_artifacts([child])
            continue
        try:
            if zipfile.is_zipfile(path):
                _audit_zip(path)
            else:
                with path.open('rb') as stream:
                    if _scan_stream(stream):
                        raise ValueError('A file appears to contain an API credential; public release was not created')
        except OSError as error:
            raise ValueError('Cannot audit a public artifact before packaging') from error


def reject_embedded_credentials(files):
    """Retain the source-archive API while auditing all included payloads."""
    audit_public_artifacts(files)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def identity(path):
    stat=path.stat()
    return dict(bytes=stat.st_size,mtime_ns=stat.st_mtime_ns)


def source_files():
    files=set()
    for tree in ('desktop','shared','vendor','assets','licenses','scripts','tests','native/engine','native/library','native/color','native/hdr','native/metadata/upstream','native/shaders','native/reference','native/docs',
                 'android/app/src','android/tools','docs'):
        for path in (ROOT/tree).rglob('*'):
            relative=path.relative_to(ROOT)
            if not path.is_file() or EXCLUDED.intersection(relative.parts) or path.suffix.lower() in BINARY_SUFFIXES:
                continue
            if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
                raise ValueError('External source link: '+str(relative))
            files.add(path)
    for pattern in ('README.md','LICENSE','requirements*.txt','run.ps1','.gitignore','native/README.md',
                    'android/*.kts','android/app/*.kts','android/*.md','android/.gitignore',
                    'android/gradle.properties','android/build.ps1','native/metadata/UPSTREAM.json'):
        files.update(path for path in ROOT.glob(pattern) if path.is_file())
    required=('native/engine/upstream/engine/CMakeLists.txt','native/engine/upstream/license/LICENSE',
              'native/engine/runtime/resources/vulkan/spk_grain_texture.spv',
              'native/engine/upstream/engine/src/shaders/vulkan/spk_grain_texture.comp',
              'native/engine/build-windows.sh','native/engine/build-windows.ps1',
              'native/engine/CMakeLists.txt','native/engine/mingw-toolchain.cmake',
              'native/library/include/spklib/spklib.h','native/library/src/library.cpp',
              'native/library/LICENSE','native/library/third_party/sqlite/sqlite3.c',
              'native/library/build-windows.ps1','native/color/build-windows.sh',
              'native/color/upstream/src/cmsxform.c','native/color/upstream/include/lcms2.h',
              'native/hdr/bridge.cpp','native/hdr/CMakeLists.txt','native/hdr/UPSTREAM.json',
              'native/hdr/build-windows.ps1','native/hdr/build-windows.sh',
              'native/hdr/upstream/libultrahdr-2.0.2/ultrahdr_api.h',
              'native/hdr/upstream/libultrahdr-2.0.2/LICENSE',
              'android/app/src/main/cpp/NativeSpectralJni.cpp',
              'android/app/src/main/cpp/CMakeLists.txt',
              'android/app/src/main/cpp/third_party/libraw/LICENSE.LGPL',
              'android/app/src/main/cpp/third_party/libjpeg-turbo/LICENSE.md',
              'scripts/build-windows.ps1','android/app/build.gradle.kts','android/build.ps1')
    for name in required:
        if ROOT/name not in files:raise ValueError('Missing corresponding source: '+name)
    return sorted(files)


def create_source_archive(path,version=VERSION,building_notes=''):
    files=source_files()
    reject_embedded_credentials(files)
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as archive:
        for file in files:
            before=identity(file)
            archive.write(file,file.relative_to(ROOT).as_posix())
            if identity(file)!=before:raise ValueError('Source changed during archive: '+str(file))
        archive.writestr('BUILDING.md',
            '# SpektraFilm '+version+' corresponding source\n\n'+building_notes+'\n\n'
            'Windows: Python 3.12, requirements.txt, PyInstaller. Build native/engine/build-windows.ps1 '
            'with Ubuntu WSL, MinGW POSIX, CMake/Ninja, glslang-tools and Vulkan headers; then native/library/build-windows.ps1, native/color/build-windows.sh, native/hdr/build-windows.ps1 and scripts/build-windows.ps1. The HDR codec also needs NASM in WSL and uses the included libjpeg-turbo sources.\n'
            'Android: JDK21, Gradle8.13, SDK35, NDK27.2.12479018, CMake3.22.1; '
            'set JAVA_HOME and run android/build.ps1 -GradlePath <gradle.bat> -SdkPath <SDK>.\n'
            'Read README.md, native/engine/README.md and android/BUILD-VERIFICATION.md. '
            'Includes the complete engine, shaders, material data, JNI, LibRaw, libjpeg-turbo and notices. '
            'External SDKs, caches, personal photographs, signing keys and proprietary LR/C1 modules are excluded. '
            'Development dependencies require download; installed applications operate offline.\n')
    return dict(archive='Source/'+path.name,bytes=path.stat().st_size,files=len(files),
                scope='Application, native/JNI/codec sources, shader inputs/SPIR-V, material resources, licenses and build scripts')


def verify_candidates(windows,apk,review):
    if review.get('ok') is not True or review.get('version')!=VERSION:
        raise ValueError('A successful current review is required')
    exe=windows/'SpektraFilm.exe'
    if not exe.is_file() or identity(exe)!=review.get('windows',{}).get('artifact'):
        raise ValueError('Windows candidate differs from reviewed metadata')
    if not apk.is_file() or identity(apk)!=review.get('android',{}).get('artifact'):
        raise ValueError('Android candidate differs from reviewed metadata')
    audit_public_artifacts([windows,apk])
    if review['windows'].get('smoke_ok') is not True or review['android'].get('package_ok') is not True:
        raise ValueError('Candidate smoke/package checks must pass')
    internal=windows/'_internal'
    for relative in ('native/engine/runtime/spektrafilm_engine.dll',
                     'native/engine/runtime/spektrafilm_raw.dll',
                     'native/engine/runtime/resources/vulkan/spk_grain_texture.spv',
                     'native/engine/runtime/resources/vulkan/spk_editor_restore.spv',
                     'assets/fonts/SpektraBilingualSerif-Regular.ttf',
                     'desktop/qml/components/OutputRecipeDialog.qml',
                     'desktop/qml/components/CropOverlay.qml','licenses/THIRD-PARTY.md'):
        if not (internal/relative).is_file():raise ValueError('Missing Windows resource: '+relative)
    if not list((internal/'PySide6').rglob('qwindows.dll')):
        raise ValueError('Missing Windows Qt platform plugin')
    metadata=read_json(apk.parent/'output-metadata.json')
    if not any(item.get('versionName')==VERSION and item.get('versionCode')==VERSION_CODE
               and item.get('outputFile')==apk.name for item in metadata.get('elements',[])):
        raise ValueError('Android version metadata is not current')
    with zipfile.ZipFile(apk) as package:
        names=package.namelist()
        if not any(name.endswith('/spk_grain_texture.spv') for name in names):
            raise ValueError('Missing Android grain shader')
        if not any(name=='lib/arm64-v8a/libspektra_spectral.so' for name in names):
            raise ValueError('Missing Android spectral engine')
    return exe


def install_stage(stage,items=ITEMS):
    stage=stage.resolve()
    if stage.parent!=RELEASE.resolve() or not stage.name.startswith('.stage-'):
        raise ValueError('Unexpected release staging path')
    backup=RELEASE/('.previous-'+uuid.uuid4().hex[:8]);backup.mkdir()
    moved=[];installed=[]
    try:
        for name in items:
            old=RELEASE/name
            if old.exists():old.rename(backup/name);moved.append(name)
        for name in items:
            new=stage/name
            if new.exists():new.rename(RELEASE/name);installed.append(name)
    except Exception:
        for name in reversed(installed):(RELEASE/name).rename(stage/name)
        for name in reversed(moved):(backup/name).rename(RELEASE/name)
        raise
    # Only this exact private rollback directory is disposable after success.
    shutil.rmtree(backup);stage.rmdir()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--windows',required=True,type=Path)
    parser.add_argument('--apk',required=True,type=Path)
    parser.add_argument('--verification',required=True,type=Path)
    parser.add_argument('--evidence',required=True,type=Path)
    args=parser.parse_args()
    windows,apk=args.windows.resolve(),args.apk.resolve()
    review=read_json(args.verification)
    verify_candidates(windows,apk,review)
    if not args.evidence.is_dir():raise ValueError('Evidence directory is required')
    RELEASE.mkdir(exist_ok=True)
    stage=RELEASE/('.stage-'+uuid.uuid4().hex[:8]);stage.mkdir()
    try:
        shutil.copytree(windows,stage/'Windows/SpektraFilm')
        (stage/'Android').mkdir();(stage/'Source').mkdir()
        apk_name=f'SpektraFilm-{VERSION}-arm64-v8a.apk'
        shutil.copy2(apk,stage/'Android'/apk_name)
        shutil.copytree(args.evidence,stage/'Evidence')
        shutil.copy2(args.verification,stage/'Evidence/release-review.json')
        source=create_source_archive(stage/'Source'/f'SpektraFilm-source-{VERSION}.zip')
        manifest=dict(version=VERSION,published_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
            windows=dict(executable='Windows/SpektraFilm/SpektraFilm.exe',version=VERSION,smoke_verified=True),
            android=dict(apk='Android/'+apk_name,version_code=VERSION_CODE,abi='arm64-v8a',
                         signature='local debug key / v2 verified',device_runtime_verified=False),
            source=source,evidence='Evidence/release-review.json',
            changes=review.get('changes',[]),verification=review.get('checks',{}),
            limitations=review.get('limitations',[]))
        write_json(stage/'manifest.json',manifest)
        (stage/'README.md').write_text(f'# SpektraFilm {VERSION}\n\n'
            'Windows: Windows/SpektraFilm/SpektraFilm.exe；便携版，保留整个目录及 _internal。\n\n'
            f'Android: Android/{apk_name}；arm64-v8a，Android8+，本地调试签名。\n\n'
            '本轮：自然RAW与可选完整光谱、基础调整/校准/HSL/曲线/色轮/蒙版、原位裁切/XPan/真实90度旋转、'
            '分类批量同步、输出配方、PNG16/TIFF16/线性DNG与宽色域ICC。桌面六任务工作区，手机预览和工具分离。\n\n'
            '验证：Windows候选成品核心流程、原尺寸TIFF、批量导入与高位深输出关键检查；Android构建、lint、主机实际编码解码、版本资源及签名。'
            '当前没有ADB设备，Android真机布局/触感和大图耗时未重新验收。历史RAW/大图测速不冒充本轮结果。\n\n'
            '默认原尺寸导出，显式裁切/配方缩放按用户设置；RAW原片另存不包含显影效果，处理后线性DNG是独立输出。'
            '字体保持中文朱雀仿宋/英文数字Noto Serif SC，重启旧实例以加载新版。\n\n'
            '完整证据与限制见manifest.json和Evidence；可重建源码在Source，说明及许可随源码保留。'
            '本次不生成哈希清单、不重复昂贵历史测试。\n',encoding='utf-8')
        # Confirm staging completed while the reviewed candidates stayed fixed.
        verify_candidates(windows,apk,review)
        audit_public_artifacts([stage])
        install_stage(stage)
    except Exception:
        # Retain a failed stage for diagnosis; the existing release is intact.
        raise
    print(json.dumps(dict(ok=True,version=VERSION,windows=manifest['windows']['executable'],
        android=manifest['android']['apk'],source=source,device_runtime_verified=False),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
