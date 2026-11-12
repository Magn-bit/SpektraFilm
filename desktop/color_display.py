"""Float RGB LittleCMS display conversion and opt-in ICC soft proofing.

The source is encoded wide-gamut float32, not the RGB8 preview. Display and
proof transforms affect preview only; exported samples/ICC remain unchanged.
LittleCMS 2.20 is built from its MIT source under native/color.
"""
from __future__ import annotations

from collections import OrderedDict
import ctypes as ct
from functools import lru_cache
import json
import os
from pathlib import Path
import struct
import sys
import threading

import numpy as np
from PySide6.QtCore import QObject, Property, Signal, Slot
from PySide6.QtWidgets import QFileDialog

from shared.color_management import icc_profile, convert_pixels
from .preferences import _atomic_json

ROOT=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
_LOCK=threading.RLock()
_CMS=None
_TRANSFORMS=OrderedDict()
RGB_FLOAT=(1<<22)|(4<<16)|(3<<3)|4


@lru_cache(maxsize=8)
def _standard_srgb_monitor(data):
    """Recognize matrix/TRC sRGB, including Windows' sampled v2 profile.

    Profile names and filenames are not evidence of primaries or calibration.
    A LUT, calibration table, shifted colourants or changed TRC rejects the
    shortcut and keeps that monitor in LittleCMS.
    """
    if not data or data==icc_profile('sRGB'):return True
    try:
        from .raw_source import _icc_tags,_icc_curve
        from shared.color_management import decode
        tags=_icc_tags(data);standard=_icc_tags(icc_profile('sRGB'))
        if any(key in tags for key in (b'A2B0',b'A2B1',b'A2B2',b'B2A0',b'B2A1',b'B2A2',b'vcgt')):return False
        if b'bkpt' in tags and any(struct.unpack_from('>iii',tags[b'bkpt'],8)):return False
        samples=np.linspace(0,1,1025,dtype=np.float32)
        expected=decode(samples)
        for channel in (b'r',b'g',b'b'):
            colorant=tags[channel+b'XYZ'];reference=standard[channel+b'XYZ']
            if colorant[:4]!=b'XYZ ':return False
            xyz=np.asarray(struct.unpack_from('>iii',colorant,8))/65536
            target=np.asarray(struct.unpack_from('>iii',reference,8))/65536
            if np.max(np.abs(xyz-target))>.00008:return False
            if np.max(np.abs(_icc_curve(tags[channel+b'TRC'],samples)-expected))>.000025:return False
        return True
    except (ValueError,KeyError,struct.error):return False


def standard_srgb_display(config):
    return not config.get('proof') and _standard_srgb_monitor(config.get('monitor'))


def canvas_pixels(pixels, source_space, config):
    """Proof the canvas with the engine's output gamut, never alter exports.

    The default judges the wide original print. Narrower canvas spaces apply
    CAM16 chroma compression without applying a second lightness shoulder.
    """
    target=(config or {}).get('canvas_space','ProPhoto RGB')
    if target=='ProPhoto RGB':return pixels,source_space
    from .native_spectral import transform_color
    return transform_color(pixels,source_space,target),target


@lru_cache(maxsize=8)
def _srgb_profile_transform(source_space,monitor):
    from .raw_source import _icc_tags
    source=_icc_tags(icc_profile(source_space));target=_icc_tags(monitor)
    def matrix(tags):
        return np.column_stack([np.asarray(struct.unpack_from('>iii',tags[channel+b'XYZ'],8),np.float64)/65536
                                for channel in (b'r',b'g',b'b')])
    return source,target,np.linalg.solve(matrix(target),matrix(source)).astype(np.float32)


@lru_cache(maxsize=8)
def _srgb_fast_tables(monitor):
    from .raw_source import _icc_curve
    source,target,matrix=_srgb_profile_transform('sRGB',monitor)
    axis=np.linspace(0,1,65537,dtype=np.float32)
    decoding=np.ascontiguousarray(_icc_curve(source[b'rTRC'],axis),dtype=np.float32)
    encoding=np.ascontiguousarray([_icc_curve(target[c+b'TRC'],axis,inverse=True)
                                  for c in (b'r',b'g',b'b')],dtype=np.float32)
    curve=np.asarray(struct.unpack_from('>7i',source[b'rTRC'],12),np.float32)/np.float32(65536)
    return decoding,encoding,matrix,curve


def _matrix_srgb_display(source,source_space,monitor):
    # Windows' sampled v2 sRGB profile contains slightly different rounded
    # colourants. Honor those exact tables instead of replacing it with the
    # name-matched analytic sRGB profile, which can shift a saturated shadow.
    from .raw_source import _icc_curve
    if source_space=='sRGB':
        with _LOCK:lib=_cms()
        if hasattr(lib,'spk_matrix_display_srgb'):
            decoding,encoding,matrix,curve=_srgb_fast_tables(monitor)
            output=np.empty_like(source)
            status=lib.spk_matrix_display_srgb(ct.c_void_p(source.ctypes.data),ct.c_void_p(output.ctypes.data),
                source.shape[0]*source.shape[1],ct.c_void_p(decoding.ctypes.data),ct.c_void_p(encoding.ctypes.data),
                len(decoding),ct.c_void_p(matrix.ctypes.data),ct.c_void_p(curve.ctypes.data))
            if status:raise ValueError('显示矩阵变换需要有限 RGB 浮点像素')
            return output
    source_tags,target_tags,matrix=_srgb_profile_transform(source_space,monitor)
    output=np.empty_like(source)
    for top in range(0,len(source),128):
        block=source[top:top+128]
        linear=np.stack([_icc_curve(source_tags[c+b'TRC'],block[...,i])
                         for i,c in enumerate((b'r',b'g',b'b'))],axis=-1)@matrix.T
        for i,c in enumerate((b'r',b'g',b'b')):
            output[top:top+len(block),...,i]=_icc_curve(target_tags[c+b'TRC'],linear[...,i],inverse=True)
    return output


def _cms():
    global _CMS
    if _CMS is None:
        lib=ct.CDLL(str(ROOT/'native/color/runtime/spektrafilm_lcms2.dll'))
        specs={
            'cmsOpenProfileFromMem':([ct.c_void_p,ct.c_uint32],ct.c_void_p),
            'cmsCloseProfile':([ct.c_void_p],ct.c_int),
            'cmsGetColorSpace':([ct.c_void_p],ct.c_uint32),
            'cmsCreateTransform':([ct.c_void_p,ct.c_uint32,ct.c_void_p,ct.c_uint32,ct.c_uint32,ct.c_uint32],ct.c_void_p),
            'cmsCreateProofingTransform':([ct.c_void_p,ct.c_uint32,ct.c_void_p,ct.c_uint32,ct.c_void_p,ct.c_uint32,ct.c_uint32,ct.c_uint32],ct.c_void_p),
            'cmsDeleteTransform':([ct.c_void_p],None),
            'cmsDoTransform':([ct.c_void_p,ct.c_void_p,ct.c_void_p,ct.c_uint32],None),
            'cmsSetAlarmCodes':([ct.POINTER(ct.c_uint16)],None),
        }
        for name,(arguments,result) in specs.items():
            fn=getattr(lib,name);fn.argtypes=arguments;fn.restype=result
        if hasattr(lib,'spk_matrix_display_srgb'):
            lib.spk_matrix_display_srgb.argtypes=[ct.c_void_p,ct.c_void_p,ct.c_uint32,
                ct.c_void_p,ct.c_void_p,ct.c_uint32,ct.c_void_p,ct.c_void_p]
            lib.spk_matrix_display_srgb.restype=ct.c_int
        # Gamut warning is an explicit option; neutral grey/purple is visible
        # on photographs without being confused with the red mask overlay.
        alarms=(ct.c_uint16*16)(65535,0,65535)
        lib.cmsSetAlarmCodes(alarms)
        _CMS=lib
    return _CMS


def _profile(lib,data):
    handle=lib.cmsOpenProfileFromMem(data,len(data))
    if not handle:raise ValueError('ICC 配置无效或不受支持')
    return handle


def validate_profile(data,*,display=False):
    if not isinstance(data,bytes) or not 128<=len(data)<=8*1024**2:raise ValueError('ICC 配置大小无效')
    with _LOCK:
        lib=_cms();handle=_profile(lib,data)
        try:
            if display and lib.cmsGetColorSpace(handle)!=0x52474220:raise ValueError('显示器需要 RGB ICC 配置')
        finally:lib.cmsCloseProfile(handle)


def transform_pixels(pixels,source_space,config):
    source=np.ascontiguousarray(pixels,dtype=np.float32)
    if source.ndim!=3 or source.shape[2]!=3:raise ValueError('显示变换需要 RGB 浮点像素')
    monitor=config.get('monitor') or icc_profile('sRGB')
    proof=config.get('proof')
    # Our built-in RGB profiles are matrix/TRC profiles. With the standard
    # sRGB display and no proof transform, their direct float transform is the
    # same colour operation; a generic ICC curve evaluator adds hundreds of
    # milliseconds to a small interactive frame on some Windows CPUs. Keep
    # arbitrary monitor profiles and all proof/gamut transforms in LittleCMS.
    if not proof and _standard_srgb_monitor(monitor):
        if monitor==icc_profile('sRGB'):
            return source.copy() if source_space == 'sRGB' else convert_pixels(source,source_space,'sRGB')
        return _matrix_srgb_display(source,source_space,monitor)
    key=(source_space,monitor,proof,int(config.get('intent',1)),bool(config.get('gamut',False)))
    output=np.empty_like(source)
    with _LOCK:
        lib=_cms();transform=_TRANSFORMS.get(key)
        if transform is None:
            handles=[]
            try:
                for data in (icc_profile(source_space),monitor):handles.append(_profile(lib,data))
                flags=0x0040|0x2000 # no cache, black-point compensation
                if proof:
                    handles.append(_profile(lib,proof));flags|=0x4000
                    if config.get('gamut'):flags|=0x1000
                    transform=lib.cmsCreateProofingTransform(handles[0],RGB_FLOAT,handles[1],RGB_FLOAT,handles[2],key[3],1,flags)
                else:transform=lib.cmsCreateTransform(handles[0],RGB_FLOAT,handles[1],RGB_FLOAT,key[3],flags)
                if not transform:raise ValueError('无法创建此 ICC 显示／打样变换')
            finally:
                for handle in handles:lib.cmsCloseProfile(handle)
            _TRANSFORMS[key]=transform
            while len(_TRANSFORMS)>8:lib.cmsDeleteTransform(_TRANSFORMS.popitem(last=False)[1])
        _TRANSFORMS.move_to_end(key)
        for top in range(0,len(source),128):
            block=source[top:top+128];target=output[top:top+128]
            lib.cmsDoTransform(transform,ct.c_void_p(block.ctypes.data),ct.c_void_p(target.ctypes.data),block.shape[0]*block.shape[1])
    return output


def system_monitor_profile(device=''):
    if os.name!='nt':return ''
    gdi=ct.windll.gdi32
    gdi.CreateDCW.argtypes=[ct.c_wchar_p,ct.c_wchar_p,ct.c_void_p,ct.c_void_p];gdi.CreateDCW.restype=ct.c_void_p
    gdi.GetICMProfileW.argtypes=[ct.c_void_p,ct.POINTER(ct.c_uint32),ct.c_wchar_p]
    gdi.DeleteDC.argtypes=[ct.c_void_p]
    dc=gdi.CreateDCW('DISPLAY',device or None,None,None)
    if not dc:return ''
    try:
        size=ct.c_uint32(32768);buffer=ct.create_unicode_buffer(size.value)
        return buffer.value if gdi.GetICMProfileW(dc,ct.byref(size),buffer) else ''
    finally:gdi.DeleteDC(dc)


class ColorDisplay(QObject):
    changed=Signal()
    renderChanged=Signal()
    message=Signal(str)

    def __init__(self,parent,path):
        super().__init__(parent);self._path=Path(path);self._device='';self._monitor=None;self._proof=None
        try:self._settings=json.loads(self._path.read_text(encoding='utf-8'))
        except (OSError,ValueError):self._settings={}
        if not isinstance(self._settings,dict):self._settings={}
        self._enabled=bool(self._settings.get('enabled',True));self._proof_enabled=False
        self._canvas_space=self._settings.get('canvas_space','ProPhoto RGB')
        if self._canvas_space not in ('sRGB','Adobe RGB (1998)','Display P3','ProPhoto RGB'):self._canvas_space='ProPhoto RGB'
        self._gamut=False;self._proof_space='sRGB';self._monitor_path='';self._proof_path=''
        self.setMonitor('')

    @Property(bool,notify=changed)
    def enabled(self):return self._enabled
    @Property(bool,notify=changed)
    def proofEnabled(self):return self._proof_enabled
    @Property(bool,notify=changed)
    def gamutWarning(self):return self._gamut
    @Property(str,notify=changed)
    def proofSpace(self):return self._proof_space
    @Property(str,notify=changed)
    def canvasSpace(self):return self._canvas_space
    @Property(str,notify=changed)
    def monitorName(self):return Path(self._monitor_path).stem if self._monitor_path else 'sRGB'
    @Property(str,notify=changed)
    def proofName(self):return Path(self._proof_path).stem if self._proof_path else self._proof_space

    def snapshot(self):
        return dict(monitor=self._monitor if self._enabled else None,
                    proof=(self._proof or icc_profile(self._proof_space)) if self._proof_enabled else None,
                    gamut=self._gamut,canvas_space=self._canvas_space)

    def _save(self):
        try:_atomic_json(self._path,dict(self._settings,enabled=self._enabled,canvas_space=self._canvas_space))
        except OSError as error:self.message.emit(str(error))

    @Slot(str)
    def setCanvasSpace(self,value):
        if value not in ('sRGB','Adobe RGB (1998)','Display P3','ProPhoto RGB') or value==self._canvas_space:return
        self._canvas_space=value;self._save();self.changed.emit();self.renderChanged.emit()

    @Slot(str)
    def setMonitor(self,device):
        self._device=device;path=system_monitor_profile(device)
        try:
            data=Path(path).read_bytes() if path else None
            if data:validate_profile(data,display=True)
        except (OSError,ValueError):path='';data=None
        if data!=self._monitor:self._monitor=data;self._monitor_path=path;self.changed.emit();self.renderChanged.emit()

    @Slot(bool)
    def setEnabled(self,value):
        self._enabled=bool(value);self.changed.emit();self.renderChanged.emit()
        self._save()

    @Slot(bool)
    def setProofEnabled(self,value):
        self._proof_enabled=bool(value);self.changed.emit();self.renderChanged.emit()

    @Slot(bool)
    def setGamutWarning(self,value):
        self._gamut=bool(value);self.changed.emit();self.renderChanged.emit()

    @Slot(str)
    def setProofSpace(self,value):
        if value not in ('sRGB','Adobe RGB (1998)','Display P3','ProPhoto RGB'):return
        self._proof_space=value;self._proof=None;self._proof_path='';self.changed.emit();self.renderChanged.emit()

    @Slot()
    def chooseProofProfile(self):
        path,_=QFileDialog.getOpenFileName(None,'选择打样 ICC 配置','','ICC 配置 (*.icc *.icm)')
        if not path:return
        try:data=Path(path).read_bytes();validate_profile(data)
        except (OSError,ValueError) as error:self.message.emit(str(error));return
        self._proof=data;self._proof_path=path;self._proof_enabled=True;self.changed.emit();self.renderChanged.emit()
