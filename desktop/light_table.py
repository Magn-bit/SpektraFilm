"""A bounded, source-backed light table with positions measured in millimetres."""
from __future__ import annotations

from dataclasses import asdict
from collections import OrderedDict
import json
import math
from pathlib import Path
import uuid

from PIL.ImageQt import ImageQt
from PySide6.QtCore import QObject, Property, QTimer, QThreadPool, QRunnable, Signal, Slot, QAbstractListModel, QModelIndex, Qt
from PySide6.QtGui import QImage

from .imaging import Settings
from .preferences import _atomic_json


class _Signals(QObject):
    done = Signal(object)


class _VisibleRows(QAbstractListModel):
    """Keep delegates alive while a frame is dragged or developed."""
    Role=Qt.UserRole+1
    def __init__(self,parent):
        super().__init__(parent);self.items=[]
    def roleNames(self):return {self.Role:b'modelData'}
    def rowCount(self,parent=QModelIndex()):return 0 if parent.isValid() else len(self.items)
    def data(self,index,role=Qt.DisplayRole):
        if index.isValid() and role==self.Role and 0<=index.row()<len(self.items):return self.items[index.row()]
    def sync(self,rows):
        # Settings may carry thousands of brush points; the delegate only
        # needs placement and a bounded developed image, never that graph.
        keys=('id','index','name','x','y','angle','width_mm','height_mm','source','error')
        rows=[{key:row.get(key) for key in keys} for row in rows]
        ids={row['id'] for row in rows}
        for index in range(len(self.items)-1,-1,-1):
            if self.items[index]['id'] not in ids:
                self.beginRemoveRows(QModelIndex(),index,index);self.items.pop(index);self.endRemoveRows()
        for target,row in enumerate(rows):
            old=next((i for i in range(target,len(self.items)) if self.items[i]['id']==row['id']),None)
            if old is None:
                self.beginInsertRows(QModelIndex(),target,target);self.items.insert(target,dict(row));self.endInsertRows()
            else:
                if old!=target:
                    self.beginMoveRows(QModelIndex(),old,old,QModelIndex(),target)
                    self.items.insert(target,self.items.pop(old));self.endMoveRows()
                if self.items[target]!=row:
                    self.items[target]=dict(row);idx=self.index(target);self.dataChanged.emit(idx,idx,[self.Role])


class _Develop(QRunnable):
    def __init__(self, controller, row, settings):
        super().__init__(); self.ctrl=controller; self.row=row; self.settings=settings; self.signals=_Signals()

    def run(self):
        try:
            _, picture, _, _ = self.ctrl._render_photo(self.row['path'],self.settings,640)
            result=QImage(ImageQt(picture)).copy()
            self.signals.done.emit((self.row['id'],asdict(self.settings),result,''))
        except Exception as error:
            self.signals.done.emit((self.row['id'],asdict(self.settings),None,str(error)))


class LightTable(QObject):
    changed=Signal()
    message=Signal(str)

    def __init__(self,controller):
        super().__init__(controller); self.ctrl=controller
        self._file=controller._store.parent/'light-table.json'
        try:
            saved=json.loads(self._file.read_text(encoding='utf-8'))
            self._positions={str(k):v for k,v in saved.get('positions',{}).items()
                             if isinstance(v,dict) and all(isinstance(v.get(t),(int,float)) and math.isfinite(v[t]) for t in ('x','y','angle'))}
        except (OSError,ValueError,TypeError,AttributeError):self._positions={}
        self._rows=[];self._visible=[];self._view=(0,0,500,350);self._cached=OrderedDict();self._active=False;self._closed=False;self._worker=None
        self._model=_VisibleRows(self)
        self._pool=QThreadPool(self);self._pool.setMaxThreadCount(1)
        self._timer=QTimer(self);self._timer.setInterval(120);self._timer.timeout.connect(self._pump)
        self._save_timer=QTimer(self);self._save_timer.setSingleShot(True);self._save_timer.timeout.connect(self._save)
        controller.photosChanged.connect(self._sync)
        controller.stateChanged.connect(self._invalidate_current)

    @Property(QObject,constant=True)
    def rows(self):return self._model

    @Property(bool,notify=changed)
    def busy(self):return self._worker is not None

    @Slot(bool)
    def setActive(self,value):
        self._active=bool(value)
        if value:self._sync();self._timer.start()
        else:self._timer.stop()

    def _sync(self):
        previous={r['path']:r for r in self._rows};rows=[]
        for i,photo in enumerate(self.ctrl._photos):
            row=previous.get(photo['path'])
            if row is None:
                pos=self._positions.get(photo['path'],dict(x=24+(i%8)*100,y=24+(i//8)*90,angle=0))
                row=dict(id=uuid.uuid4().hex,path=photo['path'],x=pos['x'],y=pos['y'],angle=pos['angle'],source='',error='',settings=None)
            row['index']=i;row['name']=photo['name']
            current=self.ctrl._settings if i==self.ctrl.currentIndex else Settings.from_mapping(photo['settings'])
            aspect=max(1,photo.get('width',0))/max(1,photo.get('height',0))
            long_edge=float(current.film_format_mm)*(max(aspect,1/aspect) if current.film_format_axis=='short' else 1)
            row.update(width_mm=long_edge if aspect>=1 else long_edge*aspect,
                       height_mm=long_edge/aspect if aspect>=1 else long_edge)
            rows.append(row)
        stale=set(r['id'] for r in self._rows)-set(r['id'] for r in rows)
        for ident in stale:self.ctrl.provider.discard('lighttable_'+ident)
        self._rows=rows
        if self._active:self.setViewport(*self._view);self.changed.emit()

    def _invalidate_current(self):
        if not self._active:return
        for row in self._rows:
            if row['path']==self.ctrl.currentPath and row['settings']!=asdict(self.ctrl._settings):
                row['settings']=None
                photo=self.ctrl._photos[row['index']]
                aspect=max(1,photo.get('width',0))/max(1,photo.get('height',0))
                setting=self.ctrl._settings
                edge=float(setting.film_format_mm)*(max(aspect,1/aspect) if setting.film_format_axis=='short' else 1)
                row.update(width_mm=edge if aspect>=1 else edge*aspect,height_mm=edge/aspect if aspect>=1 else edge)
                self.setViewport(*self._view)
                break

    @Slot(float,float,float,float)
    def setViewport(self,x,y,width,height):
        if not all(math.isfinite(v) for v in (x,y,width,height)):return
        self._view=(x,y,width,height)
        # A small margin prevents decode churn at the edge. All placements
        # remain lightweight; only the visible subset creates QML delegates.
        def intersects(row):
            radians=math.radians(row['angle']);c=abs(math.cos(radians));s=abs(math.sin(radians))
            rw,rh=row['width_mm'],row['height_mm'];half_w=(rw*c+rh*s)/2;half_h=(rw*s+rh*c)/2
            cx,cy=row['x']+rw/2,row['y']+rh/2
            return cx+half_w>=x-80 and cy+half_h>=y-80 and cx-half_w<=x+width+80 and cy-half_h<=y+height+80
        visible=[r for r in self._rows if intersects(r)]
        self._model.sync(visible)
        if visible!=self._visible:self._visible=visible;self.changed.emit()

    def _pump(self):
        if not self._active or self._closed or self._worker is not None or self.ctrl.busy:return
        for row in self._visible:
            current=self.ctrl._settings if row['index']==self.ctrl.currentIndex else Settings.from_mapping(self.ctrl._photos[row['index']]['settings'])
            snapshot=asdict(current)
            if row['settings']==snapshot:continue
            row['settings']=snapshot
            self._worker=_Develop(self.ctrl,dict(row),current)
            self._worker.signals.done.connect(self._done)
            self.changed.emit();self._pool.start(self._worker);return

    def _done(self,result):
        self._worker=None
        if self._closed:return
        ident,snapshot,image,error=result
        row=next((r for r in self._rows if r['id']==ident),None)
        if row is not None and row['settings']==snapshot:
            row['error']=error
            if image is not None:
                row['revision']=row.get('revision',0)+1
                self.ctrl.provider.publish('lighttable_'+ident,image)
                row['source']='image://photos/lighttable_'+ident+'?v='+str(row['revision'])
                self._cached[ident]=True;self._cached.move_to_end(ident)
                while len(self._cached)>48:
                    old,_=self._cached.popitem(last=False)
                    self.ctrl.provider.discard('lighttable_'+old)
                    prior=next((r for r in self._rows if r['id']==old),None)
                    if prior is not None:prior.update(source='',settings=None)
        self.setViewport(*self._view);self.changed.emit()

    @Slot(str,float,float,float)
    def place(self,ident,x,y,angle):
        if not all(math.isfinite(v) for v in (x,y,angle)):return
        row=next((r for r in self._rows if r['id']==ident),None)
        if row is None:return
        row.update(x=max(0,min(4000,x)),y=max(0,min(3000,y)),angle=angle%360)
        self._positions[row['path']]={k:row[k] for k in ('x','y','angle')}
        self._save_timer.start(500)
        self.setViewport(*self._view);self.changed.emit()

    @Slot()
    def arrange(self):
        for i,row in enumerate(self._rows):
            row.update(x=24+(i%8)*100,y=24+(i//8)*90,angle=0)
            self._positions[row['path']]={k:row[k] for k in ('x','y','angle')}
        self._save_timer.start(500);self.setViewport(*self._view);self.changed.emit()

    def _save(self):
        try:_atomic_json(self._file,dict(version=1,positions=self._positions))
        except OSError as error:self.message.emit('看片台位置保存失败：'+str(error))

    def close(self):
        self._closed=True;self._timer.stop();self._save_timer.stop();self._save();self._pool.waitForDone()
