"""One bounded milestone: nine real print materials, film presets, half-frame preflash and live UI.

No full RAW export, no hashes. Only comparison sheets use resized display pixels.
"""
from dataclasses import replace
from pathlib import Path
import argparse,json,sys,tempfile,time
import numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
from PySide6.QtCore import QObject,QMetaObject,QUrl,Qt,qInstallMessageHandler
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from desktop.controller import Controller,PhotoProvider
from desktop.imaging import Settings,read_photo,photo_dimensions
from desktop.typography import load_mincho
from desktop import native_spectral
from desktop.raw_source import source_pixels,normalized_pixels,quantize_display
from shared.darkroom import PAPERS

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source',type=Path,default=ROOT/'output/current-ui/source-preview.jpg')
parser.add_argument('--output',type=Path,default=ROOT/'output/lab-frames-papers-review')
parser.add_argument('--ui-only',action='store_true')
parser.add_argument('--papers-only',action='store_true')
args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
errors=[];qInstallMessageHandler(lambda kind,context,message:errors.append(str(message)))
app=QApplication([]);app.setStyle('Fusion');QQuickStyle.setStyle('Basic');family=load_mincho(app,ROOT)
store=tempfile.TemporaryDirectory();ctrl=Controller(PhotoProvider(),store.name);engine=QQmlApplicationEngine()
engine.addImageProvider('photos',ctrl.provider)
for key,value in dict(ctrl=ctrl,minchoFamily=family,interfaceDisplayFamily=family,interfaceEditorialFamily=family,
    assetsUrl=QUrl.fromLocalFile(str(ROOT/'assets')+'/').toString(),systemReduceMotion=True).items():engine.rootContext().setContextProperty(key,value)
component_url=QUrl.fromLocalFile(str(ROOT/'desktop/qml/components')).toString()
engine.loadData(('import QtQuick\nimport QtQuick.Controls.Basic\nimport "'+component_url+'" as C\nApplicationWindow { width:1366;height:768;visible:true;color:"#EBEEE9";C.CompositionDialog { id:composition;objectName:"compositionDialog" } }').encode('utf-8'))
assert engine.rootObjects(),errors
window=engine.rootObjects()[0];window.resize(1366,768);window.show();comp=ctrl.composition
base=replace(Settings(),film_enabled=True,lens_correction=False,defringe=False,grain=0,halation=0)
report=json.loads((args.output/'papers-checkpoint.json').read_text(encoding='utf-8')) if args.ui_only and (args.output/'papers-checkpoint.json').exists() else dict(source=str(args.source),window=[1366,768],papers=[],physical_presets=[])

def find(name):
    obj=window.findChild(QObject,name)
    if obj is not None:return obj
    def walk(parent):
        for child in parent.childItems():
            if child.objectName()==name:return child
            item=walk(child)
            if item is not None:return item
    obj=walk(window.contentItem());assert obj is not None,name;return obj

def wait_ready(templates=False,timeout=20):
    start=time.monotonic()
    while time.monotonic()-start<timeout:
        app.processEvents();time.sleep(.025)
        if not comp.state['busy'] and not comp.state['native_pending'] and comp.state['native_canvas']:
            if not templates or (not comp._template_pending and not comp._template_in_flight):
                QTest.qWait(100);return
        if not comp.state['busy'] and comp.state['status'] and not comp._film_timer.isActive():raise AssertionError(comp.state['status'])
    raise AssertionError(('preview timeout',dict(style=comp.style,busy=comp._busy,operation=comp._operation,rendered=comp._film_rendered,revision=comp._film_revision,url=comp._film_url,geometry=bool(comp._film_geometry),rows=len(comp.rows),templates=comp._frame_templates,pending=comp._template_pending,in_flight=comp._template_in_flight),errors))

def click(item):
    QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,item.mapToScene(item.boundingRect().center()).toPoint())
    QTest.qWait(80)

try:
    if not args.ui_only:
        source=read_photo(str(args.source),384);input_pixels=normalized_pixels(source_pixels(source));outputs=[]
        paths=[ROOT/'native/engine/runtime/resources/profiles',ROOT/'vendor/spektrafilm/data/profiles']
        for paper in PAPERS:
            records=[json.loads((path/(paper['id']+'.json')).read_text(encoding='utf-8')) for path in paths]
            data=records[0]['data'];keys=('wavelengths','log_sensitivity','channel_density','density_curves','base_density')
            for key in keys:
                a,b=np.asarray(data[key],float),np.asarray(records[1]['data'][key],float)
                # Upstream dye spectra intentionally leave unmeasured tails NaN;
                # the profile loader prepares those supports. Do not invent data.
                assert np.array_equal(a,b,equal_nan=True),(paper['id'],key)
                if key!='channel_density':assert np.isfinite(a).all(),(paper['id'],key)
            settings=replace(base,paper=paper['id'],stock='kodak_tri_x_400' if paper['kind']=='bw' else 'kodak_portra_400')
            start=time.perf_counter();pixels=native_spectral.render_spectral(input_pixels,settings,preview=True)
            assert pixels.shape==input_pixels.shape and np.isfinite(pixels).all(),paper['id']
            outputs.append((paper,Image.fromarray(quantize_display(pixels))))
            report['papers'].append(dict(id=paper['id'],name=records[0]['info']['name'],stock=settings.stock,
                resolved=native_spectral.parameters(settings)['print_stock'],wavelength_count=len(data['wavelengths']),
                channel_density_shape=list(np.asarray(data['channel_density']).shape),mean_rgb=pixels.mean(axis=(0,1)).tolist(),
                unmeasured_dye_samples=int(np.count_nonzero(~np.isfinite(np.asarray(data['channel_density'],float)))),
                elapsed_ms=round((time.perf_counter()-start)*1000,2),runtime_vendor_arrays_equal=True))
        color=[np.asarray(image).astype(float) for paper,image in outputs if paper['kind']=='color']
        pairwise=[float(np.abs(a-b).mean()) for i,a in enumerate(color) for b in color[i+1:]]
        assert min(pairwise)>.05,pairwise
        report['minimum_color_paper_pairwise_mean_difference_rgb8']=min(pairwise)
        font=ImageFont.truetype(str(ROOT/'assets/fonts/SpektraBilingualSerif-Regular.ttf'),15)
        sheet=Image.new('RGB',(3*280+32,3*250+32),'#F4F5EF');draw=ImageDraw.Draw(sheet)
        for i,(paper,image) in enumerate(outputs):
            image.thumbnail((264,208));x=16+(i%3)*280;y=16+(i//3)*250
            sheet.paste(image,(x+(264-image.width)//2,y));draw.text((x,y+214),paper['name'],font=font,fill='#30352D')
        sheet.save(args.output/'nine-print-materials.png')
        (args.output/'papers-checkpoint.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        if args.papers_only:
            print(json.dumps(report,ensure_ascii=False),flush=True)
            raise SystemExit(0)
    width,height=photo_dimensions(str(args.source));entry=dict(path=str(args.source),name=args.source.name,width=width,height=height,settings=base)
    assert comp.open_selection([entry]);comp.applyFramePreset('film_135')
    dialog=find('compositionDialog');QMetaObject.invokeMethod(dialog,'open');wait_ready()
    section=find('compositionPresetSection');dialog.setProperty('presetExpanded',True);comp.requestFrameTemplates(True);wait_ready(templates=True)
    assert len(comp._frame_templates)==5,comp._frame_templates
    window.grabWindow().save(str(args.output/'frame-styles-expanded-1366.png'))
    dialog.setProperty('presetExpanded',False);comp.requestFrameTemplates(False);QTest.qWait(120)
    viewport=find('compositionOptionsViewport');footer=find('compositionOutputFooter')
    assert viewport.mapToScene(viewport.boundingRect().bottomRight()).y() <= footer.mapToScene(footer.boundingRect().topLeft()).y(), 'scroll/footer overlap'
    report['scroll_footer_separate']=True
    for preset in comp.state['frame_presets']:
        if preset['enabled']:assert preset['source'],preset
    assert window.grabWindow().save(str(args.output/'film-135-1366.png'))
    for preset_id,expected in (('film_120_square','120_6x6'),('film_filed','135')):
        dialog.setProperty('presetExpanded',True);comp.requestFrameTemplates(True);QTest.qWait(100)
        click(find('compositionPreset_'+preset_id));wait_ready()
        assert comp.state['frame_format']==expected and comp.state['style']=='film'
        assert comp.state['native_geometry']['format']==expected
        report['physical_presets'].append(dict(id=preset_id,format=expected,dimensions=[comp.state['width'],comp.state['height']]))
        window.grabWindow().save(str(args.output/(preset_id+'-1366.png')))
    # Same source twice isolates the print trim: preview-size only, not full RAW.
    assert comp.open_selection([entry,entry]);comp.applyFramePreset('film_half');wait_ready()
    rows=[dict(row) for row in comp.rows];options=comp.state
    small=read_photo(str(args.source),240)
    for row in rows:row['_prepared']=small
    a,geometry=comp._render_film_rows(rows,options,preview=True)
    changed=[dict(row) for row in rows];changed[0]['settings']=replace(base,preflash_exposure=.1)
    b,_=comp._render_film_rows(changed,options,preview=True)
    differences=[]
    for quad in geometry['gates']:
        points=np.asarray(quad).reshape(4,2);h,w=a.shape[:2]
        l,r=np.rint(points[:,0].min()*w).astype(int),np.rint(points[:,0].max()*w).astype(int)
        t,bt=np.rint(points[:,1].min()*h).astype(int),np.rint(points[:,1].max()*h).astype(int)
        inset=3;delta=np.abs(a[t+inset:bt-inset,l+inset:r-inset]-b[t+inset:bt-inset,l+inset:r-inset])
        differences.append(float(delta.mean()))
    assert differences[0]>.0001 and differences[1]<.00005,differences
    report['independent_pair_preflash_mean_rgb_delta']=differences
    small.close()
    if not args.ui_only:source.close()
    window.grabWindow().save(str(args.output/'half-frame-1366.png'))
    errors=[m for m in errors if any(s in m for s in ('ReferenceError','TypeError','Cannot assign','Binding loop','Error:'))]
    assert not errors,errors
    report['qml_errors']=errors;report['ok']=True
    (args.output/'materials-and-frames.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)
finally:
    ctrl.close();window.close();engine.deleteLater();app.processEvents();store.cleanup()
