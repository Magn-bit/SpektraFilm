"""Cancelable, metadata-light import staging for the existing quick session.

Scanning never develops RAW files, copies photos or creates a catalog. Only
visible thumbnails and the active candidate are decoded; committed paths enter
the controller's existing bounded import queue without changing edit semantics.
"""
from __future__ import annotations

import os
from pathlib import Path
import threading
import time

from PySide6.QtCore import QObject,Property,Signal,Slot,QAbstractListModel,QModelIndex,Qt,QThreadPool,QRunnable,QTimer,QUrl
from PySide6.QtGui import QImage
from PIL.ImageQt import ImageQt

from shared.photo_formats import PHOTO_EXTENSIONS,PHOTO_DIALOG_FILTER,RAW_EXTENSIONS
from .dialogs import StudioFileDialog


class _Work(QRunnable):
    def __init__(self,fn):super().__init__();self.fn=fn
    def run(self):self.fn()


class _Rows(QAbstractListModel):
    def __init__(self,parent):super().__init__(parent);self.rows=[]
    def roleNames(self):return {Qt.UserRole+1:b'entry'}
    def rowCount(self,parent=QModelIndex()):return 0 if parent.isValid() else len(self.rows)
    def data(self,index,role):return dict(self.rows[index.row()]) if index.isValid() and role==Qt.UserRole+1 else None
    def clear(self):self.beginResetModel();self.rows=[];self.endResetModel()
    def append(self,rows):
        if not rows:return
        first=len(self.rows);self.beginInsertRows(QModelIndex(),first,first+len(rows)-1);self.rows.extend(rows);self.endInsertRows()
    def changed(self,first,last=None):
        if self.rows:self.dataChanged.emit(self.index(first,0),self.index(first if last is None else last,0),[Qt.UserRole+1])


class ImportWorkspace(QObject):
    changed=Signal()
    imported=Signal(int)
    batchReady=Signal(int,object)
    scanFinished=Signal(int,object)
    previewFinished=Signal(int,int,object)

    def __init__(self,controller):
        super().__init__(controller);self.ctrl=controller;self._model=_Rows(self)
        self._scan_pool=QThreadPool(self);self._scan_pool.setMaxThreadCount(1)
        self._preview_pool=QThreadPool(self);self._preview_pool.setMaxThreadCount(1)
        self._generation=0;self._cancel=threading.Event();self._closed=False
        self._roots=[];self._recursive=False;self._scanning=False;self._adding=False
        self._status='';self._error='';self._selected=set();self._active=-1;self._anchor=0
        self._preview='';self._preview_error='';self._thumb_keys=set();self._pending=[];self._added=0
        self._preview_timer=QTimer(self);self._preview_timer.setSingleShot(True);self._preview_timer.setInterval(75);self._preview_timer.timeout.connect(self._load_preview)
        self._add_timer=QTimer(self);self._add_timer.setSingleShot(True);self._add_timer.timeout.connect(self._add_chunk)
        self.batchReady.connect(self._batch);self.scanFinished.connect(self._finished);self.previewFinished.connect(self._preview_done)

    @Property(QObject,constant=True)
    def photos(self):return self._model
    @Property('QVariantMap',notify=changed)
    def state(self):
        active=dict(self._model.rows[self._active]) if 0<=self._active<len(self._model.rows) else {}
        return dict(source_paths=list(self._roots),source_path=self._roots[0] if len(self._roots)==1 else '',
            source_name=(Path(self._roots[0]).name or self._roots[0]) if len(self._roots)==1 else str(len(self._roots))+' 个来源' if self._roots else '',
            recursive=self._recursive,scanning=self._scanning,adding=self._adding,
            count=len(self._model.rows),selected=len(self._selected),active_index=self._active,active=active,
            preview=self._preview,preview_error=self._preview_error,status=self._status,error=self._error,
            can_import=bool(self._selected) and not self._adding and not self.ctrl.exporting)

    @Slot()
    def chooseFolder(self):
        folder=StudioFileDialog.getExistingDirectory(None,'选择照片文件夹',self._roots[0] if self._roots else '',location_key='photo-import')
        if folder:self.setSources([folder])
    @Slot()
    def choosePhotos(self):
        paths,_=StudioFileDialog.getOpenFileNames(None,'选择照片',self._roots[0] if self._roots else '',PHOTO_DIALOG_FILTER,location_key='photo-import')
        if paths:self.setSources(paths)
    @Slot(bool)
    def setRecursive(self,value):
        if self._recursive==bool(value):return
        self._recursive=bool(value)
        if self._roots:self._set_sources(self._roots,preserve=True)
        else:self.changed.emit()
    @Slot('QVariantList')
    def receiveDrop(self,urls):
        paths=[QUrl(value).toLocalFile() for value in urls]
        self._set_sources(self._roots+paths,preserve=True)
    @Slot('QVariantList')
    def setSources(self,paths):
        self._set_sources(paths)
    def _set_sources(self,paths,preserve=False):
        if self._closed or self._adding:return
        roots=list(dict.fromkeys(str(value) for value in paths if value))
        previous={os.path.normcase(row['path']):row['selected'] for row in self._model.rows} if preserve else {}
        self._cancel.set();self._scan_pool.clear();self._preview_pool.clear();self._preview_timer.stop()
        self._generation+=1;token=self._generation;cancel=threading.Event();self._cancel=cancel
        self.ctrl.provider.discard(*self._thumb_keys,'import-candidate');self._thumb_keys.clear()
        self._roots=roots;self._selected.clear();self._model.clear();self._active=-1;self._anchor=0;self._preview='';self._preview_error=''
        self._error='';self._status='';self._scanning=bool(roots);recursive=self._recursive
        existing={os.path.normcase(os.path.abspath(row['path'])) for row in self.ctrl.photos}
        existing.update(os.path.normcase(os.path.abspath(path)) for path in getattr(self.ctrl,'_queued_paths',()))
        self.changed.emit()
        if not roots:return
        def scan():
            batch=[];seen=set();errors=[];started=time.monotonic()
            def publish():
                nonlocal batch,started
                if batch:self.batchReady.emit(token,batch);batch=[]
                started=time.monotonic()
            def photo(path,stat):
                key=os.path.normcase(os.path.abspath(path))
                if key in seen or Path(path).suffix.lower() not in PHOTO_EXTENSIONS:return
                seen.add(key);suffix=Path(path).suffix.lower()
                batch.append(dict(path=os.path.abspath(path),name=Path(path).name,format=suffix[1:].upper(),
                    size=int(stat.st_size),modified=float(stat.st_mtime),raw=suffix in RAW_EXTENSIONS,
                    already_current=key in existing,selected=key not in existing and previous.get(key,True),dimensions=''))
                if len(batch)>=64 or time.monotonic()-started>.1:publish()
            stack=[]
            try:
                for root in roots:
                    if cancel.is_set():break
                    try:
                        if os.path.isdir(root):stack.append(root)
                        elif os.path.isfile(root):photo(root,os.stat(root))
                        else:errors.append('来源不可用：'+str(root))
                    except OSError as error:errors.append(str(error))
                while stack and not cancel.is_set():
                    folder=stack.pop()
                    try:
                        with os.scandir(folder) as entries:
                            for entry in entries:
                                if cancel.is_set():break
                                try:
                                    if entry.is_dir(follow_symlinks=False):
                                        if recursive:stack.append(entry.path)
                                    elif entry.is_file(follow_symlinks=False) and Path(entry.name).suffix.lower() in PHOTO_EXTENSIONS:photo(entry.path,entry.stat(follow_symlinks=False))
                                except OSError as error:errors.append(str(error))
                    except OSError as error:errors.append(str(error))
                if not cancel.is_set():publish()
                self.scanFinished.emit(token,dict(cancelled=cancel.is_set(),errors=errors[:8]))
            except Exception as error:self.scanFinished.emit(token,dict(cancelled=False,errors=[str(error)]))
        self._scan_pool.start(_Work(scan))

    @Slot(int,object)
    def _batch(self,token,rows):
        if self._closed or token!=self._generation or self._cancel.is_set():return
        first=len(self._model.rows)
        for index,row in enumerate(rows,first):
            row['index']=index
            if row['selected']:self._selected.add(index)
        self._model.append(rows)
        if self._active<0 and rows:self.activate(0)
        self.changed.emit()
    @Slot(int,object)
    def _finished(self,token,result):
        if self._closed or token!=self._generation or not self._scanning:return
        self._scanning=False;self._status='已停止读取' if result['cancelled'] else ''
        if result['errors']:self._error='部分来源无法读取：'+result['errors'][0] if self._model.rows else result['errors'][0]
        elif not self._model.rows and not result['cancelled']:self._status='没有找到支持的照片'
        self.changed.emit()
    @Slot()
    def cancelScan(self):
        self._cancel.set();self._scanning=False;self._status='已停止读取';self.changed.emit()
    @Slot(int,result=str)
    def thumbnail(self,index):
        if not 0<=index<len(self._model.rows):return ''
        key=f'import-{self._generation}-{index}'
        if key not in self._thumb_keys:
            self.ctrl.provider.register_thumbnail(key,self._model.rows[index]['path']);self._thumb_keys.add(key)
        return 'image://photos/'+key
    @Slot(int)
    def activate(self,index):
        if not 0<=index<len(self._model.rows):return
        if index==self._active:self.changed.emit();return
        self._active=index;self._preview='';self._preview_error='';self._preview_timer.start();self.changed.emit()
    @Slot(int,bool)
    def toggle(self,index,extend=False):
        if self._adding or not 0<=index<len(self._model.rows):return
        indices=range(min(index,self._anchor),max(index,self._anchor)+1) if extend else [index]
        checked=index not in self._selected
        for current in indices:
            row=self._model.rows[current]
            if row['already_current']:continue
            row['selected']=checked
            if checked:self._selected.add(current)
            else:self._selected.discard(current)
        self._model.changed(min(indices),max(indices));self._anchor=index;self.activate(index)
    @Slot(bool)
    def selectAll(self,value):
        if self._adding:return
        for index,row in enumerate(self._model.rows):
            row['selected']=bool(value) and not row['already_current']
            if row['selected']:self._selected.add(index)
            else:self._selected.discard(index)
        if self._model.rows:self._model.changed(0,len(self._model.rows)-1)
        self.changed.emit()
    def _load_preview(self):
        if self._closed or not 0<=self._active<len(self._model.rows):return
        token,index=self._generation,self._active;path=self._model.rows[index]['path'];self._preview_pool.clear()
        def work():
            from .imaging import read_thumbnail
            try:
                image=read_thumbnail(path,960);dimensions=image.info.get('source_size',image.size)
                result=dict(image=QImage(ImageQt(image)).copy(),dimensions=f'{dimensions[0]:,} × {dimensions[1]:,}',error='')
                image.close()
            except Exception as error:result=dict(image=None,dimensions='',error='无法预览这张照片：'+str(error))
            self.previewFinished.emit(token,index,result)
        self._preview_pool.start(_Work(work))
    @Slot(int,int,object)
    def _preview_done(self,token,index,result):
        if self._closed or token!=self._generation or index!=self._active:return
        if result['image'] is not None:
            self.ctrl.provider.publish('import-candidate',result['image']);self._preview=f'image://photos/import-candidate?v={token}-{index}'
        self._preview_error=result['error'];self._model.rows[index]['dimensions']=result['dimensions'];self._model.changed(index);self.changed.emit()
    @Slot()
    def addSelected(self):
        if not self.state['can_import']:return
        self._cancel.set();self._scanning=False;self._adding=True;self._added=0
        self._pending=sorted(self._selected)
        self._status='正在加入当前会话';self.changed.emit();self._add_timer.start(0)
    def _add_chunk(self):
        if self._closed:return
        chunk,self._pending=self._pending[:128],self._pending[128:]
        if chunk:
            try:self.ctrl.add_paths([self._model.rows[index]['path'] for index in chunk])
            except Exception as error:
                self._adding=False;self._pending=[];self._error='无法加入照片：'+str(error);self.changed.emit();return
            self._added+=len(chunk)
            for index in chunk:
                self._model.rows[index].update(selected=False,already_current=True);self._selected.discard(index)
            self._model.changed(min(chunk),max(chunk));self.changed.emit()
        if self._pending:self._add_timer.start(0);return
        self._adding=False;self._status='已加入 '+str(self._added)+' 张';self.changed.emit();self.imported.emit(self._added)
    def close(self):
        self._closed=True;self._cancel.set();self._scan_pool.clear();self._preview_pool.clear();self._preview_timer.stop();self._add_timer.stop()
        self._scan_pool.waitForDone();self._preview_pool.waitForDone()
        self.ctrl.provider.discard(*self._thumb_keys,'import-candidate');self._thumb_keys.clear()
