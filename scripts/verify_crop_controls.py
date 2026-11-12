"""Actual mouse clicks for crop ratio menu and gradient-track visual regression."""
from pathlib import Path
import argparse,sys,tempfile,time,traceback,json
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
from PySide6.QtCore import QUrl,QTimer,Qt,QObject,qInstallMessageHandler
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine,QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PIL import Image
from desktop.controller import Controller,PhotoProvider
from desktop.typography import load_mincho

OUT=ROOT/'output/editor-workspace';messages=[]
parser=argparse.ArgumentParser()
parser.add_argument('--qml-root',type=Path,default=ROOT/'desktop/qml')
args=parser.parse_args()
qInstallMessageHandler(lambda kind,context,message:messages.append(str(message)))
app=QApplication([]);app.setStyle('Fusion');QQuickStyle.setStyle('Basic');family=load_mincho(app,ROOT)
store=tempfile.TemporaryDirectory();provider=PhotoProvider();ctrl=Controller(provider,store.name)
source=Path(store.name)/'rectangle.png';Image.new('RGB',(390,250),(157,133,91)).save(source)
engine=QQmlApplicationEngine();engine.addImageProvider('photos',provider);ctx=engine.rootContext()
for name,value in [('ctrl',ctrl),('minchoFamily',family),('assetsUrl',QUrl.fromLocalFile(str(ROOT/'assets')+'/').toString()),('interfaceDisplayFamily',family),('interfaceEditorialFamily',family),('interfaceFontDescription','中文朱雀仿宋 / 英文 Noto Serif SC'),('systemReduceMotion',True)]:ctx.setContextProperty(name,value)
engine.load(QUrl.fromLocalFile(str(args.qml_root/'Studio.qml')))
assert engine.rootObjects(),messages
window=engine.rootObjects()[0];window.resize(1366,768);window.setProperty('activeTask','geometry');window.show()
def prop(obj,name):
    value=obj.property(name);return value.toVariant() if hasattr(value,'toVariant') else value
def item(name):
    found=window.findChild(QObject,name)
    def visual(parent):
        for child in parent.childItems():
            if child.objectName()==name:return child
            result=visual(child)
            if result is not None:return result
        return None
    if found is None:found=visual(window.contentItem())
    assert found is not None,(name,messages);return found
def js(obj,code):
    expression=QQmlExpression(ctx,obj,code);out=expression.evaluate();assert not expression.hasError(),expression.error().toString();return out
def click(obj):
    point=obj.mapToScene(obj.boundingRect().center()).toPoint()
    print('click',obj.objectName(),point,flush=True)
    QTest.mouseClick(obj.window() or window,Qt.LeftButton,Qt.NoModifier,point)
deadline=time.monotonic()+30;phase='import';ok=False;report={}
def tick():
    global phase,ok
    try:
        assert time.monotonic()<deadline,(phase,ctrl.status)
        if phase=='import':ctrl.add_paths([str(source)]);phase='openCrop'
        elif phase=='openCrop':
            if ctrl.busy or not ctrl.frame:QTimer.singleShot(80,tick);return
            js(window,'openCrop()');phase='openMenu'
        elif phase=='openMenu':
            if ctrl.cropBusy or not ctrl.cropSource or not prop(item('photoViewport'),'hasImage'):QTimer.singleShot(80,tick);return
            click(item('cropRatioButton'));phase='chooseXPan'
        elif phase=='chooseXPan':
            menu=item('cropRatioMenu');print('menu',{key:prop(menu,key) for key in ['visible','opened','count','x','y','width','height']},flush=True)
            assert prop(menu,'opened') and prop(menu,'count')==7 and prop(menu,'width')==196
            report['menu_width']=prop(menu,'width');report['menu_button_offset']=[prop(menu,'x'),prop(menu,'y')]
            assert window.grabWindow().save(str(OUT/'crop-ratio-menu-1366x768.png'))
            click(item('cropRatioItem_XPan 65:24'));phase='checkXPan'
        elif phase=='checkXPan':
            crop=item('cropOverlay');assert prop(crop,'ratioName')=='XPan 65:24' and abs(prop(crop,'ratio')-65/24)<1e-12
            bounds=prop(crop,'draft');actual=(bounds[2]-bounds[0])*390/((bounds[3]-bounds[1])*250)
            assert abs(actual-65/24)<1e-9,actual
            assert not prop(item('cropRatioMenu'),'visible')
            assert window.grabWindow().save(str(OUT/'crop-xpan-selected-1366x768.png'))
            report['xpan_ratio']=actual;click(item('cropRatioButton'));phase='chooseFree'
        elif phase=='chooseFree':
            assert prop(item('cropRatioMenu'),'opened')
            click(item('cropRatioItem_自由'));phase='checkFree'
        elif phase=='checkFree':
            assert prop(item('cropOverlay'),'ratioName')=='自由' and prop(item('cropOverlay'),'ratio')==0
            assert not prop(item('cropRatioMenu'),'visible')
            assert window.grabWindow().save(str(OUT/'crop-free-selected-1366x768.png'))
            click(item('cropRatioButton'));phase='escapeMenu'
        elif phase=='escapeMenu':
            assert prop(item('cropRatioMenu'),'opened')
            QTest.keyClick(window,Qt.Key_Escape)
            assert not prop(item('cropRatioMenu'),'visible')
            assert prop(window,'cropping'),'Escape must close menu, preserving crop mode'
            report['escape_closes_menu_only']=True
            js(window,'cancelCrop()');window.setProperty('activeTask','color');item('colorToolsPanel').setProperty('openGroup','calibration');phase='finish'
        else:
            assert window.grabWindow().save(str(OUT/'calibration-track-1366x768.png'))
            unexpected=[m for m in messages if any(word in m for word in ['ReferenceError','TypeError','Cannot assign','Binding loop','Unable to assign'])]
            assert not unexpected,unexpected
            report.update(real_mouse_open=True,real_mouse_xpan=True,real_mouse_free=True,qml_errors=unexpected)
            (OUT/'crop-menu-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(report,flush=True);ok=True;window.close();app.quit();return
        QTimer.singleShot(180,tick)
    except Exception:
        traceback.print_exc();print('QML',messages,flush=True);window.close();app.exit(2)
QTimer.singleShot(200,tick);result=app.exec();ctrl.close();del engine;store.cleanup();raise SystemExit(result if ok else 2)
