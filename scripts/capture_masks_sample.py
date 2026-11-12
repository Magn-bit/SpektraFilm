"""Capture the live Windows editor with the reproducible local-mask sample."""
from pathlib import Path
import json
import hashlib
import os
import sys
import tempfile
import time

os.environ['QT_QPA_PLATFORM']='windows'
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'vendor'))
from PySide6.QtCore import QObject,QUrl,QMetaObject
from dataclasses import replace
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication
from desktop.controller import Controller,PhotoProvider,_full_settings
from desktop.typography import load_mincho


def main():
    report=json.loads((ROOT/'output/mask-sample/report.json').read_text(encoding='utf-8'))
    source=Path(sys.argv[1]) if len(sys.argv)>1 else Path(report['source'])
    if not source.exists() and len(sys.argv)==1:
        backup=ROOT/'output/mask-reference/source-windsock.jpg'
        if backup.is_file() and hashlib.sha256(backup.read_bytes()).hexdigest()==report.get('source_sha256'):source=backup
    if not source.exists():raise FileNotFoundError(f'Sample source unavailable: {source}')
    app=QApplication([]);app.setStyle('Fusion');family=load_mincho(app,ROOT)
    with tempfile.TemporaryDirectory() as store:
        provider=PhotoProvider();ctrl=Controller(provider,store);engine=QQmlApplicationEngine()
        ctrl.toast.connect(lambda message:print(message,flush=True))
        engine.addImageProvider('photos',provider)
        for key,value in {'ctrl':ctrl,'minchoFamily':family,
                'interfaceDisplayFamily':app._interface_font_selection['display'],
                'interfaceEditorialFamily':app._interface_font_selection['editorial'],
                'systemReduceMotion':True,'assetsUrl':QUrl.fromLocalFile(str(ROOT/'assets')+'/').toString(),
                'interfaceFontDescription':'现有项目字体'}.items():engine.rootContext().setContextProperty(key,value)
        engine.load(QUrl.fromLocalFile(str(ROOT/'desktop/qml/Studio.qml')))
        if not engine.rootObjects():raise RuntimeError('QML load failed')
        window=engine.rootObjects()[0];window.setWidth(1480);window.setHeight(960);window.setVisible(True)
        def wait(predicate,timeout=30):
            limit=time.monotonic()+timeout
            while not predicate() and time.monotonic()<limit:app.processEvents();time.sleep(.01)
            if not predicate():raise RuntimeError('Timed out: '+ctrl.status)
        def settle():
            for _ in range(18):app.processEvents();time.sleep(.015)
        def capture(name):
            settle();target=ROOT/'output/mask-sample'/name
            if not window.grabWindow().save(str(target)):raise RuntimeError('Capture failed')
        try:
            ctrl.add_paths([str(source)]);wait(lambda:bool(ctrl.frame) and not ctrl.busy)
            settings=dict(report['global_settings'],masks=report['masks'])
            ctrl._settings=_full_settings(settings);ctrl._changed();ctrl._persist()
            ctrl.selectMask('windsock');wait(lambda:not ctrl.busy)
            window.setProperty('editTab',3)
            panel=window.findChild(QObject,'maskPanel');panel.setProperty('showOverlay',False)
            capture('windows-mask-ui.png')
            panel.setProperty('showOverlay',True);capture('windows-mask-ui-overlay.png')
            ctrl.selectMask('clouds');capture('windows-linear-ui.png')
            window.setProperty('editTab',1);capture('windows-curves-ui.png')
            library=window.findChild(QObject,'styleLibrary');QMetaObject.invokeMethod(library,'open')
            for category in ('portrait','landscape'):
                library.setProperty('category',category)
                preset=next(item for item in ctrl.stylePresets if item['category']==category)
                library.setProperty('chosenId',preset['id']);window.findChild(QObject,'stylePresetList').setProperty('contentY',0)
                capture('windows-style-'+category+'.png')
                if category=='portrait':capture('windows-style-library.png')
            QMetaObject.invokeMethod(library,'close')
            tools=window.findChild(QObject,'colorToolsPanel');tools.setProperty('openGroup','grading')
            capture('windows-grading-ui.png')
            ctrl._settings=replace(ctrl._settings,masks=())
            ctrl.stateChanged.emit();window.setProperty('editTab',0);window.setProperty('adjustmentGroup','geometry')
            capture('windows-geometry-ui.png')
            ctrl.requestCropPreview();wait(lambda:not ctrl.cropBusy and bool(ctrl.cropSource))
            dialog=window.findChild(QObject,'cropDialog')
            QMetaObject.invokeMethod(dialog,'open')
            dialog.setProperty('draft',[.12,.08,.91,.87]);capture('windows-crop-ui.png')
            print('CAPTURE_OK output/mask-sample/windows-*-ui*.png')
        finally:
            window.close();ctrl.close();engine.deleteLater();app.processEvents()


if __name__=='__main__':main()
