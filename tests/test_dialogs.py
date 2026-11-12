import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFontInfo, QTextLayout
from PySide6.QtWidgets import QApplication, QFileDialog, QLineEdit
from desktop.dialogs import StudioFileDialog
from desktop.typography import load_mincho

class DialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')
        cls.family = load_mincho(cls.app, Path(__file__).resolve().parents[1])

    def test_actual_chinese_and_latin_use_screen_reading_font(self):
        self.assertEqual(QFontInfo(self.app.font()).family(), self.family)
        layout = QTextLayout('胶片档案 曝光补偿 保存 取消 Portra 400', self.app.font())
        layout.beginLayout(); layout.createLine(); layout.endLayout()
        families = {run.rawFont().familyName() for run in layout.glyphRuns()}
        self.assertTrue(families)
        allowed={self.family,self.app._interface_font_selection['cjk']}
        self.assertTrue(families.issubset(allowed),families)
        if self.family=='SF Pro Text' and self.app._interface_font_selection['cjk']=='PingFang SC':
            self.assertEqual(families,{'SF Pro Text','PingFang SC'})

    def test_open_supports_real_multiple_files(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = [Path(folder) / name for name in ('照片 一.png', '照片 二.png')]
            for path in paths: path.write_bytes(b'fixture')
            dialog = StudioFileDialog('导入照片', folder, '照片 (*.png)')
            self.assertEqual(dialog.picker.fileMode(), QFileDialog.ExistingFiles)
            self.assertTrue(dialog.picker.testOption(QFileDialog.DontUseNativeDialog))
            edit = dialog.picker.findChild(QLineEdit, 'fileNameEdit')
            edit.setText('"照片 一.png" "照片 二.png"')
            self.assertEqual({Path(p) for p in dialog.picker.selectedFiles()}, set(paths))
            dialog.close(); dialog.deleteLater(); self.app.processEvents()

    def test_save_and_directory_preserve_selection_semantics(self):
        with tempfile.TemporaryDirectory() as folder:
            suggested = Path(folder) / '我的作品.jpg'
            save = StudioFileDialog('保存作品', str(suggested), 'JPG (*.jpg)', mode='save')
            self.assertEqual(save.picker.acceptMode(), QFileDialog.AcceptSave)
            self.assertEqual([Path(p) for p in save.picker.selectedFiles()], [suggested])
            self.assertFalse(suggested.exists())
            directory = StudioFileDialog('选择文件夹', folder, mode='directory')
            self.assertEqual(directory.picker.fileMode(), QFileDialog.Directory)
            self.assertTrue(directory.picker.testOption(QFileDialog.ShowDirsOnly))
            for dialog in (save, directory): dialog.close(); dialog.deleteLater()
            self.app.processEvents()

    def test_cancel_returns_no_file(self):
        QTimer.singleShot(0, lambda: self.app.activeModalWidget().reject())
        paths, _ = StudioFileDialog.getOpenFileNames(caption='导入照片')
        self.assertEqual(paths, [])

    def test_existing_file_is_preserved_with_inline_feedback(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'原片.jpg'; path.write_bytes(b'original')
            dialog = StudioFileDialog('保存作品', str(path), 'JPG (*.jpg)', mode='save')
            dialog.picker.accept()
            self.assertIn('已存在', dialog.errorLabel.text())
            self.assertEqual(dialog.result(), 0)
            self.assertEqual(path.read_bytes(), b'original')
            dialog.close(); dialog.deleteLater(); self.app.processEvents()
