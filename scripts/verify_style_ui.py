"""Exercise the preset picker and selected-name feedback in the real desktop UI."""
from pathlib import Path
from dataclasses import asdict
import json
import os
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
os.environ.pop('QT_QPA_PLATFORM',None)
from PySide6.QtCore import QObject,QPointF,Qt,QUrl
from PySide6.QtQml import QQmlApplicationEngine,QQmlEngine,QQmlExpression
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from desktop.controller import Controller,PhotoProvider
from desktop.imaging import Settings
from desktop.typography import load_mincho


def main():
    out=ROOT/'output/style-ui-0.8.2';out.mkdir(parents=True,exist_ok=True)
    app=QApplication([]);app.setOrganizationName('SpektraFilm');app.setApplicationName('SpektraFilm style verification')
    app.setStyle('Fusion');QQuickStyle.setStyle('Basic');family=load_mincho(app,ROOT)
    ctrl=Controller(PhotoProvider(),tempfile.mkdtemp(prefix='spektrafilm-style-ui-'))
    engine=QQmlApplicationEngine();engine.addImageProvider('photos',ctrl.provider)
    for key,value in dict(ctrl=ctrl,minchoFamily=family,
        interfaceDisplayFamily=app._interface_font_selection['display'],
        interfaceEditorialFamily=app._interface_font_selection['editorial'],
        systemReduceMotion=True,assetsUrl=QUrl.fromLocalFile(str(ROOT/'assets')+'/').toString()).items():
        engine.rootContext().setContextProperty(key,value)
    errors=[];engine.warnings.connect(lambda values:errors.extend(item.toString() for item in values))
    engine.load(QUrl.fromLocalFile(str(ROOT/'desktop/qml/Studio.qml')))
    assert engine.rootObjects(),errors
    window=engine.rootObjects()[0];window.resize(1366,768);window.show()
    report={'ok':False,'scenarios':[]}
    def wait(predicate,seconds=90):
        end=time.perf_counter()+seconds
        while not predicate() and time.perf_counter()<end:
            app.processEvents();QTest.qWait(3);time.sleep(.001)
        assert predicate(),dict(status=ctrl.status,warnings=errors)
    def child(name):
        def walk(parent):
            for item in parent.childItems():
                if item.objectName()==name:return item
                found=walk(item)
                if found:return found
        item=walk(window.contentItem()) or window.findChild(QObject,name)
        assert item is not None,name;return item
    def js(item,code):
        expression=QQmlExpression(QQmlEngine.contextForObject(item),item,code)
        result=expression.evaluate();assert not expression.hasError(),expression.error().toString()
        return result
    def click(item):QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,item.mapToScene(QPointF(item.width()/2,item.height()/2)).toPoint());app.processEvents()
    def capture(name):
        QTest.qWait(100);path=out/(name+'.png');assert window.grabWindow().save(str(path));return str(path.relative_to(ROOT))
    try:
        ctrl.add_paths(['D:/Download/DSC09118.ARW']);wait(lambda:bool(ctrl.frame) and not ctrl.busy)
        window.setProperty('activeTask','color');QTest.qWait(80)
        entry=child('openStylesButton')
        assert entry.property('text')=='无预设',entry.property('text')
        assert entry.property('text')!='浏览精选'
        click(entry);dialog=child('styleLibrary');wait(lambda:dialog.property('opened'))
        assert dialog.property('chosenId')=='none',dialog.property('chosenId')
        assert [item['id'] for item in ctrl.stylePresets[:5]] == [
            'none','portrait-natural','portrait-soft','portrait-warm','portrait-bright']
        report['scenarios'].append({'state':'first picker entry is none','screenshot':capture('picker-none')})
        listing=child('stylePresetList');js(listing,'positionViewAtIndex(5,ListView.Center)');QTest.qWait(100)
        click(child('stylePreset_portrait-window'))
        assert dialog.property('chosenId')=='portrait-window'
        click(child('applyStyleButton'));wait(lambda:not dialog.property('opened'))
        assert ctrl.currentStyleName=='窗边自然光',ctrl.currentStyleName
        assert entry.property('text')=='窗边自然光',entry.property('text')
        window.resize(1440,900);QTest.qWait(100)
        report['scenarios'].append({'state':'applied preset name remains visible','screenshot':capture('applied-name')})
        ctrl.setChannelMixer('red','blue',18)
        assert ctrl.settings['channel_mixer']['red']['blue']==18
        click(entry);wait(lambda:dialog.property('opened'))
        js(listing,'positionViewAtBeginning()');QTest.qWait(100)
        click(child('stylePreset_none'))
        click(child('applyStyleButton'));wait(lambda:not dialog.property('opened'))
        assert ctrl.currentStyleName=='无预设' and entry.property('text')=='无预设'
        assert ctrl.settings['exposure']==0 and ctrl.settings['temperature']==6500 and not ctrl.settings['film_enabled']
        assert ctrl.settings['channel_mixer']==asdict(Settings().channel_mixer)
        report['scenarios'].append({'state':'none preset resets only style fields','selected_name':ctrl.currentStyleName})
        assert not errors,errors
        report['ok']=True;report['qml_warnings']=errors
    finally:
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        window.close();ctrl.close();engine.deleteLater();app.processEvents()
    print(json.dumps(report,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
