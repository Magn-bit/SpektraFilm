"""Current-user photo-open handoff, independent of optional GUI automation.

Only local photo paths and an activate request cross the pipe. A locked owner
starts the endpoint before editor initialization; requests queue until bind().
No decoder, shell, Python evaluation or arbitrary command is exposed here.
"""
from __future__ import annotations

from collections import deque
import json
import os
from pathlib import Path
import sys
import time

from PySide6.QtCore import QEvent,QIODevice,QLockFile,QObject,QStandardPaths,QTimer,QUrl
from PySide6.QtGui import QWindow
from PySide6.QtNetwork import QLocalServer,QLocalSocket

from shared.photo_formats import PHOTO_EXTENSIONS

MAX_BYTES=4*1024*1024
MAX_PATHS=8192


def _user_id():
    if os.name!='nt':return str(os.getuid())
    import ctypes as ct
    from ctypes import wintypes as wt
    advapi=ct.WinDLL('advapi32',use_last_error=True);kernel=ct.WinDLL('kernel32',use_last_error=True)
    advapi.OpenProcessToken.argtypes=[wt.HANDLE,wt.DWORD,ct.POINTER(wt.HANDLE)]
    advapi.GetTokenInformation.argtypes=[wt.HANDLE,ct.c_int,ct.c_void_p,wt.DWORD,ct.POINTER(wt.DWORD)]
    advapi.ConvertSidToStringSidW.argtypes=[ct.c_void_p,ct.POINTER(wt.LPWSTR)]
    kernel.GetCurrentProcess.restype=wt.HANDLE;kernel.CloseHandle.argtypes=[wt.HANDLE];kernel.LocalFree.argtypes=[ct.c_void_p]
    token,text=wt.HANDLE(),wt.LPWSTR()
    try:
        if not advapi.OpenProcessToken(kernel.GetCurrentProcess(),0x0008,ct.byref(token)):raise OSError('无法读取当前用户身份')
        size=wt.DWORD();advapi.GetTokenInformation(token,1,None,0,ct.byref(size));buffer=ct.create_string_buffer(size.value)
        if not advapi.GetTokenInformation(token,1,buffer,size,ct.byref(size)):raise OSError('无法读取当前用户身份')
        sid=ct.cast(buffer,ct.POINTER(ct.c_void_p))[0]
        if not advapi.ConvertSidToStringSidW(sid,ct.byref(text)):raise OSError('无法读取当前用户身份')
        return text.value
    finally:
        if token:kernel.CloseHandle(token)
        if text:kernel.LocalFree(ct.cast(text,ct.c_void_p))


def photo_paths(values):
    result=[];seen=set()
    for value in values:
        if not isinstance(value,str) or len(value)>32768:continue
        value=QUrl(value).toLocalFile() if value.startswith('file:') else value
        if not value or '\0' in value:continue
        path=Path(value).expanduser().absolute()
        key=os.path.normcase(str(path))
        if path.suffix.lower() in PHOTO_EXTENSIONS and key not in seen:
            result.append(str(path));seen.add(key)
        if len(result)>=MAX_PATHS:break
    return result


def _json(record):return json.dumps(record,ensure_ascii=False,separators=(',',':')).encode('utf-8')+b'\n'


def _line(socket,timeout):
    deadline=time.monotonic()+timeout/1000
    while not socket.canReadLine():
        remaining=int((deadline-time.monotonic())*1000)
        if remaining<=0 or socket.bytesAvailable()>MAX_BYTES or not socket.waitForReadyRead(remaining):
            raise OSError('已有窗口未响应，请稍后重试打开照片')
    data=bytes(socket.readLine(MAX_BYTES+1))
    if len(data)>MAX_BYTES:raise OSError('窗口转交消息过大')
    return json.loads(data)


class SingleInstance(QObject):
    def __init__(self,app,*,directory=None,name=None):
        super().__init__(app)
        self.app=app
        self.directory=Path(directory or QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation))
        self.name=name or 'SpektraFilm.Desktop.Open.v1.'+_user_id()
        self.directory.mkdir(parents=True,exist_ok=True)
        self.lock=QLockFile(str(self.directory/'window-instance.lock'))
        self.lock.setStaleLockTime(0)
        self.server=QLocalServer(self);self.server.setSocketOptions(QLocalServer.UserAccessOption)
        self.server.setMaxPendingConnections(8);self.server.newConnection.connect(self._accept)
        self._clients={};self._pending=deque();self._pending_keys=set()
        self._window=None;self._controller=None;self._primary=False;self._activate_pending=False
        self._drain_timer=QTimer(self);self._drain_timer.setSingleShot(True);self._drain_timer.timeout.connect(self._drain)
        app.installEventFilter(self)
        app.aboutToQuit.connect(self.close)

    def claim_or_forward(self,paths):
        paths=photo_paths(paths)
        if self.lock.tryLock(0):
            if self.server.listen(self.name):
                self._primary=True;self._queue(paths);return False
            # An older owner may still be serving this named endpoint. Never
            # remove a live server merely because this process got a file lock.
            self.lock.unlock()
        self._forward(paths)
        return True

    def _forward(self,paths):
        socket=QLocalSocket(self)
        try:
            socket.connectToServer(self.name,QIODevice.ReadWrite)
            if not socket.waitForConnected(1500):raise OSError('无法连接已有 SpektraFilm 窗口，请稍后重试')
            hello=_line(socket,8000)
            if not isinstance(hello,dict) or hello.get('protocol')!=1 or not isinstance(hello.get('pid'),int) or hello['pid']<=0:raise OSError('窗口转交协议不兼容')
            if os.name=='nt':
                import ctypes
                ctypes.windll.user32.AllowSetForegroundWindow(hello['pid'])
            socket.write(_json(dict(protocol=1,paths=paths)))
            socket.flush()
            reply=_line(socket,3000)
            if not isinstance(reply,dict) or reply.get('ok') is not True:
                raise OSError(reply.get('error') if isinstance(reply,dict) and reply.get('error') else '已有窗口未接受照片')
        except (ValueError,TypeError) as error:
            raise OSError('窗口转交消息无效') from error
        finally:
            socket.disconnectFromServer();socket.deleteLater()

    def _accept(self):
        while self.server.hasPendingConnections():
            socket=self.server.nextPendingConnection()
            if len(self._clients)>=8:socket.abort();socket.deleteLater();continue
            timer=QTimer(socket);timer.setSingleShot(True);timer.setInterval(4000);timer.timeout.connect(socket.abort);timer.start()
            self._clients[socket]=timer
            socket.disconnected.connect(lambda current=socket:self._disconnected(current))
            socket.readyRead.connect(lambda current=socket:self._read(current))
            socket.write(_json(dict(protocol=1,pid=os.getpid())));socket.flush()

    def _disconnected(self,socket):
        self._clients.pop(socket,None);socket.deleteLater()

    def _read(self,socket):
        if socket.bytesAvailable()>MAX_BYTES:socket.abort();return
        if not socket.canReadLine():return
        try:
            record=json.loads(bytes(socket.readLine(MAX_BYTES+1)))
            if not isinstance(record,dict) or record.get('protocol')!=1 or not isinstance(record.get('paths'),list):raise ValueError()
            if len(record['paths'])>MAX_PATHS:raise ValueError()
            paths=photo_paths(record['paths'])
            if len(self._pending)+len(paths)>MAX_PATHS:raise ValueError()
            self._queue(paths)
            socket.write(_json(dict(ok=True)));socket.flush();socket.disconnectFromServer()
        except (ValueError,TypeError,OSError):
            socket.write(_json(dict(ok=False,error='照片列表无效或待导入照片过多')));socket.flush();socket.disconnectFromServer()

    def _queue(self,paths):
        for path in paths:
            key=os.path.normcase(path)
            if key not in self._pending_keys:self._pending.append(path);self._pending_keys.add(key)
        self._activate_pending=True
        self._drain_timer.start(0)

    def bind(self,window,controller):
        self._window=window;self._controller=controller
        controller.stateChanged.connect(self._state_changed)
        self._drain_timer.start(0)

    def _state_changed(self):
        if self._pending and not self._controller.exporting and not self._drain_timer.isActive():self._drain_timer.start(0)

    def _activate(self):
        window=self._window
        if not window:return
        if window.visibility()==QWindow.Minimized:
            if sys.platform=='win32':
                import ctypes
                from ctypes import wintypes
                show=ctypes.WinDLL('user32').ShowWindow;show.argtypes=[wintypes.HWND,ctypes.c_int]
                show(int(window.winId()),9)
            else:window.showNormal()
        elif not window.isVisible():window.show()
        window.raise_();window.requestActivate()

    def _drain(self):
        if not self._window or not self._controller:return
        if self._activate_pending:self._activate_pending=False;self._activate()
        if self._controller.exporting:return
        paths=[]
        while self._pending and len(paths)<128:
            path=self._pending.popleft();self._pending_keys.discard(os.path.normcase(path));paths.append(path)
        if paths:self._controller.add_paths(paths)
        if self._pending:self._drain_timer.start(32)

    def eventFilter(self,watched,event):
        if watched is self.app and event.type()==QEvent.FileOpen:
            value=event.file() or event.url().toLocalFile()
            self._queue(photo_paths([value]));event.accept();return True
        return False

    def close(self):
        self._drain_timer.stop();self.server.close()
        for socket in list(self._clients):socket.abort()
        self._clients.clear()
        if self._primary:self.lock.unlock();self._primary=False
        self.app.removeEventFilter(self)
