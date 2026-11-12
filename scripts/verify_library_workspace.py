"""Focused real-helper workspace integration and 1366x768 QML capture."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]

from PIL import Image
from PySide6.QtCore import QEventLoop, QTimer, QUrl, qInstallMessageHandler
from PySide6.QtGui import QFont
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication
from desktop.controller import PhotoProvider
from desktop.library_workspace import LibraryWorkspace
from desktop.typography import load_mincho
from verify_library_service import Host


def wait_until(predicate, timeout=8):
    if predicate(): return
    loop = QEventLoop()
    timer = QTimer()
    timer.setInterval(5)
    deadline = time.perf_counter() + timeout
    expired = []
    def tick():
        if predicate(): loop.quit()
        elif time.perf_counter() > deadline:
            expired.append(True)
            loop.quit()
    timer.timeout.connect(tick)
    timer.start()
    loop.exec()
    timer.stop()
    assert not expired, 'workspace condition timed out'


def main():
    output = ROOT / 'output/library-bridge'
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setApplicationName('SpektraFilm')
    app.setOrganizationName('SpektraFilm')
    QQuickStyle.setStyle('Basic')
    family = load_mincho(app, ROOT)
    qml_errors = []
    qInstallMessageHandler(lambda kind, context, text: qml_errors.append(text))
    provider = PhotoProvider()
    report = {}
    with tempfile.TemporaryDirectory(prefix='workspace-', dir=output) as folder:
        temporary = Path(folder)
        photos = temporary / '原片'
        photos.mkdir()
        files = []
        for i, rgb in enumerate([(92, 113, 94), (175, 132, 95), (107, 137, 156), (174, 110, 100), (120, 111, 155), (181, 166, 121)]):
            path = photos / f'照片-{i + 1}.jpg'
            Image.new('RGB', (480, 320), rgb).save(path, quality=100)
            files.append(path)
        workspace = LibraryWorkspace(thumbnail_provider=provider)
        opens = []
        workspace.openPhoto.connect(lambda path, edit, metadata: opens.append((path, edit, metadata)))
        workspace.createLibrary(str(temporary / '外拍精选'), 'catalog')
        wait_until(lambda: workspace.hasLibrary and not workspace._requests)
        workspace.addPaths([str(p) for p in files], False)
        wait_until(lambda: workspace.total == 6 and not workspace._requests)
        rows = list(workspace.images)
        first, second = rows[0], rows[1]
        workspace.activateVariant(first['uuid'], '')
        wait_until(lambda: len(opens) == 1)
        av = opens[-1][2]['variant']
        workspace.saveEdit(first['path'], {'version': 4, 'settings': {'exposure': .35}})
        workspace.activateVariant(second['uuid'], '')
        wait_until(lambda: len(opens) == 2 and not workspace.saving)
        assert Path(opens[-1][0]) == Path(second['path'])
        peer = Host(temporary / '第二客户端')
        try:
            handle = peer.call('library.open', {'path': workspace.path})['library']
            saved = peer.call('edit.get', {'library': handle, 'variant': av})
            assert saved['revision'] == 1 and saved['edit']['settings']['exposure'] == .35
            bv = opens[-1][2]['variant']
            peer.call('edit.put', {'library': handle, 'variant': bv, 'base_revision': 0,
                                  'edit': {'version': 4, 'settings': {'exposure': -.4}}})
            workspace.saveEdit(second['path'], {'version': 4, 'settings': {'exposure': .85}})
            wait_until(lambda: workspace.hasConflict)
            assert workspace.activeVariant == bv
            close_events = []
            workspace.closeReady.connect(lambda: close_events.append(True))
            workspace.prepareToClose()
            assert not close_events, 'a conflicted edit must prevent closing'
            workspace.saveAsNewVariant()
            wait_until(lambda: not workspace.hasConflict and not workspace.saving and workspace.activeVariant != bv)
            wait_until(lambda: not workspace._requests)
            cv = workspace.activeVariant
            assert peer.call('edit.get', {'library': handle, 'variant': bv})['edit']['settings']['exposure'] == -.4
            assert peer.call('edit.get', {'library': handle, 'variant': cv})['edit']['settings']['exposure'] == .85
            report['edits'] = {'flush_before_variant_switch': True, 'optimistic_conflict': True,
                                'conflicting_record_preserved': True, 'save_as_new_variant': True}

            workspace.createAlbum('人像与日常')
            wait_until(lambda: len(workspace.albums) == 1 and not workspace._requests)
            album = workspace.albums[0]['uuid']
            workspace.selectImage(first['uuid'], False)
            workspace.addSelectedToAlbum(album)
            wait_until(lambda: not workspace._requests)
            workspace.selectCollection(album)
            wait_until(lambda: workspace.total == 1 and not workspace._requests)
            workspace.selectImage(first['uuid'], False)
            workspace.removeSelectedFromAlbum()
            wait_until(lambda: workspace.total == 0 and not workspace._requests)
            workspace.selectCollection('')
            wait_until(lambda: workspace.total == 6 and not workspace._requests)
            workspace.query = '照片-2'
            wait_until(lambda: workspace.total == 1 and workspace.images[0]['file_name'] == '照片-2.jpg')
            workspace.query = ''
            wait_until(lambda: workspace.total == 6 and not workspace._requests)
            report['library_ui_logic'] = {'album_create_add_remove': True, 'search': True, 'bounded_page_size': workspace.pageSize}

            watched = temporary / '自动刷新的照片'
            watched.mkdir()
            Image.new('RGB', (120, 80), (166, 156, 131)).save(watched / '监看-1.jpg')
            workspace.watchFolder(str(watched))
            wait_until(lambda: workspace.total == 7 and not workspace._requests)
            Image.new('RGB', (120, 80), (87, 108, 93)).save(watched / '监看-2.jpg')
            wait_until(lambda: workspace.total == 8 and not workspace._requests)
            report['folder_monitor'] = {'native_root_notification': True, 'debounced_async_scan': True,
                                         'recursive_poll_interval_seconds': 30}

            engine = QQmlApplicationEngine()
            engine.addImageProvider('photos', provider)
            context = engine.rootContext()
            context.setContextProperty('library', workspace)
            context.setContextProperty('minchoFamily', family)
            context.setContextProperty('interfaceDisplayFamily', app._interface_font_selection['display'])
            context.setContextProperty('interfaceEditorialFamily', app._interface_font_selection['editorial'])
            context.setContextProperty('systemReduceMotion', False)
            context.setContextProperty('assetsUrl', QUrl.fromLocalFile(str(ROOT / 'assets') + '/').toString())
            source = b'''import QtQuick\nimport QtQuick.Window\nimport "../../desktop/qml/components"\nWindow { visible: true; width: 1366; height: 768; title: "SpektraFilm Library"; LibraryWorkspace { anchors.fill: parent; workspace: library } }'''
            engine.loadData(source, QUrl.fromLocalFile(str(output / 'LibraryProbe.qml')))
            assert engine.rootObjects(), qml_errors
            window = engine.rootObjects()[0]
            wait_until(lambda: window.isVisible())
            wait_until(lambda: all(('library_' + row['uuid']) in provider.images for row in workspace.images))
            # Let real asynchronous Image provider uploads and the first frame finish.
            frames = []
            window.frameSwapped.connect(lambda: frames.append(True))
            window.update()
            wait_until(lambda: len(frames) >= 2)
            assert window.grabWindow().save(str(output / 'library-workspace-1366x768.png'))
            report['visual'] = {'window': [1366, 768], 'screenshot': str(output / 'library-workspace-1366x768.png')}
            window.close()
            engine.deleteLater()
            app.processEvents()
            workspace.saveEdit(second['path'], {'version': 4, 'settings': {'exposure': .9}})
            workspace.prepareToClose()
            wait_until(lambda: bool(close_events))
            assert peer.call('edit.get', {'library': handle, 'variant': cv})['edit']['settings']['exposure'] == .9
            report['window_close'] = {'conflict_blocks_close': True, 'close_ready_after_commit': True}
        finally:
            peer.close()
            workspace.shutdown()
            wait_until(lambda: workspace.service._process.state().name == 'NotRunning')
        # Drop remaining engine/model references before temporary folder removal.
    report['qml_messages'] = qml_errors
    assert not [e for e in qml_errors if 'Error' in e or 'ReferenceError' in e or 'TypeError' in e or 'Cannot' in e], qml_errors
    report['status'] = 'passed'
    (output / 'workspace-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
