"""Shared application identity for the GUI and documentation capture windows."""
from pathlib import Path
import sys

APP_ID = 'SpektraFilm.Desktop'


def configure_process_identity():
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)


def configure_application_icon(app, root):
    from PySide6.QtGui import QIcon
    # PNG is decoded by Qt itself, including during early plugin startup.
    icon = QIcon(str(Path(root) / 'assets/icons/spektrafilm-1024.png'))
    icon.addFile(str(Path(root) / 'assets/icons/spektrafilm.ico'))
    if icon.isNull():
        raise RuntimeError('SpektraFilm application icon is missing')
    app.setWindowIcon(icon)
    return icon


def configure_window_icon(window, app, root):
    window.setIcon(app.windowIcon())
    if sys.platform != 'win32':
        return
    from PySide6.QtGui import QGuiApplication
    if QGuiApplication.platformName() != 'windows':
        return
    import ctypes as ct
    from ctypes import wintypes as wt
    user32 = ct.WinDLL('user32', use_last_error=True)
    load = user32.LoadImageW
    load.argtypes = [wt.HINSTANCE, wt.LPCWSTR, wt.UINT, ct.c_int, ct.c_int, wt.UINT]
    load.restype = wt.HANDLE
    send = user32.SendMessageW
    send.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    send.restype = ct.c_ssize_t
    handles = []
    for kind, size in ((0, 16), (1, 48)):
        handle = load(None, str(Path(root) / 'assets/icons/spektrafilm.ico'),
                      1, size, size, 0x10)  # IMAGE_ICON, LR_LOADFROMFILE
        if handle:
            send(int(window.winId()), 0x80, kind, int(handle))  # WM_SETICON
            handles.append(handle)
    # WM_SETICON does not take ownership. Keep handles until QApplication exits.
    if handles:
        retained = getattr(app, '_spektrafilm_native_icons', [])
        retained.extend(handles)
        app._spektrafilm_native_icons = retained

