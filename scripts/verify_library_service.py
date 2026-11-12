"""One focused, small-library Windows SDK/async-transport integration milestone.

Uses synthetic photo/header/database fixtures only. No RAW decode, rendering,
network, proprietary adjustments or hash manifest is involved.
"""
from __future__ import annotations

import json
from pathlib import Path
import queue
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
HELPER = ROOT / 'native/library/runtime/spklib-host.exe'


class Host:
    def __init__(self, store):
        self.proc = subprocess.Popen([str(HELPER), '--store', str(store)], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True, encoding='utf-8')
        self.queue = queue.Queue()
        self.reader = threading.Thread(target=lambda: [self.queue.put(line) for line in self.proc.stdout], daemon=True)
        self.reader.start()
        self.ready = json.loads(self.queue.get(timeout=5))
        assert self.ready['event'] == 'ready' and self.ready['protocol'] == 1
        self.rid = 0

    def call(self, method, params=None, error=None):
        self.rid += 1
        self.proc.stdin.write(json.dumps({'id': self.rid, 'method': method, 'params': params or {}}, ensure_ascii=False) + '\n')
        self.proc.stdin.flush()
        reply = json.loads(self.queue.get(timeout=8))
        assert reply['id'] == self.rid, reply
        if error:
            assert reply.get('error', {}).get('code') == error, reply
            return reply['error']
        assert 'error' not in reply, reply
        return reply['result']

    def close(self):
        if self.proc.poll() is None:
            self.call('host.shutdown')
            self.proc.wait(timeout=5)
        assert self.proc.returncode == 0


def make_c1_fixture(root):
    package = root / '只读来源 # %.cocatalog'
    package.mkdir()
    photos = root / 'C1 照片'
    photos.mkdir()
    photo = photos / '照片.ARW'
    photo.write_bytes(b'synthetic-c1-source-header')
    database = package / '只读来源 # %.cocatalogdb'
    with sqlite3.connect(database) as db:
        db.executescript((ROOT / 'native/library/tests/fixtures/capture_one_16_8_schema.sql').read_text(encoding='utf-8'))
        db.execute("INSERT INTO ZVERSIONINFO VALUES (32,1,'16.8 Pro Win','16.8 Win',160800,'16.8 Pro Win',160800)")
        db.execute("INSERT INTO ZDOCUMENTCONTENT (Z_ENT,Z_PK,ZDOCUMENTTYPE,ZDOCUMENTUUID,ZROOTCOLLECTION) VALUES (34,1,1,'FIXTURE-DOCUMENT',1)")
        anchor = Path(photos.anchor)
        db.execute('INSERT INTO ZPATHLOCATION (Z_ENT,Z_PK,ZMACROOT,ZWINROOT,ZRELATIVEPATH,ZISRELATIVE,ZVOLUME) VALUES (38,1,?,?,?,0,?)',
                   ('/Volumes/Unavailable', photos.anchor, str(photos.relative_to(anchor)), photos.anchor))
        db.execute("INSERT INTO ZIMAGE (Z_ENT,Z_PK,ZIMAGEUUID,ZIMAGEFILENAME,ZIMAGELOCATION,ZISINSIDECATALOG,ZISTRASHED,ZIMAGECLASSIFICATION,ZWIDTH,ZHEIGHT) VALUES (12,1,'FIXTURE-IMAGE',?,1,0,0,17,9504,6336)", (photo.name,))
        db.execute("INSERT INTO ZVARIANT (Z_ENT,Z_PK,ZINDEX,ZVARIANTUUID,ZIMAGE,ZCOMBINEDSETTINGS,ZISMODIFIED) VALUES (15,1,127,'FIXTURE-VARIANT',1,101,0)")
        db.execute('INSERT INTO ZVARIANTLAYER (Z_ENT,Z_PK,ZVARIANT,ZROTATION,ZFLIP) VALUES (20,101,1,0,0)')
        db.execute("INSERT INTO ZVARIANTMETADATA (Z_ENT,Z_PK,ZLAYER,ZBASIC_RATING,ZCOLOR_TAG_INDEX,ZCONTENT_KEYWORDS) VALUES (13,101,101,3,2,'portrait; daylight')")
        db.execute("INSERT INTO ZCOLLECTION (Z_ENT,Z_PK,ZUUID,ZNAME,ZPARENT,ZCOLLECTIONINDEX,ZALLIMAGESCOLLECTION) VALUES (7,1,'FIXTURE-ROOT','root',NULL,0,2)")
        db.execute("INSERT INTO ZCOLLECTION (Z_ENT,Z_PK,ZUUID,ZNAME,ZPARENT,ZCOLLECTIONINDEX) VALUES (40,2,'FIXTURE-ALL','All',1,1),(2,3,'FIXTURE-ALBUM','选择',1,2)")
        db.execute('INSERT INTO ZIMAGEINCOLLECTION (Z_ENT,Z_PK,ZCOLLECTION,ZIMAGE) VALUES (47,1,3,1)')
    db.close()
    return package, database, photo


def verify_native(root, report):
    first = Host(root / '主目录')
    second = Host(root / '第二个客户端')
    try:
        methods = first.call('sdk.methods')['methods']
        assert len(methods) >= 40
        report['methods'] = len(methods)
        report['sdk'] = first.call('sdk.version')
        photos = root / '照片 # %'
        photos.mkdir()
        files = [photos / '甲.ARW', photos / '乙.NEF']
        for p in files:
            p.write_bytes(b'fixture-image-header-' + p.stem.encode('utf-8'))
        before = {p: p.read_bytes() for p in files}
        library = first.call('library.create', {'path': str(root / '中文资料库'), 'kind': 'catalog', 'name': '中文资料库'})
        handle = library['library']
        libpath = library['info']['path']
        add = first.call('images.add', {'library': handle, 'items': [str(p) for p in files], 'mode': 'reference'})
        assert add['added'] == 2
        image, variant = add['results'][0]['image'], add['results'][0]['variant']
        listed = first.call('images.list', {'library': handle, 'check_files': True, 'full': True})
        assert listed['total'] == 2 and all(p['exists'] for p in listed['images'])
        album = first.call('collection.create', {'library': handle, 'kind': 'album', 'name': '精选'})['collection']
        assert first.call('collection.add', {'library': handle, 'collection': album, 'images': [image]})['added'] == 1
        assert first.call('images.list', {'library': handle, 'collection': album})['total'] == 1
        first.call('meta.set', {'library': handle, 'variants': [variant], 'rating': 4, 'color_tag': 2})
        first.call('images.describe', {'library': handle, 'items': [{'image': image, 'metadata': {'width': 9504, 'height': 6336, 'camera_model': 'Synthetic A7CR'}}]})
        assert first.call('edit.put', {'library': handle, 'variant': variant, 'base_revision': 0, 'edit': {'exposure': .3}})['revision'] == 1
        client2 = second.call('library.open', {'path': libpath})['library']
        assert second.call('edit.put', {'library': client2, 'variant': variant, 'base_revision': 1, 'edit': {'exposure': .6}})['revision'] == 2
        conflict = first.call('edit.put', {'library': handle, 'variant': variant, 'base_revision': 1, 'edit': {'exposure': -.3}}, error='conflict')
        assert conflict['data']['revision'] == 2
        assert first.call('edit.get', {'library': handle, 'variant': variant})['edit']['exposure'] == .6
        variant2 = first.call('variant.create', {'library': handle, 'image': image, 'from_variant': variant})
        assert variant2['edit_copied'] and first.call('edit.get', {'library': handle, 'variant': variant2['variant']})['edit'] == {'exposure': .6}
        second.call('library.close', {'library': client2})
        first.call('library.close', {'library': handle})
        handle = first.call('library.open', {'path': libpath})['library']
        reopened = first.call('images.list', {'library': handle, 'check_files': True})
        assert all(p['exists'] for p in reopened['images']), reopened
        assert {Path(p['path']) for p in reopened['images']} == set(files)
        first.call('library.close', {'library': handle})
        with sqlite3.connect(Path(libpath) / 'Library.spkdb') as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        db.close()
        assert all(p.read_bytes() == content for p, content in before.items())
        report['catalog'] = {'unicode_paths': True, 'reopened_drive_paths': True, 'album_membership': True,
                             'variants': True, 'metadata_and_tags': True, 'revision_conflict': True,
                             'source_bytes_unchanged': True, 'integrity_check': 'ok'}

        session = first.call('library.create', {'path': str(root / '拍摄会话'), 'kind': 'session'})
        sh = session['library']
        session_path = Path(session['info']['path'])
        source = session_path / 'Capture/原片.ARW'
        source.write_bytes(b'original-session-photo')
        first.call('session.scan', {'library': sh})
        images = first.call('images.list', {'library': sh})['images']
        assert len(images) == 1
        sid = images[0]['uuid']
        second.call('library.open', {'path': str(session_path)}, error='in_use')
        (session_path / 'Selects/原片.ARW').write_bytes(b'existing-photo')
        collision = first.call('session.move', {'library': sh, 'images': [sid], 'to': 'selects', 'on_conflict': 'fail'})
        assert collision['conflicts'] and source.is_file()
        moved = first.call('session.move', {'library': sh, 'images': [sid], 'to': 'selects', 'on_conflict': 'suffix'})
        target = Path(moved['moved'][0]['to'])
        assert not source.exists() and target.read_bytes() == b'original-session-photo'
        assert (session_path / 'Selects/原片.ARW').read_bytes() == b'existing-photo'
        restored = first.call('session.restore', {'library': sh, 'images': [sid]})
        assert restored['moved'] and Path(restored['moved'][0]['to']).read_bytes() == b'original-session-photo'
        assert Path(restored['moved'][0]['to']).parent == source.parent
        first.call('library.close', {'library': sh})
        report['session'] = {'exclusive_writer': True, 'scan': True, 'never_overwrites': True, 'suffix_move': True, 'restore': True}

        package, database, photo = make_c1_fixture(root)
        source_bytes, source_stat = database.read_bytes(), database.stat()
        source_entries = list(package.iterdir())
        database.chmod(stat.S_IREAD)
        try:
            probe = first.call('capture_one.probe', {'path': str(package)})
            assert probe['supported'] and probe['counts']['images'] == 1, probe
            link = first.call('capture_one.link', {'source': str(package), 'path': str(root / '只读镜像')})
            linked = first.call('images.list', {'library': link['library'], 'check_files': True})
            assert linked['images'][0]['exists'] and Path(linked['images'][0]['path']) == photo, linked
            first.call('collection.update', {'library': link['library'], 'collection': 'FIXTURE-ALBUM', 'name': '不能修改'}, error='read_only')
            copy = first.call('capture_one.copy', {'source': str(package), 'path': str(root / '独立副本')})
            copied = first.call('images.list', {'library': copy['library'], 'check_files': True})
            assert copied['images'][0]['exists'] and copied['images'][0]['rating'] == 3
            assert first.call('capture_one.update', {'library': copy['library']})['skipped']
            assert database.read_bytes() == source_bytes and database.stat().st_mtime_ns == source_stat.st_mtime_ns
            assert list(package.iterdir()) == source_entries
            first.call('library.close', {'library': link['library']})
            first.call('library.close', {'library': copy['library']})
            journal = Path(str(database) + '-journal')
            journal.write_bytes(b'synthetic-open-write')
            first.call('capture_one.probe', {'path': str(package)}, error='source_busy')
            journal.unlink()
        finally:
            database.chmod(stat.S_IREAD | stat.S_IWRITE)
        report['capture_one_fixture'] = {'schema': 'upstream 16.8 fixture', 'windows_root': True,
                                         'read_only_probe_link_copy': True, 'unchanged_bytes_and_mtime': True,
                                         'no_source_journals_created': True, 'hot_journal_refused': True,
                                         'proprietary_adjustments_imported': False}
    finally:
        first.close()
        second.close()


def verify_qprocess(root, report):
    from PySide6.QtCore import QCoreApplication, QTimer
    from desktop.library_service import LibraryService
    app = QCoreApplication.instance() or QCoreApplication([])
    service = LibraryService(store=root / '异步目录')
    errors, results, ticks = [], {}, []
    heartbeat = QTimer()
    heartbeat.setInterval(1)
    heartbeat.timeout.connect(lambda: ticks.append(time.perf_counter()))
    heartbeat.start()
    watchdog = QTimer()
    watchdog.setSingleShot(True)
    watchdog.timeout.connect(lambda: (errors.append('timeout'), service.close(), app.quit()))
    watchdog.start(8000)

    def result(rid, method, payload):
        results[method] = payload
        if method == 'library.create':
            service.call('library.info', {'library': payload['library']})
        elif method == 'library.info':
            service.close()

    service.result.connect(result)
    service.failed.connect(lambda rid, method, error: errors.append((method, error)))
    service.stopped.connect(app.quit)
    begin = time.perf_counter()
    service.call('sdk.version')
    service.call('library.create', {'path': str(root / '异步资料库'), 'kind': 'catalog'})
    app.exec()
    elapsed = time.perf_counter() - begin
    heartbeat.stop()
    watchdog.stop()
    assert not errors, errors
    assert set(results) == {'sdk.version', 'library.create', 'library.info'}
    assert len(ticks) > 1
    report['qprocess_bridge'] = {'queued_before_ready': True, 'asynchronous_results': len(results),
                                 'ui_heartbeat_ticks': len(ticks), 'elapsed_ms': round(elapsed * 1000, 1),
                                 'graceful_shutdown': True}


def main():
    output = ROOT / 'output/library-bridge'
    output.mkdir(parents=True, exist_ok=True)
    report = {}
    begin = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='critical-', dir=output) as temporary:
        root = Path(temporary)
        verify_native(root, report)
        verify_qprocess(root, report)
    report['total_seconds'] = round(time.perf_counter() - begin, 2)
    report['status'] = 'passed'
    (output / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
