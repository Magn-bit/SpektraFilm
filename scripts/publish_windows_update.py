"""Review and publish the current Windows build; preserve Android evidence."""
from datetime import datetime,timezone,timedelta
from pathlib import Path
import argparse,ctypes as ct,json,os,shutil,subprocess,tempfile,uuid
from publish_local_release import ROOT,RELEASE,read_json,write_json,identity,create_source_archive,install_stage

import sys
sys.path.insert(0,str(ROOT))
from desktop.version import VERSION
REQUIRED=(
    'native/engine/runtime/spektrafilm_engine.dll','native/engine/runtime/spektrafilm_raw.dll',
    'native/engine/runtime/resources/vulkan/spk_editor_color.spv',
    'native/engine/runtime/resources/vulkan/spk_scan_hdr_expand.spv',
    'native/engine/runtime/resources/vulkan/spk_overscan_light.spv',
    'native/library/runtime/spklib-host.exe','native/color/runtime/spektrafilm_lcms2.dll',
    'native/hdr/runtime/spektrafilm_hdr.dll','native/hdr/runtime/libultrahdr-LICENSE.txt',
    'native/hdr/runtime/libjpeg-turbo-LICENSE.md','native/hdr/runtime/image_io-LICENSE.txt',
    'native/hdr/runtime/adobe-hdr-gain-map-NOTICE.txt','native/hdr/runtime/UPSTREAM.json',
    'desktop/qml/Studio.qml','desktop/qml/components/CompositionDialog.qml',
    'desktop/qml/components/CompositionFrameTile.qml',
    'desktop/qml/components/PanelToggle.qml',
    'desktop/qml/components/Theme.qml','desktop/qml/components/EditorTools.qml',
    'desktop/qml/components/ShadowSurface.qml','desktop/qml/components/DeferredPopup.qml',
    'assets/icons/triangle-down.svg','assets/icons/sun.svg','assets/icons/moon.svg',
    'desktop/qml/components/ImportWorkspace.qml','desktop/translations/ui.json',
    'desktop/qml/components/FilmLibrary.qml','desktop/qml/components/ExportResults.qml',
    'desktop/qml/components/ChannelMixerPanel.qml','desktop/qml/components/ParametricCurvePanel.qml',
    'desktop/qml/components/SceneHistogram.qml',
    'desktop/qml/components/GuidedGeometryOverlay.qml','desktop/qml/components/Navigator.qml',
    'native/metadata/runtime/exiftool-13.61_64/exiftool.exe',
    'assets/fonts/SpektraBilingualSerif-Regular.ttf','licenses/THIRD-PARTY.md',
    'licenses/SpektraLab_library/LICENSE')


def file_version(exe):
    version=ct.WinDLL('version')
    version.GetFileVersionInfoSizeW.argtypes=[ct.c_wchar_p,ct.c_void_p]
    version.GetFileVersionInfoW.argtypes=[ct.c_wchar_p,ct.c_uint32,ct.c_uint32,ct.c_void_p]
    version.VerQueryValueW.argtypes=[ct.c_void_p,ct.c_wchar_p,ct.c_void_p,ct.c_void_p]
    size=version.GetFileVersionInfoSizeW(str(exe),None)
    if not size:raise ValueError('Missing Windows version resource')
    buffer=ct.create_string_buffer(size);assert version.GetFileVersionInfoW(str(exe),0,size,buffer)
    pointer=ct.c_void_p();length=ct.c_uint32()
    assert version.VerQueryValueW(buffer,'\\',ct.byref(pointer),ct.byref(length))
    fixed=ct.cast(pointer,ct.POINTER(ct.c_uint32))
    return (fixed[2]>>16,fixed[2]&65535,fixed[3]>>16,fixed[3]&65535)


def candidate_metadata(candidate):
    artifacts={}
    for name in ('SpektraFilm.exe','SpektraFilmCLI.exe'):
        path=candidate/name;assert file_version(path)==tuple(int(n) for n in VERSION.split('.'))+(0,);artifacts[name]=identity(path)
    internal=candidate/'_internal';assert list((internal/'PySide6').rglob('qwindows.dll'))
    assert list(internal.glob('libheif*.dll'))
    assert list((internal/'PySide6').rglob('qsvg.dll')),'SVG image decoder missing'
    for name in REQUIRED:
        path=internal/name;assert path.is_file(),name;artifacts['_internal/'+name]=identity(path)
    return artifacts


def runtime_review(candidate,evidence,env):
    photograph=ROOT/'output/current-ui/source-preview.jpg'
    inputs=['--open',str(photograph)] if photograph.is_file() else []
    with (evidence/'windows-smoke.log').open('w',encoding='utf-8') as log:
        result=subprocess.run([str(candidate/'SpektraFilm.exe'),'--smoke-test','--smoke-spectral','--smoke-editor',
            '--verify-export',str(evidence/'source-size.tif'),'--verification-report',str(evidence/'windows-smoke.json'),
            '--screenshot',str(evidence/'editor.png'),'--verify-workspace',str(evidence/'workspace')]+inputs,
            cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300)
    if result.returncode:raise RuntimeError((evidence/'windows-smoke.log').read_text(encoding='utf-8',errors='replace')[-4000:])
    smoke=read_json(evidence/'windows-smoke.json');workspace=read_json(evidence/'workspace/workspace.json')
    assert smoke['ok'] and workspace['ok'] and workspace['frozen'],(smoke,workspace)
    assert smoke['native_spectral']['backend']['render_core']=='native-vulkan'
    cli=candidate/'SpektraFilmCLI.exe'
    with tempfile.TemporaryDirectory(prefix='spektrafilm-release-cli-') as temporary:
        prefix=[str(cli),'--session',str(Path(temporary)/'session.json')]
        def command(*args):
            answer=subprocess.run(prefix+list(args),cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=30)
            assert answer.returncode==0,(answer.stdout,answer.stderr)
            record=json.loads(answer.stdout);assert record['ok'];return record['result']
        status=command('status');command('open',str(evidence/'workspace/proof.heic'))
        exported=command('export','--recipe','png','--destination',str(evidence/'cli-output'))
        requests=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25'}},
            {'jsonrpc':'2.0','id':2,'method':'tools/list'}]
        mcp=subprocess.run(prefix+['mcp','--enable-local'],input=''.join(json.dumps(r)+'\n' for r in requests),
            cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=15)
        assert mcp.returncode==0,mcp.stderr
        replies=[json.loads(line) for line in mcp.stdout.splitlines()];assert 'result' in replies[0]
        tool_count=len(replies[1]['result']['tools']);assert tool_count>=12
    frozen_cli=dict(status=True,source_size_export=exported,mcp_tools=tool_count)
    write_json(evidence/'console.json',frozen_cli)
    return smoke,workspace,frozen_cli


def review(candidate,evidence,resume=False):
    evidence.mkdir(parents=True,exist_ok=True);metadata=candidate_metadata(candidate)
    checkpoint=evidence/'runtime-checked-artifacts.json'
    if resume:
        assert read_json(checkpoint)==metadata,'Runtime review belongs to a different candidate'
        smoke=read_json(evidence/'windows-smoke.json');workspace=read_json(evidence/'workspace/workspace.json')
        frozen_cli=read_json(evidence/'console.json')
        assert smoke['ok'] and workspace['ok'] and workspace['frozen'] and frozen_cli['status']
    else:
        env=dict(os.environ);windows=os.environ.get('SystemRoot','C:/Windows')
        env['PATH']=os.pathsep.join([str(Path(windows)/'System32'),windows]);env['PYTHONIOENCODING']='utf-8'
        for key in ('SPEKTRAFILM_PROBE_LIVE_ONLY','SPEKTRAFILM_PROBE_TOOLS_ONLY'):env.pop(key,None)
        smoke,workspace,frozen_cli=runtime_review(candidate,evidence,env)
        assert candidate_metadata(candidate)==metadata,'Candidate changed during runtime checks'
        write_json(checkpoint,metadata)
    assert smoke['native_spectral']['backend']['render_core']=='native-vulkan'
    assert workspace.get('refinements',{}).get('ok'),'Exact candidate refinement workflow did not pass'
    # These are earlier bounded source milestones, explicitly separate from the
    # exact frozen application review above. No repeated full-RAW benchmark.
    collect={
        'style-catalog.json':'output/style-catalog-0.8.2/report.json',
        'style-ui.json':'output/style-ui-0.8.2/report.json',
        'current-refinements.json':'output/current-refinements/report.json',
        'hdr-interaction.json':'output/hdr-interaction-review/report.json',
        'hdr-quality.json':'output/hdr-interaction-review/quality.json',
        'gradient-cursor.json':'output/gradient-cursor-refinement/verification.json',
        'guided-navigator.json':'output/guided-geometry-navigator/verification.json',
        'materials-frames.json':'output/lab-frames-papers-review/materials-and-frames.json',
        'frame-layout-boundaries.json':'output/lab-frames-papers-review/layout-boundaries.json',
        'material-edr.json':'output/lab-frames-papers-review/edr-materials.json',
        'additional-materials.json':'output/lab-frames-papers-review/additional-materials.json',
        'film-library.json':'output/film-library-review/report.json',
        'half-frame.json':'output/half-frame-review/report.json',
        'paper-lut.json':'output/paper-lut-review/report.json',
        'output-proof.json':'output/output-proof-review/report.json',
        'export-results.json':'output/export-results-ui/verification.json',
        'library-facets.json':'output/library-facets/verification.json',
        'library-sources-info.json':'output/library-sources-info/verification.json',
        'single-instance.json':'output/single-instance/verification.json',
        'gui-analysis-tools.json':'output/gui-analysis-tools/verification.json',
        'localization-increment.json':'output/localization-increment-review/report.json',
        'full-cache-validation.log':'output/full-detail-cache-validation.log',
        'full-cache-lifecycle.log':'output/full-detail-lifecycle-validation.log',
        'color-validation.log':'output/lab-color-key-validation.log',
        'photo-navigation.json':'output/photo-navigation/report.json',
        'scene-histogram.json':'output/scene-histogram-review/report.json',
        'lab-232-native.json':'output/lab-232-native-review/report.json',
        'dark-theme.json':'output/dark-theme-review/verification.json',
        'hdr-container.json':'output/hdr-container-review/report.json',
        'hdr-session.json':'output/hdr-session-review/report.json',
        'source-workspace.json':'output/windows-08-source-node-fixed/workspace/workspace.json',
        'lab-232-desktop.json':'output/lab-232-desktop-review/report.json'}
    milestones=evidence/'source-milestones';milestones.mkdir(exist_ok=True)
    for name,relative in collect.items():
        source=ROOT/relative
        if not source.is_file():raise ValueError('Missing milestone evidence: '+relative)
        shutil.copy2(source,milestones/name)
    photo_navigation=read_json(ROOT/'output/photo-navigation/report.json')
    assert photo_navigation.get('ok') and any('without clicking its thumbnail' in item for item in photo_navigation.get('checks',[]))
    report=dict(ok=True,version=VERSION,windows=dict(artifacts=metadata,smoke_ok=True),
        reference=dict(product='SpektraLab',version='2.3.2',commit='1952c63537ec576d24422f1065b12495631346a5',
            baseline_commit='2201f5fa4d256b0c742b46b8e31f8176a12ca6ea',
            scope='Apple 2.3.2 source delta over the audited 2.2.0 contracts, plus Windows 1.3.4 beta.2 shipped evidence; no macOS runtime equivalence claim'),
        changes=[
            'Background file validation and first-photo-priority import; custom directory icon probes disabled',
            'Confirmed import and export directories persist independently across restarts; cancelling preserves the previous location',
            'None is the first style; 18 practical portrait/landscape styles, stable grouping and selected-name feedback without promotional copy',
            'Continuous slider input uses local handle feedback and field notifications; full-size detail is invalidated immediately on edits',
            'Distributed neutral-evidence white balance with conservative confidence gating; optics now grouped within Basic',
            'Actual applied lens and local correction profile are shown, including unmatchable and unapplied states',
            'Crash-recoverable batch export snapshots, conflict-safe retry and monotonic per-file progress; masks and undo stay photo-specific',
            'One gallery entry, preserved bilingual serif fonts, photo-first workspace and bounded task panels',
            'Responsive HDR and three-line gradients with latest-input scheduling and consistent final processing',
            'Source-size detail/comparison tiles, independent working/preview/full-render disk budgets and exact same-color-domain export reuse',
            '30 film stocks and 9 actual paper profiles, current-photo material auditions and named categorized presets',
            'Native physical edges, half-frame source pairing/project files, per-hole printing gates and EXIF date/data back',
            'Channel mixer, four color wheels, five-channel parametric plus movable-point curves and guided geometry navigator',
            'Decode scene histogram remeasured after real native scene curves, including channel distributions and current exposure axis',
            'Source-sized JPEG HDR gain maps from the active spectral session in sRGB or Display P3; the Qt editing canvas remains SDR',
            'Real encoded recipe proofs, Unicode EXIF retention, per-file export errors and immutable-snapshot retry',
            'Same-window offline CLI/MCP, image content and native metering/latitude/place tools; disabled by default',
            'Combined gallery facets and metadata, single-instance Open With, export naming and correctly scoped paper cube tables',
            'Binary switch text and selected styling consistently show the current state across film, optics, geometry, masks, composition, settings and export controls',
            'Importing photos automatically selects and displays the first loaded image without requiring a thumbnail click'],
        checks=dict(executable=smoke['checks'],workspace=workspace['checks'],refinements=workspace['refinements'],console=frozen_cli,
            photo_navigation=photo_navigation,
            source_milestones=list(collect),milestone_scope='Bounded source checks reused; exact frozen runtime results are separately recorded above',
            testing='Key integration nodes only; no hashes, repeated whole-directory checks or historical full-RAW benchmarks'),
        limitations=[
            'Windows release only; Android remains 0.5.0/code23 with its matching source archive',
            'C1/LR private RAW algorithms, Apple Metal/EDR and macOS runtime equivalence are not claimed',
            'No separate light table or rating workflow, per the requested simpler product direction',
            'Native calibrated minilab is available only for Portra 400/Portra Endura; full spectral mode remains available',
            'Paper cube input is normalized paired-negative dye density, not ordinary RGB or current Cineon DI; 8 supported materials',
            'JPEG HDR gain-map export supports sRGB/Display P3 color printing or slide development; Qt remains an SDR display canvas, and composition/physical-edge HDR is explicitly refused',
            'Digital-intermediate photo previews use a dedicated view LUT while raw DI export retains Cineon codes; physical film-edge DI is explicitly refused rather than silently printing through paper',
            'Pair projects retain local full settings and unknown upstream fields; upstream look/auto-meter strategy mapping is not exhaustively equivalent',
            'Date/data imprint shares one date back; independent per-hole Data fields are not supported by this native ABI',
            'Photo-source-size exports retain source pixel density; explicit cropping, physical film fitting and composition canvas sizing are deliberate framing operations',
            'Performance conclusions refer to documented fixtures/builds and concurrent GPU load; no new universal RAW timing is asserted'])
    write_json(evidence/'review.json',report);return report


def publish(candidate,evidence):
    report=read_json(evidence/'review.json');assert report['ok'] and report['version']==VERSION
    assert candidate_metadata(candidate)==report['windows']['artifacts']
    previous=read_json(RELEASE/'manifest.json');android=previous['android'];assert (RELEASE/android['apk']).is_file()
    old_source=RELEASE/android.get('source',previous['source']['archive']);assert old_source.is_file()
    stage=RELEASE/('.stage-win-'+uuid.uuid4().hex[:8]);stage.mkdir()
    shutil.copytree(candidate,stage/'Windows/SpektraFilm');(stage/'Source').mkdir()
    shutil.copy2(old_source,stage/'Source'/old_source.name)
    shutil.copytree(evidence,stage/f'Evidence/Windows-{VERSION}')
    old_evidence=RELEASE/'Evidence/android-0.5.0-review.json'
    if old_evidence.is_file():shutil.copy2(old_evidence,stage/'Evidence/android-0.5.0-review.json')
    write_json(stage/'Evidence/release-review.json',report)
    source=create_source_archive(stage/'Source'/f'SpektraFilm-source-{VERSION}.zip',version=VERSION,
        building_notes='Windows corresponding source, including native library SDK and LittleCMS build inputs. '
            'Android development sources are unbuilt; current APK matching source is '+old_source.name+'.')
    manifest=dict(version=VERSION,published_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
        windows=dict(executable='Windows/SpektraFilm/SpektraFilm.exe',console='Windows/SpektraFilm/SpektraFilmCLI.exe',
            version=VERSION,smoke_verified=True,ui_revision='2026-11-12-workspace-depth-subtle-film-base'),
        android=android|dict(version='0.5.0',source='Source/'+old_source.name,unchanged=True),source=source,
        evidence=f'Evidence/Windows-{VERSION}/review.json',changes=report['changes'],verification=report['checks'],limitations=report['limitations'])
    write_json(stage/'manifest.json',manifest)
    (stage/'README.md').write_text('# SpektraFilm · Windows '+VERSION+'\n\n'
        '启动 Windows/SpektraFilm/SpektraFilm.exe，保留整个目录与 _internal。关闭旧实例后重开。\n\n'
        '直接拖入或使用导入页；图库为可选路径。新照片默认自然原片，可自行开启胶片。'
        '物理片边/日期/双帧在排版工作区；印相选择可选DI显示，原Cineon DI在输出配方。'
        'DI不支持物理片边；HDR增益图使用sRGB/Display P3照片JPEG配方，排版不支持，编辑画布仍为SDR。'
        '显示器ICC与软打样在设置的色彩页，语言支持中/繁中/英/日即时切换。\n\n'
        'SpektraFilmCLI.exe 提供离线批处理和显式 stdio MCP；同GUI会话接口默认关闭，可在设置的诊断页开启。'
        '详见源码 docs/local-automation.md。验证范围和资源限制见 Evidence/Windows-'+VERSION+'/review.json。\n\n'
        'Android保持0.5.0/code23及对应源码；本次没有Android或macOS/iOS更新。\n',encoding='utf-8')
    assert candidate_metadata(candidate)==report['windows']['artifacts']
    install_stage(stage,items=('Windows','Source','Evidence','README.md','manifest.json'));return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=('review','publish'))
    parser.add_argument('--windows',type=Path,required=True);parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--resume',action='store_true',help='Reuse successful runtime checks for the unchanged candidate')
    args=parser.parse_args()
    if args.mode=='publish' and args.resume:parser.error('--resume only applies to review')
    result=review(args.windows.resolve(),args.evidence.resolve(),args.resume) if args.mode=='review' else publish(args.windows.resolve(),args.evidence.resolve())
    print(json.dumps(dict(ok=result.get('ok',True),version=VERSION,mode=args.mode),ensure_ascii=False),flush=True)
