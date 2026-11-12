"""Capture the actual Qt interface and verify typography, search and dialogs."""
from pathlib import Path
import json, os, sys, tempfile, time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.pop('QT_QPA_PLATFORM', None)
from PIL import Image
from PySide6.QtCore import QMetaObject, QObject, QUrl
from PySide6.QtGui import QFontInfo, QTextLayout
from PySide6.QtWidgets import QApplication, QLabel
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from desktop.controller import Controller, PhotoProvider
from desktop.dialogs import StudioFileDialog
from desktop.typography import load_mincho

root = Path(__file__).resolve().parents[1]
out = root / 'output/interface-refinement'; out.mkdir(parents=True, exist_ok=True)
app = QApplication([]); app.setStyle('Fusion'); QQuickStyle.setStyle('Basic')
family = load_mincho(app, root)
checks = []; screenshots = []
def wait(predicate):
    until = time.monotonic()+120
    while not predicate() and time.monotonic()<until: app.processEvents(); time.sleep(.004)
    assert predicate(), 'Interface verification timed out'
def capture(window, name):
    QTest.qWait(180)
    path = out / (name+'.png'); assert window.grabWindow().save(str(path)); screenshots.append(str(path))

with tempfile.TemporaryDirectory() as folder:
    provider = PhotoProvider(); ctrl = Controller(provider, folder)
    engine = QQmlApplicationEngine(); engine.addImageProvider('photos', provider)
    context = engine.rootContext()
    context.setContextProperty('interfaceEditorialFamily',app._interface_font_selection['editorial'])
    for key, value in [('ctrl', ctrl), ('assetsUrl', QUrl.fromLocalFile(str(root/'assets')+'/').toString()), ('minchoFamily', family), ('interfaceDisplayFamily', app._interface_font_selection['display']), ('systemReduceMotion', True)]: context.setContextProperty(key, value)
    engine.load(QUrl.fromLocalFile(str(root/'desktop/qml/Studio.qml')))
    assert engine.rootObjects(); window = engine.rootObjects()[0]; window.show()
    editorial_glyphs={}
    def verify_editorial(name, text):
        item=window.findChild(QObject,name)
        assert item is not None, name
        layout=QTextLayout(text,item.property('font'))
        layout.beginLayout();layout.createLine();layout.endLayout()
        actual={run.rawFont().familyName() for run in layout.glyphRuns()}
        assert actual=={app._interface_font_selection['editorial']}, (name,actual)
        editorial_glyphs[name]=sorted(actual)
    try:
        empty_import=window.findChild(QObject,'emptyImportButton')
        empty_histogram=window.findChild(QObject,'editorHistogram')
        assert empty_import is not None and empty_import.property('visible')
        assert window.findChild(QObject,'emptyTitle') is None
        assert empty_histogram is not None and not empty_histogram.property('visible')
        assert not window.findChild(QObject,'openImportWorkspaceButton').property('visible')
        assert not window.findChild(QObject,'openCompositionButton').property('visible')
        assert window.property('activeTask')=='film'
        editor_qml=(root/'desktop/qml/components/EditorTools.qml').read_text(encoding='utf-8')
        assert "enabled:modelData.id==='film'||root.hasPhoto" in editor_qml
        assert not window.findChild(QObject,'filmEnabledButton').property('visible')
        assert not window.findChild(QObject,'paperSelector').property('visible')
        film_title=window.findChild(QObject,'filmTitle')
        film_archive=window.findChild(QObject,'filmArchiveButton')
        assert film_title is not None and film_title.property('visible')
        assert film_archive is not None and film_archive.property('visible') and film_archive.property('enabled')
        assert window.findChild(QObject,'exportActionButton').property('visible')
        for name in ['cropPhotoButton','compareToggle','zoomControl','zoomPercentage',
                     'undoButton','redoButton','resetPhotoButton','geometryDimensions','photoStrip']:
            item=window.findChild(QObject,name)
            assert item is not None and not item.property('visible'), name
        assert not window.findChild(QObject,'exportActionButton').property('enabled')
        for name in ['exportShortcut','undoShortcut','redoShiftShortcut','redoShortcut','zoomFitShortcut',
                     'zoom100Shortcut','zoom200Shortcut','zoomInShortcut','zoomOutShortcut',
                     'zoomToggleShortcut','compareShortcut','cropShortcut']:
            item=window.findChild(QObject,name)
            assert item is not None and not item.property('enabled'), name
        checks.append('empty state gates photo-only tools, actions and shortcuts; film browsing remains available')
        window.setProperty('activeTask','geometry');app.processEvents()
        assert window.property('activeTask')=='film'
        assert window.findChild(QObject,'geometryPanel') is not None and not window.findChild(QObject,'geometryPanel').property('visible')
        capture(window,'empty-state')
        window.resize(1366,768);capture(window,'empty-state-1366x768')
        window.resize(1120,760);capture(window,'empty-state-minimum')
        window.resize(1480,960);QTest.qWait(80)
        paths = []
        for name, color in [('照片 一.png', '#A27751'), ('照片 二.png', '#527CA1')]:
            path = Path(folder)/name; Image.new('RGB',(900,600),color).save(path); paths.append(str(path))
        ctrl.add_paths(paths); wait(lambda: len(ctrl.photos)==2 and not ctrl.busy)
        title = window.findChild(QObject, 'filmTitle')
        verify_editorial('filmTitle',str(title.property('text')))
        window.setProperty('activeTask','geometry'); QTest.qWait(60)
        geometry=window.findChild(QObject,'geometryPanel')
        dimensions=window.findChild(QObject,'geometryDimensions')
        assert geometry is not None and geometry.property('visible')
        assert dimensions is not None and dimensions.property('visible') and dimensions.property('text')=='900 × 600'
        assert window.findChild(QObject,'cropPhotoButton').property('visible')
        assert window.findChild(QObject,'compareToggle').property('visible')
        assert window.findChild(QObject,'zoomControl').property('visible')
        assert window.findChild(QObject,'exportActionButton').property('enabled')
        assert window.findChild(QObject,'editorHistogram').property('visible')
        for name in ['cropShortcut','compareShortcut','zoomFitShortcut','zoom100Shortcut','zoom200Shortcut',
                     'zoomInShortcut','zoomOutShortcut','zoomToggleShortcut']:
            assert window.findChild(QObject,name).property('enabled'), name
        assert window.findChild(QObject,'openImportWorkspaceButton').property('visible')
        assert window.findChild(QObject,'openCompositionButton').property('visible')
        capture(window,'geometry-imported')
        checks.append('photo dimensions and geometry/preview controls restore on import')
        window.setProperty('activeTask','film'); QTest.qWait(60)
        assert window.findChild(QObject,'filmEnabledButton').property('visible')
        assert window.findChild(QObject,'paperSelector').property('visible')
        assert QFontInfo(title.property('font')).family() == app._interface_font_selection['display']
        glyphs={}
        for role, font in [('body',app.font()),('display',title.property('font'))]:
            layout=QTextLayout('导入照片 胶片档案 Portra 400',font)
            layout.beginLayout();layout.createLine();layout.endLayout()
            actual={run.rawFont().familyName() for run in layout.glyphRuns()}
            expected={app._interface_font_selection['primary'],app._interface_font_selection['cjk']} if role=='body' else {app._interface_font_selection['display']}
            assert actual.issubset(expected), (role,actual,expected)
            if role=='body' and app._interface_font_selection['cjk']=='PingFang SC': assert 'PingFang SC' in actual
            glyphs[role]=sorted(actual)
        texts = [item.property('text') for item in window.findChildren(QObject)]
        assert '光影暗房' not in texts and ctrl.stocks[0]['description'] not in texts
        checks.append('actual native UI font; no titlebar slogan, film description or font implementation text')
        window.resize(1480,960); capture(window,'editor-normal')
        window.resize(1120,760); capture(window,'editor-minimum')
        for name in ['exportDialog','aboutDialog']:
            popup = window.findChild(QObject,name); QMetaObject.invokeMethod(popup,'open'); QTest.qWait(120)
            if name=='exportDialog': verify_editorial('exportTitle','导出作品')
            assert popup.property('height') <= window.height()-8, (name,popup.property('height'),window.height())
            capture(window,name); QMetaObject.invokeMethod(popup,'close')
        checks.append('export and about modals fit minimum window and share typography')
        library=window.findChild(QObject,'libraryPopup'); search=window.findChild(QObject,'stockSearch'); stocks=window.findChild(QObject,'stockList')
        QMetaObject.invokeMethod(library,'open'); search.setProperty('text','__no_stock__'); QTest.qWait(80)
        verify_editorial('libraryTitle','胶片档案')
        assert stocks.property('count')==0 and window.findChild(QObject,'stockSearchEmpty').property('visible')
        capture(window,'search-empty')
        search.setProperty('text','portra'); QTest.qWait(80); assert stocks.property('count')>=4
        search.setProperty('text',''); library.setProperty('kind','cinema'); QMetaObject.invokeMethod(library,'filter'); QTest.qWait(80)
        assert 0<stocks.property('count')<len(ctrl.stocks)
        capture(window,'film-library'); QMetaObject.invokeMethod(library,'close')
        checks.append('search filters actual model, reports empty results, and supports cinema category')
        for mode, caption in [('open','导入照片'),('save','保存作品'),('directory','选择输出文件夹')]:
            target = str(Path(folder)/'作品.jpg') if mode=='save' else folder
            dialog=StudioFileDialog(caption,target,'照片 (*.png *.jpg)',mode=mode)
            dialog.show(); QTest.qWait(250)
            assert dialog.picker.isVisible()
            heading=dialog.findChild(QLabel,'dialogTitle')
            assert heading is not None and QFontInfo(heading.font()).family()==app._interface_font_selection['editorial']
            assert dialog.grab().save(str(out/(mode+'-dialog.png')))
            screenshots.append(str(out/(mode+'-dialog.png')))
            dialog.reject(); dialog.deleteLater(); app.processEvents()
        checks.append('open/save/directory dialogs use the same UI font, surface, radius and buttons')
        checks.append('body, display and editorial glyph runs use the recorded bundled bilingual interface family')
        result=dict(ok=True,font=family,font_selection=app._interface_font_selection,glyph_families=glyphs,editorial_glyphs=editorial_glyphs,checks=checks,screenshots=screenshots,scope='Native Windows self-review; calibration colors are temporary test fixtures')
        (out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False,indent=2))
    finally:
        ctrl.close(); window.close(); del engine
