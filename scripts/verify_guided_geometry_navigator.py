"""One bounded geometry/UI milestone; no RAW benchmark or hash checks."""
from pathlib import Path
import json,sys,tempfile,time,traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import numpy as np
from PIL import Image
from dataclasses import asdict,replace
from shared.geometry import Geometry,solve_guided_geometry,normalized_matrices,apply_geometry_pixels
from PySide6.QtCore import QObject,QPoint,QPointF,Qt,QUrl,qInstallMessageHandler
from PySide6.QtQml import QQmlApplicationEngine,QQmlExpression
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from desktop.controller import Controller,PhotoProvider
from desktop.typography import load_mincho
OUT=ROOT/'output/guided-geometry-navigator';OUT.mkdir(parents=True,exist_ok=True)
report={'scope':'one 960x640 original-file geometry/UI milestone; no RAW benchmark','math':{}}
targets={'horizontals':[[.2,1/3],[.8,1/3],[.2,2/3],[.8,2/3]],'verticals':[[1/3,.2],[1/3,.8],[2/3,.2],[2/3,.8]],'rectangle':[[.2,.2],[.8,.2],[.8,.8],[.2,.8]]}
def project(matrix,points):
    values=np.c_[np.asarray(points),np.ones(len(points))]@np.asarray(matrix).reshape(3,3).T
    return (values[:,:2]/values[:,2:3]).tolist()
for mode in targets:
    expected=Geometry(rotation=3.5,vertical=0 if mode=='horizontals' else 27,horizontal=0 if mode=='verticals' else -19,auto_crop=False)
    points=project(normalized_matrices(960,640,expected)[1],targets[mode])
    solved,diagnostics=solve_guided_geometry(960,640,Geometry(auto_crop=False),mode,points)
    assert max(abs(getattr(solved,key)-getattr(expected,key)) for key in ('rotation','vertical','horizontal'))<1e-4,(mode,solved)
    report['math'][mode]={'parameters':asdict(solved),'error_degrees':diagnostics['error_degrees']}
try:solve_guided_geometry(960,640,Geometry(),'rectangle',[[.2,.2],[.8,.8],[.8,.2],[.2,.8]])
except ValueError:report['invalid_crossed_rectangle_rejected']=True
else:raise AssertionError('crossed rectangle accepted')
messages=[];qInstallMessageHandler(lambda kind,context,message:messages.append(str(message)))
app=QApplication([]);app.setOrganizationName('SpektraFilmVerification');app.setApplicationName('GuidedGeometryNavigator');QQuickStyle.setStyle('Basic')
family=load_mincho(app,ROOT);store=tempfile.TemporaryDirectory();provider=PhotoProvider();ctrl=Controller(provider,store.name)
source=Path(store.name)/'original-geometry-source.png'
with Image.open(ROOT/'output/current-ui/source-preview.jpg') as image:image.convert('RGB').resize((960,640)).save(source)
engine=QQmlApplicationEngine();engine.addImageProvider('photos',provider);ctx=engine.rootContext()
for name,value in [('ctrl',ctrl),('minchoFamily',family),('interfaceDisplayFamily',family),('interfaceEditorialFamily',family),('interfaceFontDescription',''),('assetsUrl',QUrl.fromLocalFile(str(ROOT/'assets')+'/').toString()),('systemReduceMotion',True)]:ctx.setContextProperty(name,value)
engine.load(QUrl.fromLocalFile(str(ROOT/'desktop/qml/Studio.qml')))
assert engine.rootObjects(),messages
window=engine.rootObjects()[0];window.resize(1366,768);window.show()
def item(name):
    def walk(parent):
        for child in parent.childItems():
            if child.objectName()==name:return child
            result=walk(child)
            if result is not None:return result
    found=window.findChild(QObject,name) or walk(window.contentItem());assert found is not None,name;return found
def js(obj,code):
    expression=QQmlExpression(ctx,obj,code);out=expression.evaluate();assert not expression.hasError(),expression.error().toString()
    if isinstance(out,tuple) and len(out)==2:out=out[0]
    return out.toVariant() if hasattr(out,'toVariant') else out
def wait(predicate,seconds=25):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:app.processEvents();time.sleep(.005)
    assert predicate(),(ctrl.status,messages[-8:])
def point(u,v):return view.mapToScene(QPointF(*js(view,f'viewPoint([{u},{v}])'))).toPoint()
def drag(a,b):
    QTest.mousePress(window,Qt.LeftButton,Qt.NoModifier,a)
    for k in range(1,13):QTest.mouseMove(window,a+(b-a)*k/12,3)
    QTest.mouseRelease(window,Qt.LeftButton,Qt.NoModifier,b);app.processEvents()
def capture(name):
    QTest.qWait(60);assert window.grabWindow().save(str(OUT/(name+'.png')))
try:
    ctrl.setFilmEnabled(False);ctrl.add_paths([str(source)]);wait(lambda:bool(ctrl.frame) and not ctrl.busy)
    view=item('photoViewport');wait(lambda:view.property('hasImage'))
    window.setProperty('activeTask','geometry');app.processEvents()
    entry=item('guidedGeometry_rectangle');assert entry.isVisible() and entry.isEnabled()
    QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,entry.mapToScene(QPointF(entry.width()/2,entry.height()/2)).toPoint());app.processEvents()
    report['actual_geometry_panel_entry']=True
    guides=item('guidedGeometryOverlay');wait(lambda:guides.property('active'))
    history=len(ctrl._history.get(ctrl.currentIndex,[]));initial=js(guides,'points');frame=ctrl.frame
    drag(point(*initial[0]),point(initial[0][0]+.035,initial[0][1]+.025))
    assert len(ctrl._history.get(ctrl.currentIndex,[]))==history and ctrl.frame==frame
    assert js(guides,'points')[0]!=initial[0]
    # Esc during a drag restores local points and creates no history.
    before=js(guides,'points');a=point(*before[0]);QTest.mousePress(window,Qt.LeftButton,Qt.NoModifier,a);QTest.mouseMove(window,a+QPoint(12,8),4);QTest.keyClick(window,Qt.Key_Escape);QTest.mouseRelease(window,Qt.LeftButton,Qt.NoModifier,a+QPoint(12,8));app.processEvents()
    assert np.allclose(js(guides,'points'),before) and len(ctrl._history.get(ctrl.currentIndex,[]))==history
    expected=Geometry(rotation=3.5,vertical=27,horizontal=-19,auto_crop=False)
    points=project(normalized_matrices(960,640,expected)[1],targets['rectangle'])
    js(guides,'setPoints('+json.dumps(points)+')');capture('guides-before')
    js(guides,'apply()');wait(lambda:not ctrl.busy)
    assert guides.property('applied') and len(ctrl._history[ctrl.currentIndex])==history+1
    corrected=ctrl._settings.geometry;assert max(abs(getattr(corrected,k)-getattr(expected,k)) for k in ('rotation','vertical','horizontal'))<1e-4
    mapped=project(ctrl.geometryForward,points)
    assert abs(mapped[0][1]-mapped[1][1])<1e-6 and abs(mapped[0][0]-mapped[3][0])<1e-6
    assert ctrl.sourceDimensions==[960,640] and [ctrl.imageWidth,ctrl.imageHeight]==[960,640]
    # Full-source float geometry uses the same shared correction, not a proxy crop.
    with Image.open(source) as image:pixels=np.asarray(image,dtype=np.float32)/255
    output=apply_geometry_pixels(pixels,corrected);assert output.shape==pixels.shape and np.isfinite(output).all()
    capture('guides-after');ctrl.undo();assert ctrl._settings.geometry==Geometry();ctrl.redo();assert ctrl._settings.geometry==corrected
    report['local_drag_no_render_or_history']=True;report['escape_restores_local_points']=True;report['apply_single_history_undo_redo']=True;report['full_source_shape']=list(output.shape)
    js(view,'endGuides();setZoom(2,width/2,height/2)');QTest.qWait(40)
    # Create the actual component against the same viewport when Studio integration
    # has not yet installed one. No test-only implementation of navigation exists.
    navigator=window.findChild(QObject,'photoNavigator')
    if navigator is None:
        qml="import QtQuick\nimport 'components'\nNavigator {x:14;y:14;width:176;height:132;z:100}"
        from PySide6.QtQml import QQmlComponent
        component=QQmlComponent(engine);component.setData(qml.encode(),QUrl.fromLocalFile(str(ROOT/'desktop/qml/NavigatorCheck.qml')));wait(lambda:component.status()!=QQmlComponent.Loading);navigator=component.create(ctx);assert navigator,component.errors();navigator.setParent(view);navigator.setParentItem(view);navigator.setProperty('viewport',view)
    wait(lambda:navigator.property('enabled'))
    js(view,'centerOnNormalized(.6,.55)');r=js(view,'navigatorRect');assert all(abs(a-b)<.005 for a,b in zip([r[0]+r[2]/2,r[1]+r[3]/2],[.6,.55]))
    nav=next((x for x in navigator.findChildren(QObject) if x.objectName()=='navigatorInteraction'),None);assert nav
    a=nav.mapToScene(QPointF(nav.width()*.6,nav.height()*.55)).toPoint();b=a+QPoint(12,8);old=js(view,'navigatorRect');drag(a,b);new=js(view,'navigatorRect');assert new[0]>old[0] and new[1]>old[1]
    QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,nav.mapToScene(QPointF(nav.width()*.25,nav.height()*.3)).toPoint());new=js(view,'navigatorRect');assert new[0]<old[0]
    report['navigator_click_drag_actual_viewport']=True;report['navigator_zoom_rect']=new;capture('navigator-zoom')
    js(view,'fit()');QTest.qWait(30);assert np.allclose(js(view,'navigatorRect'),[0,0,1,1]);report['navigator_fit_rect_full']=True
    errors=[m for m in messages if any(v in m for v in ('ReferenceError','TypeError','Cannot assign','is not a type','Binding loop','Error:'))]
    assert not errors,errors
    report['qml_errors']=errors;report['window_logical']=[1366,768];report['passed']=True
except Exception:
    report['passed']=False;report['failure']=traceback.format_exc();report['messages']=messages[-20:];raise
finally:
    (OUT/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    window.close();ctrl.close();engine.deleteLater();app.processEvents();store.cleanup()
print(json.dumps(report,ensure_ascii=False,indent=2))
