"""Recipe proofs use the actual encoder, never the editor's display frame.

One serial job and one encoded artifact are retained. A full proof can be
published directly by export, avoiding a second full development/encoding.
Only a bounded viewport tile is uploaded to Qt Quick for pixel inspection.
"""
from functools import lru_cache
from pathlib import Path
import tempfile
import threading

import numpy as np
from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QObject, Property, Signal, Slot, QThreadPool, QRunnable, Qt
from PySide6.QtGui import QImage

from shared.output_recipes import normalize_recipe,recipe_size
from shared.color_management import icc_profile, encode
from .output import render_recipe_pixels, export_pixels, ExportCancelled, _check
from .imaging import read_photo, _publish_export
from .raw_source import source_pixels, normalized_pixels, quantize_display
from .color_display import transform_pixels


def proof_key(path,settings,recipe):
    path=Path(path).resolve();stat=path.stat();r=normalize_recipe(recipe)
    return (str(path),stat.st_size,stat.st_mtime_ns,settings,
            r.format,r.bit_depth,r.color_space,r.quality,r.long_edge,r.short_edge,r.megapixels,r.di_blue_compensation)


class EncodedProof:
    def __init__(self,directory,path,key,dimensions):
        self.directory,self.path,self.key,self.dimensions=directory,Path(path),key,dimensions

    def matches(self,path,settings,recipe):
        return self.path.is_file() and self.key==proof_key(path,settings,recipe)

    def publish(self,destination,recipe,cancel=None):
        def copy(target):
            with self.path.open('rb') as source:
                while data:=source.read(1024*1024):
                    _check(cancel);target.write(data)
            _check(cancel)
            return self.dimensions
        if recipe.format=='di':
            from .digital_intermediate import companion_luts
            companion_luts(Path(destination).parent)
        return _publish_export(Path(destination),copy)


@lru_cache(maxsize=1)
def _di_cube():
    from .native_spectral import _RUNTIME
    path=next((_RUNTIME/'resources/DI').glob('*Rec709.cube'))
    rows=[];size=0
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        if line.startswith('LUT_3D_SIZE'):size=int(line.split()[1])
        parts=line.split()
        if len(parts)==3:
            try:rows.append([float(v) for v in parts])
            except ValueError:pass
    return np.asarray(rows,dtype=np.float32).reshape(size,size,size,3)


def _di_display(path,display):
    import tifffile
    from scipy.ndimage import map_coordinates
    cube=_di_cube();values=tifffile.imread(path)
    result=QImage(values.shape[1],values.shape[0],QImage.Format_RGB888)
    stride=result.bytesPerLine()
    target=np.ndarray((result.height(),stride),np.uint8,buffer=result.bits())
    for top in range(0,len(values),32):
        codes=values[top:top+32].astype(np.float32)/65535
        coordinates=np.clip(codes,0,1)[...,::-1].reshape(-1,3).T*(cube.shape[0]-1)
        rgb=np.empty_like(codes)
        for c in range(3):rgb[...,c]=map_coordinates(cube[...,c],coordinates,order=1,prefilter=False).reshape(codes.shape[:2])
        # The supplied view table returns Rec.709 gamma 2.4, not sRGB codes.
        rgb=transform_pixels(encode(np.maximum(rgb,0)**2.4),'sRGB',dict(display,proof=None,gamut=False))
        target[top:top+len(rgb),:result.width()*3]=quantize_display(rgb).reshape(len(rgb),-1)
    return result


def _rgb_display(values,display,*,linear=False):
    """Only row scratch, in addition to the single decoded source and RGB8 view."""
    result=QImage(values.shape[1],values.shape[0],QImage.Format_RGB888)
    target=np.ndarray((result.height(),result.bytesPerLine()),np.uint8,buffer=result.bits())
    for top in range(0,len(values),64):
        block=normalized_pixels(values[top:top+64])
        if linear:block=encode(block)
        block=transform_pixels(block,'sRGB',display)
        target[top:top+len(block),:result.width()*3]=quantize_display(block).reshape(len(block),-1)
    return result


class _Signals(QObject):
    done=Signal(object)


class _Task(QRunnable):
    def __init__(self,request):
        super().__init__();self.request=request;self.signals=_Signals()

    def run(self):
        request=self.request
        directory=None
        try:
            path,settings,recipe,full,display,cancel=request['args']
            _check(cancel)
            key=proof_key(path,settings,recipe)
            if recipe.format=='raw':
                image=read_photo(path,max_edge=None if full else 1024)
                try:result=QImage(ImageQt(image)).copy()
                finally:image.close()
                artifact=None
            else:
                directory=tempfile.TemporaryDirectory(prefix='spektrafilm-proof-')
                suffix={'jpeg':'.jpg','heif':'.heic','png':'.png','tiff':'.tif','di':'.tif','dng':'.dng'}[recipe.format]
                output=Path(directory.name)/('proof'+suffix)
                pixels=render_recipe_pixels(path,settings,recipe,max_edge=None if full else 1024,cancel=cancel)
                dimensions=export_pixels(pixels,output,recipe,cancel=cancel,metadata_source=path)
                del pixels
                _check(cancel)
                if recipe.format=='di':result=_di_display(output,display)
                elif recipe.format=='dng':
                    import tifffile
                    values=tifffile.memmap(output)
                    result=_rgb_display(values,display,linear=True)
                    del values
                else:
                    # Decode the real encoded file, including JPEG/HEIF loss,
                    # bit-depth rounding and output profile. The high precision
                    # reader converts its ICC to unclipped encoded sRGB.
                    decoded=read_photo(str(output))
                    try:
                        result=_rgb_display(source_pixels(decoded),display)
                    finally:decoded.close()
                artifact=EncodedProof(directory,output,key,dimensions) if full else None
            _check(cancel)
            self.signals.done.emit(dict(id=request['id'],image=result,artifact=artifact,full=full))
        except Exception as error:
            self.signals.done.emit(dict(id=request['id'],error=str(error),cancelled=isinstance(error,ExportCancelled)))


class OutputProof(QObject):
    changed=Signal()

    def __init__(self,ctrl):
        super().__init__(ctrl);self.ctrl=ctrl;self.pool=QThreadPool(self);self.pool.setMaxThreadCount(1)
        self._serial=0;self._task=None;self._pending=None;self._cancel=threading.Event()
        self._source='';self._tile_source='';self._image=QImage();self._full=False
        self._busy=False;self._error='';self._artifact=None;self._active=False
        self._expected=(0,0);self._tile=(0,0,0,0)

    @Property(str,notify=changed)
    def source(self):return self._source
    @Property(str,notify=changed)
    def tileSource(self):return self._tile_source
    @Property('QVariantList',notify=changed)
    def tileRect(self):return list(self._tile)
    @Property('QVariantList',notify=changed)
    def dimensions(self):return [self._image.width(),self._image.height()]
    @Property('QVariantList',notify=changed)
    def expectedDimensions(self):return list(self._expected)
    @Property(bool,notify=changed)
    def busy(self):return self._busy
    @Property(bool,notify=changed)
    def fullResolution(self):return self._full
    @Property(str,notify=changed)
    def error(self):return self._error

    @Slot('QVariantMap',bool,bool,bool)
    def request(self,value,full=False,soft=True,gamut=False):
        if self.ctrl.currentIndex<0 or self.ctrl._exporting:return
        try:recipe=normalize_recipe(value)
        except ValueError as error:self._error=str(error);self.changed.emit();return
        self._active=True;self._serial+=1;self._cancel.set()
        display=dict(self.ctrl.colorDisplay.snapshot() or {})
        display['proof']=icc_profile(recipe.color_space) if soft and recipe.format not in ('raw','di') else None
        display['gamut']=bool(gamut and soft)
        w,h=self.ctrl._output_dimensions()
        if recipe.format=='raw':w,h=self.ctrl.sourceDimensions
        self._expected=recipe_size(w,h,recipe);self._busy=True;self._error=''
        # Keep the last bounded fit view visible while replacing the proof.
        # Release the old full-resolution image before allocating its successor.
        self._image=QImage();self._full=False;self._tile_source='';self._artifact=None
        self.ctrl.provider.discard('output-proof-tile')
        self._pending=dict(id=self._serial,args=(self.ctrl.currentPath,self.ctrl._settings,recipe,full,display,threading.Event()))
        self.changed.emit()
        if self._task is None:self._start()

    def _start(self):
        request,self._pending=self._pending,None
        if request is None:return
        self._cancel=request['args'][-1];self._task=_Task(request)
        self._task.signals.done.connect(self._done);self.pool.start(self._task)

    @Slot(object)
    def _done(self,result):
        self._task=None
        if result['id']==self._serial and self._active:
            self._busy=False;self._error=result.get('error','')
            if 'image' in result:
                self._image=result['image'];self._full=result['full'];self._artifact=result['artifact']
                image=self._image.scaled(1400,1400,Qt.KeepAspectRatio,Qt.SmoothTransformation)
                self.ctrl.provider.publish('output-proof',image)
                self._source=f'image://photos/output-proof?{self._serial}'
                self._tile_source=''
            self.changed.emit()
        if self._pending is not None:self._start()

    @Slot(int,int,int,int)
    def viewTile(self,x,y,width,height):
        if not self._full or self._image.isNull():return
        x=max(0,min(self._image.width()-1,x));y=max(0,min(self._image.height()-1,y))
        width=min(max(1,width),4096,self._image.width()-x);height=min(max(1,height),4096,self._image.height()-y)
        if self._tile_source and self._tile==(x,y,width,height):return
        self.ctrl.provider.publish('output-proof-tile',self._image.copy(x,y,width,height))
        self._tile=(x,y,width,height)
        self._tile_source=f'image://photos/output-proof-tile?{self._serial}-{x}-{y}-{width}-{height}'
        self.changed.emit()

    def exportArtifact(self):return self._artifact

    @Slot()
    def release(self):
        self._active=False;self._serial+=1;self._cancel.set();self._pending=None
        self._busy=False;self._image=QImage();self._artifact=None;self._source=self._tile_source='';self._full=False
        self.ctrl.provider.discard('output-proof','output-proof-tile');self.changed.emit()

    def close(self):
        self.release();self.pool.waitForDone()
