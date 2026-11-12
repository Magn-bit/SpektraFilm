"""Actual layout entry / pointer framing / swap / high-depth output milestone."""
from pathlib import Path
import sys,tempfile,time,json,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
from PySide6.QtCore import QTimer,QUrl,Qt,QPoint,QObject,qInstallMessageHandler
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PIL import Image
from desktop.controller import Controller,PhotoProvider
from desktop.typography import load_mincho

OUT=ROOT/'output/creative-0.6';OUT.mkdir(parents=True,exist_ok=True)
messages=[];qInstallMessageHandler(lambda k,c,m:messages.append(str(m)))
app=QApplication([]);app.setStyle('Fusion');QQuickStyle.setStyle('Basic');family=load_mincho(app,ROOT)
store=tempfile.TemporaryDirectory();provider=PhotoProvider();ctrl=Controller(provider,store.name)
photo=ROOT/'output/grain-refinement/no-grain.png'
second=Path(store.name)/'second.png'
with Image.open(photo) as image:image.transpose(Image.Transpose.FLIP_LEFT_RIGHT).save(second)
engine=QQmlApplicationEngine();engine.addImageProvider('photos',provider);ctx=engine.rootContext()
for k,v in dict(ctrl=ctrl,minchoFamily=family,interfaceDisplayFamily=family,interfaceEditorialFamily=family,
    assetsUrl=QUrl.fromLocalFile(str(ROOT/'assets')+'/').toString(),systemReduceMotion=True).items():ctx.setContextProperty(k,v)
engine.load(QUrl.fromLocalFile(str(ROOT/'desktop/qml/Studio.qml')));assert engine.rootObjects(),messages
window=engine.rootObjects()[0];window.resize(1366,768);window.show()
def item(name):
    obj=window.findChild(QQuickItem,name)
    if obj is None:
        def search(parent):
            for child in parent.childItems():
                if child.objectName()==name:return child
                found=search(child)
                if found is not None:return found
        obj=search(window.contentItem())
    assert obj is not None,name
    return obj
def click(obj):QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,obj.mapToScene(obj.boundingRect().center()).toPoint())
phase=0;deadline=time.monotonic()+40;ok=False;report={}
def tick():
    global phase,ok
    try:
        assert time.monotonic()<deadline,(phase,ctrl.status)
        if phase==0:ctrl.add_paths([str(photo),str(second)]);phase=1
        elif phase==1:
            if ctrl.busy or ctrl.photoCount<2:QTimer.singleShot(60,tick);return
            ctrl.selectAllPhotos();click(item('openCompositionButton'));phase=2
        elif phase==2:
            if ctrl.composition.state['busy']:QTimer.singleShot(60,tick);return
            assert len(ctrl.composition.state['photos'])==2
            ctrl.composition.setOption('style','film');ctrl.composition.setOption('color','#181A17')
            ctrl.composition.setOption('caption','SpektraFilm');ctrl.composition.setOption('date','2026.11.08')
            ctrl.composition.position(0,.5,.5,1.3);phase=3
        elif phase==3:
            cell=item('compositionCell_0');center=cell.mapToScene(cell.boundingRect().center()).toPoint()
            QTest.mousePress(window,Qt.LeftButton,Qt.NoModifier,center)
            for i in range(1,9):QTest.mouseMove(window,center+QPoint(i*4,0),8)
            QTest.mouseRelease(window,Qt.LeftButton,Qt.NoModifier,center+QPoint(32,0))
            assert ctrl.composition.rows[0]['pan_x']<.48,ctrl.composition.rows[0]
            report['first_drag_panning']=ctrl.composition.rows[0]['pan_x']
            name=ctrl.composition.rows[0]['name'];ctrl.composition.swap(0,1)
            assert ctrl.composition.rows[1]['name']==name
            report['swap']=True
            phase=31
        elif phase==31:
            for index in range(2):
                image=item('compositionImage_'+str(index))
                assert image.property('source').toString(),messages
                if not image.property('imageReady'):QTimer.singleShot(60,tick);return
                assert image.width()>0 and image.height()>0
            report['preview_images_ready']=True
            window.grabWindow().save(str(OUT/'layout-1366x768.png'))
            ctrl.composition.setOption('edge',1200)
            ctrl.composition.start_export(OUT/'layout.tif');phase=4
        elif phase==4:
            if ctrl.composition.state['busy']:QTimer.singleShot(80,tick);return
            assert (OUT/'layout.tif').exists(),ctrl.composition.state
            report.update(ok=True,source_count=2,output=[ctrl.composition.state['width'],ctrl.composition.state['height']],
                qml_errors=[m for m in messages if any(s in m for s in ('ReferenceError','TypeError','Cannot assign','Binding loop'))])
            assert not report['qml_errors'],report
            (OUT/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(report,flush=True);ok=True;window.close();app.quit();return
        QTimer.singleShot(100,tick)
    except Exception:
        traceback.print_exc();print(messages,flush=True);window.close();app.exit(2)
QTimer.singleShot(150,tick);code=app.exec();ctrl.close();del engine;store.cleanup();raise SystemExit(code if ok else 2)
