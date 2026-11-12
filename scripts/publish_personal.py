"""Verify and publish the current local build; preserve earlier Personal releases."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import argparse, hashlib, json, os, shutil, subprocess, sys, uuid, zipfile

ROOT=Path(__file__).resolve().parents[1]
VERSION='0.2.4'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--resume-stage', help='Reuse a known retained .personal-* staging directory after inspection')
args=parser.parse_args()
OUT=ROOT/('output/personal-release-'+VERSION)
OUT.mkdir(parents=True,exist_ok=True)
digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
source=ROOT/'dist/SpektraFilm'
exe=source/'SpektraFilm.exe'
apk=ROOT/'android/app/build/outputs/apk/debug/app-debug.apk'
font_record=json.loads((ROOT/'assets/fonts/interface-font.json').read_text(encoding='utf-8'))
family=font_record['family']
font_relative=Path('assets/fonts')/font_record['file']
assert exe.stat().st_mtime>max(p.stat().st_mtime for p in (ROOT/'desktop').rglob('*.py')), 'Rebuild the latest Windows code first'
assert apk.stat().st_mtime>max(p.stat().st_mtime for p in (ROOT/'android/app/src').rglob('*.kt')), 'Rebuild the latest Android code first'
assert 'BUILD SUCCESSFUL' in (ROOT/'output/android/build-personal-0.2.4.log').read_text(encoding='utf-8',errors='replace')
assert not (OUT/'verified-export.jpg').exists(), 'Inspect an existing verification result before repeating publication'
assert digest(ROOT/font_relative)==font_record['sha256']
assert digest(source/'_internal'/font_relative)==font_record['sha256']
for original in font_record['sources'].values():
    assert digest(ROOT/'assets/fonts'/original['file'])==original['sha256']
for license_file in font_record['licenses']:
    assert (source/'_internal/assets/fonts'/license_file).is_file()
for qml in (ROOT/'desktop/qml').rglob('*.qml'):
    assert digest(qml)==digest(source/'_internal'/qml.relative_to(ROOT)), qml
with zipfile.ZipFile(apk) as package:
    assert hashlib.sha256(package.read(font_relative.as_posix())).hexdigest()==font_record['sha256']
    for license_file in font_record['licenses']:
        assert 'assets/fonts/'+license_file in package.namelist()
    assert 'assets/PingFang.ttc' not in package.namelist(), 'Unused personal font assets remain in this build'
    assert 'lib/arm64-v8a/libpython3.10.so' in package.namelist()
    dex=b''.join(package.read(n) for n in package.namelist() if n.startswith('classes') and n.endswith('.dex'))
    for symbol in (b'InterfaceTypography',b'PhotoBrowserDialog',b'removePhotos',b'render_argb'):
        assert symbol in dex,symbol

destination=ROOT/'release/Personal'
def require_closed_destination():
    if sys.platform!='win32': return
    command="""@(Get-CimInstance Win32_Process -Filter "Name='SpektraFilm.exe'" | Select-Object -ExpandProperty ExecutablePath) | ConvertTo-Json -Compress"""
    result=subprocess.run(['powershell.exe','-NoProfile','-Command',command],capture_output=True,text=True,check=True)
    paths=json.loads(result.stdout.strip() or '[]')
    if isinstance(paths,str): paths=[paths]
    for path in paths:
        if path and Path(path).resolve().is_relative_to(destination.resolve()):
            raise RuntimeError('The current Personal application is running; leave it open and publish only after a normal user close.')
require_closed_destination()
if args.resume_stage:
    stage=(ROOT/args.resume_stage).resolve()
    assert stage.parent==(ROOT/'release').resolve() and stage.name.startswith('.personal-') and stage.is_dir(), 'Invalid retained staging directory'
else:
    stage=ROOT/'release'/('.personal-'+uuid.uuid4().hex[:8])
    stage.mkdir()
windows=stage/'Windows/SpektraFilm'
windows.parent.mkdir(exist_ok=True)
shutil.copytree(source,windows,dirs_exist_ok=True)
android=stage/'Android'
android.mkdir(exist_ok=True)
target_apk=android/f'SpektraFilm-{VERSION}-personal.apk'
if target_apk.exists():
    assert digest(target_apk)==digest(apk), 'Inspect a differing staged APK before replacing it'
else:
    shutil.copy2(apk,target_apk)
environment=os.environ.copy()
system=os.environ.get('SYSTEMROOT','C:/Windows')
environment['PATH']=str(Path(system)/'System32')+';'+system
for key in ('PYTHONPATH','PYTHONHOME','QT_PLUGIN_PATH','QT_QPA_PLATFORM','SPEKTRAFILM_FONT_DIR'):
    environment.pop(key,None)
def run(args,name,env=None,timeout=150):
    print('Verifying '+name,flush=True)
    with (OUT/(name+'.log')).open('w',encoding='utf-8') as stream:
        result=subprocess.run([str(a) for a in args],cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=timeout)
    assert result.returncode==0,(name,(OUT/(name+'.log')).read_text(encoding='utf-8',errors='replace')[-2500:])
report=OUT/'windows-smoke.json'
run([windows/'SpektraFilm.exe','--smoke-test','--verify-export',OUT/'verified-export.jpg','--verification-report',report,'--screenshot',OUT/'editor.png'],'windows-smoke',environment)
evidence=json.loads(report.read_text(encoding='utf-8'))
assert evidence['ok'] and evidence['font_family']==family
for role in ('body','display','editorial'):
    assert evidence['glyph_families'][role]==[family], (role,evidence['glyph_families'])
    assert {run['weight'] for run in evidence['glyph_runs'][role]}=={400}
assert evidence['settings']['spectral'] and 'source integrity' in evidence['checks']
for state in ('empty','export','library'):
    args=[windows/'SpektraFilm.exe','--capture-state',state,'--screenshot',OUT/(state+'.png')]
    if state=='export': args+=['--open',OUT/'verified-export.jpg']
    run(args,state,environment,30)
signer=ROOT/'.tools/android-sdk/build-tools/35.0.0/apksigner.bat'
run(['cmd.exe','/d','/c',signer,'verify','--verbose',target_apk],'android-signature',timeout=30)
run([ROOT/'.tools/android-sdk/platform-tools/adb.exe','devices','-l'],'android-devices',timeout=20)
run([ROOT/'.tools/android-sdk/build-tools/35.0.0/aapt.exe','dump','badging',target_apk],'android-package',timeout=20)
metadata=(OUT/'android-package.log').read_text(encoding='utf-8')
assert "versionCode='6'" in metadata and "versionName='0.2.4'" in metadata
manifest=dict(version=VERSION,variant='local',published_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
    windows=dict(executable='Windows/SpektraFilm/SpektraFilm.exe',sha256=digest(windows/'SpektraFilm.exe'),font_runtime_verified=True,smoke=evidence),
    android=dict(apk='Android/'+target_apk.name,sha256=digest(target_apk),signing='debug',abi='arm64-v8a',version_name=VERSION,version_code=6,device_runtime_verified=False,font_assets_verified=True),
    typography=font_record,tests=dict(python='output/test-personal-0.2.4.log',native_interface='output/interface-refinement/report.json',font_provenance='output/build-interface-font.log'))
(stage/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
(stage/'README.md').write_text('''# SpektraFilm 0.2.4 · 本地使用版

Windows：双击 Windows/SpektraFilm/SpektraFilm.exe，保留完整文件夹与 _internal。
Android：安装 Android/SpektraFilm-0.2.4-personal.apk；ARM64，Android 8+，开发调试签名。

全界面按语言统一：中文使用朱雀仿宋，英文及数字使用 Noto Serif SC Regular。
标题、正文、按钮、参数及应用弹窗使用同一套字形组合；保留四级字号与文字对比度，不合成粗体。
组合字体只用于消除两端回退差异，13009 个编码字形的轮廓与水平度量已逐字与来源核验。
原始字体及两份 SIL OFL 1.1 许可保留在 assets/fonts；不再加载或打包此前的 Apple 个人字体。
旧版和原来的 personal-fonts 目录保留，当前目录沿用 Personal 名称以保持启动路径不变。

Windows：多选后移除或 Delete；保留原片与编辑记录。适合/100%/200%、滚轮定点缩放、拖动、双击适合/100%。
Android：点照片缩略图直接编辑，右侧勾选独立用于批量，支持从列表移除；原片保留。
两端完整光谱；拖动期间的交互近似明确标注。Windows 实际 EXE 已完成预览、撤销/重做与导出验证。
Android 已编译、检查字体资源和签名；没有连接设备，未做真机运行与截图验收。
macOS/iOS 状态见项目 docs/apple-builds.md，当前目录不包含 Apple 平台成品。
''',encoding='utf-8')
files=sorted(p for p in stage.rglob('*') if p.is_file())
(stage/'SHA256SUMS.txt').write_text(chr(10).join(digest(p)+'  '+p.relative_to(stage).as_posix() for p in files)+chr(10),encoding='utf-8')
require_closed_destination()
if destination.exists():
    history=ROOT/'release/personal-history'
    history.mkdir(exist_ok=True)
    destination.rename(history/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:4]))
stage.rename(destination)
result=dict(ok=True,version=VERSION,windows=str(destination/'Windows/SpektraFilm/SpektraFilm.exe'),android=str(destination/'Android'/target_apk.name),files=len(files),evidence=str(OUT))
(OUT/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
