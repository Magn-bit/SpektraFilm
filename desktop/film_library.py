"""Visible-first film auditions and independent, transferable darkroom looks.

The scheduler retains one bounded source proxy and at most twelve card images.
It does not use the controller's mutable rendering caches or global cancellation.
"""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import tempfile
import uuid

from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer, QThreadPool, QRunnable, QAbstractListModel, QModelIndex, Qt
from PySide6.QtGui import QImage

from shared.settings_sync import DEFAULT_CATEGORIES, CATEGORY_TITLES, make_clip, normalize_clip
from .imaging import Settings, catalog, read_photo, prepare_photo_source, render


class PresetStore:
    """Atomic JSON edits preserve fields written by a newer compatible reader."""
    def __init__(self, path):
        self.path = Path(path)
        self.document = {'format': 'SpektraFilm.look-presets', 'version': 1, 'presets': []}
        self.error = ''
        self.can_write = True
        self.deleted = []
        if not self.path.exists():
            return
        try:
            value = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(value, dict) or value.get('format') != self.document['format'] or value.get('version') != 1:
                raise ValueError('预设文件版本不受支持，已保持只读')
            if not isinstance(value.get('presets'), list):
                raise ValueError('预设文件内容不完整，已保持只读')
            seen = set()
            for entry in value['presets']:
                if not isinstance(entry, dict) or not isinstance(entry.get('id'), str) or not entry['id'] or entry['id'] in seen:
                    raise ValueError('预设文件记录无效，已保持只读')
                self._name(entry.get('name'))
                normalize_clip(entry.get('clip'))
                seen.add(entry['id'])
            self.document = value
        except (OSError, ValueError, TypeError) as error:
            self.error = str(error)
            self.can_write = False

    @property
    def entries(self):
        return self.document['presets']

    def _name(self, name, except_id=None):
        if not isinstance(name, str) or not name.strip():
            raise ValueError('请填写预设名称')
        name = name.strip()
        if len(name) > 80:
            raise ValueError('预设名称最多80个字')
        if any(item['id'] != except_id and item['name'].casefold() == name.casefold() for item in self.entries):
            raise ValueError('已有同名预设')
        return name

    def _commit(self, document):
        if not self.can_write:
            raise ValueError(self.error or '预设文件为只读')
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=self.path.parent,
                                             prefix=self.path.name + '.', suffix='.tmp', delete=False) as output:
                temporary = output.name
                json.dump(document, output, ensure_ascii=False, indent=2, allow_nan=False)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary and Path(temporary).exists():
                Path(temporary).unlink()
        self.document = document
        self.error = ''

    def save(self, name, clip):
        name = self._name(name)
        clip = normalize_clip(clip)
        if not clip['settings']:
            raise ValueError('请选择要保存的调整分类')
        document = deepcopy(self.document)
        ident = str(uuid.uuid4())
        document['presets'].append(dict(id=ident, name=name, clip=clip))
        self._commit(document)
        return ident

    def rename(self, ident, name):
        name = self._name(name, ident)
        document = deepcopy(self.document)
        entry = next((item for item in document['presets'] if item['id'] == ident), None)
        if entry is None:
            raise ValueError('预设已不存在')
        entry['name'] = name
        self._commit(document)

    def delete(self, ident):
        document = deepcopy(self.document)
        index = next((i for i, item in enumerate(document['presets']) if item['id'] == ident), -1)
        if index < 0:
            raise ValueError('预设已不存在')
        entry = document['presets'].pop(index)
        self._commit(document)
        self.deleted.append((index, entry))
        self.deleted = self.deleted[-16:]

    def restore(self):
        if not self.deleted:
            return
        index, entry = self.deleted[-1]
        self._name(entry['name'])
        document = deepcopy(self.document)
        document['presets'].insert(min(index, len(document['presets'])), deepcopy(entry))
        self._commit(document)
        self.deleted.pop()


class _Films(QAbstractListModel):
    def __init__(self, parent):
        super().__init__(parent)
        self.rows = []

    def roleNames(self):
        return {Qt.UserRole + 1: b'entry'}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role):
        return self.rows[index.row()] if index.isValid() and role == Qt.UserRole + 1 else None

    def reset(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def update(self, ident, **values):
        for i, row in enumerate(self.rows):
            if row['id'] == ident:
                changed = dict(row, **values)
                if changed != row:
                    self.rows[i] = changed
                    index = self.index(i, 0)
                    self.dataChanged.emit(index, index, [Qt.UserRole + 1])
                return


class _Work(QRunnable):
    def __init__(self, owner, function):
        super().__init__()
        self.owner, self.function = owner, function

    def run(self):
        try:
            self.owner.completed.emit((True, self.function()))
        except Exception as error:
            self.owner.completed.emit((False, str(error)))


class FilmLibrary(QObject):
    changed = Signal()
    accepted = Signal()
    completed = Signal(object)
    PROXY_EDGE = 640
    CARD_EDGE = 360
    CACHE_IMAGES = 12
    CACHE_BYTES = 12 * 1024**2

    def __init__(self, controller, store_path=None):
        super().__init__(controller)
        self.ctrl = controller
        self.store = PresetStore(store_path or controller._store.parent / 'look-presets.json')
        self.model = _Films(self)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.timer = QTimer(self)
        self.timer.setInterval(120)
        self.timer.timeout.connect(self._schedule)
        self.completed.connect(self._completed)
        controller.stateChanged.connect(self._refresh)
        self._active = self._closed = self._in_flight = False
        self._generation = 0
        self._snapshot = None
        self._identity = None
        self._source_identity = None
        self._source = None
        self._filter = ('', '', '')
        self._visible = []
        self._images = OrderedDict()
        self._serial = 0
        self._error = ''
        self._jobs = self._completed_jobs = 0
        self._flight_context = None
        self._all = [dict(item) for item in catalog()]
        self._refilter()

    @Property(QObject, constant=True)
    def films(self): return self.model

    @Property('QVariantList', notify=changed)
    def makers(self): return sorted({item.get('maker', '') for item in self._all})

    @Property('QVariantList', notify=changed)
    def presets(self):
        return [dict(id=item['id'], name=item['name'], categories=normalize_clip(item['clip'])['categories']) for item in self.store.entries]

    @Property('QVariantList', constant=True)
    def categories(self):
        return [dict(id=key, name=CATEGORY_TITLES[key], selected=key in DEFAULT_CATEGORIES)
                for key in ('materials', 'exposure', 'WB', 'film_effects', 'print_effects', 'scene_placement', 'basic', 'color', 'masks', 'geometry')]

    @Property(bool, notify=changed)
    def hasPhoto(self): return not self._closed and self.ctrl._current >= 0

    @Property(int, notify=changed)
    def selectedCount(self): return 0 if self._closed else self.ctrl.selectedCount

    @Property(bool, notify=changed)
    def canWrite(self): return self.store.can_write

    @Property(bool, notify=changed)
    def canRestore(self): return self.store.can_write and bool(self.store.deleted)

    @Property(str, notify=changed)
    def error(self): return self._error or self.store.error

    @Property('QVariantMap', notify=changed)
    def diagnostics(self):
        return dict(cached=len(self._images), bytes=sum(image.sizeInBytes() for _, image in self._images.values()),
                    source_count=int(self._source is not None), active=self._active, in_flight=self._in_flight,
                    jobs=self._jobs, completed=self._completed_jobs, generation=self._generation)

    @Slot()
    def activate(self):
        self._active = True
        self._refresh()
        self.timer.start()

    @Slot()
    def deactivate(self):
        self._active = False
        self._generation += 1
        self.timer.stop()
        self._source = None
        self._source_identity = None
        # An in-flight proxy belongs only to its worker until it completes.

    @Slot(str, str, str)
    def setFilters(self, search, maker, kind):
        value = (search.strip().casefold(), maker, kind)
        if value != self._filter:
            self._filter = value
            self._refilter()

    def _refilter(self):
        search, maker, kind = self._filter
        selected = self.ctrl._settings.stock
        old = {item['id']: item for item in self.model.rows}
        rows = []
        for item in self._all:
            if maker and item.get('maker') != maker: continue
            if kind and item.get('category', item.get('type')) != kind: continue
            if search and search not in ' '.join(str(item.get(key, '')) for key in ('id', 'name', 'maker')).casefold(): continue
            previous = old.get(item['id'], {})
            rows.append(dict(item, url=previous.get('url', ''), loading=False, error='', selected=item['id'] == selected))
        self.model.reset(rows)
        self._visible = []
        self.changed.emit()

    @Slot(int, int)
    def setVisibleRange(self, first, last):
        first = max(0, first)
        self._visible = [item['id'] for item in self.model.rows[first:min(len(self.model.rows), last + 1, first + self.CACHE_IMAGES)]]
        for row in self.model.rows:
            if row['id'] not in self._visible and row['loading']:
                self.model.update(row['id'], loading=False)
        if self._active:
            self._schedule()

    def _refresh(self):
        selected = self.ctrl._settings.stock
        for row in self.model.rows:
            self.model.update(row['id'], selected=row['id'] == selected)
        if not self._active:
            self.changed.emit()
            return
        try:
            path = self.ctrl.currentPath
            stat = Path(path).stat() if path else None
            source_identity = (str(Path(path).resolve()), stat.st_size, stat.st_mtime_ns) if stat else None
            settings = self.ctrl._settings
            identity = (source_identity, json.dumps(asdict(settings), sort_keys=True, separators=(',', ':'), allow_nan=False))
        except (OSError, ValueError, TypeError) as error:
            self._error = str(error)
            self.changed.emit()
            return
        if identity != self._identity or source_identity != self._source_identity:
            source_changed = source_identity != self._source_identity
            self._generation += 1
            self._identity, self._snapshot = identity, settings
            self._error = ''
            if source_changed:
                self._source = None
                self._source_identity = source_identity
            for row in self.model.rows:
                self.model.update(row['id'], loading=False, error='', **({'url': ''} if source_changed else {}))
        self.changed.emit()

    def _card_settings(self, ident):
        return replace(self._snapshot, stock=ident, film_enabled=True, minilab_active=False)

    def _card_key(self, ident):
        # The complete immutable settings document includes WB, geometry,
        # source decode, every effect, the chosen stock and its target paper.
        return ('film-card.1/native-current', self._source_identity,
                json.dumps(asdict(self._card_settings(ident)), sort_keys=True, separators=(',', ':'), allow_nan=False))

    def _schedule(self):
        if self._closed or not self._active or self._in_flight or not self.hasPhoto or self._snapshot is None:
            return
        if self.ctrl.busy or self.ctrl.exporting:
            return
        for ident in self._visible:
            row = next((item for item in self.model.rows if item['id'] == ident), None)
            if row is None or row['error']: continue
            key = self._card_key(ident)
            if key in self._images:
                name, _ = self._images[key]
                self._images.move_to_end(key)
                self.model.update(ident, url='image://photos/' + name, loading=False)
                continue
            token, source_identity, settings = self._generation, self._source_identity, self._card_settings(ident)
            source = self._source
            path = self.ctrl.currentPath
            self._in_flight = True
            self._flight_context = (token, ident)
            self._jobs += 1
            self.model.update(ident, loading=True)
            self.changed.emit()

            def work():
                from .raw_source import source_pixels, source_metadata, display_image
                proxy = source
                if not self._active or token != self._generation or ident not in self._visible:
                    return token, ident, key, proxy, None
                if proxy is None:
                    loaded = read_photo(path, self.PROXY_EDGE)
                    proxy = display_image(source_pixels(loaded).copy(), full_size=loaded.info.get('source_size', loaded.size),
                                          metadata=source_metadata(loaded), token=('film-library', source_identity))
                if not self._active or token != self._generation or ident not in self._visible:
                    return token, ident, key, proxy, None
                # Stock rendering caches live on this private proxy, never on
                # the foreground controller's PIL source.
                prepared, _ = prepare_photo_source(proxy, path, settings)
                picture = render(prepared, settings, preview=True)
                picture.thumbnail((self.CARD_EDGE, self.CARD_EDGE), Image.Resampling.LANCZOS)
                image = QImage(ImageQt(picture)).copy()
                return token, ident, key, proxy, image

            self.pool.start(_Work(self, work))
            return

    @Slot(object)
    def _completed(self, result):
        self._in_flight = False
        context, self._flight_context = self._flight_context, None
        ok, payload = result
        if self._closed:
            return
        if not ok:
            # Do not spin forever on one material or poison later generations.
            if self._active and context and context[0] == self._generation:
                self.model.update(context[1], loading=False, error=payload)
            self.changed.emit()
            return
        token, ident, key, source, image = payload
        if self._active and key[1] == self._source_identity:
            self._source = source
        if self._active and token == self._generation and ident in self._visible and image is not None:
            self._serial += 1
            name = 'film-audition-' + str(self._serial)
            self.ctrl.provider.publish(name, image)
            self._images[key] = (name, image)
            while len(self._images) > self.CACHE_IMAGES or sum(frame.sizeInBytes() for _, frame in self._images.values()) > self.CACHE_BYTES:
                _, (evicted, _) = self._images.popitem(last=False)
                self.ctrl.provider.discard(evicted)
                for row in self.model.rows:
                    if row['url'] == 'image://photos/' + evicted:
                        self.model.update(row['id'], url='')
            self.model.update(ident, url='image://photos/' + name, loading=False, error='')
            self._completed_jobs += 1
        else:
            self.model.update(ident, loading=False)
        self.changed.emit()
        if self._active:
            QTimer.singleShot(0, self._schedule)

    @Slot()
    def retry(self):
        for row in self.model.rows:
            self.model.update(row['id'], error='', loading=False)
        self._error = ''
        self._schedule()

    @Slot(str)
    def pickFilm(self, ident):
        if self.hasPhoto and not self.ctrl.exporting:
            self.ctrl.chooseFilm(ident)
            self.accepted.emit()

    def _store_action(self, action):
        try:
            value = action()
            self._error = ''
            self.changed.emit()
            return value if value is not None else True
        except (OSError, ValueError, TypeError) as error:
            self._error = str(error)
            self.changed.emit()
            return False

    @Slot(str, 'QVariantList', result=bool)
    def savePreset(self, name, categories):
        if not self.hasPhoto or self.ctrl.exporting:
            return False
        return bool(self._store_action(lambda: self.store.save(name, make_clip(self.ctrl._settings, categories))))

    @Slot(str, str, result=bool)
    def renamePreset(self, ident, name):
        return bool(self._store_action(lambda: self.store.rename(ident, name)))

    @Slot(str, result=bool)
    def deletePreset(self, ident):
        return bool(self._store_action(lambda: self.store.delete(ident)))

    @Slot(result=bool)
    def restorePreset(self):
        return bool(self._store_action(self.store.restore))

    @Slot(str, result=bool)
    def applyPreset(self, ident):
        if not self.hasPhoto or self.ctrl.exporting:
            return False
        entry = next((item for item in self.store.entries if item['id'] == ident), None)
        if entry is None:
            return False
        try:
            result = self.ctrl.applySettingsClip(normalize_clip(entry['clip']))
            if result is False:
                return False
            self.accepted.emit()
            return True
        except (ValueError, OSError, TypeError) as error:
            self._error = str(error)
            self.changed.emit()
            return False

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self.ctrl.stateChanged.disconnect(self._refresh)
        except (RuntimeError, TypeError):
            pass
        self.deactivate()
        self.pool.waitForDone()
        self.ctrl.provider.discard(*(name for name, _ in self._images.values()))
        self._images.clear()
