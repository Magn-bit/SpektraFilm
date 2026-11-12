"""Remember normal window geometry and maximize state in Qt logical pixels."""
import json
import sys
from pathlib import Path
from PySide6.QtCore import QObject, QRect, QSettings, QTimer, Qt, Slot
from PySide6.QtGui import QGuiApplication, QWindow

def available_screens():
    return [screen.availableGeometry() for screen in QGuiApplication.screens()]

def visible_geometry(rect, available):
    """Keep restored windows reachable after monitor/DPI/layout changes."""
    if not available:
        return rect
    center=rect.center()
    screen=next((r for r in available if r.contains(center)),None)
    if screen is None:
        screen=max(available,key=lambda r: max(0,r.intersected(rect).width())*max(0,r.intersected(rect).height()))
    width=min(max(1120,rect.width()),screen.width())
    height=min(max(760,rect.height()),screen.height())
    x=max(screen.x(),min(rect.x(),screen.right()-width+1))
    y=max(screen.y(),min(rect.y(),screen.bottom()-height+1))
    return QRect(x,y,width,height)

class WindowState(QObject):
    def __init__(self,window,path):
        super().__init__(window)
        self.window=window
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.store=QSettings(str(path),QSettings.IniFormat)
        self.normal=QRect(window.geometry())
        self.maximized=False
        self._restoring=False
        self.timer=QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(350)
        self.timer.timeout.connect(self.save)
        for signal in (window.xChanged,window.yChanged,window.widthChanged,window.heightChanged):
            signal.connect(self._changed)
        window.visibilityChanged.connect(self._visibility)

    def restore(self):
        try:
            data=json.loads(self.store.value('window/state','{}'))
            values=data.get('normal') if isinstance(data,dict) else None
            if (isinstance(values,list) and len(values)==4
                and all(type(v) is int and abs(v)<2**30 for v in values)
                and values[2]>0 and values[3]>0):
                self.normal=QRect(*values)
                self.maximized=data.get('maximized') is True
        except (ValueError,TypeError):
            pass
        screens=available_screens()
        self.normal=visible_geometry(self.normal,screens)
        screen=next((r for r in screens if r.contains(self.normal.center())),self.normal)
        self._restoring=True
        try:
            self.window.setMinimumWidth(min(1120,max(1,screen.width())))
            self.window.setMinimumHeight(min(760,max(1,screen.height())))
            self.window.setGeometry(self.normal)
            if self.maximized: self.window.showMaximized()
            else: self.window.showNormal()
        finally:
            self._restoring=False

    def _changed(self,*args):
        if self._restoring: return
        if self.window.visibility()==QWindow.Windowed and not self.maximized:
            self.normal=QRect(self.window.geometry())
        self.timer.start()

    def _visibility(self,visibility):
        if self._restoring: return
        if visibility==QWindow.Maximized: self.maximized=True
        elif visibility==QWindow.Windowed:
            self.maximized=False
        self.timer.start()

    @Slot()
    def restoreNormal(self):
        """Qt's frameless showNormal can leave the Windows HWND maximized."""
        rect=QRect(self.normal)
        self._restoring=True
        try:
            if sys.platform=='win32' and QGuiApplication.platformName()=='windows':
                import ctypes
                from ctypes import wintypes
                restore=ctypes.WinDLL('user32').ShowWindow
                restore.argtypes=[wintypes.HWND,ctypes.c_int]
                restore.restype=wintypes.BOOL
                restore(int(self.window.winId()),9)
            else:
                self.window.showNormal()
            self.window.setGeometry(rect)
            self.normal=rect
            self.maximized=False
        finally:
            self._restoring=False
        self.timer.start()

    def save(self):
        self.timer.stop()
        if self.window.windowState()==Qt.WindowNoState and not self.maximized:
            self.normal=QRect(self.window.geometry())
        rect=self.normal
        data=dict(version=1,normal=[rect.x(),rect.y(),rect.width(),rect.height()],maximized=self.maximized)
        self.store.setValue('window/state',json.dumps(data))
        self.store.sync()
