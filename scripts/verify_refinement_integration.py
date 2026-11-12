"""Run the single UI refinement integration node against a bounded real photo."""
from pathlib import Path
import json,sys,tempfile,time
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
from PySide6.QtCore import QUrl,qInstallMessageHandler
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication
from PySide6 import QtSvg
from desktop.controller import Controller,PhotoProvider
from desktop.typography import load_mincho
from desktop.refinement_probe import run_refinement_probe

messages=[]
qInstallMessageHandler(lambda kind,context,message:messages.append(str(message)))
app=QApplication([]);app.setApplicationName('SpektraFilmRefinements');app.setOrganizationName('SpektraFilmVerification')
QQuickStyle.setStyle('Basic');family=load_mincho(app,ROOT)
store=tempfile.TemporaryDirectory();provider=PhotoProvider();ctrl=Controller(provider,store.name)
engine=QQmlApplicationEngine();engine.addImageProvider('photos',provider)
for name,value in [('ctrl',ctrl),('minchoFamily',family),('interfaceDisplayFamily',app._interface_font_selection['display']),
    ('interfaceEditorialFamily',app._interface_font_selection['editorial']),('interfaceFontDescription',''),
    ('assetsUrl',QUrl.fromLocalFile(str(ROOT/'assets')+'/').toString()),('systemReduceMotion',True)]:engine.rootContext().setContextProperty(name,value)
engine.load(QUrl.fromLocalFile(str(ROOT/'desktop/qml/Studio.qml')))
assert engine.rootObjects(),messages
window=engine.rootObjects()[0];window.resize(1366,768);window.show()
try:
    ctrl.add_paths([str(ROOT/'output/current-ui/source-preview.jpg')])
    report=run_refinement_probe(app,window,ctrl,ROOT/'output/refinement-integration')
    errors=[text for text in messages if ('Error:' in text or 'Unable to' in text or 'Cannot ' in text)]
    report['qml_errors']=errors
    assert not errors,errors
    (ROOT/'output/refinement-integration/report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)
finally:
    ctrl.close();window.hide();del engine;store.cleanup()
