"""Opt-in, bounded input check in the exact packaged window and controller."""
import json
from pathlib import Path
import sys
import time

from PySide6.QtCore import QObject,QPointF,Qt,QEvent,QCoreApplication
from PySide6.QtGui import QMouseEvent
from PySide6.QtQml import QQmlEngine,QQmlExpression

from .version import VERSION


def run_mask_probe(app,window,ctrl,directory):
    out=Path(directory);out.mkdir(parents=True,exist_ok=True)
    report={'ok':False,'version':VERSION,'frozen':bool(getattr(sys,'frozen',False)),
            'scope':'Exact package UI/mask milestone on a small proxy; no full-size export benchmark','checks':[]}
    warnings=[]
    engine=QQmlEngine.contextForObject(window).engine()
    engine.warnings.connect(lambda entries:warnings.extend(e.toString() for e in entries))
    def settle(seconds=.15):
        end=time.monotonic()+seconds
        while time.monotonic()<end:app.processEvents();time.sleep(.004)
    def find(name):
        def walk(parent):
            for child in parent.childItems():
                if child.objectName()==name:return child
                found=walk(child)
                if found is not None:return found
        value=walk(window.contentItem()) or window.findChild(QObject,name)
        assert value is not None,name
        return value
    def click(target):
        assert target.isVisible() and target.width()>10 and target.height()>10, (target.objectName(),'not ready',target.isVisible(),target.width(),target.height())
        p=target.mapToScene(QPointF(target.width()/2,target.height()/2)).toPoint()
        assert 8<p.x()<window.width()-8 and 8<p.y()<window.height()-8,(target.objectName(),p)
        pointer(QEvent.MouseButtonPress,p,Qt.LeftButton,Qt.LeftButton)
        pointer(QEvent.MouseButtonRelease,p,Qt.LeftButton,Qt.NoButton);settle()
    def pointer(kind,p,button,buttons):
        # Queued Qt input avoids QTest's synchronous native dispatch while the
        # installed Windows file-drop filter is inside the application's loop.
        local=QPointF(p);global_position=QPointF(window.mapToGlobal(p))
        QCoreApplication.postEvent(window,QMouseEvent(kind,local,global_position,button,buttons,Qt.NoModifier))
    def js(target,code):
        expr=QQmlExpression(QQmlEngine.contextForObject(target),target,code)
        value=expr.evaluate();assert not expr.hasError(),expr.error().toString()
        return value[0] if isinstance(value,tuple) else value
    try:
        window.resize(1366,768);window.setProperty('toolsVisible',True)
        window.setProperty('activeTask','basic');settle()
        assert window.grabWindow().save(str(out/'initial.png'))
        nav=find('toolSectionNavigator');click(nav);click(find('toolSectionOption_4'))
        settle(.2);assert js(nav,'currentTitle')=='高动态范围'
        toggle=find('toggleToolsButton');click(toggle)
        assert not window.property('toolsVisible') and toggle.isVisible()
        click(toggle);assert window.property('toolsVisible')
        report['checks'].append('Packaged menu jumps to expanded HDR; seam control restores tools')
        window.setProperty('activeTask','local');settle()
        view=find('photoViewport')
        for kind in ('brush','linear','radial'):
            ctrl.addMaskOfKind(kind);ctrl.updateMaskParameter('exposure',.8);settle()
            def point(u,v):
                return view.mapToScene(QPointF(view.property('imageX')+view.property('imageWidth')*u,
                                              view.property('imageY')+view.property('imageHeight')*v)).toPoint()
            start,end=point(.27,.32),point(.7,.69)
            history=len(ctrl._history.get(ctrl.currentIndex,[]));versions=[]
            pointer(QEvent.MouseButtonPress,start,Qt.LeftButton,Qt.LeftButton);settle(.012)
            for i in range(1,49):
                pointer(QEvent.MouseMove,start+(end-start)*(i/48),Qt.NoButton,Qt.LeftButton);settle(.012)
                versions.append(ctrl._mask_overlay.version)
            pointer(QEvent.MouseButtonRelease,end,Qt.LeftButton,Qt.NoButton);settle()
            assert ctrl._before is None and len(ctrl._history[ctrl.currentIndex])==history+1
            if kind=='brush':assert len(set(versions))>=2,'Overlay starvation'
            else:
                overlay=find('gradientMaskOverlay');assert overlay.isVisible()
                grab=overlay.grabToImage();settle();assert not grab.image().isNull()
                image=grab.image()
                assert len({image.pixelColor(image.width()*i//10,image.height()//2).alpha() for i in range(1,10)})>=3
            ctrl.undo();ctrl.redo();settle()
            assert window.grabWindow().save(str(out/(kind+'.png')))
            report['checks'].append('Packaged '+kind+' actual drag, live coverage and single undo/redo')
        report['qml_warnings']=warnings;assert not warnings,warnings
        report['ok']=True
    finally:
        (out/'mask-ui.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report
