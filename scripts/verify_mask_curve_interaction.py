"""One small-proxy UI milestone for brush deletion, gradient direction and curves."""
from pathlib import Path
import argparse,json,sys,tempfile,time,traceback
from dataclasses import replace
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
from PySide6.QtCore import QUrl,QTimer,Qt,QObject,QPoint,QPointF,qInstallMessageHandler
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine,QQmlExpression
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PIL import Image
import numpy as np
from desktop.controller import Controller,PhotoProvider
from desktop.typography import load_mincho
from desktop.mask_overlay import _BrushRaster,_Task
from shared.local_masks import MaskLayer,MaskStroke,rasterize_mask

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--qml-root',type=Path,default=ROOT/'desktop/qml')
parser.add_argument('--output',type=Path,default=ROOT/'output/mask-curve-refinement')
args=parser.parse_args()
OUT=args.output;OUT.mkdir(parents=True,exist_ok=True)
report={'qml_root':str(args.qml_root.resolve())};messages=[];qInstallMessageHandler(lambda kind,context,message:messages.append(str(message)))
overlay_jobs=[];original_overlay_run=_Task.run
def timed_overlay_run(task):
    started=time.perf_counter();original_overlay_run(task)
    overlay_jobs.append({'start':started,'duration_ms':(time.perf_counter()-started)*1000,
                         'point_count':sum(len(stroke.points) for stroke in task.key[0].strokes)})
_Task.run=timed_overlay_run
app=QApplication([]);app.setOrganizationName('SpektraFilmVerification');app.setApplicationName('MaskCurveInteraction');QQuickStyle.setStyle('Basic')
family=load_mincho(app,ROOT);store=tempfile.TemporaryDirectory();provider=PhotoProvider();ctrl=Controller(provider,store.name)
source=Path(store.name)/'proxy.png';candidate=ROOT/'output/grain-refinement/no-grain.png'
if candidate.exists():
    with Image.open(candidate) as image:image.convert('RGB').resize((960,640)).save(source)
else:
    pixels=np.zeros((640,960,3),np.uint8);pixels[:]=np.linspace(15,235,960,dtype=np.uint8)[None,:,None];Image.fromarray(pixels).save(source)
engine=QQmlApplicationEngine();engine.addImageProvider('photos',provider);ctx=engine.rootContext()
for name,value in [('ctrl',ctrl),('minchoFamily',family),('interfaceDisplayFamily',family),('interfaceEditorialFamily',family),('interfaceFontDescription',''),('assetsUrl',QUrl.fromLocalFile(str(ROOT/'assets')+'/').toString()),('systemReduceMotion',True)]:ctx.setContextProperty(name,value)
engine.load(QUrl.fromLocalFile(str(args.qml_root.resolve()/'Studio.qml')));assert engine.rootObjects(),messages
window=engine.rootObjects()[0];window.resize(1366,768);window.setProperty('activeTask','local');window.show()

def item(name,owner=None):
    owner=owner or window;found=owner.findChild(QObject,name)
    def visual(parent):
        for child in parent.childItems():
            if child.objectName()==name:return child
            result=visual(child)
            if result is not None:return result
        return None
    if found is None:found=visual(owner.contentItem() if owner is window else owner)
    assert found is not None,name
    return found
def prop(obj,name):
    v=obj.property(name);return v.toVariant() if hasattr(v,'toVariant') else v
def js(obj,code):
    expression=QQmlExpression(ctx,obj,code);out=expression.evaluate();assert not expression.hasError(),expression.error().toString()
    if isinstance(out,tuple) and len(out)==2:out=out[0]
    return out.toVariant() if hasattr(out,'toVariant') else out
def click(obj):QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,obj.mapToScene(obj.boundingRect().center()).toPoint())
def reveal(obj):
    scroll=item('parameterScroll');flick=scroll.property('contentItem');y=obj.mapToItem(flick,QPointF(0,0)).y()+flick.property('contentY')
    flick.setProperty('contentY',max(0,min(y-10,flick.property('contentHeight')-scroll.property('availableHeight'))));QTest.qWait(40)
def point(u,v):
    view=item('photoViewport');p=js(view,f'viewPoint([{u},{v}])');return view.mapToScene(QPointF(*p)).toPoint()
def drag(a,b,steps=8):
    QTest.mousePress(window,Qt.LeftButton,Qt.NoModifier,a)
    for k in range(1,steps+1):QTest.mouseMove(window,a+(b-a)*k/steps,12)
    QTest.mouseRelease(window,Qt.LeftButton,Qt.NoModifier,b)
def capture(name):assert window.grabWindow().save(str(OUT/(name+'-1366x768.png')))

phase='import';deadline=time.monotonic()+45;ok=False;brush_released=0.
def tick():
    global phase,ok,brush_released
    try:
        assert time.monotonic()<deadline,(phase,ctrl.status)
        if phase=='import':ctrl.add_paths([str(source)]);phase='brush'
        elif phase=='brush':
            if ctrl.busy or not ctrl.frame:QTimer.singleShot(60,tick);return
            click(item('addMask_brush'));QTest.qWait(30)
            t=time.perf_counter();drag(point(.2,.35),point(.7,.5));report['brush_drag_dispatch_ms']=round((time.perf_counter()-t)*1000,2)
            assert len(ctrl._settings.masks[-1].strokes)==1
            brush_released=time.perf_counter();phase='brushSettle';QTimer.singleShot(1,tick);return
        elif phase=='brushSettle':
            if ctrl._mask_overlay.cache_key!=ctrl._mask_overlay.key or not ctrl.maskOverlaySource:
                assert time.perf_counter()-brush_released<2.,'overlay did not settle'
                QTimer.singleShot(1,tick);return
            report['last_input_to_overlay_settled_ms']=round((time.perf_counter()-brush_released)*1000,2)
            report['first_brush_overlay_jobs']=[dict(worker_ms=round(job['duration_ms'],2),points=job['point_count']) for job in overlay_jobs]
            phase='delete'
        elif phase=='delete':
            if ctrl._mask_overlay.busy or ctrl._mask_overlay.timer.isActive():QTimer.singleShot(30,tick);return
            capture('brush-actions');button=item('removeLastMaskStrokeButton');reveal(button);click(button)
            assert len(ctrl._settings.masks[-1].strokes)==0
            ctrl.undo();assert len(ctrl._settings.masks[-1].strokes)==1
            erase_button=item('maskBrushMode_1');reveal(erase_button);click(erase_button);QTest.qWait(35)
            assert prop(erase_button,'selected'), 'erase mode did not become selected'
            drag(point(.4,.41),point(.52,.45),4)
            assert ctrl._settings.masks[-1].strokes[-1].erase
            clear_button=item('clearMaskStrokesButton');reveal(clear_button);click(clear_button)
            assert not ctrl._settings.masks[-1].strokes
            ctrl.undo();assert len(ctrl._settings.masks[-1].strokes)==2
            report['delete_stroke_undo_erase']=True
            report['clear_strokes_undo']=True
            phase='gradient'
        elif phase=='gradient':
            item('parameterScroll').property('contentItem').setProperty('contentY',0)
            click(item('addMask_linear'));QTest.qWait(30)
            drag(point(.18,.28),point(.79,.28))
            layer=ctrl._settings.masks[-1];alpha=rasterize_mask(layer,960,640)
            a=float(alpha[round(.28*639),round(.18*959)]);b=float(alpha[round(.28*639),round(.79*959)])
            assert a>.99 and b<.01,(layer.start,layer.end,a,b)
            report['linear_press_release_alpha']=[a,b];phase='curves'
        elif phase=='curves':
            capture('linear-direction');window.setProperty('activeTask','color');QTest.qWait(45)
            item('colorToolsPanel').setProperty('openGroup','curves');curve=item('curveEditor');reveal(curve);QTest.qWait(40)
            graph=item('curveGraph');center=graph.mapToScene(QPointF(graph.width()*.48,graph.height()*.51)).toPoint()
            click_point=center;QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,click_point);QTest.qWait(25)
            assert len(ctrl._settings.curves.master)==3,ctrl._settings.curves.master
            # The interior point may leave all four sides; release deletes it
            # as one undoable gesture. Dragging back in restores its draft.
            history=len(ctrl._history[0]);outside=graph.mapToScene(QPointF(-24,graph.height()*.5)).toPoint()
            drag(center,outside);assert len(ctrl._settings.curves.master)==2
            assert len(ctrl._history[0])==history+1
            ctrl.undo();assert len(ctrl._settings.curves.master)==3
            history=len(ctrl._history[0]);original=ctrl._settings.curves.master
            QTest.mousePress(window,Qt.LeftButton,Qt.NoModifier,center);QTest.mouseMove(window,center+QPoint(25,-30),30)
            QTest.keyClick(window,Qt.Key_Escape);QTest.mouseRelease(window,Qt.LeftButton,Qt.NoModifier,center+QPoint(25,-30))
            assert ctrl._settings.curves.master==original and len(ctrl._history[0])==history
            endpoint=graph.mapToScene(QPointF(0,graph.height())).toPoint();drag(endpoint,endpoint+QPoint(-24,12));assert len(ctrl._settings.curves.master)==3
            click(graph);js(curve,'selectedPoint=1');graph.forceActiveFocus();QTest.keyClick(window,Qt.Key_Delete)
            assert len(ctrl._settings.curves.master)==2 and ctrl.photoCount==1
            report['curve_drag_out_delete_undo_cancel_endpoint_keyboard']=True;phase='finish'
        else:
            capture('curve-editor');unexpected=[m for m in messages if any(s in m for s in ('ReferenceError','TypeError','Binding loop','Cannot assign','Unable to assign','failed to load'))]
            assert not unexpected,unexpected
            generation=ctrl._generation;active=ctrl.activeMaskId
            ctrl.renameMask(active,'渐变范围');assert ctrl._generation==generation
            ctrl.updateMaskParameter('exposure',.5);assert ctrl._generation>generation
            generation=ctrl._generation;ctrl.deleteMask();assert ctrl._generation>generation
            ctrl.undo();assert any(layer.id==active and layer.exposure==.5 for layer in ctrl._settings.masks)
            generation=ctrl._generation;ctrl.selectMask(ctrl._settings.masks[0].id);assert ctrl._generation==generation
            report['neutral_metadata_skips_render_nonzero_delete_renders']=True
            # Exact incremental brush result for growing paint and erase with
            # soft edges/flow, including undo, inversion and source scaling.
            raster=_BrushRaster();base=MaskLayer(id='perf');last=();maximum_error=0.;times=[]
            for i in range(12):
                stroke=MaskStroke(points=tuple((.1+k*.006,.2+.07*np.sin(k*.12+i)) for k in range(100)),radius=.04,feather=.65,flow=.45,erase=i%3==2)
                for n in (10,45,100):
                    layer=replace(base,strokes=(*last,replace(stroke,points=stroke.points[:n])),inverted=i%4==3)
                    start=time.perf_counter();actual=raster.render(layer,384,256);times.append((time.perf_counter()-start)*1000)
                    exact=rasterize_mask(layer,384,256);maximum_error=max(maximum_error,float(np.max(np.abs(actual-exact))))
                last=(*last,stroke)
            assert maximum_error<1e-6,maximum_error
            report.update(incremental_alpha_max_error=maximum_error,incremental_384x256_ms_median=round(float(np.median(times)),2),window_logical=[1366,768],qml_errors=unexpected)
            (OUT/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(report,flush=True);ok=True;window.close();app.quit();return
        QTimer.singleShot(110,tick)
    except Exception:
        traceback.print_exc();print('QML',messages,flush=True);window.close();app.exit(2)
QTimer.singleShot(150,tick);code=app.exec();ctrl.close();del engine;store.cleanup();raise SystemExit(code if ok else 2)
