"""One bounded milestone: native print tables, exact cube order and async GUI."""
from dataclasses import replace
from pathlib import Path
import io
import json
import sys
import tempfile
import threading
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import numpy as np
from PySide6.QtCore import QObject,QMetaObject,QUrl,Qt,QTimer,qInstallMessageHandler
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from desktop.controller import Controller,PhotoProvider,Job
from desktop.imaging import Settings
from desktop.paper_lut import catalogue,native_table,export_paper_lut,start_export
from desktop.typography import load_mincho

OUTPUT=ROOT/'output/paper-lut-review';OUTPUT.mkdir(parents=True,exist_ok=True)
messages=[];qInstallMessageHandler(lambda kind,context,message:messages.append(str(message)))
app=QApplication([]);app.setStyle('Fusion');QQuickStyle.setStyle('Basic')
family=load_mincho(app,ROOT)
temporary=tempfile.TemporaryDirectory();folder=Path(temporary.name)
ctrl=Controller(PhotoProvider(),str(folder/'state'))
gui_thread=threading.get_ident();toasts=[]
ctrl.toast.connect(lambda text:toasts.append((text,threading.get_ident())))
engine=QQmlApplicationEngine();engine.addImageProvider('photos',ctrl.provider)
for key,value in dict(ctrl=ctrl,minchoFamily=family,interfaceDisplayFamily=family,interfaceEditorialFamily=family,
        assetsUrl=QUrl.fromLocalFile(str(ROOT/'assets')+'/').toString(),systemReduceMotion=True).items():
    engine.rootContext().setContextProperty(key,value)
components=QUrl.fromLocalFile(str(ROOT/'desktop/qml/components')).toString()
source=ROOT/'output/current-ui/source-preview.jpg'
qml=('import QtQuick\nimport QtQuick.Controls.Basic\nimport "'+components+'" as C\n'
     'ApplicationWindow {width:1366;height:768;visible:true;color:"#E4E4DE";'
     'Image {anchors.left:parent.left;anchors.top:parent.top;anchors.bottom:parent.bottom;anchors.right:tools.left;anchors.margins:24;'
     'source:"'+QUrl.fromLocalFile(str(source)).toString()+'";fillMode:Image.PreserveAspectFit}'
     'Rectangle {anchors.fill:tools;color:"#F8F7F3"} C.EditorTools {id:tools;objectName:"tools";'
     'anchors.right:parent.right;anchors.top:parent.top;anchors.bottom:parent.bottom;width:380;task:"film";'
     'stock:({name:"Portra 400",maker:"Kodak",type:"negative"})}}')
engine.loadData(qml.encode('utf-8'));assert engine.rootObjects(),messages
window=engine.rootObjects()[0];window.resize(1366,768);window.show()


def wait(condition,seconds=25):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        app.processEvents();time.sleep(.01)
        if condition():return
    raise AssertionError(('timeout',ctrl._status,list(ctrl._jobs),messages[-10:]))


def find(name):
    found=window.findChild(QObject,name)
    if found is not None:return found
    def visit(parent):
        for child in parent.childItems():
            if child.objectName()==name:return child
            result=visit(child)
            if result is not None:return result
    result=visit(window.contentItem());assert result is not None,name;return result


def read_samples(path):
    lines=Path(path).read_text(encoding='utf-8').splitlines()
    samples=[line for line in lines if line and line[0] in '-+.0123456789']
    return np.loadtxt(io.StringIO('\n'.join(samples)),dtype=np.float64),lines


report={'source':str(source),'window':[1366,768]}
try:
    tables=[]
    for paper,entry in catalogue().items():
        path=folder/(paper+'.cube')
        value=export_paper_lut(paper,path)
        native,metadata=native_table(paper)
        samples,lines=read_samples(path)
        ordered=native.transpose(2,1,0,3).reshape(-1,3)
        assert samples.shape==(entry['lut_size']**3,3)
        assert np.array_equal(samples.astype(np.float32),ordered),'float32 or RGB-axis order changed'
        assert 'DOMAIN_MIN 0 0 0' in lines and 'DOMAIN_MAX 1 1 1' in lines
        assert any('NOT ordinary photo RGB, NOT Cineon' in line for line in lines)
        assert any(entry['paired_film'] in line for line in lines)
        before=path.read_bytes()
        try:export_paper_lut(paper,path)
        except FileExistsError:pass
        else:raise AssertionError('existing cube overwritten')
        assert path.read_bytes()==before
        tables.append(dict(paper=paper,size=value['size'],bytes=value['bytes'],paired_film=metadata['paired_film'],
            declared_pairing=metadata['declared_pairing'],output_space=metadata['output_color_space']))
    unsupported=folder/'unsupported.cube'
    try:export_paper_lut('ilford_multigrade_iv_rc',unsupported)
    except ValueError:pass
    else:raise AssertionError('unsupported LUT fabricated')
    assert not unsupported.exists() and not list(folder.glob('*.tmp'))
    report['tables']=tables
    report['exact_float32_red_fastest']=True
    report['unsupported_and_existing_preserved']=True

    ctrl.add_paths([str(source)])
    wait(lambda:ctrl.currentIndex>=0 and not ctrl.busy)
    ctrl.chooseFilm('kodak_portra_400');wait(lambda:not ctrl.busy)
    section=find('printSection');section.setProperty('expanded',True);app.processEvents()
    button=find('exportPaperLutButton');assert button.isEnabled() and ctrl.paperLutInfo['available']
    # Reveal the final control, using the same scroll area as the application.
    scroll=find('parameterScroll');flick=scroll.property('contentItem')
    flick.setProperty('contentY',max(0,flick.property('contentHeight')-flick.property('height')))
    app.processEvents()
    ticks=[];timer=QTimer();timer.setInterval(5);timer.timeout.connect(lambda:ticks.append(time.monotonic()));timer.start()
    target=folder/'相纸 颜色.cube'
    with patch('desktop.controller.QFileDialog.getSaveFileName',return_value=(str(target),'相纸 LUT (*.cube)')):
        QMetaObject.invokeMethod(button,'clicked')
    assert ctrl.paperLutInfo['busy'] and not button.isEnabled()
    assert not ctrl.exportPaperLut(),'duplicate job admitted'
    wait(lambda:not ctrl.paperLutInfo['busy'])
    timer.stop();assert target.is_file() and toasts and all(thread==gui_thread for text,thread in toasts)
    assert button.isEnabled() and not ctrl._jobs
    window.grabWindow().save(str(OUTPUT/'paper-lut-control-1366.png'))
    ctrl._settings=replace(ctrl._settings,stock='ilford_hp5_plus_400',paper='auto');ctrl.stateChanged.emit();app.processEvents()
    assert not ctrl.paperLutInfo['available'] and not button.isEnabled()
    # Actual failed worker must also release its busy state and produce no file.
    assert start_export(ctrl,'ilford_multigrade_iv_rc',str(unsupported),Job)
    wait(lambda:not ctrl.paperLutInfo['busy'])
    assert not unsupported.exists() and '失败' in toasts[-1][0]
    assert not list(folder.glob('*.tmp'))
    errors=[item for item in messages if any(word in item for word in ('ReferenceError','TypeError','Error:','Unable to assign','Cannot assign'))]
    assert not errors,errors
    report['gui']={'async_job':True,'main_thread_completion':True,'duplicate_guard':True,'failure_cleanup':True,
        'unicode_path':True,'capability_disable':True,'qml_errors':errors,'timer_ticks_during_export':len(ticks)}
    (OUTPUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
finally:
    ctrl.close();window.close();engine.deleteLater();app.processEvents();temporary.cleanup()
