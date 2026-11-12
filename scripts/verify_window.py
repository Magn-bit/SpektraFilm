"""Exercise real Windows window-state transitions without changing user settings."""
import json,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QRect,Qt,QTimer,QEventLoop
from PySide6.QtGui import QGuiApplication,QWindow
from desktop.window_state import WindowState,visible_geometry,available_screens
app=QGuiApplication([])
app.setQuitOnLastWindowClosed(False)
def settle():
    loop=QEventLoop();QTimer.singleShot(160,loop.quit);loop.exec()
def close_window(window,state):
    window.close()
    state.save()  # Mirrors main.py's aboutToQuit save and cancels its timer.
    settle()
checks=[]
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)/'window.ini'
    first=QWindow();first.setFlags(Qt.FramelessWindowHint)
    screen=available_screens()[0]
    rect=visible_geometry(QRect(screen.x()+50,screen.y()+35,1180,780),available_screens())
    first.setGeometry(rect);first.showNormal();settle()
    state=WindowState(first,path);state.save()
    expected=first.geometry()
    first.showMaximized();settle();state.save()
    assert state.normal==expected,('maximize lost geometry',state.normal,expected)
    checks.append('maximize retains normal geometry')
    first.showMinimized();settle();state.save()
    assert state.maximized
    checks.append('minimize retains maximized preference')
    close_window(first,state)
    second=QWindow();second.setFlags(Qt.FramelessWindowHint)
    restored=WindowState(second,path);restored.restore();settle()
    assert second.windowState()==Qt.WindowMaximized
    checks.append('restore opens maximized')
    restored.restoreNormal();settle()
    assert second.geometry()==expected,(second.geometry(),expected)
    assert second.windowState()==Qt.WindowNoState,second.windowState()
    close_window(second,restored)
    checks.append('restore returns to normal position and size')
    third=QWindow();third.setFlags(Qt.FramelessWindowHint)
    final=WindowState(third,path);final.restore();settle()
    assert third.geometry()==expected,(third.geometry(),expected,final.maximized)
    assert third.windowState()==Qt.WindowNoState
    checks.append('normal close and reopen roundtrip')
    third.showMinimized();settle();close_window(third,final)
    fourth=QWindow();fourth.setFlags(Qt.FramelessWindowHint)
    last=WindowState(fourth,path);last.restore();settle()
    assert fourth.windowState()==Qt.WindowNoState
    checks.append('minimized close never reopens minimized')
    close_window(fourth,last)
target=Path('output/window-runtime.json')
target.write_text(json.dumps({'ok':True,'checks':checks},indent=2),encoding='utf-8')
print(target.read_text(encoding='utf-8'))

