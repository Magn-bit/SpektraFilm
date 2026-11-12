"""Small-proxy milestone: real brush/gradient/levels input and bounded overlays."""
from pathlib import Path
import sys,tempfile,time,traceback,json,argparse
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
parser=argparse.ArgumentParser();parser.add_argument('--qml-root',type=Path,default=ROOT/'desktop/qml');args=parser.parse_args()
QML_ROOT=args.qml_root.resolve();PACKAGED=QML_ROOT!=(ROOT/'desktop/qml').resolve();EVIDENCE_SUFFIX='-packaged' if PACKAGED else ''
from PySide6.QtCore import QUrl,QTimer,Qt,QObject,QPoint,QPointF,qInstallMessageHandler
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine,QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PIL import Image
from desktop.controller import Controller,PhotoProvider
from desktop.typography import load_mincho
from shared.local_masks import rasterize_mask
import numpy as np

OUT=ROOT/'output/editor-workspace';messages=[]
qInstallMessageHandler(lambda kind,context,message:messages.append(str(message)))
app=QApplication([]);app.setOrganizationName('SpektraFilmVerification');app.setApplicationName('MaskLevelsMilestone');app.setStyle('Fusion');QQuickStyle.setStyle('Basic');family=load_mincho(app,ROOT)
store=tempfile.TemporaryDirectory();provider=PhotoProvider();ctrl=Controller(provider,store.name)
source=Path(store.name)/'proxy.png'
candidate=ROOT/'output/grain-refinement/no-grain.png'
if candidate.exists():
    with Image.open(candidate) as image:image.convert('RGB').resize((960,640)).save(source)
else:
    rgb=np.repeat(np.linspace(25,235,960,dtype=np.uint8)[None,:,None],640,axis=0);Image.fromarray(np.repeat(rgb,3,axis=2)).save(source)
engine=QQmlApplicationEngine();engine.addImageProvider('photos',provider);ctx=engine.rootContext()
for name,value in [('ctrl',ctrl),('minchoFamily',family),('assetsUrl',QUrl.fromLocalFile(str(ROOT/'assets')+'/').toString()),('interfaceDisplayFamily',family),('interfaceEditorialFamily',family),('interfaceFontDescription','中文朱雀仿宋 / 英文 Noto Serif SC'),('systemReduceMotion',True)]:ctx.setContextProperty(name,value)
engine.load(QUrl.fromLocalFile(str(QML_ROOT/'Studio.qml')));assert engine.rootObjects(),messages
window=engine.rootObjects()[0];window.resize(1366,768);window.setProperty('activeTask','local');window.show()
def prop(obj,name):
    value=obj.property(name);return value.toVariant() if hasattr(value,'toVariant') else value
def item(name,owner=None):
    owner=owner or window;found=owner.findChild(QObject,name)
    def visual(parent):
        for child in parent.childItems():
            if child.objectName()==name:return child
            result=visual(child)
            if result is not None:return result
        return None
    if found is None:found=visual(owner.contentItem() if owner is window else owner)
    assert found is not None,(name,messages);return found
def js(obj,code):
    expression=QQmlExpression(ctx,obj,code);out=expression.evaluate();assert not expression.hasError(),expression.error().toString()
    if isinstance(out,tuple) and len(out)==2:out=out[0]
    return out.toVariant() if hasattr(out,'toVariant') else out
def click(obj):QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,obj.mapToScene(obj.boundingRect().center()).toPoint())
def typeText(text):
    for char in text:QTest.keyClick(window,Qt.Key(ord(char.upper())))
def point(u,v):
    viewport=item('photoViewport');p=js(viewport,f'viewPoint([{u},{v}])');return viewport.mapToScene(QPointF(*p)).toPoint()
def drag(start,end,steps=9):
    QTest.mousePress(window,Qt.LeftButton,Qt.NoModifier,start)
    for k in range(1,steps+1):QTest.mouseMove(window,start+(end-start)*k/steps,12)
    QTest.mouseRelease(window,Qt.LeftButton,Qt.NoModifier,end)
def reveal(obj):
    scroll=item('parameterScroll');flick=scroll.property('contentItem');y=obj.mapToItem(flick,QPointF(0,0)).y()+flick.property('contentY')
    flick.setProperty('contentY',max(0,min(y-30,flick.property('contentHeight')-scroll.property('availableHeight'))));QTest.qWait(35)
def top():item('parameterScroll').property('contentItem').setProperty('contentY',0)
def capture(name):assert window.grabWindow().save(str(OUT/(name+EVIDENCE_SUFFIX+'-1366x768.png')))
deadline=time.monotonic()+65;phase='import';ok=False;report={};overlay_before='';auto_index=0;auto_cases=[('wb','autoWhiteBalanceButton','white_balance'),('tone','autoToneButton','tone'),('levels','autoLevelsButton','levels'),('geometry','autoGeometryButton','geometry')]
def tick():
    global phase,ok,overlay_before,auto_index
    try:
        assert time.monotonic()<deadline,(phase,ctrl.status)
        if phase=='import':ctrl.add_paths([str(source)]);phase='brush'
        elif phase=='brush':
            if ctrl.busy or not ctrl.frame:QTimer.singleShot(80,tick);return
            assert len(ctrl.levelHistogram.get('master',[]))==256
            click(item('addMask_brush'));QTest.qWait(30)
            drag(point(.28,.37),point(.65,.55))
            layer=ctrl._settings.masks[-1];assert len(layer.strokes)==1 and len(layer.strokes[0].points)>3
            report['brush_points']=len(layer.strokes[0].points);phase='brushReady'
        elif phase=='brushReady':
            if ctrl._mask_overlay.busy or ctrl._mask_overlay.timer.isActive() or not ctrl.maskOverlaySource:QTimer.singleShot(60,tick);return
            assert 'strokes' not in ctrl.activeMaskGuide
            click(item('maskOverlayColor_cyan'));phase='erase'
        elif phase=='erase':
            if ctrl._mask_overlay.busy or ctrl._mask_overlay.timer.isActive():QTimer.singleShot(60,tick);return
            click(item('maskBrushMode_1'));drag(point(.4,.44),point(.53,.49),5)
            layer=ctrl._settings.masks[-1];assert layer.strokes[-1].erase
            alpha=rasterize_mask(layer,960,640);assert np.any((alpha>0)&(alpha<1))
            report['feather_fractional_alpha']=int(np.count_nonzero((alpha>0)&(alpha<1)));phase='maskExposure'
        elif phase=='maskExposure':
            if ctrl._mask_overlay.busy or ctrl._mask_overlay.timer.isActive():QTimer.singleShot(60,tick);return
            overlay_before=ctrl.maskOverlaySource;control=item('maskExposureControl');reveal(control)
            handle=item('parameterHandle_exposure',control);p=handle.mapToScene(handle.boundingRect().center()).toPoint()
            history=len(ctrl._history[0]);QTest.mousePress(window,Qt.LeftButton,Qt.NoModifier,p)
            assert not prop(item('photoViewport'),'overlayVisible')
            QTest.mouseMove(window,p+QPoint(30,0),0)
            assert prop(control,'pointerEditing') and prop(control,'pointerValue')>.2
            actual=handle.mapToScene(handle.boundingRect().center()).x()-p.x();assert abs(actual-30)<1.5,actual
            report['immediate_thumb_error_px']=abs(actual-30)
            QTest.mouseRelease(window,Qt.LeftButton,Qt.NoModifier,p+QPoint(30,0));assert len(ctrl._history[0])==history+1
            assert prop(item('photoViewport'),'overlayVisible')
            assert ctrl._settings.masks[-1].exposure>.2;phase='maskExposureCheck'
        elif phase=='maskExposureCheck':
            assert ctrl.maskOverlaySource==overlay_before
            report['adjustment_kept_overlay']=True;top();QTest.qWait(25);click(item('addMask_linear'));QTest.qWait(20)
            start=point(.5,.5);drag(start,start+QPoint(30,18),5)
            layer=ctrl._settings.masks[-1];assert layer.start[0]>.25 and layer.end[0]>.75
            report['linear_move']=list(layer.start);phase='linearReady'
        elif phase=='linearReady':
            if ctrl._mask_overlay.busy or ctrl._mask_overlay.timer.isActive():QTimer.singleShot(60,tick);return
            capture('mask-linear-guide');click(item('addMask_radial'));QTest.qWait(20)
            start=point(.5,.5);drag(start,start+QPoint(-25,12),5)
            layer=ctrl._settings.masks[-1];assert layer.center[0]<.5 and layer.center[1]>.5
            report['radial_move']=list(layer.center);phase='radialReady'
        elif phase=='radialReady':
            if ctrl._mask_overlay.busy or ctrl._mask_overlay.timer.isActive():QTimer.singleShot(60,tick);return
            capture('mask-radial-guide');window.setProperty('activeTask','basic');item('parameterScroll').parent().setProperty('basicGroup','levels');phase='levels'
        elif phase=='levels':
            levels=item('levelsEditor');reveal(levels);handle=item('levelHandle_black');p=handle.mapToScene(handle.boundingRect().center()).toPoint();drag(p,p+QPoint(18,0),5)
            assert ctrl._settings.levels.master.black>.02
            report['input_black']=ctrl._settings.levels.master.black
            handle=item('levelHandle_gamma');p=handle.mapToScene(handle.boundingRect().center()).toPoint();drag(p,p+QPoint(-12,0),5)
            assert ctrl._settings.levels.master.gamma>1
            handle=item('levelHandle_output_white');reveal(handle);p=handle.mapToScene(handle.boundingRect().center()).toPoint();drag(p,p+QPoint(-16,0),5)
            assert ctrl._settings.levels.master.output_white<1
            phase='numeric'
        elif phase=='numeric':
            field=item('levelInput_gamma');reveal(field);click(field);QTest.keyClick(window,Qt.Key_A,Qt.ControlModifier);typeText('1.237');QTest.keyClick(window,Qt.Key_Return)
            assert abs(ctrl._settings.levels.master.gamma-1.237)<1e-12
            channels=item('levelChannel_red');reveal(channels);click(channels);QTest.qWait(20)
            field=item('levelInput_black');reveal(field);click(field);QTest.keyClick(window,Qt.Key_A,Qt.ControlModifier);typeText('12.75');QTest.keyClick(window,Qt.Key_Return)
            assert abs(ctrl._settings.levels.red.black-.05)<1e-12
            ctrl.undo();assert ctrl._settings.levels.red.black==0;ctrl.redo();assert abs(ctrl._settings.levels.red.black-.05)<1e-12
            report['gamma_precision']=ctrl._settings.levels.master.gamma;report['red_black_precision']=ctrl._settings.levels.red.black
            window.setProperty('sidebarWidth',320);click(item('toggleHistogramButton'));assert not prop(item('globalHistogramPanel'),'expanded');QTest.qWait(45)
            reveal(item('levelsEditor').parentItem().parentItem());QTest.qWait(35)
            scroll=item('parameterScroll');bounds=scroll.mapRectToScene(scroll.boundingRect())
            for channel in ('green','blue'):
                button=item('levelChannel_'+channel);rect=button.mapRectToScene(button.boundingRect())
                assert bounds.left()<=rect.left() and rect.right()<=bounds.right(),(channel,rect,bounds)
                click(button);assert prop(item('levelsEditor'),'channel')==channel
            for key in ('black','gamma','white','output_black','output_white'):
                field=item('levelInput_'+key);rect=field.mapRectToScene(field.boundingRect())
                assert bounds.top()<=rect.top() and rect.bottom()<=bounds.bottom(),(key,rect,bounds)
            capture('levels-input-output');report['narrow_channels_green_blue']=True;report['complete_levels_visible']=True
            click(item('toggleHistogramButton'));assert prop(item('globalHistogramPanel'),'expanded')
            phase='autoStart'
        elif phase=='autoStart':
            if ctrl.busy:QTimer.singleShot(70,tick);return
            group,button,kind=auto_cases[auto_index]
            window.setProperty('activeTask','geometry' if group=='geometry' else 'basic')
            if group!='geometry':item('parameterScroll').parent().setProperty('basicGroup',group)
            QTest.qWait(20);reveal(item(button));click(item(button));assert ctrl.autoAdjustBusy,kind;phase='autoWait'
        elif phase=='autoWait':
            if ctrl.autoAdjustBusy:QTimer.singleShot(70,tick);return
            report.setdefault('auto_real_buttons',[]).append(auto_cases[auto_index][2]);auto_index+=1
            phase='autoStart' if auto_index<len(auto_cases) else 'finish'
        else:
            unexpected=[m for m in messages if any(word in m for word in ['ReferenceError','TypeError','Cannot assign','Binding loop','Unable to assign','failed to load'])]
            assert not unexpected,unexpected
            report.update(source_size=[960,640],window_logical=[1366,768],qml_errors=unexpected,history_exact=True,histogram_bins=256,qml_root=str(QML_ROOT),controller='development Python controller; native staged runtime')
            (OUT/('mask-levels'+EVIDENCE_SUFFIX+'-verification.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(report,flush=True);ok=True;window.close();app.quit();return
        QTimer.singleShot(150,tick)
    except Exception:
        traceback.print_exc();print('QML',messages,flush=True);window.close();app.exit(2)
QTimer.singleShot(180,tick);result=app.exec();ctrl.close();del engine;store.cleanup();raise SystemExit(result if ok else 2)
