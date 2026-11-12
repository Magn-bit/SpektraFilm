"""Native UI checks for anchored zoom, comparisons and session removal."""
from pathlib import Path
import json,os,sys,tempfile,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.pop('QT_QPA_PLATFORM',None)
from PIL import Image,ImageDraw
from PySide6.QtCore import QUrl,QObject,QMetaObject,Q_ARG,QPointF,QPoint,Qt
from PySide6.QtGui import QWheelEvent,QTextLayout
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from desktop.controller import Controller,PhotoProvider
from desktop.typography import load_mincho

root=Path(__file__).resolve().parents[1];out=root/'output/photo-navigation';out.mkdir(parents=True,exist_ok=True)
qml_root=Path(os.environ.get('SPEKTRAFILM_QML_ROOT',root/'desktop/qml')).resolve()
asset_root=qml_root.parent.parent
app=QApplication([]);app.setStyle('Fusion');QQuickStyle.setStyle('Basic');family=load_mincho(app,asset_root)
layout=QTextLayout('导入照片 胶片档案 Portra 400',app.font());layout.beginLayout();layout.createLine();layout.endLayout()
glyph_families={run.rawFont().familyName() for run in layout.glyphRuns()}
assert glyph_families.issubset({family,app._interface_font_selection['cjk']}),glyph_families
checks=[];shots=[]
def wait(predicate):
    until=time.monotonic()+120
    while not predicate() and time.monotonic()<until:app.processEvents();time.sleep(.004)
    assert predicate(),'navigation check timed out'
def shot(window,name):
    QTest.qWait(120);path=out/(name+'.png');assert window.grabWindow().save(str(path));shots.append(str(path))
with tempfile.TemporaryDirectory() as folder:
    first=Path(folder)/'细节校验.png';second=Path(folder)/'第二张.png'
    image=Image.new('RGB',(2400,1600),'#B6C1BA');draw=ImageDraw.Draw(image)
    for x in range(0,2400,12):draw.line((x,0,x,1600),fill='#3B5145',width=2)
    for y in range(0,1600,100):draw.line((0,y,2400,y),fill='#FFFFFF',width=1)
    image.save(first);Image.new('RGB',(700,1100),'#97A8B2').save(second)
    ctrl=Controller(PhotoProvider(),folder);engine=QQmlApplicationEngine();engine.addImageProvider('photos',ctrl.provider)
    for key,value in [('ctrl',ctrl),('minchoFamily',family),('systemReduceMotion',True),('assetsUrl',QUrl.fromLocalFile(str(asset_root)+'/').toString())]:engine.rootContext().setContextProperty(key,value)
    engine.load(QUrl.fromLocalFile(str(qml_root/'Studio.qml')));assert engine.rootObjects()
    window=engine.rootObjects()[0];window.show();window.requestActivate()
    try:
        ctrl.importPhotos();wait(lambda:window.property('workspaceMode')=='import')
        importer=ctrl.importWorkspace;importer.setSources([str(folder)])
        wait(lambda:not importer.state['scanning'] and importer.state['count']==2)
        assert importer.state['selected']==2
        importer.addSelected();wait(lambda:not importer.state['adding'])
        assert window.property('workspaceMode')=='import','Import page must remain visible until the first render is ready'
        wait(lambda:len(ctrl.photos)==2 and ctrl.currentIndex==0 and bool(ctrl.frame) and window.property('workspaceMode')=='edit')
        assert ctrl.currentPath==ctrl.photos[0]['path'],(ctrl.currentPath,ctrl.photos[0]['path'])
        wait(lambda:not ctrl.busy)
        wait(lambda:window.isActive());window.resize(1120,760);QTest.qWait(150)
        view=window.findChild(QObject,'photoViewport');flick=window.findChild(QObject,'photoFlickable');image=window.findChild(QObject,'photoOutput')
        wait(lambda:view.property('hasImage'))
        assert image.property('visible') and ctrl.currentPath==ctrl.photos[0]['path']
        checks.append('the first imported photo renders in the edit canvas without clicking its thumbnail')
        ratio=view.property('effectiveRatio');assert 0<ratio<1
        shot(window,'fit')
        QTest.keyClick(window,Qt.Key_1,Qt.ControlModifier);wait(lambda:ctrl.detailReady)
        assert window.property('actualSize') and abs(view.property('effectiveRatio')-1)<.001
        detail_tile=window.findChild(QObject,'fullDetailTile')
        wait(lambda:detail_tile.property('visible') and bool(ctrl.fullDetail.source))
        full_detail=ctrl.provider.images.get('full-detail')
        assert full_detail is not None and not full_detail.isNull() and full_detail.width()>0
        assert abs(image.property('width')-ctrl.sourceDimensions[0]/view.property('dpr'))<1
        checks.append('Ctrl+1 displays source-resolution detail tiles at native physical-pixel scale')
        # Check an off-centre image point remains under the same screen point.
        px=view.property('width')*.61;py=view.property('height')*.57
        before=((px-view.property('imageX'))/view.property('imageWidth'),(py-view.property('imageY'))/view.property('imageHeight'))
        assert QMetaObject.invokeMethod(view,'setZoom',Qt.DirectConnection,Q_ARG('QVariant',2),Q_ARG('QVariant',px),Q_ARG('QVariant',py))
        QTest.qWait(80)
        after=((px-view.property('imageX'))/view.property('imageWidth'),(py-view.property('imageY'))/view.property('imageHeight'))
        assert all(abs(a-b)<.002 for a,b in zip(before,after)),(before,after)
        assert 0<=flick.property('contentX')<=flick.property('contentWidth')-flick.property('width')+.5
        checks.append('200% zoom preserves the cursor anchor and clamps pan bounds')
        window.setProperty('comparing',True);QTest.qWait(80)
        comparison=window.findChild(QObject,'comparisonView')
        for prop in ('x','y','width','height'):assert abs(comparison.property(prop)-image.property(prop))<.1,prop
        shot(window,'detail-200-compare');checks.append('comparison shares image geometry at 200% after panning')
        window.setProperty('comparing',False);QTest.qWait(40)
        point=view.mapToScene(QPointF(view.property('width')*.7,view.property('height')*.4)).toPoint()
        wheel=QWheelEvent(QPointF(point),QPointF(window.mapToGlobal(point)),QPoint(),QPoint(0,120),Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False)
        QTest.mouseMove(window,point);QTest.qWait(40)
        old_ratio=view.property('effectiveRatio');app.sendEvent(window,wheel);QTest.qWait(80)
        assert view.property('effectiveRatio')>old_ratio
        checks.append('actual wheel events zoom the image')
        QTest.mouseDClick(window,Qt.LeftButton,Qt.NoModifier,point);QTest.qWait(100)
        assert not window.property('actualSize')
        assert flick.property('contentX')==0 and flick.property('contentY')==0
        checks.append('double-click returns to fit and resets pan')
        # Search owns Delete; removing a photo cannot steal text deletion.
        library=window.findChild(QObject,'libraryPopup');search=window.findChild(QObject,'stockSearch')
        QMetaObject.invokeMethod(library,'open');QTest.qWait(100);search.setProperty('text','portra');search.forceActiveFocus()
        QTest.keyClick(window,Qt.Key_Home);QTest.keyClick(window,Qt.Key_Delete);QTest.qWait(40)
        assert len(ctrl.photos)==2 and search.property('text')=='ortra'
        QMetaObject.invokeMethod(library,'close');QTest.qWait(80)
        ctrl.selectPhoto(1);wait(lambda:not ctrl.busy)
        QTest.keyClick(window,Qt.Key_Delete);wait(lambda:len(ctrl.photos)==1 and not ctrl.busy)
        assert first.is_file() and second.is_file()
        checks.append('Delete respects text fields and removes session entries without changing source files')
        ctrl.selectAllPhotos();ctrl.removeSelectedPhotos();wait(lambda:not ctrl.busy)
        assert not ctrl.frame and ctrl.currentIndex==-1;shot(window,'removed-empty')
        checks.append('removing the final photo restores a clean empty state')
        result=dict(ok=True,font=family,glyph_families=sorted(glyph_families),checks=checks,screenshots=shots,fixture='synthetic line chart; not a bundled sample photo')
        (out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False,indent=2))
    finally:ctrl.close();window.close();del engine
