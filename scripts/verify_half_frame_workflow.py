"""Bounded pair/date milestone: actual native gates, storage lifecycle and QML.

No large RAW, native rebuild or hash verification.
"""
from dataclasses import asdict, replace
from pathlib import Path
import json,sys,tempfile,time
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
from PySide6.QtCore import QObject,QMetaObject,QUrl,qInstallMessageHandler
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication
from PySide6.QtQuickControls2 import QQuickStyle
from desktop.controller import Controller,PhotoProvider
from desktop.imaging import Settings,read_photo
from desktop.film_canvas import render_film_edge
from desktop.typography import load_mincho
from shared.date_back import imprint_options,date_capabilities,exposure_text
from shared.film_pair import read_pair,pair_document,write_pair

OUTPUT=ROOT/'output/half-frame-review';OUTPUT.mkdir(parents=True,exist_ok=True)
messages=[];qInstallMessageHandler(lambda kind,context,message:messages.append(str(message)))
app=QApplication([]);QQuickStyle.setStyle('Basic');family=load_mincho(app,ROOT)
temporary=tempfile.TemporaryDirectory();folder=Path(temporary.name)
source=ROOT/'output/current-ui/source-preview.jpg'
ctrl=Controller(PhotoProvider(),str(folder));comp=ctrl.composition
engine=QQmlApplicationEngine();engine.addImageProvider('photos',ctrl.provider)
for key,value in dict(ctrl=ctrl,minchoFamily=family,interfaceDisplayFamily=family,interfaceEditorialFamily=family,
    assetsUrl=QUrl.fromLocalFile(str(ROOT/'assets')+'/').toString(),systemReduceMotion=True).items():engine.rootContext().setContextProperty(key,value)
components=QUrl.fromLocalFile(str(ROOT/'desktop/qml/components')).toString()
engine.loadData(('import QtQuick\nimport QtQuick.Controls.Basic\nimport "'+components+'" as C\nApplicationWindow { width:1366;height:768;visible:true;C.CompositionDialog{} }').encode('utf-8'))
assert engine.rootObjects(),messages
window=engine.rootObjects()[0];window.resize(1366,768);window.show()
report={'source':str(source),'window':[1366,768]}
base=replace(Settings(),film_enabled=True,grain=0,halation=0,lens_correction=False,defringe=False)
proxy=read_photo(str(source),240)
placements=[dict(path=str(source),metadata=dict(date='2026:11:09 14:00:00',data_text='1/250 F5.6'),pan_x=.5,pan_y=.5,zoom=1.,rotation=0)]*2
options=dict(style='half_frame',frame_format='135_half',edge_view='strip',pair_axis='horizontal',
    pair_on_strip=True,pair_spacing_mm=1.,fog=1.,leaks=0.,date_imprint_active=False,placements=placements)

def native(settings,**changes):return render_film_edge([proxy,proxy],settings,dict(options,**changes),preview=True)
def wait_ready(timeout=20):
    start=time.monotonic()
    while time.monotonic()-start<timeout:
        app.processEvents();time.sleep(.02)
        if not comp._busy and comp._film_rendered==comp._film_revision:return
        if comp._film_error:raise AssertionError(comp._film_error)
    raise AssertionError((comp.state['status'],comp._busy,comp._film_rendered,comp._film_revision,messages[-8:]))
def find(name):
    value=window.findChild(QObject,name)
    if value is not None:return value
    def visit(parent):
        for child in parent.childItems():
            if child.objectName()==name:return child
            found=visit(child)
            if found is not None:return found
    value=visit(window.contentItem());assert value is not None,name;return value

try:
    # Existing native pair requests accept two explicit gates without overscan.
    small,gs=native([base,base],pair_on_strip=False,pair_spacing_mm=.5)
    wide,gw=native([base,base],pair_on_strip=False,pair_spacing_mm=2.)
    assert small.shape[0]==wide.shape[0] and small.shape[1]<wide.shape[1]
    assert len(gs['gates'])==len(gw['gates'])==2 and all(np.isfinite(frame).all() for frame in (small,wide))
    vertical,gv=native([base,base],pair_on_strip=False,pair_spacing_mm=.5,pair_axis='vertical')
    assert vertical.shape[:2]==small.shape[1::-1] and gv['vertical']
    strip_a,ga=native([base,base],pair_spacing_mm=.5)
    strip_b,gb=native([base,base],pair_spacing_mm=2.)
    assert strip_a.shape==strip_b.shape and np.array_equal(strip_a,strip_b)
    report['spacing']={'without_strip_mm':[.5,2.],'shapes':[list(small.shape),list(wide.shape)],
        'strip_fixed_1mm':True,'vertical':True,'native_two_gates':True}

    disabled=replace(base,print_effects=False)
    a,_=native([disabled,disabled])
    b,_=native([disabled,replace(disabled,preflash_exposure=.8)])
    assert np.array_equal(a,b)
    scan=replace(base,scan_film=True)
    a,_=native([scan,scan]);b,_=native([scan,replace(scan,print_exposure=1.,preflash_exposure=.8,print_y=45)])
    assert np.array_equal(a,b)
    positive=replace(base,stock='kodak_ektachrome_100')
    a,_=native([positive,positive]);b,_=native([positive,replace(positive,print_exposure=1.,preflash_exposure=.8)])
    assert np.array_equal(a,b)
    report['print_gates']={'effects_off_ignores_preflash':True,'scan_ignores_hole_print':True,'positive_ignores_hole_print':True}

    assert exposure_text(1/250,5.6)=='1/250 F5.6'
    rows=imprint_options(dict(options,date_imprint_active=True,date_style='lcd',date_also_data=True,date_size=2.),placements)
    assert rows['date_imprint_text']=="'26 11 9" and rows['date_imprint_data_text']=='1/250 F5.6' and rows['date_imprint_size']==1
    assert not date_capabilities(dict(style='film',frame_format='135_xpan',date_imprint_active=True))['available']
    assert date_capabilities(dict(style='film',frame_format='120_645'))['faces']==['data']
    assert not imprint_options(dict(options,pair_on_strip=False,date_imprint_active=True,date_style='data'),placements)['date_imprint_active']
    date,_=native([base,base],date_imprint_active=True,date_style='lcd')
    data,_=native([base,base],date_imprint_active=True,date_style='lcd',date_also_data=True)
    delta=float(np.mean(np.abs(date-data)));assert delta>0
    report['date']={'format_limits':True,'automatic_exif_data':True,'japan_order':True,'half_data_size_max':1,
        'date_plus_data_native_delta':delta}

    photos,errors=ctrl._read_imports([str(source)]);assert not errors
    photo=dict(photos[0],settings=base)
    comp.style='half_frame';comp.open_selection([photo,photo]);wait_ready()
    comp.setOption('pair_on_strip',False);comp.setOption('pair_spacing_mm',1.7);comp.position(1,.35,.65,1.2);wait_ready()
    pair_path=folder/'test.spektrapair';assert comp.savePairPath(str(pair_path))
    value=read_pair(pair_path);assert value['schemaVersion']==1 and value['spacingMM']==1.7 and not value['onStrip']
    value['forward']={'keep':True};value['left']['forward']={'keep':True};write_pair(pair_path,value)
    assert comp.openPairPath(str(pair_path));wait_ready()
    assert comp.pair_spacing_mm==1.7 and comp.rows[1]['pan_x']==.35 and comp.rows[1]['zoom']==1.2
    assert comp.savePairPath(str(pair_path));saved=read_pair(pair_path)
    assert saved['forward']=={'keep':True} and saved['left']['forward']=={'keep':True}
    comp.removeHole(1);wait_ready();assert comp.rows[1]['_empty'] and comp.state['filled_count']==1
    assert comp.savePairPath(str(pair_path)) and read_pair(pair_path)['right'] is None
    assert comp.replaceHolePath(1,str(source));wait_ready();assert not comp.rows[1]['_empty'] and comp.state['filled_count']==2
    assert comp.savePairPath(str(pair_path)) and read_pair(pair_path)['right']['path']==str(source.resolve())
    report['pair_file']={'schema':1,'roundtrip':True,'unknown_fields_retained':True,'placement_retained':True,
        'remove_keeps_empty_hole':True,'replace':True}

    popup=find('compositionDialog');QMetaObject.invokeMethod(popup,'open');app.processEvents();time.sleep(.1);app.processEvents()
    popup.setProperty('tool',0);app.processEvents();window.grabWindow().save(str(OUTPUT/'pair-spacing-1366.png'))
    popup.setProperty('tool',1);app.processEvents();window.grabWindow().save(str(OUTPUT/'pair-holes-1366.png'))
    final_path=folder/'pair-final.tif'
    assert comp.start_export(str(final_path));wait_ready()
    import tifffile
    with tifffile.TiffFile(final_path) as final:
        page=final.pages[0]
        assert page.dtype==np.uint16 and page.imagewidth>proxy.width and 'InterColorProfile' in page.tags
        report['original_source_export']={'width':page.imagewidth,'height':page.imagelength,'bits':16,'icc':True,'preview_edge':240}
    comp.setOption('pair_on_strip',True);comp.setOption('date_imprint_active',True);comp.setOption('date_style','lcd');comp.setOption('date_also_data',True)
    # Use explicit available metadata without inventing it in product code.
    for row in comp.rows:row['metadata']=dict(placements[0]['metadata'])
    comp._invalidate_film();comp.changed.emit();wait_ready();popup.setProperty('tool',2)
    app.processEvents();time.sleep(.1);app.processEvents();window.grabWindow().save(str(OUTPUT/'pair-date-data-1366.png'))
    errors=[message for message in messages if any(word in message for word in ('ReferenceError','TypeError','Error:','Unable to assign','Cannot assign'))]
    assert not errors,errors
    report['qml']={'errors':errors,'pair_buttons':True,'date_data_controls':True}
    (OUTPUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
finally:
    ctrl.close();window.close();engine.deleteLater();app.processEvents();temporary.cleanup()
