"""Critical real-QML milestone for visible cursors and three-line gradient editing."""
from pathlib import Path
import json, math, sys, tempfile, time, traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
from PIL import Image
from PySide6.QtCore import QObject,QPoint,QPointF,Qt,QUrl,qInstallMessageHandler
from PySide6.QtGui import QCursor
from PySide6.QtQml import QQmlApplicationEngine,QQmlExpression
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from desktop.controller import Controller,PhotoProvider
from desktop.typography import load_mincho
from shared.local_masks import rasterize_mask
OUT=ROOT/'output/gradient-cursor-refinement';OUT.mkdir(parents=True,exist_ok=True)
messages=[]
qInstallMessageHandler(lambda kind,context,message:messages.append(str(message)))
app=QApplication([]);app.setOrganizationName('SpektraFilmVerification');app.setApplicationName('GradientCursorRefinement');QQuickStyle.setStyle('Basic')
family=load_mincho(app,ROOT);store=tempfile.TemporaryDirectory();provider=PhotoProvider();ctrl=Controller(provider,store.name)
source=Path(store.name)/'DSC09118-UI-preview.png'
with Image.open(ROOT/'output/current-ui/source-preview.jpg') as image:image.convert('RGB').resize((960,640)).save(source)
engine=QQmlApplicationEngine();engine.addImageProvider('photos',provider);ctx=engine.rootContext()
for name,value in [('ctrl',ctrl),('minchoFamily',family),('interfaceDisplayFamily',family),('interfaceEditorialFamily',family),('interfaceFontDescription',''),('assetsUrl',QUrl.fromLocalFile(str(ROOT/'assets')+'/').toString()),('systemReduceMotion',True)]:ctx.setContextProperty(name,value)
engine.load(QUrl.fromLocalFile(str(ROOT/'desktop/qml/Studio.qml')))
assert engine.rootObjects(),messages
window=engine.rootObjects()[0];window.resize(1366,768);window.setProperty('activeTask','local');window.show()
report={'window_logical':[1366,768],'source_dimensions':[960,640],'proxy_provenance':json.loads((ROOT/'output/current-ui/source-preview.json').read_text(encoding='utf-8')),'scope':'one small-proxy UI milestone; no RAW/export benchmark'}
def item(name,owner=None):
    owner=owner or window;found=owner.findChild(QObject,name)
    def walk(parent):
        for child in parent.childItems():
            if child.objectName()==name:return child
            result=walk(child)
            if result is not None:return result
    if found is None:found=walk(owner.contentItem() if owner is window else owner)
    assert found is not None,name
    return found
def js(obj,code):
    expression=QQmlExpression(ctx,obj,code);out=expression.evaluate();assert not expression.hasError(),expression.error().toString()
    if isinstance(out,tuple) and len(out)==2:out=out[0]
    return out.toVariant() if hasattr(out,'toVariant') else out

def wait(predicate,seconds=20):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:app.processEvents();time.sleep(.005)
    assert predicate(),(ctrl.status,messages[-8:])
def capture(name):
    wait(lambda:not ctrl.busy and ctrl._mask_overlay.cache_key==ctrl._mask_overlay.key);QTest.qWait(80);assert window.grabWindow().save(str(OUT/(name+'-1366x768.png')))
def norm_point(u,v):
    p=js(view,f'viewPoint([{u},{v}])');return view.mapToScene(QPointF(*p)).toPoint()
def point_local(x,y):return view.mapToScene(QPointF(x,y)).toPoint()
def mouse_drag(a,b,steps=12,sample=None):
    QTest.mousePress(window,Qt.LeftButton,Qt.NoModifier,a)
    for k in range(1,steps+1):
        p=a+(b-a)*k/steps;t=time.perf_counter();QTest.mouseMove(window,p,6)
        if sample:sample(p,(time.perf_counter()-t)*1000)
    QTest.mouseRelease(window,Qt.LeftButton,Qt.NoModifier,b);app.processEvents()
def layer():return ctrl._settings.masks[-1]
def mask_points():return [list(layer().start),list(layer().end)]
def history():return len(ctrl._history[ctrl.currentIndex])
def assert_close(a,b,tolerance=.006):
    assert all(abs(x-y)<=tolerance for x,y in zip(a,b)),(a,b)
def actual_pointer(label,point):
    window.requestActivate();QCursor.setPos(window.mapToGlobal(point));QTest.mouseMove(window,point,12);app.processEvents();time.sleep(.03);app.processEvents();shape=window.cursor().shape()
    assert shape!=Qt.BlankCursor,(label,shape)
    report.setdefault('cursor_shapes',{})[label]=shape.name
try:
    ctrl.add_paths([str(source)]);wait(lambda:bool(ctrl.frame) and not ctrl.busy)
    view=item('photoViewport');wait(lambda:view.property('hasImage'))
    actual_pointer('normal',norm_point(.5,.5))
    ctrl.addMaskOfKind('brush');wait(lambda:view.property('brushEnabled'))
    brush=item('maskBrushArea');assert brush.property('cursorShape')!=Qt.BlankCursor
    actual_pointer('brush',norm_point(.5,.5));assert item('brushCursor').isVisible()
    mouse_drag(norm_point(.42,.42),norm_point(.56,.44),8);wait(lambda:ctrl._mask_overlay.cache_key==ctrl._mask_overlay.key);actual_pointer('brush',norm_point(.56,.44));capture('visible-brush-cursor')
    ctrl.addMaskOfKind('linear');QTest.qWait(40)
    # An accidental background click must not destroy an existing range.
    before=mask_points();count=history();QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,norm_point(.12,.2));app.processEvents()
    assert mask_points()==before and history()==count
    mouse_drag(norm_point(.12,.2),norm_point(.78,.2))
    alpha=rasterize_mask(layer(),960,640)
    wait(lambda:ctrl._mask_overlay.cache_key==ctrl._mask_overlay.key)
    report['creation_press_release_alpha']=[float(alpha[128,115]),float(alpha[128,749])]
    assert report['creation_press_release_alpha'][0]>.99 and report['creation_press_release_alpha'][1]<.01
    # Hit the middle line far from its small center pin, then translate.
    original=mask_points();middle=[sum(v[0] for v in original)/2,.67];a=norm_point(*middle);b=a+QPoint(22,16)
    local=view.mapFromScene(QPointF(a));assert js(view,f'gradientHit({local.x()},{local.y()})')=='move'
    count=history();errors=[];dispatch=[]
    def sample(p,ms):
        handle=js(view,'guideMask');delta=js(view,f'pointAt({view.mapFromScene(QPointF(p)).x()},{view.mapFromScene(QPointF(p)).y()})')
        start=js(view,f'pointAt({local.x()},{local.y()})')
        expected=js(view,f'viewPoint([{original[0][0]+delta[0]-start[0]},{original[0][1]+delta[1]-start[1]}])')
        actual=js(view,'viewPoint(guideMask.start)');errors.append(math.dist(actual,expected));dispatch.append(ms)
    mouse_drag(a,b,24,sample)
    assert history()==count+1 and ctrl._before is None
    moved=mask_points();assert_close([moved[0][0]-original[0][0],moved[0][1]-original[0][1]],[moved[1][0]-original[1][0],moved[1][1]-original[1][1]],1e-7)
    assert max(errors)<.05,max(errors)
    ctrl.undo();assert mask_points()==original;ctrl.redo();assert mask_points()==moved
    report['middle_line_move_one_undo_redo']=True
    report['local_draft_position_max_error_px']=max(errors)
    report['qtest_move_dispatch_ms']={'max':max(dispatch),'median':sorted(dispatch)[len(dispatch)//2],'includes_requested_delay_ms':6}
    # Move a dashed boundary away from both dots. Tangential motion preserves direction.
    original=mask_points();a=norm_point(original[0][0],.7);b=a+QPoint(18,31);count=history()
    local=view.mapFromScene(QPointF(a));assert js(view,f'gradientHit({local.x()},{local.y()})')=='start'
    mouse_drag(a,b);changed=mask_points()
    assert changed[0][0]>original[0][0] and changed[1]==original[1]
    assert abs(changed[0][1]-changed[1][1])<1e-7 and history()==count+1
    report['boundary_drag_fixed_normal']=True
    # Dedicated rotation control keeps the center and physical feather width.
    original=mask_points();controls=js(view,'gradientControls()');rotation=next(h['p'] for h in controls if h['id']=='linear_rotation')
    center=js(view,'viewPoint([(guideMask.start[0]+guideMask.end[0])/2,(guideMask.start[1]+guideMask.end[1])/2])')
    vector=[rotation[0]-center[0],rotation[1]-center[1]];target=[center[0]-vector[1],center[1]+vector[0]]
    mouse_drag(point_local(*rotation),point_local(*target));rotated=mask_points()
    assert abs(rotated[1][1]-rotated[0][1])>.3
    assert_close([(rotated[0][0]+rotated[1][0])/2,(rotated[0][1]+rotated[1][1])/2],[(original[0][0]+original[1][0])/2,(original[0][1]+original[1][1])/2],.001)
    report['rotation_preserves_center']=True
    capture('three-line-gradient')
    original=mask_points();count=history();mid=[(original[0][0]+original[1][0])/2,(original[0][1]+original[1][1])/2];a=norm_point(*mid)
    QTest.mousePress(window,Qt.LeftButton,Qt.NoModifier,a);QTest.mouseMove(window,a+QPoint(-20,12),12);QTest.keyClick(window,Qt.Key_Escape);QTest.mouseRelease(window,Qt.LeftButton,Qt.NoModifier,a+QPoint(-20,12));app.processEvents()
    assert mask_points()==original and history()==count
    report['escape_restores_without_undo_entry']=True
    # Geometry mapping and zoom are the same map used by CPU/native overlays.
    matrix=[.92,.03,.02,-.02,.94,.03,.04,-.02,1]
    import numpy as np
    inverse=np.linalg.inv(np.array(matrix).reshape(3,3)).ravel().tolist()
    view.setProperty('geometryForward',matrix);view.setProperty('geometryInverse',inverse)
    js(view,'setZoom(1.8,width/2,height/2)');QTest.qWait(25)
    roundtrip=js(view,'(function(){var p=viewPoint([.42,.43]);return pointAt(p[0],p[1])})()')
    assert_close(roundtrip,[.42,.43],1e-10)
    report['zoom_projective_coordinate_roundtrip_error']=max(abs(roundtrip[i]-[.42,.43][i]) for i in range(2))
    view.setProperty('geometryForward',[1,0,0,0,1,0,0,0,1]);view.setProperty('geometryInverse',[1,0,0,0,1,0,0,0,1]);js(view,'fit()')
    ctrl.invertMask();inverted=rasterize_mask(layer(),960,640);ctrl.invertMask();normal=rasterize_mask(layer(),960,640)
    assert float(np.max(abs(inverted+normal-1)))<1e-6;report['inversion_real_alpha_complement']=True
    view.setProperty('suppressMaskOverlay',True);app.processEvents();assert not item('gradientOutline').isVisible() and not item('maskOverlay').isVisible()
    view.setProperty('suppressMaskOverlay',False);app.processEvents();assert item('gradientOutline').isVisible();report['parameter_adjustment_overlay_suppression']=True
    actual_pointer('gradient',norm_point(.5,.5))
    window.setProperty('comparing',True);app.processEvents();assert not view.property('brushEnabled')
    compare=item('comparisonView');target=item('comparisonDragTarget');actual_pointer('comparison',target.mapToScene(QPointF(target.width()/2,target.height()/2)).toPoint())
    window.setProperty('comparing',False);view.setProperty('cropping',True);app.processEvents();assert not view.property('brushEnabled')
    actual_pointer('crop',norm_point(.5,.5));assert item('cropInteraction').property('cursorShape')!=Qt.BlankCursor
    view.setProperty('cropping',False);window.setProperty('activeTask','basic');js(view,'setZoom(1.6,width/2,height/2)');QTest.qWait(30)
    actual_pointer('zoom_pan',norm_point(.5,.5));report['normal_mask_compare_crop_pan_visible']=True
    unexpected=[m for m in messages if any(s in m for s in ('ReferenceError','TypeError','Binding loop','Cannot assign','Unable to assign','failed to load'))]
    assert not unexpected,unexpected
    report['qml_errors']=unexpected;report['passed']=True
    (OUT/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
except Exception:
    capture('failure');traceback.print_exc();print('QML',messages,flush=True);raise
finally:
    window.close();ctrl.close();engine.deleteLater();app.processEvents();store.cleanup()


