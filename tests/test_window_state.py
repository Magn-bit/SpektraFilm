import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QRect,Qt
from PySide6.QtGui import QGuiApplication,QWindow
from desktop.window_state import WindowState,visible_geometry

class WindowStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QGuiApplication.instance() or QGuiApplication([])
    def test_visible_placement_is_exact(self):
        rect=QRect(120,80,1200,800)
        self.assertEqual(visible_geometry(rect,[QRect(0,0,1920,1080)]),rect)
    def test_disconnected_monitor_returns_to_visible_area(self):
        result=visible_geometry(QRect(5400,-400,1600,1100),[QRect(0,0,1920,1040)])
        self.assertTrue(QRect(0,0,1920,1040).contains(result))
    def test_negative_coordinate_monitor_is_preserved(self):
        rect=QRect(-1700,100,1200,800)
        self.assertEqual(visible_geometry(rect,[QRect(-1920,0,1920,1080),QRect(0,0,1920,1080)]),rect)
    def test_geometry_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            first=QWindow(); first.setFlags(Qt.FramelessWindowHint); first.setGeometry(QRect(130,90,1180,780))
            state=WindowState(first,Path(directory)/'window.ini');state.save()
            second=QWindow(); second.setFlags(Qt.FramelessWindowHint)
            restored=WindowState(second,Path(directory)/'window.ini')
            with patch('desktop.window_state.available_screens',return_value=[QRect(0,0,1920,1080)]):
                restored.restore()
            self.assertEqual(second.geometry(),QRect(130,90,1180,780))
            second.close();first.close()

    def test_small_selected_screen_controls_minimum_size(self):
        with tempfile.TemporaryDirectory() as directory:
            window=QWindow();window.setFlags(Qt.FramelessWindowHint)
            window.setGeometry(QRect(-790,30,700,600))
            state=WindowState(window,Path(directory)/'window.ini')
            with patch('desktop.window_state.available_screens',return_value=[QRect(-800,0,800,700),QRect(0,0,1920,1080)]):
                state.restore()
            self.assertEqual(window.minimumWidth(),800)
            self.assertEqual(window.minimumHeight(),700)
            self.assertTrue(QRect(-800,0,800,700).contains(window.geometry()))
            window.close()

    def test_corrupt_records_fall_back_without_crashing(self):
        for raw in ['[]','null','{"normal":[true,0,1200,800]}','{"normal":[0,0,-1,800]}','{"normal":[0,0,999999999999,800]}','not json']:
            with self.subTest(raw=raw),tempfile.TemporaryDirectory() as directory:
                window=QWindow();window.setFlags(Qt.FramelessWindowHint);window.setGeometry(QRect(20,30,1200,800))
                state=WindowState(window,Path(directory)/'window.ini')
                state.store.setValue('window/state',raw)
                with patch('desktop.window_state.available_screens',return_value=[QRect(0,0,1920,1080)]):
                    state.restore()
                self.assertEqual(window.geometry(),QRect(20,30,1200,800))
                window.close()

    def test_maximized_record_retains_normal_geometry(self):
        with tempfile.TemporaryDirectory() as directory:
            window=QWindow();window.setFlags(Qt.FramelessWindowHint)
            state=WindowState(window,Path(directory)/'window.ini')
            state.store.setValue('window/state','{"normal":[40,50,1200,800],"maximized":true}')
            with patch('desktop.window_state.available_screens',return_value=[QRect(0,0,1920,1080)]):
                state.restore()
            self.app.processEvents();state.save()
            import json
            self.assertEqual(json.loads(state.store.value('window/state'))['normal'],[40,50,1200,800])
            self.assertTrue(state.maximized)
            window.close()

if __name__=='__main__':unittest.main()
