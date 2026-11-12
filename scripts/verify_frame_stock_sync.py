"""Bounded film-edge stock/preview/TIFF and layout milestone; no RAW benchmark."""
from dataclasses import asdict, replace
from pathlib import Path
import json, sys, tempfile, time
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import numpy as np
import tifffile
from PySide6.QtCore import QObject,QMetaObject,QSettings,QUrl,qInstallMessageHandler
from PySide6.QtGui import QCursor
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication
from desktop.controller import Controller,PhotoProvider
from desktop.imaging import catalog
from desktop.typography import load_mincho
from desktop.film_canvas import render_film_edge
from shared.composition_edge import native_overscan_options

def main():
    out=ROOT/'output/frame-stock-sync-084';out.mkdir(parents=True,exist_ok=True)
    messages=[];qInstallMessageHandler(lambda kind,context,message:messages.append(str(message)))
    app=QApplication([]);app.setOrganizationName('SpektraFilmReview');app.setApplicationName('FrameStock084')
    QQuickStyle.setStyle('Basic');family=load_mincho(app,ROOT)
    with tempfile.TemporaryDirectory() as folder:
        QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,folder)
        ctrl=Controller(PhotoProvider(),folder);ctrl.updatePreference('appearance','light')
        engine=QQmlApplicationEngine();engine.addImageProvider('photos',ctrl.provider)
        for key,value in dict(ctrl=ctrl,minchoFamily=family,interfaceDisplayFamily=family,
            interfaceEditorialFamily=family,assetsUrl=QUrl.fromLocalFile(str(ROOT/'assets')+'/').toString(),systemReduceMotion=True).items():
            engine.rootContext().setContextProperty(key,value)
        engine.load(QUrl.fromLocalFile(str(ROOT/'desktop/qml/Studio.qml')))
        assert engine.rootObjects(),messages
        window=engine.rootObjects()[0];window.resize(1366,768);window.show();composition=ctrl.composition
        def pump(seconds=.08):
            end=time.monotonic()+seconds
            while time.monotonic()<end:app.processEvents();time.sleep(.005)
        def wait(predicate):
            end=time.monotonic()+30
            while not predicate() and time.monotonic()<end:pump(.02)
            assert predicate(),(ctrl.status,composition.state['status'],messages)
        source=Path(folder)/'full-source.tif'
        pixels=np.empty((384,576,3),np.uint16)
        pixels[:,:,0]=np.linspace(5000,59000,576,dtype=np.uint16)[None,:]
        pixels[:,:,1]=np.linspace(10000,49000,384,dtype=np.uint16)[:,None]
        pixels[:,:,2]=27000;tifffile.imwrite(source,pixels,photometric='rgb')
        identity=(source.stat().st_size,source.stat().st_mtime_ns)
        ctrl.add_paths([str(source)]);wait(lambda:bool(ctrl.frame) and not ctrl.busy)
        ctrl.setFilmEnabled(True)
        report=dict(ok=False,catalog_labels={},renders=[],scope=__doc__)
        for stock in catalog():
            label=native_overscan_options({'style':'film'},stock['id'])['overscan_edge_text']
            assert label and label!='FILM',stock['id'];report['catalog_labels'][stock['id']]=label
        captured=[]
        def observed(*args,**kwargs):
            result=render_film_edge(*args,**kwargs)
            captured.append(dict(preview=kwargs.get('preview'),stock=result[1]['stock'],text=result[1]['edge_text']))
            return result
        try:
            with patch('desktop.film_canvas.render_film_edge',side_effect=observed):
                for stock,text in [('kodak_portra_400','KODAK PORTRA 400'),('kodak_vision3_500t','EASTMAN 5219'),('fujifilm_velvia_50','FUJIFILM VELVIA 50')]:
                    ctrl.selectStock(stock);wait(lambda:not ctrl.busy)
                    assert ctrl.prepareComposition();wait(lambda:not composition.state['busy'])
                    composition.applyFramePreset('film_135')
                    wait(lambda:not composition.state['busy'] and not composition.state['native_pending'] and bool(composition.state['native_canvas']))
                    geometry=composition.state['native_geometry'];assert (geometry['stock'],geometry['edge_text'])==(stock,text)
                    destination=out/(stock+'.tif')
                    composition._export([dict(row) for row in composition.rows],composition.state,destination)
                    assert captured[-1]==dict(preview=False,stock=stock,text=text)
                    image=tifffile.imread(destination);assert image.dtype==np.uint16 and image.shape[0]>=384 and image.shape[1]>=576
                    report['renders'].append(dict(stock=stock,edge_text=text,preview=True,tiff16_shape=list(image.shape)))
            popup=window.findChild(QObject,'compositionDialog');QMetaObject.invokeMethod(popup,'open');pump()
            dialog=popup.property('item');assert dialog.property('frameCategory')==0
            dialog.setProperty('presetExpanded',True);composition.requestFrameTemplates(True)
            wait(lambda:not composition._template_pending and not composition._template_in_flight and not composition.state['busy'])
            for width,height in [(1366,768),(1440,900)]:
                window.resize(width,height);pump(.2)
                QCursor.setPos(window.x()+10,window.y()+10)
                assert window.grabWindow().save(str(out/f'composition-{width}.png'))
            composition.setOption('style','paper');pump();assert dialog.property('frameCategory')==1
            composition.applyFramePreset('film_135');pump();assert dialog.property('frameCategory')==0
            assert identity==(source.stat().st_size,source.stat().st_mtime_ns)
            assert not messages,messages
            report.update(ok=True,qml_messages=messages,category_sync=True,window_sizes=[[1366,768],[1440,900]],native_calls=captured)
            (out/'review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(dict(ok=True,stock_count=len(report['catalog_labels']),renders=report['renders'],qml_messages=messages),ensure_ascii=False),flush=True)
        finally:
            ctrl.close();qInstallMessageHandler(None);del engine

if __name__=='__main__':main()
