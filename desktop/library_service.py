"""Asynchronous local transport for the MIT SpektraLab_library SDK.

The child owns SQLite connections and executes requests in order. No database,
catalog scan or waitFor* call runs on Qt's UI thread. The method/params/results
are the unmodified ABI 1 contract in native/library/API-SPEC.md. Never replay
mutations automatically: a timeout or process loss can have an unknown outcome.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys

from PySide6.QtCore import QObject, Property, QProcess, QStandardPaths, QTimer, Signal, Slot


ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
DEFAULT_HELPER = ROOT / 'native/library/runtime/spklib-host.exe'
MAX_REQUEST_BYTES = 8 * 1024 * 1024
MAX_REPLY_BYTES = 64 * 1024 * 1024
MAX_PENDING = 128


@dataclass
class _Request:
    method: str
    wire: bytes
    timeout_ms: int
    timer: QTimer | None = None
    sent: bool = False


class LibraryService(QObject):
    """Own one helper; connect ``result``/``failed`` before submitting requests.

    ``call()`` returns a monotonically increasing request ID and starts the
    helper lazily. ``ready`` also supplies SDK version/protocol metadata. The
    result/error payload is a normal Python dictionary suitable for a model.
    A restart invalidates every library handle; clients must reopen explicitly.
    """

    ready = Signal(dict)
    readyChanged = Signal()
    result = Signal(int, str, dict)
    failed = Signal(int, str, dict)
    stopped = Signal()
    diagnostic = Signal(str)

    def __init__(self, parent=None, *, store=None, helper=None):
        super().__init__(parent)
        self._helper = Path(helper) if helper is not None else DEFAULT_HELPER
        default_store = Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)) / 'Libraries'
        self._store = Path(store) if store is not None else default_store
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.SeparateChannels)
        self._process.readyReadStandardOutput.connect(self._read_stdout)
        self._process.readyReadStandardError.connect(self._read_stderr)
        self._process.errorOccurred.connect(self._process_error)
        self._process.finished.connect(self._finished)
        self._pending: dict[int, _Request] = {}
        self._next_id = 1
        self._ready = False
        self._closing = False
        self._stdout = bytearray()
        self._stderr = bytearray()
        self._startup = QTimer(self)
        self._startup.setSingleShot(True)
        self._startup.timeout.connect(self._startup_timeout)
        self._shutdown = QTimer(self)
        self._shutdown.setSingleShot(True)
        self._shutdown.timeout.connect(self._process.kill)

    @Property(bool, notify=readyChanged)
    def isReady(self):
        return self._ready

    @Property(str, constant=True)
    def helperPath(self):
        return str(self._helper)

    def _set_ready(self, value):
        if self._ready != value:
            self._ready = value
            self.readyChanged.emit()

    @Slot()
    def start(self):
        if self._process.state() != QProcess.NotRunning:
            return
        self._closing = False
        self._stdout.clear()
        self._stderr.clear()
        if not self._helper.is_file():
            self._fail_all('helper_missing', '资料库组件尚未安装。', unknown=False)
            self.diagnostic.emit('Library helper missing: ' + str(self._helper))
            return
        self._process.setProgram(str(self._helper))
        self._process.setArguments(['--store', str(self._store)])
        self._process.start()
        self._startup.start(10_000)

    def call(self, method: str, params: dict | None = None, *, timeout_ms=30_000) -> int:
        """Submit without blocking; ID is also carried by either completion signal.

        A queued request starts its timeout only when sent after the handshake.
        ``timeout`` means refresh state before retrying any mutation; SQLite
        transactions and persisted session move intents remain SDK-owned.
        """
        if not isinstance(method, str) or not method or (params is not None and not isinstance(params, dict)):
            raise ValueError('method must be nonempty and params must be an object')
        if self._closing:
            raise RuntimeError('library helper is shutting down')
        if len(self._pending) >= MAX_PENDING:
            raise RuntimeError('too many pending library requests')
        rid = self._next_id
        self._next_id += 1
        wire = (json.dumps({'id': rid, 'method': method, 'params': params or {}},
                           ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')
        if len(wire) > MAX_REQUEST_BYTES:
            raise ValueError('library request exceeds 8 MiB')
        self._pending[rid] = _Request(method, wire, max(1000, int(timeout_ms)))
        if self._ready:
            self._send(rid)
        else:
            # Defer so callers can register their request ID before completion.
            QTimer.singleShot(0, self.start)
        return rid

    def _send(self, rid):
        item = self._pending.get(rid)
        if item is None or item.sent:
            return
        item.sent = True
        item.timer = QTimer(self)
        item.timer.setSingleShot(True)
        item.timer.timeout.connect(lambda request_id=rid: self._request_timeout(request_id))
        if self._process.write(item.wire) != len(item.wire):
            self._fail_one(rid, {'code': 'transport', 'message': '资料库请求发送失败。',
                                 'data': {'outcome_unknown': True}})
            return
        item.timer.start(item.timeout_ms)

    def _take(self, rid):
        item = self._pending.pop(rid, None)
        if item is not None and item.timer is not None:
            item.timer.stop()
            item.timer.deleteLater()
        return item

    def _fail_one(self, rid, error):
        item = self._take(rid)
        if item is not None:
            self.failed.emit(rid, item.method, error)

    def _fail_all(self, code, message, *, unknown):
        for rid, item in list(self._pending.items()):
            self._fail_one(rid, {'code': code, 'message': message,
                                'data': {'outcome_unknown': bool(unknown and item.sent)}})

    def _request_timeout(self, rid):
        self._fail_one(rid, {'code': 'timeout', 'message': '资料库操作超时，请刷新状态后重试。',
                             'data': {'outcome_unknown': True}})

    def _startup_timeout(self):
        self._fail_all('startup_timeout', '资料库组件启动超时。', unknown=False)
        self._process.kill()

    @Slot()
    def _read_stdout(self):
        self._stdout.extend(bytes(self._process.readAllStandardOutput()))
        while b'\n' in self._stdout:
            line, _, remaining = self._stdout.partition(b'\n')
            self._stdout = bytearray(remaining)
            if len(line) > MAX_REPLY_BYTES:
                self._protocol_error('资料库响应过大，请缩小分页。')
                return
            if not line.strip():
                continue
            try:
                reply = json.loads(line.decode('utf-8'))
                if not isinstance(reply, dict):
                    raise ValueError('response is not an object')
                if reply.get('event') == 'ready':
                    if reply.get('protocol') != 1:
                        raise ValueError('unsupported helper protocol')
                    self._startup.stop()
                    self._set_ready(True)
                    self.ready.emit(reply)
                    for rid in list(self._pending):
                        self._send(rid)
                    continue
                rid = reply.get('id')
                if not isinstance(rid, int):
                    raise ValueError('missing numeric request id')
                item = self._take(rid)
                if item is None:
                    continue  # timed out or shutdown: never apply a late result
                payload = reply.get('error') if 'error' in reply else reply.get('result')
                if not isinstance(payload, dict):
                    self.failed.emit(rid, item.method, {'code': 'protocol', 'message': '无效的资料库响应。', 'data': None})
                elif 'error' in reply:
                    self.failed.emit(rid, item.method, payload)
                else:
                    self.result.emit(rid, item.method, payload)
            except (UnicodeError, ValueError, TypeError) as exc:
                self._protocol_error('资料库响应格式无效。' + str(exc))
                return
        if len(self._stdout) > MAX_REPLY_BYTES:
            self._protocol_error('资料库响应过大，请缩小分页。')

    def _protocol_error(self, message):
        self._set_ready(False)
        self._fail_all('protocol', message, unknown=True)
        self._process.kill()

    @Slot()
    def _read_stderr(self):
        self._stderr.extend(bytes(self._process.readAllStandardError()))
        self._stderr = self._stderr[-65_536:]
        self.diagnostic.emit(self._stderr.decode('utf-8', errors='replace'))

    def _process_error(self, error):
        if error == QProcess.FailedToStart:
            self._startup.stop()
            self._set_ready(False)
            self._fail_all('start_failed', '资料库组件无法启动。', unknown=False)
            self.diagnostic.emit(self._process.errorString())

    def _finished(self, exit_code, exit_status):
        self._startup.stop()
        self._shutdown.stop()
        self._set_ready(False)
        self._fail_all('process_stopped', '资料库组件已关闭，请重新打开资料库。', unknown=True)
        if not self._closing and (exit_code or exit_status == QProcess.CrashExit):
            self.diagnostic.emit('Library helper exited: ' + str(exit_code))
        self.stopped.emit()

    @Slot()
    def close(self):
        """Queue graceful shutdown; the event loop remains live for up to 2 s."""
        self._closing = True
        self._startup.stop()
        self._set_ready(False)
        if self._process.state() == QProcess.NotRunning:
            self._fail_all('closed', '资料库组件已关闭。', unknown=False)
            return
        self._process.write(b'{"id":0,"method":"host.shutdown","params":{}}\n')
        self._shutdown.start(2000)
