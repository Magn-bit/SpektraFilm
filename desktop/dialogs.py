"""Themed file dialogs retaining Qt's file model and keyboard navigation."""
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QEvent, QSettings, QStandardPaths
from PySide6.QtGui import QColor, QFont, QGuiApplication
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QFrame,
    QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton, QSizeGrip,
    QVBoxLayout, QWidget)
from .localization import tr

class _TitleBar(QWidget):
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.window().windowHandle():
            self.window().windowHandle().startSystemMove()
            event.accept()
        else:
            super().mousePressEvent(event)

class _Picker(QFileDialog):
    validationError = Signal(str)

    def accept(self):
        paths = [Path(value) for value in self.selectedFiles()]
        if not paths:
            self.validationError.emit('请选择文件或输入文件名。')
            return
        if self.fileMode() == QFileDialog.ExistingFiles and any(not path.is_file() for path in paths):
            self.validationError.emit('所选文件不存在，请检查路径。')
            return
        if self.fileMode() == QFileDialog.Directory and not paths[0].is_dir():
            self.validationError.emit('请选择存在的文件夹。')
            return
        if self.acceptMode() == QFileDialog.AcceptSave:
            if paths[0].exists():
                self.validationError.emit('此名称已存在，请换一个文件名，原有文件将保留。')
                return
            if not paths[0].parent.is_dir():
                self.validationError.emit('保存文件夹不存在，请重新选择。')
                return
        self.validationError.emit('')
        super().accept()

class StudioFileDialog(QDialog):
    def __init__(self, caption, directory='', name_filter='', *, mode='open', parent=None):
        super().__init__(parent)
        # QFileDialog's widget internals derive fonts using pointSize().  The
        # approved QML application font uses pixels, whose pointSize() is -1.
        # Convert only this dialog's clone before constructing its children.
        widget_font=QFont(self.font())
        logical_dpi=max(1.0,float(self.logicalDpiY()))
        if widget_font.pixelSize()>0:
            widget_font.setPointSizeF(widget_font.pixelSize()*72.0/logical_dpi)
        self.setFont(widget_font)
        title_points=18.0*72.0/logical_dpi
        self._source_caption,self._source_filter,self._mode=caption,name_filter,mode
        self.setObjectName('studioFileDialog')
        self.setWindowTitle(caption)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowModality(Qt.ApplicationModal)
        self._owner = QGuiApplication.focusWindow()
        self.resize(850, 600)
        self.setMinimumSize(660, 460)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 22)
        panel = QFrame(self)
        panel.setObjectName('dialogSurface')
        outer.addWidget(panel)
        shadow = QGraphicsDropShadowEffect(panel)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 7)
        shadow.setColor(QColor(24, 28, 22, 45))
        panel.setGraphicsEffect(shadow)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 18, 24, 12)
        layout.setSpacing(16)
        header = _TitleBar(panel)
        row = QHBoxLayout(header)
        row.setContentsMargins(0, 0, 0, 0)
        title = self._title = QLabel(tr(caption), header)
        title.setObjectName('dialogTitle')
        title.setAttribute(Qt.WA_TransparentForMouseEvents)
        row.addWidget(title, 1)
        close = self._close = QPushButton(tr('关闭'), header)
        close.setObjectName('dialogClose')
        close.setAccessibleName('关闭对话框')
        close.setAutoDefault(False)
        close.clicked.connect(self.reject)
        row.addWidget(close)
        layout.addWidget(header)
        self.picker = _Picker(panel)
        self.picker.setOption(QFileDialog.DontUseNativeDialog, True)
        # Avoid shell-extension IO for custom icons on removable/network drives.
        self.picker.setOption(QFileDialog.DontUseCustomDirectoryIcons, True)
        self.picker.setOption(QFileDialog.DontConfirmOverwrite, True)
        self.picker.setWindowFlags(Qt.Widget)
        self.picker.setWindowModality(Qt.NonModal)
        self.picker.setSizeGripEnabled(False)
        self.picker.setViewMode(QFileDialog.Detail)
        self.picker.setLabelText(QFileDialog.LookIn, '位置')
        self.picker.setLabelText(QFileDialog.FileName, '文件名')
        self.picker.setLabelText(QFileDialog.FileType, '文件类型')
        self.picker.setLabelText(QFileDialog.Reject, '取消')
        if mode == 'directory':
            self.picker.setFileMode(QFileDialog.Directory)
            self.picker.setOption(QFileDialog.ShowDirsOnly, True)
            self.picker.setLabelText(QFileDialog.Accept, '选择文件夹')
        elif mode == 'save':
            self.picker.setAcceptMode(QFileDialog.AcceptSave)
            self.picker.setFileMode(QFileDialog.AnyFile)
            self.picker.setLabelText(QFileDialog.Accept, '保存')
        else:
            self.picker.setFileMode(QFileDialog.ExistingFiles)
            self.picker.setLabelText(QFileDialog.Accept, '导入')
        if name_filter:
            self.picker.setNameFilter(name_filter)
        if directory:
            path = Path(directory)
            self.picker.setDirectory(str(path if path.is_dir() else path.parent))
            if not path.is_dir():
                self.picker.selectFile(path.name)
        self.picker.accepted.connect(self.accept)
        self.picker.rejected.connect(self.reject)
        layout.addWidget(self.picker, 1)
        self.errorLabel = QLabel('', panel)
        self.errorLabel.setObjectName('dialogError')
        self.errorLabel.setWordWrap(True)
        self.errorLabel.hide()
        self.picker.validationError.connect(self._show_error)
        layout.addWidget(self.errorLabel)
        grip = QSizeGrip(panel)
        grip.setFixedSize(12, 12)
        layout.addWidget(grip, 0, Qt.AlignRight)
        family = QApplication.instance().font().family().replace('"', '')
        editorial = getattr(QApplication.instance(),'_interface_font_selection',{}).get('editorial',family).replace('"','')
        self.setStyleSheet('''
            QWidget { color: #252725; font-family: "%s"; font-weight: 400; }
            QFrame#dialogSurface { background: #FFFFFF; border: 1px solid #D8DDD2; border-radius: 12px; }
            QFileDialog { background: #FFFFFF; }
            QLabel#dialogTitle { font-family: "%s"; font-size: %spt; }
            QLabel#dialogError { color: #9C3F32; padding: 2px 0; }
            QPushButton { background: #EBEEE9; border: 1px solid #D8DDD2; border-radius: 5px; min-height: 34px; min-width: 74px; padding: 0 12px; }
            QPushButton:hover { background: #E7E9E3; }
            QPushButton:pressed { background: #DDE3D9; }
            QPushButton:focus { border: 1px solid #66745E; }
            QPushButton:default { background: #252725; color: #FFFFFF; border-color: #252725; }
            QPushButton:default:hover { background: #343A33; }
            QPushButton:disabled { color: #555E54; background: #D8DDD2; }
            QPushButton#dialogClose { background: transparent; border-color: transparent; min-width: 42px; }
            QPushButton#dialogClose:hover { background: #E7E9E3; }
            QLineEdit, QComboBox { background: #FFFFFF; border: 1px solid #D8DDD2; border-radius: 4px; min-height: 32px; padding: 0 8px; selection-background-color: #EAF0E6; selection-color: #252725; }
            QLineEdit:focus, QComboBox:focus { border-color: #66745E; }
            QComboBox::drop-down { border: 0; width: 24px; }
            QTreeView, QListView { background: #FFFFFF; alternate-background-color: #FCFCFB; border: 1px solid #D8DDD2; border-radius: 5px; padding: 4px; outline: none; selection-background-color: #EAF0E6; selection-color: #252725; }
            QTreeView::item, QListView::item { min-height: 29px; }
            QHeaderView::section { background: #EBEEE9; color: #555E54; border: 0; border-bottom: 1px solid #D8DDD2; padding: 7px; }
            QToolButton { background: transparent; border: 1px solid transparent; border-radius: 4px; padding: 5px; }
            QToolButton:hover { background: #E7E9E3; }
            QToolButton:focus { border-color: #66745E; }
            QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
            QScrollBar::handle:vertical { background: #A9B0A3; border-radius: 3px; min-height: 30px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        ''' % (family,editorial,title_points))
        self._retranslate_ui()

    def _retranslate_ui(self):
        self.setWindowTitle(tr(self._source_caption))
        self._title.setText(tr(self._source_caption))
        self._close.setText(tr('关闭'))
        self._close.setAccessibleName(tr('关闭对话框'))
        for role,source in [(QFileDialog.LookIn,'位置'),(QFileDialog.FileName,'文件名'),
                            (QFileDialog.FileType,'文件类型'),(QFileDialog.Reject,'取消')]:
            self.picker.setLabelText(role,tr(source))
        self.picker.setLabelText(QFileDialog.Accept,tr({'directory':'选择文件夹','save':'保存'}.get(self._mode,'导入')))
        if self._source_filter:
            self.picker.setNameFilter(tr(self._source_filter))

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type()==QEvent.LanguageChange and hasattr(self,'picker'):
            self._retranslate_ui()
            if getattr(self,'_source_error',''):
                self.errorLabel.setText(tr(self._source_error))

    def _show_error(self, message):
        self._source_error=message
        self.errorLabel.setText(tr(message))
        self.errorLabel.setVisible(bool(message))

    def showEvent(self, event):
        super().showEvent(event)
        if self._owner and self._owner != self.windowHandle():
            self.windowHandle().setTransientParent(self._owner)
            area = self._owner.screen().availableGeometry()
            center = self._owner.geometry().center()
            x = max(area.left(), min(center.x() - self.width() // 2, area.right() - self.width() + 1))
            y = max(area.top(), min(center.y() - self.height() // 2, area.bottom() - self.height() + 1))
            self.move(x, y)

    @staticmethod
    def _locations():
        return QSettings('SpektraFilm', 'FileDialogs')

    @staticmethod
    def _initial_directory(directory, key, prefer_saved=False):
        saved=StudioFileDialog._locations().value(key, '', type=str)
        choices=(saved,directory) if prefer_saved else (directory,saved)
        for value in choices:
            if not value:continue
            path=Path(value)
            for candidate in (path,*path.parents):
                if candidate.is_dir():return str(candidate)
        return QStandardPaths.writableLocation(QStandardPaths.PicturesLocation)

    @staticmethod
    def getOpenFileNames(parent=None, caption='', directory='', filter='', *, location_key=''):
        key=location_key or 'open/'+caption
        initial=StudioFileDialog._initial_directory(directory,key,bool(location_key))
        dialog = StudioFileDialog(caption, initial, filter, parent=parent)
        accepted = dialog.exec() == QDialog.Accepted
        paths=dialog.picker.selectedFiles() if accepted else []
        if paths:StudioFileDialog._locations().setValue(key,str(Path(paths[0]).parent))
        return (paths, dialog.picker.selectedNameFilter())

    @staticmethod
    def getSaveFileName(parent=None, caption='', directory='', filter=''):
        dialog = StudioFileDialog(caption, directory, filter, mode='save', parent=parent)
        accepted = dialog.exec() == QDialog.Accepted
        paths = dialog.picker.selectedFiles()
        return (paths[0] if accepted and paths else '', dialog.picker.selectedNameFilter())

    @staticmethod
    def getExistingDirectory(parent=None, caption='', directory='', *, location_key=''):
        key=location_key or 'directory/'+caption
        initial=StudioFileDialog._initial_directory(directory,key,bool(location_key))
        dialog = StudioFileDialog(caption, initial, mode='directory', parent=parent)
        accepted = dialog.exec() == QDialog.Accepted
        paths = dialog.picker.selectedFiles()
        folder=paths[0] if accepted and paths else ''
        if folder:StudioFileDialog._locations().setValue(key,folder)
        return folder
