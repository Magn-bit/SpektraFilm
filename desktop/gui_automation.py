"""Explicit, current-user-only local automation of the *live* GUI session.

No listener exists by default. QLocalServer uses OS user access restrictions and
a random bearer token stored in a protected application directory. Request
dispatch is queued to Qt's controller thread. Open/export return bounded job
records; neither waits for decoding or rendering on that thread. There is no
arbitrary attribute lookup, Python evaluation, subprocess or shell operation.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict, fields, replace
import base64
import json
import os
from pathlib import Path
import secrets
import time
import uuid

from PySide6.QtCore import QObject, Property, QBuffer, QCoreApplication, QIODevice, QStandardPaths, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtGui import QImage

from .automation import (MAX_REQUEST_BYTES, TOOL_SCHEMAS, _atomic_json, _json,
                         _parse_json, _read_json, _settings, _source_path, _schema, STRING)


PROTOCOL = 1
MAX_CLIENTS = 8
MAX_QUEUED = 32
_CLIENT_APPLICATION = None


def default_endpoint_directory():
    return Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)) / 'automation'


def _protect_directory(directory):
    """Protect before placing any credential file in the directory."""
    directory.mkdir(parents=True, exist_ok=True)
    if os.name != 'nt':
        directory.chmod(0o700)
        return
    import ctypes as ct
    from ctypes import wintypes as wt
    advapi = ct.WinDLL('advapi32', use_last_error=True)
    kernel = ct.WinDLL('kernel32', use_last_error=True)
    advapi.OpenProcessToken.argtypes = [wt.HANDLE, wt.DWORD, ct.POINTER(wt.HANDLE)]
    advapi.GetTokenInformation.argtypes = [wt.HANDLE, ct.c_int, ct.c_void_p, wt.DWORD, ct.POINTER(wt.DWORD)]
    advapi.ConvertSidToStringSidW.argtypes = [ct.c_void_p, ct.POINTER(wt.LPWSTR)]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [wt.LPCWSTR, wt.DWORD, ct.POINTER(ct.c_void_p), ct.c_void_p]
    advapi.SetFileSecurityW.argtypes = [wt.LPCWSTR, wt.DWORD, ct.c_void_p]
    kernel.GetCurrentProcess.restype = wt.HANDLE
    kernel.CloseHandle.argtypes = [wt.HANDLE]
    kernel.LocalFree.argtypes = [ct.c_void_p]
    token, sid_text, descriptor = wt.HANDLE(), wt.LPWSTR(), ct.c_void_p()
    try:
        if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, ct.byref(token)):
            raise OSError('无法保护本机会话凭据目录。')
        size = wt.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, ct.byref(size))
        buffer = ct.create_string_buffer(size.value)
        if not advapi.GetTokenInformation(token, 1, buffer, size, ct.byref(size)):
            raise OSError('无法读取当前用户身份。')
        sid = ct.cast(buffer, ct.POINTER(ct.c_void_p))[0]
        if not advapi.ConvertSidToStringSidW(sid, ct.byref(sid_text)):
            raise OSError('无法读取当前用户身份。')
        # Protected DACL, current user only, inherited by files/subdirectories.
        sddl = 'D:P(A;OICI;FA;;;' + sid_text.value + ')'
        if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ct.byref(descriptor), None):
            raise OSError('无法保护本机会话凭据目录。')
        if not advapi.SetFileSecurityW(str(directory), 0x80000004, descriptor):
            raise OSError('无法保护本机会话凭据目录。')
    finally:
        if token: kernel.CloseHandle(token)
        if sid_text: kernel.LocalFree(ct.cast(sid_text, ct.c_void_p))
        if descriptor: kernel.LocalFree(descriptor)


GUI_TOOL_SCHEMAS = dict(TOOL_SCHEMAS)
GUI_TOOL_SCHEMAS['status'] = ('Read the live GUI session, its current selection and asynchronous jobs.', _schema())
GUI_TOOL_SCHEMAS['open'] = ('Queue local photos in the same GUI window; return a job ID without waiting for import.', TOOL_SCHEMAS['open'][1])
GUI_TOOL_SCHEMAS['copy'] = ('Copy categories into the live GUI parameter clipboard.', TOOL_SCHEMAS['copy'][1])
GUI_TOOL_SCHEMAS['paste'] = ('Paste into explicit photos, or the current GUI selection; each change is undoable.', TOOL_SCHEMAS['paste'][1])
GUI_TOOL_SCHEMAS['export'] = ('Start the real GUI export worker and return a job ID. Query spektra_job for progress/result.', TOOL_SCHEMAS['export'][1])
GUI_TOOL_SCHEMAS['job'] = ('Read one asynchronous import/export job.', _schema({'job': STRING}, ['job']))
GUI_TOOL_SCHEMAS['cancel_export'] = ('Request cancellation of an export job started through this interface.', _schema({'job': STRING}, ['job']))
GUI_TOOL_SCHEMAS['describe'] = ('Describe an open photo, its material pairing, settings, processing and current-window preview state.', _schema({'photo': STRING}))
GUI_TOOL_SCHEMAS['preview_image'] = ('Read the completed current GUI preview as a bounded JPEG image. If rendering, retry after the returned delay; does not change source/export size.', _schema({'photo': STRING, 'long_edge': dict(type='integer',minimum=64,maximum=2048)}))
GUI_TOOL_SCHEMAS['auto_meter'] = ('Queue the actual GUI spectral exposure/filter-pack solver; accepted results use the same undoable adjustment as the interface.', _schema({'photo': STRING, 'target': dict(type='string',enum=['exposure','filter_pack','both']), 'method': dict(type='string',enum=['balanced','center','protect_highlights','protect_shadows'])}))
GUI_TOOL_SCHEMAS['latitude'] = ('Queue the actual GUI scene/medium latitude measurement and return an asynchronous job.', _schema({'photo': STRING}))
GUI_TOOL_SCHEMAS['place'] = ('Measure the current scene then apply its recommended Scene Placement only when the real engine fit is valid and still current.', _schema({'photo': STRING}))


class GuiAutomation(QObject):
    """QObject for an explicit settings switch; constructing it starts nothing."""
    changed = Signal()
    error = Signal(str)
    _queued = Signal(object)

    def __init__(self, controller, parent=None, *, directory=None):
        super().__init__(parent or controller)
        if self.thread() != controller.thread():
            raise ValueError('GUI automation must live in the controller Qt thread')
        self.ctrl = controller
        self._directory = Path(directory) if directory else Path(controller._store).parent / 'automation'
        self._server = QLocalServer(self)
        self._server.setSocketOptions(QLocalServer.UserAccessOption)
        self._server.setMaxPendingConnections(MAX_CLIENTS)
        self._server.newConnection.connect(self._accept)
        self._queued.connect(self._dispatch, Qt.QueuedConnection)
        self._clients = {}
        self._pending = 0
        self._token = ''
        self._session = ''
        self._descriptor = None
        self._status = '本机会话接口已关闭'
        self._jobs = OrderedDict()
        self._export_job = None
        self._analysis_jobs = {}
        self.ctrl.stateChanged.connect(self._state_changed)

    @Property(bool, notify=changed)
    def enabled(self): return self._server.isListening()
    @enabled.setter
    def enabled(self, value): self.setEnabled(value)
    @Property(str, notify=changed)
    def status(self): return self._status
    @Property(str, notify=changed)
    def sessionId(self): return self._session if self.enabled else ''

    @Slot(bool)
    def setEnabled(self, value):
        value = bool(value)
        if value == self.enabled: return
        if not value:
            self.close()
            return
        try:
            _protect_directory(self._directory)
            self._session = uuid.uuid4().hex
            self._token = secrets.token_urlsafe(32)
            name = f'SpektraFilm-{os.getpid()}-{self._session}'
            if not self._server.listen(name): raise OSError('本机会话接口无法启动。')
            self._descriptor = self._directory / f'gui-{os.getpid()}-{self._session}.json'
            _atomic_json(self._descriptor, {'protocol': PROTOCOL, 'pid': os.getpid(), 'session': self._session,
                                           'server': name, 'token': self._token, 'created': time.time()})
            if os.name != 'nt': self._descriptor.chmod(0o600)
            self._status = '本机会话接口已开启'
            self.changed.emit()
        except OSError:
            self.close()
            self._status = '本机会话接口无法启动。'
            self.error.emit(self._status)
            self.changed.emit()

    @Slot()
    def close(self):
        self._server.close()
        self._token = ''
        for socket in list(self._clients): socket.abort()
        self._clients.clear()
        if self._descriptor:
            try: self._descriptor.unlink(missing_ok=True)
            except OSError: pass
        self._descriptor = None
        self._status = '本机会话接口已关闭'
        self.changed.emit()

    def _accept(self):
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            if len(self._clients) >= MAX_CLIENTS:
                socket.abort(); socket.deleteLater(); continue
            socket.setReadBufferSize(MAX_REQUEST_BYTES + 1)
            timer = QTimer(socket)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda sock=socket: sock.abort() if sock in self._clients else None)
            timer.start(5000)
            self._clients[socket] = {'buffer': bytearray(), 'timer': timer, 'used': False}
            socket.readyRead.connect(lambda sock=socket: self._read(sock))
            socket.disconnected.connect(lambda sock=socket: self._disconnected(sock))
            if socket.bytesAvailable(): self._read(socket)

    def _disconnected(self, socket):
        self._clients.pop(socket, None)
        socket.deleteLater()

    def _send(self, socket, payload):
        if socket not in self._clients: return
        socket.write((_json(payload) + '\n').encode('utf-8'))
        socket.disconnectFromServer()

    def _read(self, socket):
        client = self._clients.get(socket)
        if not client or client['used']: return
        client['buffer'].extend(bytes(socket.readAll()))
        if len(client['buffer']) > MAX_REQUEST_BYTES:
            socket.abort(); return
        if b'\n' not in client['buffer']: return
        client['used'] = True
        ident = None
        try:
            request = _parse_json(bytes(client['buffer']).split(b'\n', 1)[0])
            if not isinstance(request, dict): raise ValueError('请求必须为对象')
            ident = request.get('id')
            token = request.get('token')
            if not isinstance(token, str) or not secrets.compare_digest(token, self._token) or not self.enabled:
                self._send(socket, {'id': ident, 'error': {'code': 'unauthorized', 'message': '本机会话认证失败。'}})
                return
            method, args = request.get('method'), request.get('arguments', {})
            if method not in GUI_TOOL_SCHEMAS or not isinstance(args, dict):
                raise ValueError('不支持的结构化操作')
            if self._pending >= MAX_QUEUED: raise ValueError('操作队列繁忙，请稍后重试')
            schema = GUI_TOOL_SCHEMAS[method][1]
            if set(args) - set(schema['properties']) or any(key not in args for key in schema['required']):
                raise ValueError('操作参数不符合接口契约')
            self._pending += 1
            self._queued.emit((socket, ident, method, args, self._session))
        except (ValueError, TypeError, UnicodeError):
            self._send(socket, {'id': ident, 'error': {'code': 'invalid_request', 'message': '本机会话请求无效。'}})

    @Slot(object)
    def _dispatch(self, envelope):
        socket, ident, method, args, session = envelope
        self._pending -= 1
        if not self.enabled or session != self._session or socket not in self._clients: return
        try:
            if QThread.currentThread() != self.ctrl.thread(): raise RuntimeError('控制器线程不匹配')
            result = self._call(method, args)
            self._send(socket, {'id': ident, 'result': result})
        except Exception as exc:
            # The wire error never includes the received envelope or token.
            self._send(socket, {'id': ident, 'error': {'code': 'operation_failed', 'message': str(exc)}})

    def _summary(self, index):
        photo = self.ctrl._photos[index]
        return {'id': photo['path'], 'path': photo['path'], 'index': index,
                'width': photo.get('width', 0), 'height': photo.get('height', 0),
                'current': index == self.ctrl.currentIndex, 'selected': index in self.ctrl._selected}

    def _index(self, photo='current'):
        if photo == 'current' and self.ctrl.currentIndex >= 0: return self.ctrl.currentIndex
        if not isinstance(photo, str): raise ValueError('photo 应为 current 或已打开照片的绝对路径')
        target = os.path.normcase(str(Path(photo).expanduser().resolve()))
        for index, row in enumerate(self.ctrl._photos):
            if os.path.normcase(row['path']) == target: return index
        raise ValueError('照片尚未在当前窗口打开。')

    def _mutation_allowed(self):
        if self.ctrl._closed: raise ValueError('窗口正在关闭。')
        if self.ctrl.exporting: raise ValueError('当前正在导出，请等待完成。')
        if self.ctrl._before is not None: raise ValueError('当前正在手动调整，请结束拖动后重试。')

    def _focus(self, photo):
        index = self._index(photo)
        if index != self.ctrl.currentIndex: self.ctrl.selectPhoto(index)
        return index

    def _selected_indices(self, photos):
        if photos is None: return self.ctrl.selectedIndices or ([self.ctrl.currentIndex] if self.ctrl.currentIndex >= 0 else [])
        if not isinstance(photos, list) or not photos: raise ValueError('photos 应为非空照片路径列表')
        return sorted({self._index(path) for path in photos})

    def _call(self, method, args):
        # Explicit dispatch, never getattr() from untrusted method strings.
        if method == 'status':
            self._state_changed()
            return {'scope': 'live-gui-session', 'session': self._session, 'pid': os.getpid(), 'offline': True,
                    'network': False, 'photos': [self._summary(i) for i in range(len(self.ctrl._photos))],
                    'current': self.ctrl.currentPath, 'selected': [self._summary(i)['id'] for i in self.ctrl.selectedIndices],
                    'busy': self.ctrl.busy, 'exporting': self.ctrl.exporting, 'status': self.ctrl.status,
                    'jobs': list(self._jobs.values()), 'methods': list(GUI_TOOL_SCHEMAS)}
        if method == 'job':
            if args['job'] not in self._jobs: raise ValueError('任务不存在或已过期。')
            self._state_changed()
            return dict(self._jobs[args['job']])
        if method == 'cancel_export':
            if args['job'] != self._export_job: raise ValueError('此导出任务已结束或不属于该接口。')
            self.ctrl.cancelBatchExport()
            return {'job': args['job'], 'cancellation_requested': True}
        if method == 'catalog':
            from .automation import AutomationSession
            # This pure catalog helper does not read or create a sidecar.
            result, _ = AutomationSession._catalog(self, {}, **args)
            result['recipes'] = self.ctrl.outputRecipes
            return result
        if method == 'get':
            index = self._index(args['photo'])
            settings = self.ctrl.settings if index == self.ctrl.currentIndex else asdict(_settings(self.ctrl._photos[index]['settings']))
            return dict(self._summary(index), settings=settings, can_undo=bool(self.ctrl._history.get(index)), can_redo=bool(self.ctrl._redo.get(index)))
        if method == 'describe':
            return self._describe(args.get('photo', 'current'))
        if method == 'preview_image':
            return self._preview_image(args.get('photo', 'current'), args.get('long_edge', 1280))
        self._mutation_allowed()
        if method in ('auto_meter','latitude','place'):
            return self._start_analysis(method, args)
        if method == 'open':
            values = args['paths']
            if not isinstance(values, list) or not 0 < len(values) <= 256: raise ValueError('每次 open 接收 1–256 张照片；更多照片可分批调用。')
            paths = [str(_source_path(path)) for path in values]
            job = self._new_job('open', paths=paths)
            self.ctrl.add_paths(paths)
            self._state_changed()
            return {'accepted': True, 'job': job['id'], 'scope': 'live-gui-session'}
        if method == 'set':
            index = self._focus(args['photo'])
            updates = args['settings']
            if not isinstance(updates, dict): raise ValueError('settings 应为对象')
            values = dict(self.ctrl.settings)
            values.update(updates)
            if 'stock' in updates and 'paper' not in updates:
                from shared.darkroom import paper_choices
                if values.get('paper') not in {'auto', *(p['id'] for p in paper_choices(values['stock']))}: values['paper'] = 'auto'
            canonical = _settings(values)
            previous = self.ctrl.settings
            self.ctrl._replace_tools(**{field.name: getattr(canonical, field.name) for field in fields(canonical)})
            return {'photo': self._summary(index)['id'], 'settings': self.ctrl.settings, 'changed': previous != self.ctrl.settings}
        if method in ('undo', 'redo'):
            index = self._focus(args['photo'])
            previous = self.ctrl.settings
            if method == 'undo': self.ctrl.undo()
            else: self.ctrl.redo()
            return {'photo': self._summary(index)['id'], 'changed': previous != self.ctrl.settings, 'settings': self.ctrl.settings}
        if method == 'copy':
            from shared.settings_sync import DEFAULT_CATEGORIES, category_fields, make_clip
            index = self._focus(args['photo'])
            categories = args.get('categories', list(DEFAULT_CATEGORIES))
            category_fields(categories)
            self.ctrl.copySettings(categories)
            return make_clip(self.ctrl.settings, categories, self.ctrl._photos[index]['name'])
        if method == 'paste':
            from shared.settings_sync import DEFAULT_CATEGORIES, category_fields
            categories = args.get('categories', list(DEFAULT_CATEGORIES))
            category_fields(categories)
            indices = self._selected_indices(args.get('photos'))
            if not indices or not self.ctrl.canPasteSettings: raise ValueError('未选择照片或参数剪贴板为空。')
            self.ctrl._selected = set(indices)
            self.ctrl.selectionChanged.emit()
            self.ctrl.pasteSettings(categories)
            return {'photos': [self._summary(i)['id'] for i in indices], 'count': len(indices)}
        if method == 'import_clip':
            from shared.settings_sync import normalize_clip, apply_clip
            clip = normalize_clip(_read_json(args['path'], MAX_REQUEST_BYTES))
            canonical = _settings(apply_clip(self.ctrl.settings, clip))
            normalized = asdict(canonical)
            self.ctrl.setSettingsClipboard(dict(clip,settings={key:normalized[key] for key in clip['settings']}))
            return {'source_name': clip['source_name'], 'categories': clip['categories']}
        if method == 'export_clip':
            from shared.settings_sync import make_clip
            clipboard = self.ctrl._settings_clipboard
            if not clipboard: raise ValueError('参数剪贴板为空。')
            info = self.ctrl.clipboardInfo
            clip = make_clip(clipboard, info['categories'], info['source_name'])
            target = Path(args['path']).expanduser().resolve()
            if target.exists(): raise ValueError('目标文件已存在，请使用新文件名。')
            _atomic_json(target, clip)
            return {'path': str(target)}
        if method == 'export':
            from shared.output_recipes import normalize_recipe
            if not self.ctrl.canStartExport: raise ValueError('请等待导入完成后导出。')
            recipe = args.get('recipe', 'jpg-high')
            if isinstance(recipe, str):
                recipe = next((item for item in self.ctrl._output_recipes if item.id == recipe), None)
                if recipe is None: raise ValueError('导出配方不存在。')
            recipe = replace(normalize_recipe(recipe), open_after=False)
            indices = self._selected_indices(args.get('photos'))
            if not indices: raise ValueError('没有选择导出照片。')
            self.ctrl._selected = set(indices)
            self.ctrl.selectionChanged.emit()
            destination = args.get('destination')
            if destination is not None:
                if not isinstance(destination, str) or not destination.strip(): raise ValueError('导出位置无效。')
                destination = str(Path(destination).expanduser().resolve())
            job = self._new_job('export', sources=[self.ctrl._photos[i]['path'] for i in indices], recipe=asdict(recipe))
            self._export_job = job['id']
            if not self.ctrl.export_recipe_batch(recipe, destination):
                job.update(state='failed', error='导出未启动，请检查所选照片和导出配方。')
                self._export_job = None
                raise ValueError(job['error'])
            return {'accepted': True, 'job': job['id'], 'source_resolution': recipe.long_edge == 0}
        raise ValueError('不支持的操作')

    def _describe(self, photo):
        from shared.darkroom import paper_choices
        index = self._index(photo)
        settings = self.ctrl.settings if index == self.ctrl.currentIndex else asdict(_settings(self.ctrl._photos[index]['settings']))
        stock = next((row for row in self.ctrl.stocks if row['id'] == settings['stock']), {})
        current = index == self.ctrl.currentIndex
        return dict(self._summary(index), filename=self.ctrl._photos[index]['name'],
            scope='live-gui-session', settings=settings,
            film=dict(enabled=settings['film_enabled'],mode='spectral' if settings['spectral'] else 'LUT',stock=stock,
                      paper=settings['paper'],compatible_papers=paper_choices(settings['stock'])),
            processing=dict(current=current,busy=self.ctrl.busy,status=self.ctrl.status if current else '',
                preview_ready=current and bool(self.ctrl.frame) and self.ctrl._display_generation == self.ctrl._generation,
                preview_long_edge=self.ctrl.preferences['preview_long_edge'],
                detail_state=self.ctrl.fullDetail.state if current else 'off',
                analysis_current=current and self.ctrl.analysisIsCurrent),
            analysis=self.ctrl.analysis if current and self.ctrl.analysisIsCurrent else {},
            can_undo=bool(self.ctrl._history.get(index)),can_redo=bool(self.ctrl._redo.get(index)),
            source_resolution_unchanged=True)

    def _preview_image(self, photo, long_edge):
        index = self._index(photo)
        if index != self.ctrl.currentIndex:
            raise ValueError('预览读取当前窗口照片；请先在窗口选中该照片。')
        if isinstance(long_edge,bool) or not isinstance(long_edge,int) or not 64 <= long_edge <= 2048:
            raise ValueError('long_edge 需要 64–2048 之间的整数。')
        if not self.ctrl.frame or self.ctrl._display_generation != self.ctrl._generation:
            return dict(photo=self.ctrl.currentPath,state='rendering',retry_after_ms=160,
                        scope='live-gui-session',preview_only=True)
        with self.ctrl.provider.lock:
            image = QImage(self.ctrl.provider.images.get('frame',QImage()))
        if image.isNull(): raise ValueError('当前窗口尚无可读取的照片预览。')
        if max(image.width(),image.height()) > long_edge:
            image = image.scaled(long_edge,long_edge,Qt.KeepAspectRatio,Qt.SmoothTransformation)
        buffer = QBuffer(); buffer.open(QIODevice.WriteOnly)
        if not image.save(buffer,'JPEG',92): raise ValueError('预览图片编码失败。')
        data = base64.b64encode(bytes(buffer.data())).decode('ascii'); buffer.close()
        return dict(photo=self.ctrl.currentPath,state='ready',scope='live-gui-session',
            width=image.width(),height=image.height(),preview_only=True,
            color_domain='monitor-managed-display',source_resolution_unchanged=True,
            image=dict(mimeType='image/jpeg',data=data))

    def _start_analysis(self, method, args):
        if self.ctrl.analysisBusy: raise ValueError('已有测光或宽容度任务正在运行。')
        target = args.get('target','both')
        metering = args.get('method','balanced')
        if target not in ('exposure','filter_pack','both') or metering not in ('balanced','center','protect_highlights','protect_shadows'):
            raise ValueError('自动配光目标或测光方式无效。')
        index = self._focus(args.get('photo','current'))
        from .disk_cache import source_identity
        stamp = source_identity(self.ctrl.currentPath)
        job = self._new_job(method,photo=self.ctrl.currentPath,source_stamp=stamp)
        before = set(self.ctrl._jobs)
        if method == 'auto_meter': self.ctrl.autoMeter(target,metering)
        else: self.ctrl.measureLatitude()
        worker = next((worker for ident,worker in self.ctrl._jobs.items()
            if ident not in before and worker.context.get('kind') == 'analysis'),None)
        if worker is None:
            job.update(state='failed',error='分析任务未启动。',finished=time.time())
            raise ValueError(job['error'])
        native_job = worker.context['job']
        self._analysis_jobs[native_job] = job['id']
        # The controller connected first; its canonical settings/history update
        # finishes before this observer records or safely applies Scene Placement.
        worker.signals.done.connect(self._analysis_done)
        job.update(state='running',target=target if method == 'auto_meter' else 'latitude',method=metering)
        return dict(accepted=True,job=job['id'],scope='live-gui-session')

    @Slot(object)
    def _analysis_done(self, result):
        ident = self._analysis_jobs.pop(result.get('job'),None)
        if ident is None or ident not in self._jobs: return
        job = self._jobs[ident]
        job['finished'] = time.time()
        if not result['ok']:
            job.update(state='failed',error=result.get('error','分析失败。')); return
        try:
            from .disk_cache import source_identity
            stamp = source_identity(job['photo'])
        except OSError: stamp = None
        key = 'metering' if job['kind'] == 'auto_meter' else 'latitude'
        current = (self.ctrl.currentPath == job['photo'] and self.ctrl.analysisIsCurrent
            and self.ctrl.analysis.get(key) == result['value'] and stamp == job['source_stamp'])
        if not current:
            job.update(state='discarded',error='照片或参数已变化，此分析结果未应用。'); return
        applied = job['kind'] == 'auto_meter'
        if job['kind'] == 'place':
            fit = result['value'].get('fit',{})
            if fit.get('valid') and not self.ctrl.exporting and self.ctrl._before is None:
                self.ctrl.applyLatitude(); applied = bool(self.ctrl.analysis.get('applied'))
        job.update(state='completed',result=dict(analysis=result['value'],applied=applied,
            settings=self.ctrl.settings,photo=self.ctrl.currentPath))

    def _new_job(self, kind, **extra):
        while len(self._jobs) >= 64:
            old = next((key for key, value in self._jobs.items() if value['state'] not in ('queued', 'running')), None)
            if old is None: raise ValueError('任务过多，请等待已提交任务。')
            self._jobs.pop(old)
        job = dict(id=uuid.uuid4().hex, kind=kind, state='queued', created=time.time(), **extra)
        self._jobs[job['id']] = job
        return job

    @Slot()
    def _state_changed(self):
        for job in self._jobs.values():
            if job['kind'] == 'open' and job['state'] in ('queued', 'running'):
                job['state'] = 'running'
                loaded = {os.path.normcase(p['path']) for p in self.ctrl._photos}
                job['completed'] = [p for p in job['paths'] if os.path.normcase(p) in loaded]
                if not self.ctrl._importing and not self.ctrl._import_queue and not self.ctrl._queued_paths:
                    missing = [p for p in job['paths'] if os.path.normcase(p) not in loaded]
                    job.update(state='failed' if missing else 'completed', missing=missing, finished=time.time())
        if self._export_job:
            job = self._jobs[self._export_job]
            if self.ctrl.exporting:
                job.update(state='running', done=max(job.get('done', 0), self.ctrl.batchProgress),
                           total=self.ctrl.batchTotal, status=self.ctrl.status)
            elif job['state'] == 'running':
                result = deepcopy_dict(self.ctrl.batchResult)
                state = 'cancelled' if result.get('cancelled') else 'failed' if result.get('errors') else 'completed'
                job.update(state=state, result=result, finished=time.time())
                self._export_job = None


def deepcopy_dict(value):
    return _parse_json(_json(value))


class GuiAutomationClient:
    """Blocking console/MCP client only; never call this from the GUI Qt thread."""
    scope = 'live-gui-session'
    tool_schemas = GUI_TOOL_SCHEMAS

    def __init__(self, *, directory=None, session=None, timeout_ms=5000):
        global _CLIENT_APPLICATION
        if QCoreApplication.instance() is None:
            _CLIENT_APPLICATION = QCoreApplication([])
            QCoreApplication.setOrganizationName('SpektraFilm')
            QCoreApplication.setApplicationName('SpektraFilm')
        self._timeout = max(1000, min(30_000, int(timeout_ms)))
        directory = Path(directory) if directory else default_endpoint_directory()
        records = []
        if directory.is_dir():
            for path in directory.glob('gui-*.json'):
                try:
                    record = _read_json(path, 8192)
                    if (record.get('protocol') != PROTOCOL or not isinstance(record.get('token'), str)
                            or len(record['token']) < 32 or not isinstance(record.get('session'), str)):
                        continue
                    expected = f"SpektraFilm-{int(record['pid'])}-{record['session']}"
                    if record.get('server') != expected or (session and record['session'] != session): continue
                    records.append(record)
                except (OSError, ValueError, KeyError, TypeError): continue
        live = []
        for record in records:
            self._record = record
            try:
                self.call('status', {}, timeout_ms=750)
                live.append(record)
            except (OSError, ValueError): continue
        if not live: raise ValueError('未找到已启用的 SpektraFilm 窗口。请在应用设置中开启本机会话接口。')
        if len(live) > 1: raise ValueError('已开启多个窗口，请用 --gui-session 指定：' + ', '.join(r['session'] for r in live))
        self._record = live[0]

    def call(self, method, arguments=None, *, timeout_ms=None):
        if method not in GUI_TOOL_SCHEMAS: raise ValueError('GUI 不支持此操作。')
        socket = QLocalSocket()
        wait = int(timeout_ms or self._timeout)
        socket.connectToServer(self._record['server'])
        if not socket.waitForConnected(wait):
            socket.abort()
            raise OSError('本机会话连接不可用。')
        request = {'id': uuid.uuid4().hex, 'token': self._record['token'], 'method': method,
                   'arguments': {} if arguments is None else arguments}
        content = (_json(request) + '\n').encode('utf-8')
        if len(content) > MAX_REQUEST_BYTES: raise ValueError('请求超过 8 MiB。')
        socket.write(content)
        socket.flush()
        buffer = bytearray()
        deadline = time.monotonic() + wait / 1000
        try:
            while b'\n' not in buffer:
                if socket.bytesAvailable(): buffer.extend(bytes(socket.readAll()))
                if len(buffer) > 64 * 1024 * 1024: raise ValueError('响应过大。')
                if b'\n' in buffer: break
                remaining = int(max(0, deadline - time.monotonic()) * 1000)
                if not remaining or not socket.waitForReadyRead(remaining):
                    if socket.bytesAvailable(): continue
                    raise ValueError('操作响应超时；写操作结果未知，请刷新窗口状态后再决定是否重试。')
            reply = _parse_json(bytes(buffer).split(b'\n', 1)[0])
            if reply.get('id') != request['id']: raise ValueError('会话响应编号不匹配。')
            if 'error' in reply: raise ValueError(reply['error'].get('message', '操作失败。'))
            return reply['result']
        finally:
            socket.abort()
