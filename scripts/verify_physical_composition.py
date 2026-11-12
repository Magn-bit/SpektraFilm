"""One physical-composition integration: native preview and original-size pair TIFF.

An optional real RAW is decoded only as a bounded UI preview. The source-depth
export uses owned RGB16 fixtures; this is not a repeated full-RAW benchmark.
"""
from dataclasses import replace
from pathlib import Path
import argparse,json,sys,tempfile,time
import numpy as np
import tifffile

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
from PySide6.QtCore import QObject,QMetaObject,QUrl,qInstallMessageHandler
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from desktop.controller import Controller,PhotoProvider
from desktop.imaging import Settings,photo_dimensions
from desktop.typography import load_mincho


parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--real-source',type=Path)
parser.add_argument('--output',type=Path,default=ROOT/'output/composition-native-review')
args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
errors=[];qInstallMessageHandler(lambda kind,context,message:errors.append(str(message)))
app=QApplication([]);app.setStyle('Fusion');QQuickStyle.setStyle('Basic')
family=load_mincho(app,ROOT);temporary=tempfile.TemporaryDirectory()
ctrl=Controller(PhotoProvider(),temporary.name)
engine=QQmlApplicationEngine();engine.addImageProvider('photos',ctrl.provider)
for key,value in dict(ctrl=ctrl,minchoFamily=family,interfaceDisplayFamily=family,
    interfaceEditorialFamily=family,assetsUrl=QUrl.fromLocalFile(str(ROOT/'assets')+'/').toString(),
    systemReduceMotion=True).items():engine.rootContext().setContextProperty(key,value)
engine.load(QUrl.fromLocalFile(str(ROOT/'desktop/qml/Studio.qml')))
assert engine.rootObjects(),errors
window=engine.rootObjects()[0];window.resize(1366,768);window.show()
composition=ctrl.composition
base=replace(Settings(),film_enabled=True,lens_correction=False,defringe=False,grain=0,halation=0)
report=dict(physical_preview=False,original_pair_export=False)


def settle(timeout=40):
    start=time.monotonic()
    while time.monotonic()-start<timeout:
        app.processEvents();time.sleep(.025)
        if not composition.state['busy'] and not composition.state['native_pending'] and composition.state['native_canvas']:
            return
        if not composition.state['busy'] and composition.state['status'] and not composition._film_timer.isActive():
            raise AssertionError(composition.state['status'])
    raise AssertionError(('native preview timeout',composition.state['status']))


def entry(path,settings=base):
    width,height=photo_dimensions(str(path))
    return dict(path=str(path),name=path.name,width=width,height=height,settings=settings)


try:
    # True RGB16 sources stay larger than the 1000px preview cache.
    height,width=1200,1800
    pixels=np.empty((height,width,3),np.uint16)
    pixels[:,:,0]=np.linspace(1800,56000,width,dtype=np.uint16)[None,:]
    pixels[:,:,1]=np.linspace(3000,49000,height,dtype=np.uint16)[:,None]
    pixels[:,:,2]=np.linspace(43000,6000,width,dtype=np.uint16)[None,:]
    left,right=Path(temporary.name)/'left.tif',Path(temporary.name)/'right.tif'
    tifffile.imwrite(left,pixels,photometric='rgb');tifffile.imwrite(right,np.rot90(pixels).copy(),photometric='rgb')
    source=args.real_source or left
    assert composition.open_selection([entry(source)])
    composition.setOption('style','film')
    QMetaObject.invokeMethod(window.findChild(QObject,'compositionDialog'),'open')
    settle()
    report['physical_preview']=True
    report['source_dimensions']=[composition.rows[0]['width'],composition.rows[0]['height']]
    report['native_preview_geometry']=composition.state['native_geometry']
    window.grabWindow().save(str(args.output/'native-135-window.png'))
    composition.setOption('frame_format','120_6x6');settle()
    assert composition.state['native_geometry']['format']=='120_6x6'
    window.grabWindow().save(str(args.output/'native-120-window.png'))
    assert composition.open_selection([entry(left),entry(right,replace(base,exposure=.4,print_exposure=.35,contrast=12))])
    composition.setOption('style','half_frame');settle()
    geometry=composition.state['native_geometry']
    assert len(geometry['gates'])==2 and geometry['pair_layered']
    assert max(image.size[0] for image in (row['_prepared'] for row in composition.rows))<=1000
    window.grabWindow().save(str(args.output/'native-pair-window.png'))
    output=args.output/'native-pair-original.tif'
    with __import__('unittest.mock',fromlist=['patch']).patch.object(ctrl,'_source',side_effect=AssertionError('No preview cache in final output')):
        composition._export(composition.rows,composition.state,output)
    actual=tifffile.imread(output)
    assert actual.dtype==np.uint16 and max(actual.shape[:2])>1800,actual.shape
    assert np.unique(actual[:,:,0]).size>256
    with tifffile.TiffFile(output) as image:assert 34675 in image.pages[0].tags
    report['original_pair_export']=True;report['export_dimensions']=[actual.shape[1],actual.shape[0]]
    report['output_bits']=16
    composition.setOption('pair_axis','vertical');composition.setOption('date_imprint_active',True);composition.setOption('date','2026-11-09');settle()
    assert composition.state['native_geometry']['vertical']
    window.grabWindow().save(str(args.output/'native-pair-date-window.png'))
    report['vertical_pair_and_native_date']=True
    report['qml_errors']=[message for message in errors if any(word in message for word in ('ReferenceError','TypeError','Error:','Binding loop'))]
    assert not report['qml_errors'],report['qml_errors']
    report['ok']=True
    (args.output/'integration.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
finally:
    ctrl.close();window.close();engine.deleteLater();app.processEvents();temporary.cleanup()
