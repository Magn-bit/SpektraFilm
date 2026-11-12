"""Explicit reference-release check, with cancellable Qt network I/O."""
import json
from PySide6.QtCore import QObject,Property,Signal,Slot,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QNetworkAccessManager,QNetworkRequest

class UpdateCheck(QObject):
    changed=Signal()
    def __init__(self,parent):
        super().__init__(parent);self._reply=None;self._status='';self._url='';self._closed=False
        self._network=QNetworkAccessManager(self)
    @Property(bool,notify=changed)
    def busy(self):return self._reply is not None
    @Property(str,notify=changed)
    def status(self):return self._status
    @Property(bool,notify=changed)
    def available(self):return bool(self._url)
    @Slot()
    def check(self):
        if self._reply is not None or self._closed:return
        request=QNetworkRequest(QUrl('https://api.github.com/repos/JamesQiu2005/SpektraLab/releases/latest'))
        request.setRawHeader(b'Accept',b'application/vnd.github+json');request.setRawHeader(b'User-Agent',b'SpektraFilm')
        request.setTransferTimeout(10000)
        self._reply=self._network.get(request);self._reply.finished.connect(self._done)
        self._reply.downloadProgress.connect(self._limit)
        self._status='正在检查参考引擎更新…';self.changed.emit()
    def _limit(self,received,total):
        if self._reply is not None and (received>1048576 or total>1048576):self._reply.abort()
    def _done(self):
        reply,self._reply=self._reply,None
        if reply is None:return
        try:
            if reply.error():raise ValueError()
            record=json.loads(bytes(reply.readAll()));url=str(record.get('html_url',''))
            if not url.startswith('https://github.com/JamesQiu2005/SpektraLab/releases/'):raise ValueError()
            self._url=url;self._status=str(record['tag_name'])[:80]+' · '+str(record.get('published_at',''))[:10]
        except (ValueError,KeyError,TypeError):
            self._url='';self._status='暂时无法连接更新来源，请稍后重试。'
        finally:reply.deleteLater()
        if not self._closed:self.changed.emit()
    @Slot()
    def openRelease(self):
        if self._url:QDesktopServices.openUrl(QUrl(self._url))
    def close(self):
        self._closed=True
        if self._reply is not None:self._reply.abort()
