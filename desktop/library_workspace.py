"""Opt-in catalog/session workspace backed by the real native library SDK.

Quick sessions remain independent. This class owns catalog UI state and edit
revisions, never RAW pixels. Only the selected page registers lazy thumbnails.
Connect flushCurrent to the editor's synchronous persist hook; connect openPhoto
to activation and its persisted(path, record) signal back to saveEdit.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Callable
from datetime import date
import json
import re
import math
from urllib.parse import quote

from PySide6.QtCore import QFileSystemWatcher, QObject, Property, QThreadPool, QTimer, QUrl, QSettings, Signal, Slot

from .library_service import LibraryService


_COLLECTION_NAMES = {'root': '资料库', 'all_images': '全部照片', 'recent_imports': '最近导入',
                     'recent_captures': '最近拍摄', 'trash': '未留用', 'in_library': '库内原片'}


class LibraryWorkspace(QObject):
    changed = Signal()
    selectionChanged = Signal()
    saveStateChanged = Signal()
    filtersChanged = Signal()
    photoInfoChanged = Signal()
    openPhoto = Signal(str, dict, dict)
    flushCurrent = Signal()
    quickSessionRequested = Signal()
    closeReady = Signal()
    notice = Signal(str)

    def __init__(self, parent=None, *, service=None, thumbnail_provider=None, view_settings=None):
        super().__init__(parent)
        self.service = service or LibraryService(self)
        self._provider = thumbnail_provider
        self._requests: dict[int, tuple] = {}
        self._busy = set()
        self._handle = ''
        self._info = {}
        self._collections = []
        self._images = []
        self._folders = []
        self._locations = []
        self._selected = []
        self._collection = ''
        self._query = ''
        self._filters = {}
        self._facets = {}
        self._filters_expanded = False
        self._sources_expanded = False
        self._filter_open = {'date','camera'}
        self._view_settings = view_settings or QSettings(self)
        self._facet_seq = 0
        self._facets_loading = False
        self._metadata_pool = QThreadPool(self)
        self._metadata_pool.setMaxThreadCount(1)
        self._metadata_loading = False
        self._metadata_offset = 0
        self._metadata_job = None
        self._closing = False
        self._metadata_refresh = QTimer(self)
        self._metadata_refresh.setSingleShot(True)
        self._metadata_refresh.setInterval(650)
        self._metadata_refresh.timeout.connect(self._load_images)
        self._sort = 'captured'
        self._descending = False
        self._offset = 0
        self._limit = 64
        self._total = 0
        self._epoch = 0
        self._query_seq = 0
        self._error = ''
        self._active = None
        self._edits = {}
        self._save_inflight = None
        self._after_flush: Callable | None = None
        self._thumbnail_keys = set()
        self._activation_seq = 0
        self._folder_sync_pending = False
        self._watcher = QFileSystemWatcher(self)
        self._watch_debounce = QTimer(self)
        self._watch_debounce.setSingleShot(True)
        self._watch_debounce.setInterval(500)
        self._watch_debounce.timeout.connect(self.syncFolders)
        self._watcher.directoryChanged.connect(lambda path: self._watch_debounce.start())
        # QFileSystemWatcher watches roots; a quiet, coalesced metadata scan also
        # catches changes deeper in recursive folders and disconnected disks.
        self._watch_poll = QTimer(self)
        self._watch_poll.setInterval(30_000)
        self._watch_poll.timeout.connect(self.syncFolders)
        self._search = QTimer(self)
        self._search.setSingleShot(True)
        self._search.setInterval(180)
        self._search.timeout.connect(self._load_images)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(280)
        self._save_timer.timeout.connect(self._pump_save)
        self.service.result.connect(self._result)
        self.service.failed.connect(self._failed)
        self.service.stopped.connect(self._stopped)
        self.selectionChanged.connect(self.photoInfoChanged.emit)
        self.changed.connect(self.photoInfoChanged.emit)

    @Property(bool, notify=changed)
    def hasLibrary(self): return bool(self._handle)
    @Property(bool, notify=changed)
    def busy(self): return bool(self._busy)
    @Property(str, notify=changed)
    def error(self): return self._error
    @Property(str, notify=changed)
    def name(self): return self._info.get('name', '')
    @Property(str, notify=changed)
    def kind(self): return self._info.get('kind', '')
    @Property(str, notify=changed)
    def path(self): return self._info.get('path', '')
    @Property(str, notify=changed)
    def originKind(self): return self._info.get('origin', {}).get('kind', 'none')
    @Property(bool, notify=changed)
    def isCaptureOneCopy(self): return bool(self._info.get('copied_from'))
    @Property('QVariantMap', notify=changed)
    def info(self): return self._info
    @Property('QVariantList', notify=changed)
    def collections(self): return self._collections
    @Property('QVariantList', notify=changed)
    def albums(self): return [row for row in self._collections if row.get('kind') == 'album' and row.get('editable')]
    @Property('QVariantList', notify=changed)
    def images(self): return self._images
    @Property('QVariantList', notify=changed)
    def folders(self): return self._folders
    @Property('QVariantList', notify=changed)
    def locations(self): return self._locations
    @Property('QVariantList',notify=changed)
    def unwatchedLocations(self):
        roots=[(Path(row['path']),row.get('recursive',True)) for row in self._folders]
        return [row for row in self._locations if not any(Path(row['path'])==path or recursive and Path(row['path']).is_relative_to(path) for path,recursive in roots)]
    @Property(str, notify=changed)
    def currentCollection(self): return self._collection
    @Property(bool, notify=changed)
    def canRemoveFromAlbum(self):
        return any(row.get('uuid') == self._collection and row.get('editable') and row.get('kind') == 'album'
                   for row in self._collections)
    @Property(int, notify=changed)
    def total(self): return self._total
    @Property(int, notify=changed)
    def offset(self): return self._offset
    @Property(int, constant=True)
    def pageSize(self): return self._limit
    @Property('QVariantList', notify=selectionChanged)
    def selectedImages(self): return self._selected
    @Property(int, notify=selectionChanged)
    def selectedCount(self): return len(self._selected)
    @Property(str, notify=saveStateChanged)
    def activeVariant(self): return self._active.get('variant', '') if self._active else ''
    @Property(bool, notify=saveStateChanged)
    def saving(self): return self._save_inflight is not None or any(s.get('dirty') for s in self._edits.values())
    @Property(bool, notify=saveStateChanged)
    def hasConflict(self): return any(s.get('blocked') for s in self._edits.values())
    @Property(str, notify=changed)
    def query(self): return self._query
    @query.setter
    def query(self, value):
        value = str(value).strip()
        if value != self._query:
            self._query = value
            self._offset = 0
            self._query_seq += 1
            self._search.start()
            self.filtersChanged.emit()
            self.changed.emit()

    @Property(bool, notify=filtersChanged)
    def filtersExpanded(self):return self._filters_expanded
    @Property(bool,notify=filtersChanged)
    def sourcesExpanded(self):return self._sources_expanded
    @Property(bool,notify=changed)
    def foldersSyncing(self):return self._folder_sync_pending
    @Property('QVariantMap',notify=photoInfoChanged)
    def photoInfo(self):
        selected=set(self._selected)
        rows=[row for row in self._images if row['uuid'] in selected]
        if not rows:return {}
        def common(values):
            present={str(value).strip() for value in values if value is not None and str(value).strip()}
            if not present:return '—'
            return next(iter(present)) if len(present)==1 and all(value is not None and str(value).strip() for value in values) else '多种'
        def number(value,suffix='',signed=False):
            if not isinstance(value,(int,float)) or not math.isfinite(value):return None
            return (format(value,'+.2f' if signed else '.2f').rstrip('0').rstrip('.'))+suffix
        def shutter(value):
            if not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:return None
            return '1/'+str(round(1/value))+' s' if value<.5 else number(value,' s')
        cameras=[row.get('camera') or {} for row in rows]
        exposures=[row.get('exposure') or {} for row in rows]
        info=[dict(label=label,value=value) for label,value in (
            ('相机',common([camera.get('model') for camera in cameras])),
            ('镜头',common([camera.get('lens') for camera in cameras])),
            ('拍摄时间',common([(row.get('captured_local') or '').replace('T',' ') or None for row in rows])),
            ('尺寸',common([f"{row['width']} × {row['height']}" if row.get('width') and row.get('height') else None for row in rows])),
            ('格式',common([Path(row.get('path','')).suffix.lstrip('.').upper() or None for row in rows])),
            ('感光度',common([number(exposure.get('iso'),' ISO') for exposure in exposures])),
            ('光圈',common(['f/'+number(exposure.get('aperture')) if number(exposure.get('aperture')) else None for exposure in exposures])),
            ('快门',common([shutter(exposure.get('shutter')) for exposure in exposures])),
            ('焦距',common([number(exposure.get('focal_length'),' mm') for exposure in exposures])),
            ('曝光补偿',common([number(exposure.get('compensation'),' EV',True) for exposure in exposures]))) ]
        return dict(name=rows[0]['file_name'] if len(rows)==1 else str(len(rows))+' 张照片',rows=info,
                    path=rows[0]['path'] if len(rows)==1 else common([str(Path(row['path']).parent) for row in rows]))
    @Property(bool, notify=changed)
    def facetsLoading(self):return self._facets_loading
    @Property(bool, notify=filtersChanged)
    def hasFilters(self):return bool(self._filters or self._query)
    @Property(int, notify=filtersChanged)
    def activeFilterCount(self):
        return sum(len(value) if isinstance(value,list) else 1 for key,value in self._filters.items() if key!='captured_to')
    @Property('QVariantMap', notify=filtersChanged)
    def activeFilters(self):return deepcopy(self._filters)
    @Property('QVariantList', notify=filtersChanged)
    def filterGroups(self):
        groups=[]
        def append(key,title,rows):
            if rows:groups.append(dict(key=key,title=title,rows=rows,expanded=key in self._filter_open))
        captured=self._facets.get('captured') or {}
        dates=[]
        for row in sorted(captured.get('years',[]),key=lambda r:r['value'],reverse=True):
            year=str(row['value'])
            dates.append(dict(key='date',value=year,title=year+'年',count=row['count'],selected=self._date_selected(year),depth=0))
            for month in sorted((m for m in captured.get('months',[]) if str(m['value']).startswith(year+'-')),key=lambda r:r['value'],reverse=True):
                value=str(month['value'])
                dates.append(dict(key='date',value=value,title=str(int(value[-2:]))+'月',count=month['count'],selected=self._date_selected(value),depth=1))
        append('date','拍摄日期',dates)
        for key,title,filter_key in (('camera','相机','camera_models'),('lens','镜头','lenses'),('kind','文件类型','kinds'),('keyword','关键词','keywords')):
            rows=[]
            source=list(self._facets.get(key) or [])
            for value in self._filters.get(filter_key,[]):
                if not any(row.get('value')==value for row in source):source.append(dict(value=value,count=0))
            for row in source:
                value=row.get('value');label={'raw':'RAW','raster':'照片','movie':'视频','pair':'半格组合','other':'其他'}.get(value,value) if key=='kind' else value
                rows.append(dict(key=filter_key,value=value,title=str(label or '未知'),count=row.get('count',0),selected=value in self._filters.get(filter_key,[]),depth=0))
            append(key,title,rows)
        edited=self._facets.get('edited') or {}
        append('edited','显影状态',[dict(key='has_edit',value=value,title=title,count=edited.get('yes' if value else 'no',0),selected=self._filters.get('has_edit') is value,depth=0) for value,title in ((True,'已有显影调整'),(False,'尚无显影调整'))])
        return groups

    def _date_selected(self,value):
        return self._filters.get('captured_from')==(value+'-01-01' if len(value)==4 else value+'-01') and self._filters.get('captured_to')==self._date_range(value)[1]

    @staticmethod
    def _date_range(value):
        if re.fullmatch(r'\d{4}',value):return value+'-01-01',str(int(value)+1)+'-01-01'
        if re.fullmatch(r'\d{4}-\d{2}',value):
            year,month=map(int,value.split('-'));date(year,month,1)
            return value+'-01',date(year+int(month==12),1 if month==12 else month+1,1).isoformat()
        raise ValueError('日期范围无效')

    def _view_key(self):return 'library/views/'+quote(self.path,safe='')
    def _save_view(self):
        if self._handle:self._view_settings.setValue(self._view_key(),json.dumps(dict(query=self._query,filters=self._filters,sort=self._sort,descending=self._descending,expanded=self._filters_expanded,open=sorted(self._filter_open)),ensure_ascii=False))
    def _restore_view(self):
        try:record=json.loads(str(self._view_settings.value(self._view_key(),'')))
        except (ValueError,TypeError):record={}
        if not isinstance(record,dict):record={}
        self._query=str(record.get('query',''))[:256]
        self._filters={}
        raw=record.get('filters',{})
        if isinstance(raw,dict):
            for key in ('camera_models','lenses','kinds','keywords'):
                values=raw.get(key)
                if isinstance(values,list):self._filters[key]=[v for v in values[:128] if v is None or isinstance(v,str)]
            if isinstance(raw.get('has_edit'),bool):self._filters['has_edit']=raw['has_edit']
            for key in ('captured_from','captured_to'):
                if isinstance(raw.get(key),str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}',raw[key]):self._filters[key]=raw[key]
        self._filters={key:value for key,value in self._filters.items() if value!=[]}
        self._sort=record.get('sort','captured') if record.get('sort') in ('captured','imported','name','added') else 'captured'
        self._descending=bool(record.get('descending',False));self._filters_expanded=bool(record.get('expanded',False))
        opened=record.get('open',['date','camera'])
        self._filter_open={key for key in (opened if isinstance(opened,list) else ['date','camera']) if isinstance(key,str)} & {'date','camera','lens','kind','keyword','edited'}

    @Slot(bool)
    def setFiltersExpanded(self,value):
        self._filters_expanded=bool(value)
        if value:self._sources_expanded=False
        self._save_view();self.filtersChanged.emit()
    @Slot(bool)
    def setSourcesExpanded(self,value):
        self._sources_expanded=bool(value)
        if value:self._filters_expanded=False
        self.filtersChanged.emit()
    @Slot(str)
    def toggleFilterGroup(self,key):
        if key in self._filter_open:self._filter_open.remove(key)
        else:self._filter_open.add(key)
        self._save_view();self.filtersChanged.emit()
    @Slot(str,'QVariant')
    def toggleFilter(self,key,value):
        if key=='date':
            try:start,end=self._date_range(str(value))
            except ValueError:return
            if self._filters.get('captured_from')==start and self._filters.get('captured_to')==end:
                self._filters.pop('captured_from',None);self._filters.pop('captured_to',None)
            else:self._filters.update(captured_from=start,captured_to=end)
        elif key=='has_edit' and isinstance(value,bool):
            if self._filters.get(key) is value:self._filters.pop(key,None)
            else:self._filters[key]=value
        elif key in ('camera_models','lenses','kinds','keywords') and (value is None or isinstance(value,str)):
            values=list(self._filters.get(key,[]))
            if value in values:values.remove(value)
            else:values.append(value)
            if values:self._filters[key]=values
            else:self._filters.pop(key,None)
        else:return
        self._search.stop();self._offset=0;self._selected=[];self.selectionChanged.emit();self.filtersChanged.emit();self._load_images()
    @Slot()
    def clearFilters(self):
        self._search.stop();self._filters={};self._query='';self._offset=0;self._selected=[];self.selectionChanged.emit();self.filtersChanged.emit();self._load_images()

    def _request(self, method, params, success=None, failure=None, *, busy=True):
        try:
            rid = self.service.call(method, params)
        except (ValueError, RuntimeError) as exc:
            self._set_error(str(exc))
            return None
        self._requests[rid] = (success, failure)
        if busy:
            self._busy.add(rid)
            self.changed.emit()
        return rid

    def _result(self, rid, method, payload):
        handler = self._requests.pop(rid, None)
        self._busy.discard(rid)
        if handler and handler[0]: handler[0](payload)
        self.changed.emit()

    def _failed(self, rid, method, error):
        handler = self._requests.pop(rid, None)
        self._busy.discard(rid)
        if handler and handler[1]: handler[1](error)
        else: self._set_error(error.get('message', '资料库操作失败。'))
        self.changed.emit()

    def _set_error(self, message):
        self._error = str(message)
        self.changed.emit()
        self.notice.emit(self._error)

    @Slot()
    def dismissError(self):
        self._error = ''
        self.changed.emit()

    def _stopped(self):
        if self._handle:
            self._save_view()
            self._epoch += 1
            self._metadata_loading = False
            self._set_error('资料库连接已关闭，请重新打开。未保存的调整仍保留在当前编辑器。')
            self._handle = ''
            self.changed.emit()

    def _await_clean(self, action):
        self._after_flush = action
        self.flushCurrent.emit()
        self._save_timer.stop()
        self._pump_save()
        self._run_after_flush()

    def _run_after_flush(self):
        if self._save_inflight is not None:
            return
        if any(s.get('blocked') for s in self._edits.values()):
            self._after_flush = None
            return
        if any(s.get('dirty') for s in self._edits.values()):
            return
        action, self._after_flush = self._after_flush, None
        if action: action()

    @Slot(str)
    def openLibrary(self, path):
        self._await_clean(lambda: self._request('library.open', {'path': path}, self._adopt))

    @Slot(str, str)
    def createLibrary(self, path, kind='catalog'):
        if kind not in ('catalog', 'session'): return
        self._await_clean(lambda: self._request('library.create', {'path': path, 'kind': kind}, self._adopt))

    @Slot(str, str)
    def linkCaptureOne(self, source, path=''):
        params = {'source': source}
        if path: params['path'] = path
        self._await_clean(lambda: self._request('capture_one.link', params, self._adopt))

    @Slot(str, str)
    def copyCaptureOne(self, source, path):
        params = {'source': source, 'path': path}
        origin = self._info.get('origin', {})
        if (self._handle and origin.get('kind') != 'none' and origin.get('path')
                and (Path(source) == Path(origin['path']) or Path(source).parent == Path(origin['path']))):
            params['mirror'] = self._handle
        self._await_clean(lambda: self._request('capture_one.copy', params, self._adopt))

    def _adopt(self, payload):
        old = self._handle
        self._save_view()
        self._epoch += 1
        self._handle = payload['library']
        self._info = payload['info']
        self._collection = ''
        self._selected = []
        self._active = None
        self._edits.clear()
        self._offset = 0
        self._facets = {}
        self._sources_expanded=False
        self._metadata_loading = False
        self._metadata_offset = 0
        self._folder_sync_pending = False
        self._restore_view()
        self.filtersChanged.emit()
        self._error = ''
        if old and old != self._handle:
            self._request('library.close', {'library': old}, busy=False)
        self.selectionChanged.emit()
        self.saveStateChanged.emit()
        self.refresh()

    @Slot()
    def quickSession(self):
        def done():
            old = self._handle
            self._save_view()
            self._epoch += 1
            self._handle = ''
            self._info = {}
            self._collections = []
            self._images = []
            self._facets = {}
            self._filters = {}
            self._query = ''
            self._facets_loading = False
            self._metadata_loading = False
            self._metadata_refresh.stop()
            self._selected = []
            self._active = None
            self._edits.clear()
            self._watch_poll.stop()
            self._watch_debounce.stop()
            if self._watcher.directories(): self._watcher.removePaths(self._watcher.directories())
            if old: self._request('library.close', {'library': old}, busy=False)
            self.changed.emit()
            self.filtersChanged.emit()
            self.selectionChanged.emit()
            self.saveStateChanged.emit()
            self.quickSessionRequested.emit()
        self._await_clean(done)

    def _scoped(self, callback):
        epoch = self._epoch
        return lambda result: callback(result) if self._epoch == epoch else None

    @Slot()
    def refresh(self):
        if not self._handle: return
        params = {'library': self._handle}
        self._request('library.info', params, self._scoped(self._set_info), busy=False)
        self._request('collections.list', params, self._scoped(self._set_collections), busy=False)
        self._request('folders.list', params, self._scoped(self._set_folders), busy=False)
        self._request('locations.list', params, self._scoped(lambda p: self._set_list('_locations', p['locations'])), busy=False)
        self._load_images()
        self._schedule_describe()

    def _set_info(self, payload): self._info = payload
    def _set_list(self, key, rows): setattr(self, key, rows)

    def _set_folders(self, payload):
        self._folders = payload['folders']
        desired = {row['path'] for row in self._folders if row.get('online')}
        if self.kind == 'session': desired.add(self.path)
        current = set(self._watcher.directories())
        if current - desired: self._watcher.removePaths(list(current - desired))
        if desired - current: self._watcher.addPaths(list(desired - current))
        if desired: self._watch_poll.start()
        else: self._watch_poll.stop()

    def _set_collections(self, payload):
        rows = payload['collections']
        by_parent = {}
        ids = {row['uuid'] for row in rows}
        for row in rows:
            by_parent.setdefault(row.get('parent') if row.get('parent') in ids else None, []).append(row)
        by_parent.setdefault(None, []).sort(key=lambda row: 0 if row['kind'] == 'root' else 1)
        ordered, visited = [], set()
        def append(parent, depth):
            for original in by_parent.get(parent, []):
                if original['uuid'] in visited: continue
                visited.add(original['uuid'])
                row = dict(original)
                row['depth'] = depth
                row['title'] = _COLLECTION_NAMES.get(row['kind'], row.get('title') or row.get('name') or '未命名')
                ordered.append(row)
                append(row['uuid'], depth + (0 if row['kind'] == 'root' else 1))
        append(None, 0)
        for row in rows:
            if row['uuid'] not in visited:
                ordered.append(dict(row, depth=0, title=row.get('title') or row.get('name') or '未命名'))
        self._collections = ordered
        if self._collection not in ids:
            invalid = bool(self._collection)
            self._collection = next((row['uuid'] for row in rows if row['kind'] == 'all_images'), '')
            if invalid: self._load_images()

    @Slot(str)
    def selectCollection(self, uuid):
        if uuid == self._collection: return
        self._collection = uuid
        self._offset = 0
        self._selected = []
        self.selectionChanged.emit()
        self._load_images()

    @Slot(str, bool)
    def setSort(self, key, descending=False):
        if key not in ('captured', 'imported', 'name', 'added'): return
        self._sort, self._descending = key, bool(descending)
        self._offset = 0
        self._load_images()

    @Slot(int)
    def setPage(self, page):
        self._offset = max(0, min(max(0, self._total - 1) // self._limit, page)) * self._limit
        self._selected = []
        self.selectionChanged.emit()
        self._load_images()

    def _load_images(self):
        if not self._handle or self._closing: return
        self._save_view()
        self._query_seq += 1
        sequence, epoch = self._query_seq, self._epoch
        params = {'library': self._handle, 'offset': self._offset, 'limit': self._limit,
                  'sort': self._sort, 'descending': self._descending, 'full': True}
        if self._collection: params['collection'] = self._collection
        filters=deepcopy(self._filters)
        if self._query: filters['text']=self._query
        if filters:params['filter']=filters
        self._load_facets(params,sequence,epoch)
        def loaded(payload):
            if sequence != self._query_seq or epoch != self._epoch: return
            self._total = payload['total']
            self._offset = payload['offset']
            self._images = payload['images']
            valid = {row['uuid'] for row in self._images}
            self._selected = [uuid for uuid in self._selected if uuid in valid]
            new_keys = set()
            for row in self._images:
                row['thumbnail'] = ''
                if self._provider:
                    key = 'library_' + row['uuid']
                    new_keys.add(key)
                    self._provider.register_thumbnail(key, row['path'])
                    row['thumbnail'] = 'image://photos/' + key
            if self._provider:
                for key in self._thumbnail_keys - new_keys: self._provider.discard(key)
            self._thumbnail_keys = new_keys
            self.selectionChanged.emit()
        def failed(error):
            if sequence == self._query_seq and epoch == self._epoch:
                self._set_error(error.get('message', '照片列表读取失败。'))
        self._request('images.list', params, loaded, failed)

    def _load_facets(self,params,sequence,epoch):
        self._facets_loading=True
        scope={key:deepcopy(params[key]) for key in ('library','collection','filter') if key in params}
        def loaded(payload):
            if epoch!=self._epoch or sequence!=self._query_seq:return
            if self._facets!=payload:
                self._facets=payload
                self.filtersChanged.emit()
            self._facets_loading=False
        def failed(error):
            if epoch!=self._epoch or sequence!=self._query_seq:return
            self._facets_loading=False
            self._set_error(error.get('message','筛选统计读取失败。'))
        self._request('images.facets',scope,loaded,failed,busy=False)

    def _schedule_describe(self):
        if not self._handle or self._metadata_loading or self._closing:return
        self._metadata_loading=True
        epoch,handle=self._epoch,self._handle
        def loaded(payload):
            if epoch!=self._epoch or handle!=self._handle:return
            rows=payload['images']
            local=[row for row in rows if row.get('origin')=='local']
            self._metadata_offset+=len(rows)-len(local)
            if not local:
                self._metadata_loading=False
                if rows:QTimer.singleShot(50,self._schedule_describe)
                return
            from .library_metadata import HeaderJob
            job=HeaderJob(epoch,handle,local)
            self._metadata_job=job
            job.signals.finished.connect(self._described_headers)
            self._metadata_pool.start(job)
        def failed(error):
            if epoch==self._epoch:self._metadata_loading=False
        self._request('images.list',{'library':handle,'filter':{'described':False},
                      'limit':64,'offset':self._metadata_offset,'full':True},loaded,failed,busy=False)

    @Slot(int,str,list)
    def _described_headers(self,epoch,handle,items):
        if epoch!=self._epoch or handle!=self._handle or self._closing:return
        def described(payload):
            if epoch!=self._epoch:return
            self._metadata_loading=False
            self._metadata_job=None
            if not self._metadata_refresh.isActive():self._metadata_refresh.start()
            QTimer.singleShot(40,self._schedule_describe)
        def failed(error):
            if epoch==self._epoch:
                self._metadata_loading=False
                self._metadata_job=None
        self._request('images.describe',{'library':handle,'items':items},described,failed,busy=False)

    @Slot(str, bool)
    def selectImage(self, uuid, additive=False):
        if additive:
            self._selected = [u for u in self._selected if u != uuid] if uuid in self._selected else self._selected + [uuid]
        else: self._selected = [uuid]
        self.selectionChanged.emit()

    @Slot()
    def selectPage(self):
        self._selected = [row['uuid'] for row in self._images]
        self.selectionChanged.emit()

    def _row(self, uuid): return next((row for row in self._images if row['uuid'] == uuid), None)

    @Slot(str, str)
    def activateVariant(self, image, variant=''):
        row = self._row(image)
        if not row: return
        variants = row.get('variants', [])
        variant = variant or (variants[0]['uuid'] if variants else '')
        if not variant or not any(v['uuid'] == variant for v in variants): return
        target = {'path': row['path'], 'image': image, 'variant': variant, 'row': deepcopy(row)}
        self._await_clean(lambda: self._read_edit(target))

    @Slot()
    def editSelected(self):
        if self._selected: self.activateVariant(self._selected[0], '')

    def _read_edit(self, target):
        epoch = self._epoch
        self._activation_seq += 1
        activation = self._activation_seq
        def opened(payload):
            if epoch != self._epoch or activation != self._activation_seq: return
            record = payload.get('edit') or {}
            self._edits[target['variant']] = {'revision': payload['revision'], 'record': deepcopy(record),
                                               'dirty': False, 'blocked': False}
            self._active = target
            self.saveStateChanged.emit()
            metadata = {'library': self._handle, 'image': target['image'], 'variant': target['variant'],
                        'revision': payload['revision'], 'kind': self.kind, 'row': target['row']}
            self.openPhoto.emit(target['path'], deepcopy(record), metadata)
        self._request('edit.get', {'library': self._handle, 'variant': target['variant']}, opened)

    @Slot(str, 'QVariantMap')
    def saveEdit(self, path, record):
        if not self._handle or not self._active or Path(path) != Path(self._active['path']): return
        variant = self._active['variant']
        state = self._edits.get(variant)
        if not state or record == state['record']: return
        state['record'] = deepcopy(dict(record))
        state['dirty'] = True
        self.saveStateChanged.emit()
        self._save_timer.start()

    def _pump_save(self):
        if not self._handle or self._save_inflight is not None: return
        for variant, state in self._edits.items():
            if state.get('dirty') and not state.get('blocked'):
                record, revision = deepcopy(state['record']), state['revision']
                self._save_inflight = variant
                def saved(payload, key=variant, sent=record):
                    current = self._edits[key]
                    current['revision'] = payload['revision']
                    current['dirty'] = current['record'] != sent
                    self._save_inflight = None
                    self.saveStateChanged.emit()
                    self._metadata_refresh.start()
                    self._pump_save()
                    self._run_after_flush()
                def failed(error, key=variant):
                    self._edits[key]['blocked'] = True
                    self._save_inflight = None
                    self._after_flush = None
                    if error.get('code') == 'conflict':
                        self._set_error('此变体已由另一处修改。可重新载入，或将当前调整另存为新变体。')
                    else: self._set_error(error.get('message', '调整尚未保存。'))
                    self.saveStateChanged.emit()
                rid = self._request('edit.put', {'library': self._handle, 'variant': variant,
                                                 'base_revision': revision, 'edit': record}, saved, failed, busy=False)
                if rid is None:
                    self._save_inflight = None
                    state['blocked'] = True
                return
        self._run_after_flush()

    @Slot()
    def reloadCurrentEdit(self):
        if not self._active or self._save_inflight: return
        # Explicit conflict action: replace only after reading the remote record.
        self._read_edit(dict(self._active))
        self.dismissError()

    @Slot()
    def saveAsNewVariant(self):
        if not self._active or self._save_inflight: return
        target = deepcopy(self._active)
        record = deepcopy(self._edits[target['variant']]['record'])
        old_variant = target['variant']
        def created(payload):
            target['variant'] = payload['variant']
            self._edits.pop(old_variant, None)
            self._edits[target['variant']] = {'revision': 0, 'record': record, 'dirty': True, 'blocked': False}
            self._active = target
            self._after_flush = lambda: self._read_edit(target)
            self.dismissError()
            self._pump_save()
            self.refresh()
        self._request('variant.create', {'library': self._handle, 'image': target['image']}, created)

    @Slot()
    def createVariant(self):
        if not self._selected: return
        row = self._row(self._selected[0])
        if not row: return
        source = self.activeVariant if self._active and self._active['image'] == row['uuid'] else row['variants'][0]['uuid']
        def create():
            def created(payload):
                target = {'path': row['path'], 'image': row['uuid'], 'variant': payload['variant'], 'row': deepcopy(row)}
                self._read_edit(target)
                self.refresh()
            self._request('variant.create', {'library': self._handle, 'image': row['uuid'], 'from_variant': source}, created)
        self._await_clean(create)

    @Slot(str)
    def createAlbum(self, name):
        name = name.strip()
        if not name or not self._handle: return
        self._request('collection.create', {'library': self._handle, 'kind': 'album', 'name': name}, lambda p: self.refresh())

    @Slot(str)
    def addSelectedToAlbum(self, album):
        if self._handle and self._selected:
            self._request('collection.add', {'library': self._handle, 'collection': album,
                                             'images': list(self._selected)}, lambda p: self.refresh())

    @Slot()
    def removeSelectedFromAlbum(self):
        if self.canRemoveFromAlbum and self._selected:
            self._request('collection.remove', {'library': self._handle, 'collection': self._collection,
                                                'images': list(self._selected)}, lambda p: self.refresh())

    @Slot(str, str)
    def renameCollection(self, uuid, name):
        if self._handle and name.strip():
            self._request('collection.update', {'library': self._handle, 'collection': uuid, 'name': name.strip()}, lambda p: self.refresh())

    @Slot(str)
    def deleteCollection(self, uuid):
        if self._handle:
            row = next((row for row in self._collections if row['uuid'] == uuid), None)
            if row and row.get('image_count'):
                self._set_error('请先将照片移出相册，再删除相册。原片不会删除。')
                return
            self._request('collection.delete', {'library': self._handle, 'collection': uuid}, lambda p: self.refresh())

    @Slot(bool)
    def setSelectedRetained(self, retained):
        if self._handle and self._selected:
            self._request('images.trash', {'library': self._handle, 'images': list(self._selected),
                                          'trashed': not retained}, lambda p: self.refresh())

    @Slot('QVariantList', bool)
    def addPaths(self, paths, copy=False):
        if not self._handle: return
        values = []
        for path in paths:
            path = str(path)
            values.append(QUrl(path).toLocalFile() if path.startswith('file:') else path)
        values = [p for p in values if p]
        handle, epoch = self._handle, self._epoch
        def batch(offset):
            if handle != self._handle or epoch != self._epoch: return
            if offset >= len(values):
                self.refresh()
                return
            def added(payload):
                failures = [row for row in payload.get('results', []) if row.get('error')]
                if failures: self._set_error(str(len(failures)) + ' 张照片未加入，请检查原文件。')
                batch(offset + 250)
            self._request('images.add', {'library': handle, 'items': values[offset:offset + 250],
                                         'mode': 'copy' if copy else 'reference', 'recent_import': False}, added)
        batch(0)

    @Slot(str)
    def watchFolder(self, path):
        if self._handle:
            self._request('folders.add', {'library': self._handle, 'path': path, 'recursive': True}, lambda p: self.refresh())

    @Slot(str)
    def unwatchFolder(self, uuid):
        if self._handle and self.originKind=='none' and any(row['folder']==uuid for row in self._folders):
            self._request('folders.remove', {'library': self._handle, 'folder': uuid}, lambda p: self.refresh())

    @Slot()
    def syncFolders(self):
        self._sync_folders()

    @Slot(str)
    def syncWatchedFolder(self,uuid):
        if any(row['folder']==uuid for row in self._folders):self._sync_folders(uuid)

    def _sync_folders(self,folder=None):
        if self._handle and self.originKind=='none' and not self._folder_sync_pending:
            self._folder_sync_pending = True
            self.changed.emit()
            epoch = self._epoch
            def synced(payload):
                if epoch != self._epoch: return
                self._folder_sync_pending = False
                if any(payload.get(key, 0) for key in ('added', 'moved', 'removed', 'restored')):
                    self.refresh()
                else:
                    self._request('folders.list',{'library':self._handle},self._scoped(self._set_folders),busy=False)
                    self._request('locations.list',{'library':self._handle},self._scoped(lambda p:self._set_list('_locations',p['locations'])),busy=False)
            def failed(error):
                if epoch != self._epoch:return
                self._folder_sync_pending = False
                self._set_error(error.get('message', '文件夹刷新失败。'))
            params={'library':self._handle}
            if folder:params['folder']=folder
            self._request('folders.sync',params,synced,failed,busy=False)

    @Slot()
    def syncCaptureOne(self):
        if not self._handle: return
        method = 'capture_one.update' if self.isCaptureOneCopy else 'library.sync'
        self._await_clean(lambda: self._request(method, {'library': self._handle}, lambda p: self.refresh()))

    @Slot(str, str)
    def relinkLocation(self, location, path):
        if self._handle:
            self._request('location.relink', {'library': self._handle, 'location': location, 'path': path}, lambda p: self.refresh())

    @Slot(str)
    def moveSelected(self, role):
        if self.kind == 'session' and self._selected:
            handle, selected = self._handle, list(self._selected)
            self._await_clean(lambda: self._request('session.move', {'library': handle,
                                                                    'images': selected, 'to': role,
                                                                    'on_conflict': 'suffix'}, lambda p: self.refresh()))

    @Slot()
    def restoreSelected(self):
        if self.kind == 'session' and self._selected:
            self._request('session.restore', {'library': self._handle, 'images': list(self._selected),
                                              'on_conflict': 'suffix'}, lambda p: self.refresh())

    @Slot()
    def chooseOpenLibrary(self):
        from .dialogs import StudioFileDialog
        path = StudioFileDialog.getExistingDirectory(caption='打开资料库或拍摄会话', directory=self.path)
        if path: self.openLibrary(path)

    @Slot(str)
    def chooseCreateLibrary(self, kind='catalog'):
        from .dialogs import StudioFileDialog
        title = '新建拍摄会话' if kind == 'session' else '新建资料库'
        path, _ = StudioFileDialog.getSaveFileName(caption=title)
        if path: self.createLibrary(path, kind)

    @Slot(bool)
    def chooseCaptureOne(self, copy=False):
        from .dialogs import StudioFileDialog
        sources, _ = StudioFileDialog.getOpenFileNames(caption='选择 Capture One 资料库', filter='Capture One (*.cocatalogdb)')
        if not sources: return
        if not copy: self.linkCaptureOne(sources[0], '')
        else:
            target, _ = StudioFileDialog.getSaveFileName(caption='另存为独立资料库')
            if target: self.copyCaptureOne(sources[0], target)

    @Slot()
    def chooseAddPhotos(self):
        from .dialogs import StudioFileDialog
        paths, _ = StudioFileDialog.getOpenFileNames(caption='加入照片', filter='照片 (*.arw *.nef *.nrw *.cr2 *.cr3 *.raf *.dng *.orf *.rw2 *.pef *.iiq *.3fr *.fff *.jpg *.jpeg *.tif *.tiff *.png *.heic *.heif);;所有文件 (*)')
        if paths: self.addPaths(paths, False)

    @Slot()
    def chooseWatchedFolder(self):
        from .dialogs import StudioFileDialog
        path = StudioFileDialog.getExistingDirectory(caption='添加自动刷新的照片文件夹')
        if path: self.watchFolder(path)

    @Slot(str)
    def chooseRelinkLocation(self, uuid):
        from .dialogs import StudioFileDialog
        path = StudioFileDialog.getExistingDirectory(caption='重新定位原片文件夹')
        if path: self.relinkLocation(uuid, path)

    @Slot()
    def flushPending(self):
        self.flushCurrent.emit()
        self._save_timer.stop()
        self._pump_save()

    @Slot()
    def prepareToClose(self):
        """Window close barrier; conflicts retain the editor and emit no closeReady."""
        self._await_clean(self.closeReady.emit)

    @Slot()
    def shutdown(self):
        self._closing=True
        self._save_view()
        self._metadata_refresh.stop()
        self._watch_poll.stop()
        self._watch_debounce.stop()
        if self._watcher.directories(): self._watcher.removePaths(self._watcher.directories())
        self._await_clean(self.service.close)
