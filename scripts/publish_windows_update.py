"""Review and publish the current Windows build; preserve Android evidence."""
from datetime import datetime,timezone,timedelta
from pathlib import Path
import argparse,ctypes as ct,json,os,shutil,subprocess,uuid
from publish_local_release import ROOT,RELEASE,read_json,write_json,identity,create_source_archive,install_stage,audit_public_artifacts

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
    'desktop/qml/components/AiEditingPanel.qml',
    'desktop/qml/components/GradientMaskGuides.qml',
    'desktop/qml/components/StudioIconButton.qml',
    'desktop/qml/components/ToolNavigator.qml',
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
    'desktop/qml/components/qmldir','assets/icons/gear.svg','assets/icons/rotate.svg',
    'assets/icons/sparkles.svg','assets/shaders/mask-gradient.frag',
    'assets/shaders/mask-gradient.frag.qsb',
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
            '--screenshot',str(evidence/'editor.png')]+inputs,
            cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300)
    if result.returncode:raise RuntimeError((evidence/'windows-smoke.log').read_text(encoding='utf-8',errors='replace')[-4000:])
    smoke=read_json(evidence/'windows-smoke.json')
    assert smoke['ok'],smoke
    assert smoke['native_spectral']['backend']['render_core']=='native-vulkan'

    mask_dir=evidence/'mask-ui';mask_dir.mkdir(exist_ok=True)
    with (evidence/'mask-ui-smoke.log').open('w',encoding='utf-8') as log:
        result=subprocess.run([str(candidate/'SpektraFilm.exe'),'--smoke-test','--smoke-spectral',
            '--verify-masks',str(mask_dir),'--verification-report',str(mask_dir/'smoke.json'),
            '--screenshot',str(mask_dir/'before-masks.png')],cwd=ROOT,env=env,
            stdout=log,stderr=subprocess.STDOUT,timeout=300)
    if result.returncode:raise RuntimeError((evidence/'mask-ui-smoke.log').read_text(encoding='utf-8',errors='replace')[-4000:])
    mask=read_json(mask_dir/'mask-ui.json')
    assert mask['ok'] and mask['frozen'],mask

    workspace_dir=evidence/'workspace';workspace_dir.mkdir(exist_ok=True)
    probe_env=dict(env);probe_env.pop('SPEKTRAFILM_PROBE_TOOLS_ONLY',None)
    probe_env['SPEKTRAFILM_PROBE_LIVE_ONLY']='1'
    with (evidence/'workspace-smoke.log').open('w',encoding='utf-8') as log:
        result=subprocess.run([str(candidate/'SpektraFilm.exe'),'--smoke-test','--verify-workspace',
            str(workspace_dir),'--verification-report',str(workspace_dir/'smoke.json'),
            '--screenshot',str(workspace_dir/'editor.png')],cwd=ROOT,env=probe_env,
            stdout=log,stderr=subprocess.STDOUT,timeout=300)
    if result.returncode:raise RuntimeError((evidence/'workspace-smoke.log').read_text(encoding='utf-8',errors='replace')[-4000:])
    workspace=read_json(workspace_dir/'workspace.json')
    assert workspace['ok'] and workspace['frozen'] and workspace.get('live_gui',{}).get('cli_set_get_copy_paste_export'),workspace
    frozen_cli=workspace['live_gui']
    return smoke,workspace,frozen_cli,mask


def review(candidate,evidence,resume=False):
    evidence.mkdir(parents=True,exist_ok=True);metadata=candidate_metadata(candidate)
    checkpoint=evidence/'runtime-checked-artifacts.json'
    if resume:
        assert read_json(checkpoint)==metadata,'Runtime review belongs to a different candidate'
        smoke=read_json(evidence/'windows-smoke.json');workspace=read_json(evidence/'workspace/workspace.json')
        mask=read_json(evidence/'mask-ui/mask-ui.json')
        frozen_cli=workspace.get('live_gui',{})
        assert (smoke['ok'] and workspace['ok'] and workspace['frozen'] and
                frozen_cli.get('cli_set_get_copy_paste_export') and mask['ok'])
    else:
        env=dict(os.environ);windows=os.environ.get('SystemRoot','C:/Windows')
        env['PATH']=os.pathsep.join([str(Path(windows)/'System32'),windows]);env['PYTHONIOENCODING']='utf-8'
        for key in ('SPEKTRAFILM_PROBE_LIVE_ONLY','SPEKTRAFILM_PROBE_TOOLS_ONLY'):env.pop(key,None)
        smoke,workspace,frozen_cli,mask=runtime_review(candidate,evidence,env)
        assert candidate_metadata(candidate)==metadata,'Candidate changed during runtime checks'
        write_json(checkpoint,metadata)
    assert smoke['native_spectral']['backend']['render_core']=='native-vulkan'
    assert workspace.get('live_gui',{}).get('cli_set_get_copy_paste_export')
    assert mask.get('ok') and mask.get('frozen')
    # Reuse retained release evidence for unchanged product areas; keep current
    # frozen-build checks above separate from those earlier milestones.
    collect={
        'windows-0.8.5-review.json':'release/Evidence/Windows-0.8.5/review.json',
        'windows-0.8.5-smoke.json':'release/Evidence/Windows-0.8.5/smoke.json',
        'windows-0.8.5-mask-ui.json':'release/Evidence/Windows-0.8.5/mask-ui.json',
        'ui-refinement-20261112.json':'release/Evidence/UI-refinement-20261112/review.json'}
    milestones=evidence/'source-milestones';milestones.mkdir(exist_ok=True)
    for name,relative in collect.items():
        source=ROOT/relative
        if not source.is_file():raise ValueError('Missing milestone evidence: '+relative)
        shutil.copy2(source,milestones/name)
    report=dict(ok=True,version=VERSION,windows=dict(artifacts=metadata,smoke_ok=True),
        reference=dict(product='SpektraLab',version='2.3.2',commit='1952c63537ec576d24422f1065b12495631346a5',
            baseline_commit='2201f5fa4d256b0c742b46b8e31f8176a12ca6ea',
            scope='Apple 2.3.2 source delta over the audited 2.2.0 contracts, plus Windows 1.3.4 beta.2 shipped evidence; no macOS runtime equivalence claim'),
        changes=[
            'Optional external AI photo analysis and scene-aware style recommendations in the editor workspace',
            'Supported Responses, Chat Completions and Anthropic Messages endpoints with explicit user-configured model IDs',
            'Windows API credentials are protected with current-user DPAPI and never exposed to QML or included in source/release packages',
            'AI proposals are schema-validated, tied to the current photo/edit state and applied as one undoable edit; nothing is sent until the user starts analysis',
            'Provider setup stays inline in the AI workspace; photo preview and development tools remain available in the same window',
            'Mask overlay updates accept only a valid prefix of the current brush stroke, while rejecting stale edits and geometry',
            'Gradient-mask guides, editor navigation and icon controls are included in the frozen Windows package'],
        checks=dict(executable=smoke['checks'],workspace=workspace['checks'],mask_ui=mask['checks'],
            gui_automation=workspace['live_gui'],console=frozen_cli,
            source_milestones=list(collect),milestone_scope='Windows 0.8.5 evidence is reused only for unchanged areas; exact 0.8.6 frozen-build checks are recorded separately',
            testing='Core spectral/TIFF, exact-package masks and same-window CLI/MCP; no hashes or repeated full-size benchmarks'),
        limitations=[
            'Windows release only; Android remains 0.5.0/code23 with its matching source archive',
            'External model quality, provider uptime and live network responses were not tested; AI requires a provider configured by the user',
            'The exact-package export and interaction smoke used a bounded 900x600 synthetic chart; no new full-size RAW timing is asserted',
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
    audit_public_artifacts([candidate,RELEASE/android['apk'],old_source,evidence])
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
            version=VERSION,smoke_verified=True,ui_revision='2026-11-12-inline-ai-photo-workspace'),
        android=android|dict(version='0.5.0',source='Source/'+old_source.name,unchanged=True),source=source,
        evidence=f'Evidence/Windows-{VERSION}/review.json',changes=report['changes'],verification=report['checks'],limitations=report['limitations'])
    write_json(stage/'manifest.json',manifest)
    (stage/'README.md').write_text('# SpektraFilm · Windows '+VERSION+'\n\n'
        '启动 Windows/SpektraFilm/SpektraFilm.exe，保留整个目录与 _internal。关闭旧实例后重开。\n\n'
        '直接拖入或使用导入页；图库为可选路径。新照片默认自然原片，可自行开启胶片。'
        'AI 工作区可选配置外部视觉模型；分析由用户主动发起，建议经确认后作为一次可撤销调整应用。\n'
        '物理片边/日期/双帧在排版工作区；印相选择可选DI显示，原Cineon DI在输出配方。'
        'DI不支持物理片边；HDR增益图使用sRGB/Display P3照片JPEG配方，排版不支持，编辑画布仍为SDR。'
        '显示器ICC与软打样在设置的色彩页，语言支持中/繁中/英/日即时切换。\n\n'
        'SpektraFilmCLI.exe 提供离线批处理和显式 stdio MCP；同GUI会话接口默认关闭，可在设置的诊断页开启。'
        '详见源码 docs/local-automation.md。验证范围和资源限制见 Evidence/Windows-'+VERSION+'/review.json。\n\n'
        'Android保持0.5.0/code23及对应源码；本次没有Android或macOS/iOS更新。\n',encoding='utf-8')
    assert candidate_metadata(candidate)==report['windows']['artifacts']
    audit_public_artifacts([stage])
    install_stage(stage,items=('Windows','Source','Evidence','README.md','manifest.json'));return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=('review','publish'))
    parser.add_argument('--windows',type=Path,required=True);parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--resume',action='store_true',help='Reuse successful runtime checks for the unchanged candidate')
    args=parser.parse_args()
    if args.mode=='publish' and args.resume:parser.error('--resume only applies to review')
    result=review(args.windows.resolve(),args.evidence.resolve(),args.resume) if args.mode=='review' else publish(args.windows.resolve(),args.evidence.resolve())
    print(json.dumps(dict(ok=result.get('ok',True),version=VERSION,mode=args.mode),ensure_ascii=False),flush=True)
