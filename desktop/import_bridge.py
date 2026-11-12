"""One local-photo import boundary for Qt drops, Explorer and the clipboard."""
from __future__ import annotations
import sys
from pathlib import Path
from PySide6.QtCore import QObject, QEvent, QAbstractNativeEventFilter, QUrl
from PySide6.QtGui import QGuiApplication
from shared.photo_formats import PHOTO_EXTENSIONS

def mime_paths(mime):
    if mime is None:
        return []
    candidates = [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]
    if not candidates:
        key = 'application/x-qt-windows-mime;value="FileNameW"'
        if mime.hasFormat(key):
            candidates = bytes(mime.data(key)).decode('utf-16-le', errors='ignore').strip('\0').split('\0')
    if not candidates and mime.hasText():
        for line in mime.text().splitlines():
            value = line.strip().strip('"')
            if value.startswith('file:'):
                value = QUrl(value).toLocalFile()
            if value and Path(value).is_absolute():
                candidates.append(value)
    # DragEnter/DragMove are high-frequency GUI events. Only inspect the MIME
    # shape here; actual file validation belongs to the background import job.
    return [p for p in candidates if p and Path(p).is_absolute() and Path(p).suffix.lower() in PHOTO_EXTENSIONS]

def has_photos(mime):
    return bool(mime_paths(mime)) or bool(mime and mime.hasImage())

class PhotoImportBridge(QObject, QAbstractNativeEventFilter):
    """Accept drops on the window, independent of QML stacking/layer masks.

    WM_DROPFILES is a narrow Explorer fallback, also useful when the launching
    terminal and Explorer have different integrity levels. No arbitrary window
    messages or clipboard content are executed.
    """
    def __init__(self, app, window, controller):
        QObject.__init__(self, window)
        QAbstractNativeEventFilter.__init__(self)
        self.app, self.window, self.controller = app, window, controller
        self.hwnd = int(window.winId()) if sys.platform == 'win32' else 0
        window.installEventFilter(self)
        if self.hwnd:
            import ctypes
            ctypes.windll.shell32.DragAcceptFiles(self.hwnd, True)
            # Explorer's legacy file drop uses these two specific messages.
            change = getattr(ctypes.windll.user32, 'ChangeWindowMessageFilterEx', None)
            if change:
                for message in (0x0233, 0x0049):
                    change(self.hwnd, message, 1, None)
            app.installNativeEventFilter(self)

    def eventFilter(self, watched, event):
        if watched is self.window and event.type() in (QEvent.DragEnter, QEvent.DragMove, QEvent.Drop):
            if not self.controller.exporting and has_photos(event.mimeData()):
                event.acceptProposedAction()
                if event.type() == QEvent.Drop:
                    self.controller.import_mime(event.mimeData())
                return True
        return False

    def nativeEventFilter(self, event_type, message):
        if not self.hwnd:
            return False, 0
        import ctypes
        from ctypes import wintypes
        msg = wintypes.MSG.from_address(int(message))
        if msg.hWnd != self.hwnd or msg.message != 0x0233:
            return False, 0
        shell = ctypes.windll.shell32
        shell.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
        shell.DragFinish.argtypes = [wintypes.HANDLE]
        handle = msg.wParam
        paths = []
        try:
            count = shell.DragQueryFileW(handle, 0xffffffff, None, 0)
            for index in range(count):
                length = shell.DragQueryFileW(handle, index, None, 0)
                buffer = ctypes.create_unicode_buffer(length + 1)
                shell.DragQueryFileW(handle, index, buffer, length + 1)
                paths.append(buffer.value)
        finally:
            shell.DragFinish(handle)
        self.controller.add_paths(paths)
        return True, 0
