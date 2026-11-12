"""One focused live-input/optics integration node, using the real renderer."""
from pathlib import Path
import json
import os
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
os.environ.pop('QT_QPA_PLATFORM',None)
import numpy as np
from PySide6.QtCore import QObject,QPoint,QPointF,Qt,QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from desktop.controller import Controller,PhotoProvider
from desktop.typography import load_mincho


def main():
    out=ROOT/'output/current-refinements';out.mkdir(parents=True,exist_ok=True)
    app=QApplication([]);app.setOrganizationName('SpektraFilm');app.setApplicationName('SpektraFilm verification')
    app.setStyle('Fusion');QQuickStyle.setStyle('Basic');family=load_mincho(app,ROOT)
    report={'ok':False,'scope':'Source GUI, real A7CR proxy and full spectral preview; not full-size export or display FPS'}
    with tempfile.TemporaryDirectory() as store:
        ctrl=Controller(PhotoProvider(),store);engine=QQmlApplicationEngine();engine.addImageProvider('photos',ctrl.provider)
        for key,value in dict(ctrl=ctrl,minchoFamily=family,
            interfaceDisplayFamily=app._interface_font_selection['display'],
            interfaceEditorialFamily=app._interface_font_selection['editorial'],
            systemReduceMotion=True,assetsUrl=QUrl.fromLocalFile(str(ROOT/'assets')+'/').toString()).items():
            engine.rootContext().setContextProperty(key,value)
        warnings=[];engine.warnings.connect(lambda errors:warnings.extend(error.toString() for error in errors))
        engine.load(QUrl.fromLocalFile(str(ROOT/'desktop/qml/Studio.qml')))
        assert engine.rootObjects(),warnings
        window=engine.rootObjects()[0];window.resize(1366,768);window.show();window.requestActivate()
        def wait(predicate,seconds=90):
            end=time.perf_counter()+seconds
            while not predicate() and time.perf_counter()<end:
                app.processEvents();QTest.qWait(3);time.sleep(.001)
            assert predicate(),dict(status=ctrl.status,jobs=list(ctrl._jobs),warnings=warnings)
        def child(name):
            result=window.findChild(QObject,name);assert result is not None,name;return result
        def capture(name):
            QTest.qWait(120);assert window.grabWindow().save(str(out/(name+'.png')))
        try:
            ctrl.add_paths(['D:/Download/DSC09118.ARW']);wait(lambda:bool(ctrl.frame) and not ctrl.busy)
            assert ctrl.currentIndex==0
            window.setProperty('activeTask','basic');QTest.qWait(120)
            slider=child('parameterSlider_exposure');handle=child('parameterHandle_exposure')
            panel=child('parameter_exposure')
            assert slider.property('visible') and slider.property('enabled')
            # Warm the film stage once, then exercise post-film HDR edits.
            ctrl.setFilmEnabled(True);wait(lambda:not ctrl.busy)
            ctrl._preview_images(ctrl.currentPath,ctrl._settings,640,True)
            before=ctrl._settings.exposure;history=len(ctrl._history.get(0,[]))
            changes=[];publications=[];events=[];active=[True]
            ctrl.stateChanged.connect(lambda:events.append(time.perf_counter()) if active[0] else None)
            ctrl.frameChanged.connect(lambda:publications.append(time.perf_counter()) if active[0] else None)
            point=handle.mapToScene(QPointF(handle.width()/2,handle.height()/2)).toPoint()
            QTest.mousePress(window,Qt.LeftButton,Qt.NoModifier,point)
            for index in range(1,49):
                start=time.perf_counter()
                QTest.mouseMove(window,point+QPoint(index,0))
                changes.append((time.perf_counter()-start)*1000)
                QTest.qWait(12)
                time.sleep(.001)
            assert panel.property('pointerEditing') and slider.property('value')>before+.1
            expected=panel.property('pointerValue')
            active[0]=False
            QTest.mouseRelease(window,Qt.LeftButton,Qt.NoModifier,point+QPoint(48,0))
            wait(lambda:not ctrl.busy)
            assert abs(ctrl._settings.exposure-expected)<.001
            assert len(ctrl._history[0])==history+1
            ctrl.undo();wait(lambda:not ctrl.busy);assert ctrl._settings.exposure==before
            ctrl.redo();wait(lambda:not ctrl.busy);assert abs(ctrl._settings.exposure-expected)<.001
            report['input']={'events':len(changes),'mouse_dispatch_p95_ms':round(float(np.percentile(changes,95)),3),
                'broad_state_events_during_drag':len(events),'published_frames_during_drag':len(publications),
                'single_history_entry':True,'release_value':expected,'undo_redo':True}
            assert not events,'Continuous input unexpectedly serialized all settings'
            # A single direct drag must work without a preceding click.
            point=handle.mapToScene(QPointF(handle.width()/2,handle.height()/2)).toPoint()
            QTest.mouseDClick(window,Qt.LeftButton,Qt.NoModifier,point)
            wait(lambda:not ctrl.busy);assert ctrl._settings.exposure==0
            report['double_click_reset']=True
            tools=next(item for item in window.findChildren(QObject) if item.metaObject().indexOfProperty('basicGroup')>=0)
            tools.setProperty('basicGroup','optics');QTest.qWait(80)
            scroll=child('parameterScroll').property('contentItem')
            scroll.setProperty('contentY',max(0,scroll.property('contentHeight')-scroll.height()))
            QTest.qWait(100)
            assert 'FE 20mm F1.8 G' in ctrl.lensStatus and '已矫正' in ctrl.lensStatus,ctrl.lensStatus
            assert ctrl.lensProfilePath.endswith('.lcp')
            report['optics']={'status':ctrl.lensStatus,'profile':ctrl.lensProfilePath,'actual_correction':True}
            capture('optics-1366x768')
            window.resize(1440,900);QTest.qWait(80);capture('optics-1440x900')
            ctrl.setCorrection('lens_correction',False)
            assert ctrl.lensStatus=='镜头校正已关闭'
            wait(lambda:not ctrl.busy)
            assert child('lensCorrectionToggle').property('stateText')=='关闭'
            assert not child('lensCorrectionToggle').property('checked')
            ctrl.setCorrection('lens_correction',True);wait(lambda:not ctrl.busy)
            assert '已矫正' in ctrl.lensStatus
            report['optics']['off_on_states']=True
            tools.setProperty('basicGroup','tone');scroll.setProperty('contentY',0)
            window.setProperty('activeTask','color');QTest.qWait(100);capture('color-1440x900')
            assert not warnings,warnings
            report['ok']=True;report['qml_warnings']=warnings
        finally:
            (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            window.close();ctrl.close();engine.deleteLater();app.processEvents()
    print(json.dumps(report,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
