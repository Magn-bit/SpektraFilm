"""Focused async import enumeration/selection/cancel/commit plus real Qt page QA."""
from pathlib import Path
import argparse,json,sys,tempfile
from PIL import Image,ImageEnhance

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
from PySide6.QtCore import QObject,Property,QEventLoop,QTimer,QUrl,QPointF,qInstallMessageHandler
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from desktop.controller import PhotoProvider
from desktop.import_workspace import ImportWorkspace
from desktop.typography import load_mincho


parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=ROOT/'output/import-workspace-review')
parser.add_argument('--ui-root',type=Path,default=ROOT,help='Resource root whose actual QML/assets will be loaded')
args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
ui_root=args.ui_root.resolve()
messages=[];qInstallMessageHandler(lambda kind,context,message:messages.append(str(message)))
app=QApplication([]);app.setStyle('Fusion');QQuickStyle.setStyle('Basic');family=load_mincho(app,ui_root)


def until(predicate,timeout=15):
    if predicate():return
    loop=QEventLoop();poll=QTimer();poll.setInterval(20);poll.timeout.connect(lambda:loop.quit() if predicate() else None)
    deadline=QTimer();deadline.setSingleShot(True);deadline.timeout.connect(loop.quit);poll.start();deadline.start(timeout*1000);loop.exec();poll.stop();deadline.stop()
    assert predicate(),'asynchronous operation timed out'


class Owner(QObject):
    def __init__(self):super().__init__();self.provider=PhotoProvider();self.photos=[];self.exporting=False;self.added=[]
    @Property('QVariantMap',constant=True)
    def preferences(self):
        from desktop.preferences import DEFAULTS
        return dict(DEFAULTS)
    def add_paths(self,paths):self.added.extend(paths)


with tempfile.TemporaryDirectory() as folder:
    folder=Path(folder);sub=folder/'sub';sub.mkdir();owner=Owner();workspace=ImportWorkspace(owner)
    # Owned images exercise embedded file thumbnails without another RAW decode.
    source=Image.new('RGB',(600,400),'#797B60')
    existing=ROOT/'output/composition-native-review/native-135-window.png'
    if existing.is_file():
        with Image.open(existing) as screenshot:source=screenshot.crop((325,300,1154,850)).resize((600,400)).convert('RGB')
    for index in range(24):ImageEnhance.Brightness(source).enhance(.72+(index%6)*.09).save(folder/f'photo-{index:03}.jpg')
    for index in range(10):source.transpose(Image.Transpose.FLIP_LEFT_RIGHT).save(sub/f'child-{index:03}.jpg')
    (folder/'ignored.txt').write_text('not a photograph',encoding='utf-8')
    owner.photos=[dict(path=str(folder/'photo-000.jpg'))]
    engine=QQmlApplicationEngine();engine.addImageProvider('photos',owner.provider)
    for key,value in dict(ctrl=owner,importBackend=workspace,minchoFamily=family,interfaceDisplayFamily=family,interfaceEditorialFamily=family,
        assetsUrl=QUrl.fromLocalFile(str(ui_root/'assets')+'/').toString(),systemReduceMotion=True).items():engine.rootContext().setContextProperty(key,value)
    engine.loadData(b'import QtQuick\nimport QtQuick.Window\nimport "components"\nWindow { width:1366;height:768;visible:true; ImportWorkspace { anchors.fill:parent;workspace:importBackend } }',QUrl.fromLocalFile(str(ui_root/'desktop/qml/ImportReview.qml')))
    assert engine.rootObjects(),messages
    window=engine.rootObjects()[0]
    try:
        def capture(name):
            pause=QEventLoop();QTimer.singleShot(300,pause.quit);pause.exec()
            assert window.grabWindow().save(str(args.output/name))
        capture('import-empty-1366.png')
        source_button=window.findChild(QObject,'importChoosePhotos')
        QTest.mouseMove(window,source_button.mapToScene(QPointF(source_button.width()/2,source_button.height()/2)).toPoint())
        capture('import-action-hover.png')
        workspace.setSources([str(folder)]);until(lambda:not workspace.state['scanning'])
        assert workspace.state['count']==24 and workspace.state['selected']==23,workspace.state
        until(lambda:bool(workspace.state['preview']))
        capture('import-1366.png')
        workspace.selectAll(False);workspace.toggle(3,False);workspace.toggle(7,True)
        assert workspace.state['selected']==5
        workspace.setRecursive(True);until(lambda:not workspace.state['scanning'])
        assert workspace.state['count']==34 and workspace.state['selected']==15,workspace.state
        window.resize(1440,900);capture('import-1440.png')
        workspace.setSources([str(folder)]);workspace.cancelScan()
        pause=QEventLoop();QTimer.singleShot(100,pause.quit);pause.exec()
        assert not workspace.state['scanning'] and workspace.state['count']==0
        workspace.setRecursive(False);workspace.setSources([str(folder)]);until(lambda:not workspace.state['scanning'])
        workspace.selectAll(False);workspace.toggle(3,False);workspace.toggle(5,False)
        completed=[];workspace.imported.connect(completed.append);workspace.addSelected();until(lambda:bool(completed))
        assert completed==[2] and len(owner.added)==2 and workspace.state['selected']==0
        errors=[message for message in messages if any(word in message for word in ('ReferenceError','TypeError','Error:','Binding loop'))]
        assert not errors,errors
        report=dict(ok=True,top_level_count=24,recursive_count=34,excluded_current=1,range_selected=5,
            preserved_selection_after_recursive=15,cancelled_stale_scan=True,committed=2,windows=[[1366,768],[1440,900]],qml_errors=errors,
            ui_root=str(ui_root),scope='real import component, asynchronous selection/cancel/commit and settled empty/loaded screenshots; no spectral or RAW benchmark')
        (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
    finally:
        workspace.close();window.close();engine.deleteLater();app.processEvents()
