"""Latest-only worker mask rasterization; never walks brush history in QML."""
from dataclasses import replace
import numpy as np
from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QObject,QTimer,QThreadPool,QRunnable,Signal
from PySide6.QtGui import QImage
from shared.local_masks import rasterize_mask
from shared.geometry import apply_geometry_image


class _BrushRaster:
    """Three bounded alpha buffers, updated by the single overlay worker.

    A stroke uses maximum segment coverage before its flow is composited.
    Applying each input batch independently would darken overlaps; retaining
    that coverage makes the incremental preview identical to a full walk.
    """
    def __init__(self):
        self.key=None;self.prefix=None;self.base=None
        self.stroke=None;self.coverage=None;self.final=None

    def render(self,layer,width,height):
        key=(layer.id,width,height)
        prefix=layer.strokes[:-1]
        stroke=layer.strokes[-1]
        inverted=layer.inverted
        common=replace(layer,inverted=False)
        same_prefix=self.key==key and self.prefix==prefix
        if same_prefix:
            base=self.base
        elif self.key==key and self.stroke is not None and (*self.prefix,self.stroke)==prefix:
            base=self.final
        else:
            base=rasterize_mask(replace(common,strokes=prefix),width,height)
        old=self.stroke
        extending=(same_prefix and old is not None and
            (old.radius,old.feather,old.flow,old.erase)==(stroke.radius,stroke.feather,stroke.flow,stroke.erase)
            and len(stroke.points)>=len(old.points) and stroke.points[:len(old.points)]==old.points)
        if extending and len(stroke.points)==len(old.points):
            coverage=self.coverage
        else:
            segment=replace(stroke,points=stroke.points[max(0,len(old.points)-1):] if extending else stroke.points,
                            flow=1.,erase=False)
            coverage=rasterize_mask(replace(common,strokes=(segment,)),width,height)
            if extending:coverage=np.maximum(self.coverage,coverage)
        weighted=coverage*stroke.flow
        final=base*(1-weighted) if stroke.erase else base+(1-base)*weighted
        self.key,self.prefix,self.base=key,prefix,base
        self.stroke,self.coverage,self.final=stroke,coverage,final
        return 1-final if inverted else final


class _Task(QRunnable):
    def __init__(self,owner,key,color):
        super().__init__();self.owner=owner;self.key=key;self.color=color
    def run(self):
        try:
            layer,dims,geometry=self.key
            width,height=dims;scale=min(1.,1024/max(width,height))
            width,height=max(1,round(width*scale)),max(1,round(height*scale))
            if self.owner.cache_key==self.key:
                alpha=self.owner.cache_alpha
            elif layer.kind=='brush' and layer.strokes:
                alpha=self.owner.brush.render(layer,width,height)
                alpha=np.asarray(apply_geometry_image(Image.fromarray(alpha),geometry),np.float32)
            else:
                alpha=rasterize_mask(layer,width,height)
                alpha=np.asarray(apply_geometry_image(Image.fromarray(alpha),geometry),np.float32)
            pixels=np.empty((*alpha.shape,4),np.uint8)
            pixels[...,:3]=(245,74,91) if self.color=='red' else (25,213,229)
            pixels[...,3]=np.rint(np.clip(alpha,0,1)*255).astype(np.uint8)
            result=(self.key,self.color,alpha,QImage(ImageQt(Image.fromarray(pixels))).copy(),None)
        except Exception as error:result=(self.key,self.color,None,None,str(error))
        self.owner.finished.emit(result)


class MaskOverlay(QObject):
    changed=Signal()
    finished=Signal(object)
    def __init__(self,provider,parent=None):
        super().__init__(parent);self.provider=provider;self.pool=QThreadPool(self);self.pool.setMaxThreadCount(1)
        self.visible=False;self.color='red';self.source='';self.key=None;self.busy=False;self.pending=False;self.closed=False
        self.cache_key=None;self.cache_alpha=None;self.version=0
        self.brush=_BrushRaster()
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(16);self.timer.timeout.connect(self.start)
        self.finished.connect(self.done)
    def update(self,layer,dims,geometry):
        key=None if layer is None or min(dims)<1 else (replace(layer,name='',exposure=0.,temperature=0.,tint=0.,contrast=0.,saturation=0.,highlights=0.,shadows=0.,opacity=1.,enabled=True),tuple(dims),geometry)
        if key==self.key:return
        old_id=self.key[0].id if self.key else ''
        self.key=key
        if key is None or key[0].id!=old_id:
            self.source='';self.changed.emit()
        self.request()
    def set_visible(self,value):
        self.visible=bool(value)
        if self.visible:self.request()
    def set_color(self,value):
        if value in ('red','cyan') and value!=self.color:self.color=value;self.request()
    def request(self):
        self.pending=True
        if self.visible and not self.busy and not self.timer.isActive():self.timer.start()
    def start(self):
        if self.closed or self.busy or not self.visible or self.key is None:return
        self.pending=False;self.busy=True;self.pool.start(_Task(self,self.key,self.color))
    def done(self,result):
        self.busy=False
        if self.closed:return
        key,color,alpha,image,error=result
        if not error:
            self.cache_key,self.cache_alpha=key,alpha
            if key==self.key and color==self.color:
                self.provider.publish('mask-overlay',image);self.version+=1
                self.source=f'image://photos/mask-overlay?v={self.version}';self.changed.emit()
        if self.pending and self.visible:self.timer.start()
    def close(self):
        self.closed=True;self.timer.stop();self.pool.waitForDone();self.cache_alpha=None;self.brush=_BrushRaster()
