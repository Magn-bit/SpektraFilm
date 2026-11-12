"""Layout-only source-proxy fixture for viewport bounds; no native rendering."""
import json,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
from PySide6.QtCore import QUrl,QObject,QMetaObject,Qt,qInstallMessageHandler
from PySide6.QtGui import QImage
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtQuickControls2 import QQuickStyle
from desktop.controller import Controller,PhotoProvider
from desktop.imaging import Settings
from desktop.typography import load_mincho
out=ROOT/'output/lab-frames-papers-review';errors=[];qInstallMessageHandler(lambda t,c,m:errors.append(str(m)))
app=QApplication([]);QQuickStyle.setStyle('Basic');family=load_mincho(app,ROOT);store=tempfile.TemporaryDirectory();ctrl=Controller(PhotoProvider(),store.name);engine=QQmlApplicationEngine();engine.addImageProvider('photos',ctrl.provider)
for k,v in dict(ctrl=ctrl,minchoFamily=family,interfaceDisplayFamily=family,interfaceEditorialFamily=family,assetsUrl=QUrl.fromLocalFile(str(ROOT/'assets')+'/').toString(),systemReduceMotion=True).items():engine.rootContext().setContextProperty(k,v)
url=QUrl.fromLocalFile(str(ROOT/'desktop/qml/components')).toString()
engine.loadData(('import QtQuick\nimport QtQuick.Controls.Basic\nimport "'+url+'" as C\nApplicationWindow { width:1366;height:768;visible:true;C.CompositionDialog { objectName:"compositionDialog" } }').encode())
window=engine.rootObjects()[0];comp=ctrl.composition;report=dict(layouts=[],qml_errors=[])
try:
 ctrl.provider.publish('layout-source',QImage(str(ROOT/'output/current-ui/source-preview.jpg')))
 comp.rows=[dict(path='',name='source.jpg',settings=Settings(),width=1500,height=1000,source='image://photos/layout-source',zoom=1,pan_x=.5,pan_y=.5,rotation=0)]
 comp.style='film';comp.changed.emit()
 dialog=window.findChild(QObject,'compositionDialog');QMetaObject.invokeMethod(dialog,'open');QTest.qWait(100)
 def find(name):
  def walk(item):
   if item.objectName()==name:return item
   for child in item.childItems():
    value=walk(child)
    if value is not None:return value
  return walk(window.contentItem())
 viewport=find('compositionOptionsViewport');footer=find('compositionOutputFooter');last=find('compositionLeaks')
 for size in ((1366,768),(1440,900)):
  window.resize(*size);dialog.setProperty('presetExpanded',False);QTest.qWait(80)
  view=viewport.property('contentItem')
  view.setProperty('contentY',max(0,float(view.property('contentHeight'))-float(view.property('height'))));QTest.qWait(80)
  vp_top=viewport.mapToScene(viewport.boundingRect().topLeft()).y();vp_bottom=viewport.mapToScene(viewport.boundingRect().bottomRight()).y();foot_top=footer.mapToScene(footer.boundingRect().topLeft()).y();last_top=last.mapToScene(last.boundingRect().topLeft()).y();last_bottom=last.mapToScene(last.boundingRect().bottomRight()).y()
  assert vp_bottom<=foot_top and last_bottom<=vp_bottom and last_top>=vp_top,(size,vp_top,vp_bottom,foot_top,last_top,last_bottom)
  report['layouts'].append(dict(window=size,viewport=[vp_top,vp_bottom],footer_top=foot_top,last_parameter=[last_top,last_bottom],all_reachable=True))
  window.grabWindow().save(str(out/('sidebar-bottom-'+str(size[0])+'.png')))
 report['qml_errors']=[m for m in errors if any(s in m for s in ('ReferenceError','TypeError','Cannot assign','Binding loop','Error:'))];assert not report['qml_errors'],report
 report['ok']=True;(out/'layout-boundaries.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report),flush=True)
finally:ctrl.close();window.close();engine.deleteLater();app.processEvents();store.cleanup()
