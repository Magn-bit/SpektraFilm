"""Frame menu input and complete large-source canvas visibility; no large decode."""
from pathlib import Path
import argparse,json,sys,tempfile,time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
from PySide6.QtCore import QObject,QMetaObject,Qt,QUrl,qInstallMessageHandler
from PySide6.QtGui import QImage,QColor
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from desktop.controller import Controller,PhotoProvider
from desktop.imaging import Settings
from desktop.typography import load_mincho
from shared.composition import STYLES

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--qml-root',type=Path,default=ROOT/'desktop/qml')
parser.add_argument('--output',type=Path,default=ROOT/'output/frame-fix')
args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
messages=[];qInstallMessageHandler(lambda kind,context,message:messages.append(str(message)))
app=QApplication([]);app.setStyle('Fusion');QQuickStyle.setStyle('Basic')
family=load_mincho(app,ROOT);store=tempfile.TemporaryDirectory()
provider=PhotoProvider();ctrl=Controller(provider,store.name)
engine=QQmlApplicationEngine();engine.addImageProvider('photos',provider)
for name,value in dict(ctrl=ctrl,minchoFamily=family,interfaceDisplayFamily=family,
    interfaceEditorialFamily=family,assetsUrl=QUrl.fromLocalFile(str(ROOT/'assets')+'/').toString(),
    systemReduceMotion=True).items():engine.rootContext().setContextProperty(name,value)
engine.load(QUrl.fromLocalFile(str(args.qml_root.resolve()/'Studio.qml')))
assert engine.rootObjects(),messages
window=engine.rootObjects()[0];window.resize(1366,768);window.show()

def settle():
    QTest.qWait(80)

def find(name):
    obj=window.findChild(QObject,name)
    if obj is not None:return obj
    def walk(parent):
        for child in parent.childItems():
            if child.objectName()==name:return child
            result=walk(child)
            if result is not None:return result
    obj=walk(window.contentItem());assert obj is not None,name;return obj

def objects(parent):
    for child in parent.children():
        yield child
        yield from objects(child)

def click(item):
    QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,
                     item.mapToScene(item.boundingRect().center()).toPoint())
    settle()

report=dict(qml_root=str(args.qml_root.resolve()),canvas_checks=[],menu_checks=[])
try:
    # Known small proxy, declared full-source dimensions. Preview must use the
    # full-source aspect/geometry without ever allocating a 150MP test image.
    proxy=QImage(300,200,QImage.Format_RGB32);proxy.fill(QColor('#787D69'))
    provider.publish('frame-layout-fixture',proxy)
    comp=ctrl.composition
    # A pair is used so the real half-frame choice has two independently
    # addressable gates; this fixture intentionally reuses the tiny proxy.
    comp.rows=[dict(path='',name='canvas-test-a.tif',settings=Settings(),width=9564,height=6376,
        source='image://photos/frame-layout-fixture',zoom=1.,pan_x=.5,pan_y=.5,rotation=0),
        dict(path='',name='canvas-test-b.tif',settings=Settings(),width=9564,height=6376,
        source='image://photos/frame-layout-fixture',zoom=1.,pan_x=.5,pan_y=.5,rotation=0)]
    comp.changed.emit()
    QMetaObject.invokeMethod(find('compositionDialog'),'open');settle()
    # Exercise the single visual selector while the decoder is still pending.
    comp._operation='preview';comp._busy=True;comp.changed.emit();settle()
    for index,style in enumerate(STYLES):
        dialog=find('compositionDialog')
        dialog.setProperty('frameCategory',0 if style in ('film','half_frame') else 1)
        dialog.setProperty('presetExpanded',style in ('film','half_frame'));settle()
        tile=find('compositionTemplate_'+style)
        assert tile.isEnabled(),style
        click(tile)
        assert comp.state['style']==style,(style,comp.state['style'])
        report['menu_checks'].append(style)
    # The cards are real Qt buttons: keyboard focus, Enter and Space do not
    # depend on a separate duplicate dropdown.
    dialog.setProperty('frameCategory',1);settle()
    tile=find('compositionTemplate_plain');tile.forceActiveFocus(Qt.TabFocusReason)
    QTest.keyClick(window,Qt.Key_Return);settle();assert comp.state['style']=='plain'
    dialog.setProperty('frameCategory',0);dialog.setProperty('presetExpanded',True);settle()
    tile=find('compositionTemplate_film');tile.forceActiveFocus(Qt.TabFocusReason)
    QTest.keyClick(window,Qt.Key_Space);settle();assert comp.state['style']=='film'
    report['keyboard_cards']=True
    comp._busy=False;comp._operation='';comp.changed.emit();settle()
    for size in ((1366,768),(1440,900)):
        window.resize(*size);settle()
        for dimensions in ((9564,6376),(14204,10652),(10652,14204)):
            comp.rows[0].update(width=dimensions[0],height=dimensions[1])
            for style in STYLES:
                comp.setOption('style',style);settle()
                canvas=find('compositionCanvas');surface=find('compositionPreview')
                assert canvas.x()>=23.5 and canvas.y()>=23.5,(dimensions,style,canvas.position())
                assert canvas.x()+canvas.width()<=surface.width()-23.5,(dimensions,style,'right edge')
                assert canvas.y()+canvas.height()<=surface.height()-23.5,(dimensions,style,'bottom edge')
                report['canvas_checks'].append(dict(window=size,source=dimensions,style=style,
                    scale=canvas.property('fit'),preview=[canvas.width(),canvas.height()]))
                if size==(1366,768) and dimensions==(14204,10652):
                    assert window.grabWindow().save(str(args.output/(style+'.png')))
    report['qml_errors']=[m for m in messages if any(s in m for s in
        ('ReferenceError','TypeError','Cannot assign','Binding loop'))]
    assert not report['qml_errors'],report['qml_errors']
    report['ok']=True
    (args.output/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(ok=True,menu_checks=report['menu_checks'],canvas_checks=len(report['canvas_checks']),
        qml_errors=report['qml_errors']),ensure_ascii=False),flush=True)
finally:
    window.close();ctrl.close();qInstallMessageHandler(None);del engine;store.cleanup()
