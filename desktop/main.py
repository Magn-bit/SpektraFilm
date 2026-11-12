from pathlib import Path
import argparse
import os
import sys
import tempfile
import time

PYTHON_ENTRY=time.perf_counter()

ROOT=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
if Path(sys.executable).stem.casefold()=='spektrafilmcli':
    from desktop.automation import main as automation_main
    raise SystemExit(automation_main())
from PySide6.QtCore import QTimer, QUrl, QObject, QCoreApplication, QStandardPaths, qInstallMessageHandler,QSettings
from PySide6.QtGui import QFont, QFontDatabase, QTextLayout
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from desktop.controller import Controller, PhotoProvider
from desktop.window_state import WindowState
from desktop.typography import load_mincho
from desktop.application_identity import configure_process_identity, configure_application_icon, configure_window_icon

def main():
    qInstallMessageHandler(lambda kind,context,message: print(message,flush=True))
    parser=argparse.ArgumentParser()
    parser.add_argument('files',nargs='*',help='Photos opened from Explorer or another application')
    parser.add_argument('--open',nargs='*',default=[])
    parser.add_argument('--screenshot')
    parser.add_argument('--smoke-test',action='store_true')
    parser.add_argument('--verify-export')
    parser.add_argument('--verification-report')
    parser.add_argument('--smoke-spectral',action='store_true')
    parser.add_argument('--smoke-editor',action='store_true',help='Exercise levels, brightness and HDR in the exact packaged renderer')
    parser.add_argument('--smoke-film-policy',action='store_true')
    parser.add_argument('--verify-workspace',help='Opt-in exact-build workspace milestone output folder (requires --smoke-test)')
    parser.add_argument('--smoke-stock',help='Film ID for smoke verification (default: kodak_portra_400)')
    parser.add_argument('--capture-state',choices=['empty','editor','library','export','grain','darkroom'])
    args=parser.parse_args()
    if (args.verify_export or args.verify_workspace or args.smoke_spectral or args.smoke_editor or args.smoke_film_policy or args.smoke_stock) and not args.smoke_test:
        parser.error('--verify-export and smoke options require --smoke-test')
    configure_process_identity()
    QCoreApplication.setApplicationName('SpektraFilm')
    QCoreApplication.setOrganizationName('SpektraFilm')
    if not (args.smoke_test or args.capture_state):
        from desktop.preferences import PreferenceStore
        settings_path=Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation))/'preferences.json'
        scale=PreferenceStore(settings_path).values['ui_scale']
        try:external=float(os.environ.get('QT_SCALE_FACTOR','1'))
        except ValueError:external=1.
        os.environ['QT_SCALE_FACTOR']=str(scale*external)
    app=QApplication(sys.argv[:1])
    app.setApplicationName('SpektraFilm')
    app.setOrganizationName('SpektraFilm')
    paths=args.files+args.open
    single_instance=None
    if not (args.smoke_test or args.capture_state or args.screenshot):
        from desktop.single_instance import SingleInstance
        single_instance=SingleInstance(app)
        try:
            if single_instance.claim_or_forward(paths):return 0
        except OSError as error:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(None,'SpektraFilm',str(error))
            return 3
    configure_application_icon(app, ROOT)
    app.setStyle('Fusion')
    family=load_mincho(app,ROOT)
    reduced_motion=False
    if sys.platform=='win32':
        import ctypes
        enabled=ctypes.c_int(1)
        ctypes.windll.user32.SystemParametersInfoW(0x1042,0,ctypes.byref(enabled),0)
        reduced_motion=not bool(enabled.value)
    QQuickStyle.setStyle('Basic')
    provider=PhotoProvider()
    test_store=tempfile.TemporaryDirectory() if args.smoke_test or args.capture_state else None
    controller=Controller(provider,test_store.name if test_store else None)
    smoke_stock=args.smoke_stock or 'kodak_portra_400'
    if args.smoke_test and smoke_stock not in {stock['id'] for stock in controller.stocks}:
        parser.error('Unknown smoke film ID: '+smoke_stock)
    engine=QQmlApplicationEngine()
    from desktop.localization import install_localization
    language_settings=QSettings(str(Path(test_store.name)/'language.ini'),QSettings.IniFormat) if test_store else None
    install_localization(app,engine,language='zh-Hans' if test_store else None,settings=language_settings)
    engine.addImageProvider('photos',provider)
    engine.rootContext().setContextProperty('ctrl',controller)
    engine.rootContext().setContextProperty('assetsUrl',QUrl.fromLocalFile(str(ROOT/'assets')+'/').toString())
    engine.rootContext().setContextProperty('minchoFamily',family)
    engine.rootContext().setContextProperty('interfaceDisplayFamily',app._interface_font_selection['display'])
    engine.rootContext().setContextProperty('interfaceEditorialFamily',app._interface_font_selection['editorial'])
    engine.rootContext().setContextProperty('systemReduceMotion',reduced_motion)
    engine.load(QUrl.fromLocalFile(str(ROOT/'desktop/qml/Studio.qml')))
    if not engine.rootObjects(): return 2
    root_window=engine.rootObjects()[0]
    def update_display_profile():
        screen=root_window.screen()
        controller.colorDisplay.setMonitor(screen.name() if screen else '')
    root_window.screenChanged.connect(lambda screen:update_display_profile())
    update_display_profile()
    configure_window_icon(root_window, app, ROOT)
    first_frame=[False]
    def report_first_frame():
        if not first_frame[0]:
            first_frame[0]=True
            print(f'STARTUP_FIRST_FRAME_MS {(time.perf_counter()-PYTHON_ENTRY)*1000:.1f}',flush=True)
    root_window.frameSwapped.connect(report_first_frame)
    if args.capture_state:
        preview_marks=set()
        def report_preview():
            if not controller.frame:return
            stage='READY' if not controller.busy else 'PREVIEW'
            if stage not in preview_marks:
                preview_marks.add(stage)
                print(f'STARTUP_{stage}_MS {(time.perf_counter()-PYTHON_ENTRY)*1000:.1f}',flush=True)
        controller.frameChanged.connect(report_preview)
        controller.stateChanged.connect(report_preview)
    state_path=Path(test_store.name if test_store else QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation))/'window.ini'
    window_state=WindowState(engine.rootObjects()[0],state_path)
    engine.rootObjects()[0].restoreRequested.connect(window_state.restoreNormal)
    window_state.restore()
    from desktop.import_bridge import PhotoImportBridge
    import_bridge=PhotoImportBridge(app,engine.rootObjects()[0],controller)
    if single_instance:single_instance.bind(root_window,controller)
    if args.smoke_test and not paths:
        # A synthetic calibration chart is a test fixture only, never a sample
        # photograph or a normal application startup asset.
        import numpy as np
        from PIL import Image
        x=np.linspace(0,1,900)[None,:]
        y=np.linspace(0,1,600)[:,None]
        chart=np.stack([np.broadcast_to(x,(600,900)),np.broadcast_to(y,(600,900)),np.broadcast_to(.25+.5*x,(600,900))],axis=-1)
        fixture=Path(test_store.name)/'calibration-test.png'
        Image.fromarray((chart*255).astype('uint8')).save(fixture)
        paths=[str(fixture)]
    legacy_settings=None
    if args.smoke_film_policy:
        import json
        legacy_settings=dict(stock=smoke_stock,exposure=0,grain=23,grain_size=.65,
            grain_type='fine',halation=5,vignette=9,strength=80,spectral=False,film_enabled=False,
            temperature=3200,tint=40,contrast=60,warmth=25,saturation=-30,vibrance=70,
            highlights=-50,shadows=45,black_point=12,white_point=85,gamma=1.7,
            calibration_red_hue=50,calibration_blue_saturation=80,
            curves={'master':[[0,.2],[1,.8]]},grading={'shadows':{'hue':200,'saturation':50}},
            hsl={'orange':{'hue':40,'saturation':60,'luminance':30}},
            geometry={'rotation':12,'crop':[.1,.2,.8,.9]},
            masks=[{'id':'old-mask','name':'Old mask','kind':'radial','exposure':2}],
            look_lut='legacy-look',look_strength=40,lens_correction=True,defringe=True)
        controller._edit_path(paths[0]).write_text(json.dumps({'version':1,'settings':legacy_settings}),encoding='utf-8')
    if not single_instance:QTimer.singleShot(0,lambda:controller.add_paths(paths))
    if args.capture_state:
        from PySide6.QtCore import QMetaObject
        capture_started=time.monotonic()
        def capture():
            window=engine.rootObjects()[0]
            if args.capture_state!='empty' and (controller.busy or not controller.frame):
                if time.monotonic()-capture_started<60:
                    QTimer.singleShot(100,capture)
                else:
                    print('CAPTURE_FAILED: final rendered frame was not ready',flush=True)
                    app.exit(3)
                return
            if args.capture_state=='library':
                popup=window.findChild(QObject,'libraryPopup')
                QMetaObject.invokeMethod(popup,'open')
            elif args.capture_state=='grain':
                popup=window.findChild(QObject,'grainTypeMenu')
                QMetaObject.invokeMethod(popup,'open')
            elif args.capture_state=='export':
                popup=window.findChild(QObject,'exportDialog')
                QMetaObject.invokeMethod(popup,'open')
            elif args.capture_state=='darkroom':
                section=window.findChild(QObject,'printSection')
                assert section is not None,'Missing printSection capture target'
                section.setProperty('expanded',True)
                def scroll_to_bottom():
                    scroll=window.findChild(QObject,'parameterScroll')
                    assert scroll is not None,'Missing parameterScroll capture target'
                    flickable=scroll.property('contentItem')
                    bottom=max(0,float(flickable.property('contentHeight'))-float(flickable.property('height')))
                    flickable.setProperty('contentY',bottom)
                QTimer.singleShot(80,scroll_to_bottom)
            def save():
                if args.screenshot:
                    Path(args.screenshot).parent.mkdir(parents=True,exist_ok=True)
                    if not window.grabWindow().save(args.screenshot):
                        print('CAPTURE_FAILED: screenshot could not be saved',flush=True);app.exit(3);return
                print('CAPTURE_OK',args.capture_state,flush=True)
                app.exit(0)
            QTimer.singleShot(600,save)
        QTimer.singleShot(350,capture)
    if args.smoke_test:
        ticks=[0]
        phase=[0]
        checks=[]
        source_stat=[None]
        policy_checked=[False]
        stock_checked=[False]
        def report(ok):
            if args.verification_report:
                import json
                from desktop.compute import status as compute_status
                from desktop.native_spectral import backend_info
                target=Path(args.verification_report)
                target.parent.mkdir(parents=True,exist_ok=True)
                probe_fonts={'body':app.font()}
                title=engine.rootObjects()[0].findChild(QObject,'filmTitle')
                if title is not None: probe_fonts['display']=title.property('font')
                editorial=engine.rootObjects()[0].findChild(QObject,'emptyTitle')
                if editorial is not None: probe_fonts['editorial']=editorial.property('font')
                glyphs={}
                glyph_runs={}
                for role, probe_font in probe_fonts.items():
                    probe_text='导出作品 胶片档案' if role=='editorial' else '导入照片 胶片档案 Portra 400'
                    layout=QTextLayout(probe_text,probe_font)
                    layout.beginLayout();layout.createLine();layout.endLayout()
                    glyphs[role]=sorted({run.rawFont().familyName() for run in layout.glyphRuns()})
                    glyph_runs[role]=[dict(family=run.rawFont().familyName(),weight=int(run.rawFont().weight())) for run in layout.glyphRuns()]
                target.write_text(json.dumps(dict(ok=ok,status=controller.status,settings=controller.settings,checks=checks,
                    smoke_stock=smoke_stock,catalog_stocks=[stock['id'] for stock in controller.stocks],
                    render_ms=controller.renderMs,font_family=family,font_selection=app._interface_font_selection,
                    glyph_families=glyphs,glyph_runs=glyph_runs,
                    compute=compute_status(),native_spectral=backend_info()),ensure_ascii=False,indent=2),encoding='utf-8')
        def check():
            ticks[0]+=1
            if controller.frame and not controller.busy:
                if not stock_checked[0]:
                    if controller.settings['stock']!=smoke_stock:
                        controller.selectStock(smoke_stock)
                        return
                    stock_checked[0]=True
                    checks.append('requested film selected')
                if args.smoke_spectral and not controller.settings['film_enabled']:
                    controller.setFilmEnabled(True)
                    return
                if args.smoke_film_policy and not policy_checked[0]:
                    from dataclasses import asdict
                    from desktop.imaging import Settings,settings_from_record
                    actual=controller.settings
                    assert actual==asdict(settings_from_record({'version':1,'settings':legacy_settings}))
                    controller.updateParameter('contrast',70)
                    controller.updateParameter('temperature',2700)
                    controller.setFilmEnabled(False)
                    controller.setCurvePoints('master',[[0,.2],[1,.8]])
                    controller.updateHslParameter('orange','saturation',80)
                    controller.updateGradingParameter('shadows','saturation',60)
                    controller.updateGeometry('rotation',15)
                    controller.addMask()
                    assert controller.settings['contrast']==70 and controller.settings['temperature']==2700
                    assert not controller.settings['film_enabled'] and controller.settings['masks']
                    before=controller.settings
                    controller.undo()
                    assert not controller.settings['masks']
                    controller.redo()
                    assert controller.settings==before
                    policy_checked[0]=True
                    checks.extend(['optional film editor','legacy edit migration','restored tools and history'])
                    return
                if args.verify_export and phase[0]==0:
                    info=Path(paths[0]).stat()
                    source_stat[0]=(info.st_size,info.st_mtime_ns)
                    controller.beginEdit()
                    controller.updateParameter('exposure',.4)
                    controller.updateParameter('exposure',1.1)
                    if args.smoke_editor:
                        controller.updateParameter('brightness',12)
                        controller.updateParameter('whites',-8)
                        controller.updateParameter('blacks',5)
                        controller.setLevelParameter('master','gamma',1.05)
                        controller.setLevelParameter('red','output_white',.98)
                    controller.endEdit()
                    assert controller.canUndo
                    controller.undo()
                    assert controller.settings['exposure']==0
                    controller.redo()
                    assert controller.settings['exposure']==1.1
                    if args.smoke_editor:
                        assert controller.settings['brightness']==12 and controller.settings['whites']==-8
                        assert controller.settings['levels']['master']['gamma']==1.05
                        checks.append('native levels brightness and HDR with grouped history')
                    assert controller.settings['spectral']
                    checks.extend(['asynchronous import','rendered preview','grouped undo','redo'])
                    phase[0]=1
                    return
                if args.verify_export and phase[0]==1:
                    suffix=Path(args.verify_export).suffix.lower()
                    preset='TIFF' if suffix in ('.tif','.tiff') else 'JPG_HIGH'
                    assert controller.export_to(str(Path(args.verify_export).resolve()),preset=preset)
                    phase[0]=2
                    return
                if args.verify_export and phase[0]==2:
                    from PIL import Image
                    from desktop.imaging import read_photo
                    if not Path(args.verify_export).is_file():
                        report(False);app.exit(3);return
                    from shared.geometry import output_size
                    source_size=output_size(*read_photo(paths[0]).size,controller._settings.geometry)
                    with Image.open(args.verify_export) as exported:
                        assert exported.size==source_size
                        assert exported.info.get('icc_profile')
                    info=Path(paths[0]).stat()
                    assert (info.st_size,info.st_mtime_ns)==source_stat[0]
                    checks.extend(['full-size export','embedded sRGB profile','source file size and timestamp unchanged'])
                window=engine.rootObjects()[0]
                # stop before shutdown, which may briefly process more events
                # while the controller drains its background queue.
                timer.stop()
                if args.screenshot:
                    Path(args.screenshot).parent.mkdir(parents=True,exist_ok=True)
                    assert window.grabWindow().save(args.screenshot)
                if args.verify_workspace:
                    from desktop.workspace_probe import WorkspaceProbe
                    def complete(ok):
                        report(ok)
                        print('SMOKE_OK' if ok else 'SMOKE_FAILED',controller.filename,flush=True)
                        app.exit(0 if ok else 3)
                    app._workspace_probe=WorkspaceProbe(app,engine,controller,args.verify_workspace,complete)
                else:
                    report(True)
                    print('SMOKE_OK',controller.filename,controller.status,controller.renderMs,flush=True)
                    app.exit(0)
            elif ticks[0]>180:
                report(False)
                print('SMOKE_FAILED',controller.status,flush=True)
                app.exit(3)
        timer=QTimer()
        timer.timeout.connect(check)
        timer.start(500)
    app.aboutToQuit.connect(window_state.save)
    app.aboutToQuit.connect(controller.close)
    result=app.exec()
    # Qt can log while its static objects are destroyed after frozen Python
    # finalization. Release the Python callback before shutting Qt down.
    qInstallMessageHandler(None)
    # Dispose QML while its context object is still alive; otherwise bindings
    # can reevaluate after Python has released the controller during teardown.
    del engine
    if test_store: test_store.cleanup()
    return result

if __name__=='__main__': raise SystemExit(main())
