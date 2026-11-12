"""Exercise the actual Windows Qt window, not only controller method calls."""
from pathlib import Path
import ctypes,json,os,sys,tempfile,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.pop('QT_QPA_PLATFORM',None)
from PIL import Image
from PySide6.QtCore import QUrl,QMimeData,QObject,QMetaObject,QPointF,Qt
from PySide6.QtGui import QFontDatabase,QImage
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from desktop.controller import Controller,PhotoProvider
from desktop.import_bridge import PhotoImportBridge
from desktop.window_state import WindowState
from desktop.typography import load_mincho

root=Path(__file__).resolve().parents[1];out=root/'output/workflow-verification';out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);QQuickStyle.setStyle('Basic')
app.setStyle('Fusion')
family=load_mincho(app,root)
def wait(predicate,timeout=120):
    end=time.monotonic()+timeout
    while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.003)
    assert predicate(),'timed out'
clipboard=app.clipboard();saved=QMimeData()
for name in clipboard.mimeData().formats():saved.setData(name,clipboard.mimeData().data(name))
if clipboard.mimeData().hasImage():saved.setImageData(clipboard.image().copy())
if clipboard.mimeData().hasUrls():saved.setUrls(clipboard.mimeData().urls())
checks=[]
with tempfile.TemporaryDirectory() as folder:
    provider=PhotoProvider();ctrl=Controller(provider,folder);engine=QQmlApplicationEngine();engine.addImageProvider('photos',provider)
    engine.rootContext().setContextProperty('ctrl',ctrl)
    engine.rootContext().setContextProperty('assetsUrl',QUrl.fromLocalFile(str(root/'assets')+'/').toString())
    engine.rootContext().setContextProperty('minchoFamily',family)
    engine.rootContext().setContextProperty('systemReduceMotion',True)
    engine.load(QUrl.fromLocalFile(str(root/'desktop/qml/Studio.qml')))
    assert engine.rootObjects();window=engine.rootObjects()[0]
    window.show();app.processEvents()
    empty_import=window.findChild(QObject,'emptyImportButton');photo_strip=window.findChild(QObject,'photoStrip')
    assert empty_import and empty_import.property('visible') and photo_strip and not photo_strip.property('visible')
    def item(name):return window.findChild(QObject,name)
    assert window.property('activeTask')=='film'
    window.setProperty('activeTask','geometry');app.processEvents()
    assert window.property('activeTask')=='film'
    assert item('editorHistogram') is not None and not item('editorHistogram').property('visible')
    assert item('geometryPanel') is not None and not item('geometryPanel').property('visible')
    assert item('cropPhotoButton') is not None and not item('cropPhotoButton').property('visible')
    assert item('compareToggle') is not None and not item('compareToggle').property('visible')
    assert item('zoomControl') is not None and not item('zoomControl').property('visible')
    assert not item('openImportWorkspaceButton').property('visible')
    assert not item('openCompositionButton').property('visible')
    assert all(not item(name).property('visible') for name in ('undoButton','redoButton','resetPhotoButton'))
    assert item('emptyTitle') is None
    checks.append('empty state hides photo tools, history, zoom, dimensions and blank histogram while keeping film browsing')
    state=WindowState(window,Path(folder)/'window.ini');window.restoreRequested.connect(state.restoreNormal);state.restore()
    bridge=PhotoImportBridge(app,window,ctrl)
    try:
        first=Path(folder)/'拖放 照片.png';second=Path(folder)/'剪贴板文件.png'
        for path,color in [(first,(170,120,80)),(second,(80,120,170))]:Image.new('RGB',(900,600),color).save(path)
        # Explorer's documented HDROP/WM_DROPFILES path, including Unicode.
        from ctypes import wintypes
        class DROPFILES(ctypes.Structure):
            _fields_=[('pFiles',wintypes.DWORD),('pt',wintypes.POINT),('fNC',wintypes.BOOL),('fWide',wintypes.BOOL)]
        payload=(str(first)+'\0\0').encode('utf-16-le');header=DROPFILES(ctypes.sizeof(DROPFILES),wintypes.POINT(30,30),False,True)
        kernel=ctypes.windll.kernel32;kernel.GlobalAlloc.restype=wintypes.HGLOBAL;kernel.GlobalAlloc.argtypes=[wintypes.UINT,ctypes.c_size_t]
        kernel.GlobalLock.restype=ctypes.c_void_p;kernel.GlobalLock.argtypes=[wintypes.HGLOBAL];kernel.GlobalUnlock.argtypes=[wintypes.HGLOBAL]
        handle=kernel.GlobalAlloc(0x42,len(payload)+ctypes.sizeof(header));pointer=kernel.GlobalLock(handle)
        ctypes.memmove(pointer,ctypes.byref(header),ctypes.sizeof(header));ctypes.memmove(pointer+ctypes.sizeof(header),payload,len(payload));kernel.GlobalUnlock(handle)
        post=ctypes.windll.user32.PostMessageW;post.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
        assert post(int(window.winId()),0x233,handle,0)
        wait(lambda:len(ctrl.photos)==1 and not ctrl.busy);checks.append('native Explorer WM_DROPFILES Unicode import')
        window.setProperty('activeTask','geometry');wait(lambda:item('geometryPanel').property('visible'))
        dimensions=item('geometryDimensions')
        assert dimensions and dimensions.property('visible') and dimensions.property('text')=='900 × 600'
        assert item('cropPhotoButton').property('visible') and item('compareToggle').property('visible')
        assert item('zoomControl').property('visible')
        assert item('openImportWorkspaceButton').property('visible') and item('openCompositionButton').property('visible')
        checks.append('photo-dependent geometry, source dimensions and preview tools return after import')
        add_button=window.findChild(QObject,'addPhotosButton')
        assert add_button and add_button.property('visible') and photo_strip.property('visible')
        assert not empty_import.property('visible');checks.append('photo list shows one contextual import entry')
        mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(second))]);clipboard.setMimeData(mime)
        window.requestActivate();wait(lambda:window.isActive())
        QTest.keyClick(window,Qt.Key_V,Qt.ControlModifier)
        wait(lambda:len(ctrl.photos)==2 and not ctrl.busy);checks.append('Ctrl+V copied file import')
        bitmap=QImage(320,200,QImage.Format_RGB32);bitmap.fill('#769080');clipboard.setImage(bitmap)
        window.requestActivate();wait(lambda:window.isActive())
        QTest.keyClick(window,Qt.Key_V,Qt.ControlModifier)
        wait(lambda:len(ctrl.photos)==3 and not ctrl.busy);checks.append('Ctrl+V bitmap import')
        QTest.keyClick(window,Qt.Key_A,Qt.ControlModifier);wait(lambda:ctrl.selectedCount==3)
        ctrl.selectStock('kodak_gold_200');wait(lambda:not ctrl.busy)
        assert all(p['settings']['stock']=='kodak_gold_200' for p in ctrl.photos);checks.append('Ctrl+A and batch film preset')
        assert ctrl.export_batch('JPG_SHARE');wait(lambda:not ctrl.busy)
        exported=list(Path(folder).rglob('*_share.jpg'))
        assert len(exported)==3 and all(path.parent.name=='分享 JPG' for path in exported) and not ctrl.batchResult['errors'];checks.append('three actual JPG exports into per-source type folders with ICC')
        for path in exported:
            source=next(photo['path'] for photo in ctrl.photos if Path(photo['path']).stem+'_share'==path.stem)
            with Image.open(path) as picture,Image.open(source) as original:
                assert picture.info.get('icc_profile') and picture.size==original.size
        window.setProperty('comparing',True);QTest.qWait(100);window.grabWindow().save(str(out/'comparison-batch.png'))
        compare=window.findChild(QObject,'comparisonView');divider=window.findChild(QObject,'comparisonDivider')
        assert compare and divider and float(divider.property('x'))>=0;checks.append('comparison and outside labels render')
        zoom=window.findChild(QObject,'zoomControl');assert zoom.property('width')==174 and zoom.property('height')==28
        window.resize(1120,760);QTest.qWait(120)
        dialog=window.findChild(QObject,'exportDialog');QMetaObject.invokeMethod(dialog,'open');QTest.qWait(150)
        assert dialog.property('height')<=window.height()-8,(dialog.property('height'),window.height())
        window.grabWindow().save(str(out/'minimum-export.png'));checks.append('minimum window export popup fit and fixed zoom group')
        result=dict(ok=True,checks=checks,screenshots=[str(out/'comparison-batch.png'),str(out/'minimum-export.png')])
        (out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False,indent=2))
    finally:
        clipboard.setMimeData(saved);app.removeNativeEventFilter(bridge);ctrl.close();window.close();del engine
