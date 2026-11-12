"""One bounded film-library milestone: real visible cards, stale isolation, presets and UI.

Uses a small existing photograph; no large RAW export or hash checks.
"""
from dataclasses import asdict, replace
from pathlib import Path
import json
import shutil
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'vendor')]
from PySide6.QtCore import QObject, QMetaObject, QUrl, Qt, qInstallMessageHandler
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from desktop.controller import Controller, PhotoProvider
from desktop.film_library import FilmLibrary, PresetStore
from desktop.imaging import Settings
from desktop.typography import load_mincho
from shared.settings_sync import DEFAULT_CATEGORIES, make_clip
from shared.geometry import Geometry

OUTPUT = ROOT/'output/film-library-review'
OUTPUT.mkdir(parents=True, exist_ok=True)
messages=[]
qInstallMessageHandler(lambda kind, context, message: messages.append(str(message)))
app=QApplication([])
app.setStyle('Fusion')
QQuickStyle.setStyle('Basic')
family=load_mincho(app, ROOT)
temporary=tempfile.TemporaryDirectory()
folder=Path(temporary.name)
source=ROOT/'output/current-ui/source-preview.jpg'
assert source.is_file(), source
copy=folder/'second-photo.jpg'
shutil.copyfile(source,copy)
ctrl=Controller(PhotoProvider(),str(folder))
library=FilmLibrary(ctrl,folder/'look-presets-test.json')
engine=QQmlApplicationEngine()
engine.addImageProvider('photos',ctrl.provider)
for key,value in dict(ctrl=ctrl, filmService=library,minchoFamily=family,interfaceDisplayFamily=family,
    interfaceEditorialFamily=family, assetsUrl=QUrl.fromLocalFile(str(ROOT/'assets')+'/').toString(),systemReduceMotion=True).items():
    engine.rootContext().setContextProperty(key,value)
components=QUrl.fromLocalFile(str(ROOT/'desktop/qml/components')).toString()
engine.loadData(('import QtQuick\nimport QtQuick.Controls.Basic\nimport "'+components+'" as C\nApplicationWindow {width:1366;height:768;visible:true;color:"#DEDEDA";C.FilmLibrary {controller:ctrl;library:filmService;onAccepted:close()} }').encode('utf-8'))
assert engine.rootObjects(),messages
window=engine.rootObjects()[0]
window.resize(1366,768)
window.show()


def wait(predicate, timeout=20):
    start=time.monotonic()
    while time.monotonic()-start<timeout:
        app.processEvents()
        time.sleep(.02)
        if predicate():return
    raise AssertionError(('timeout',library.diagnostics,dict(photos=len(ctrl._photos),current=ctrl._current,
        busy=ctrl._busy,pending=ctrl._pending,fast=ctrl._fast_busy,fast_pending=ctrl._fast_pending,
        importing=ctrl._importing,queue=len(ctrl._import_queue),jobs=list(ctrl._jobs),status=ctrl._status),messages[-10:]))


def find(name):
    found=window.findChild(QObject,name)
    if found is not None:return found
    def visit(parent):
        for child in parent.childItems():
            if child.objectName()==name:return child
            value=visit(child)
            if value is not None:return value
    found=visit(window.contentItem())
    assert found is not None,name
    return found


def stop_foreground():
    wait(lambda:not ctrl.busy)


report={'source':str(source),'window':[1366,768]}
try:
    # Independent store safety and lossless compatible extension fields.
    path=folder/'store-safety.json'
    store=PresetStore(path)
    ident=store.save('暖色',make_clip(replace(Settings(),exposure=.35),DEFAULT_CATEGORIES))
    document=json.loads(path.read_text(encoding='utf-8'))
    document['future']={'nested':[1,2,3]}
    document['presets'][0]['future_entry']={'retain':True}
    document['presets'][0]['clip']['future_clip']={'retain':True}
    path.write_text(json.dumps(document,ensure_ascii=False),encoding='utf-8')
    store=PresetStore(path)
    store.rename(ident,'暖色改名')
    store.delete(ident)
    store.restore()
    result=json.loads(path.read_text(encoding='utf-8'))
    assert result['future']==document['future']
    assert result['presets'][0]['future_entry']=={'retain':True}
    assert result['presets'][0]['clip']['future_clip']=={'retain':True}
    corrupt=folder/'corrupt.json'
    corrupt.write_text('{broken',encoding='utf-8')
    readonly=PresetStore(corrupt)
    assert not readonly.can_write and corrupt.read_text(encoding='utf-8')=='{broken'
    try:readonly.save('test',make_clip(Settings()))
    except ValueError:pass
    else:raise AssertionError('Corrupt store became writable')
    report['preset_storage']={'rename_delete_restore':True,'unknown_fields_preserved':True,'corrupt_readonly':True}

    ctrl.add_paths([str(source),str(copy)])
    wait(lambda:len(ctrl._photos)==2 and ctrl.currentIndex>=0 and not ctrl.busy)
    # Default look groups must preserve each recipient's crop and local edits.
    first=replace(ctrl._settings,film_enabled=True,exposure=.37,grain=17.,grain_size=.8)
    ctrl._settings=first
    ctrl._persist()
    assert library.savePreset('日常显影',list(DEFAULT_CATEGORIES))
    preset_id=library.presets[0]['id']
    second=replace(Settings(),exposure=-.42,geometry=Geometry(crop=(.1,.1,.9,.9)))
    ctrl._persist_photo(1,second)
    ctrl._selected={0,1}
    ctrl._settings=replace(first,exposure=-.7)
    ctrl._persist()
    before=[Settings.from_mapping(item['settings']) for item in ctrl._photos]
    assert library.applyPreset(preset_id)
    stop_foreground()
    after=[Settings.from_mapping(item['settings']) for item in ctrl._photos]
    assert all(item.exposure==.37 for item in after)
    assert after[1].geometry==second.geometry
    assert all(ctrl._history.get(i) and ctrl._history[i][-1]==before[i] for i in (0,1))
    ctrl.undo();stop_foreground();assert ctrl._settings==before[0]
    ctrl.selectPhoto(1);stop_foreground();ctrl.undo();stop_foreground();assert ctrl._settings==before[1]
    ctrl.selectPhoto(0);stop_foreground()
    assert library.renamePreset(preset_id,'日常 · 显影')
    assert library.deletePreset(preset_id) and not library.presets
    assert library.restorePreset() and library.presets[0]['name']=='日常 · 显影'
    assert PresetStore(library.store.path).entries[0]['name']=='日常 · 显影'
    report['preset_apply']={'two_targets_undoable':True,'crop_preserved':True,'reopen':True,'default_categories':list(DEFAULT_CATEGORIES)}

    popup=find('libraryPopup')
    QMetaObject.invokeMethod(popup,'open')
    wait(lambda:len([row for row in library.model.rows if row['url']])>=3)
    wait(lambda:not library._in_flight)
    report['initial_previews']=library.diagnostics
    images=[image for _,image in library._images.values()]
    assert all(max(image.width(),image.height())<=library.CARD_EDGE for image in images)
    # Actual different film outputs, not a source thumbnail repeated per card.
    assert any(images[0]!=image for image in images[1:])
    app.processEvents();time.sleep(.15);app.processEvents()
    window.grabWindow().save(str(OUTPUT/'film-cards-1366.png'))

    # Move the visible window in batches; retained pictures stay bounded.
    stock_list=find('stockList')
    for start in (7,14,21):
        stock_list.setProperty('contentY',start*104.)
        library.setVisibleRange(start,start+3)
        wait(lambda start=start:all(item['url'] for item in library.model.rows[start:start+4]))
        assert library.diagnostics['cached']<=12
        assert library.diagnostics['bytes']<=library.CACHE_BYTES
    report['scrolled_previews']=library.diagnostics

    # Foreground work has priority: no next card while the controller is busy.
    ctrl._busy=True
    stock_list.setProperty('contentY',0.)
    library.setVisibleRange(0,1)
    jobs=library._jobs
    QTest.qWait(160)
    assert library._jobs==jobs
    ctrl._busy=False
    ctrl.stateChanged.emit()
    library.setVisibleRange(0,1)
    wait(lambda:library._in_flight or all(row['url'] for row in library.model.rows[:2]))
    generation=library._generation
    library.deactivate()
    QTest.qWait(30)
    wait(lambda:not library._in_flight)
    assert library._source is None and library._generation>generation
    library.activate()
    library.setVisibleRange(0,2)
    wait(lambda:all(row['url'] for row in library.model.rows[:3]) and not library._in_flight)
    assert library._source_identity is not None
    report['scheduler']={'foreground_yields':True,'obsolete_close_isolated':True,'reopen_source_identity':True,'cache_bound':12,'source_bound':1}

    old_identity=library._source_identity
    ctrl.selectPhoto(1)
    stop_foreground()
    library.setVisibleRange(0,1)
    wait(lambda:library._source_identity!=old_identity and all(row['url'] for row in library.model.rows[:2]) and not library._in_flight)
    assert all(key[1]==library._source_identity for key in library._images if library._images[key][0] in [row['url'].rsplit('/',1)[-1] for row in library.model.rows[:2]])
    report['scheduler']['source_switch_isolated']=True
    # Exercise the same semantic selection as the main film entry.
    audition=library._card_settings(library.model.rows[1]['id'])
    library.pickFilm(audition.stock)
    stop_foreground()
    assert ctrl._settings==audition
    report['scheduler']['selection_matches_audition']=True

    # Real QML preset editor, focus/keyboard, error and readable list.
    QMetaObject.invokeMethod(popup,'open')
    popup.setProperty('page','presets')
    QTest.qWait(100)
    window.grabWindow().save(str(OUTPUT/'saved-presets-1366.png'))
    button=find('saveFilmPreset')
    QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,button.mapToScene(button.boundingRect().center()).toPoint())
    QTest.qWait(100)
    assert find('filmPresetEditor').property('opened')
    find('filmPresetName').setProperty('text','新预设')
    window.grabWindow().save(str(OUTPUT/'preset-save-1366.png'))
    QMetaObject.invokeMethod(find('confirmFilmPreset'),'click')
    QTest.qWait(100)
    assert len(library.presets)==2
    qml_errors=[line for line in messages if any(word in line for word in ('ReferenceError','TypeError','is not defined','Cannot assign','Unable to assign','Error:'))]
    assert not qml_errors,qml_errors
    report['qml']={'errors':qml_errors,'save_editor':True,'actual_photograph':True}
    (OUTPUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
finally:
    library.close()
    ctrl.close()
    window.close()
    engine.deleteLater()
    app.processEvents()
    temporary.cleanup()
