"""Session-derived full-size HDR gain maps and real ISO/Ultra HDR JPEG files.

The SDR raster stays the ordinary recipe output. Prints/edited slides derive
grain-aware gain from those final pixels; unedited slides use actual paired
spectral renditions, mapped to the exact final geometry. Neither uses enlarged
thumbnail gain. The native libultrahdr codec carries/decodes the real map.
"""
from __future__ import annotations

import ctypes as C
from dataclasses import asdict
from functools import lru_cache
import io
import json
import math
from pathlib import Path
import sys

import numpy as np
from PIL import Image


class HDROutputError(RuntimeError):
    pass


class HDRRendition(np.ndarray):
    """An unchanged SDR array accompanied by its same-size mono gain map."""
    def __new__(cls,pixels,gain_map,headroom,*,color_space='sRGB',identity=None,curve=None):
        result=np.asarray(pixels).view(cls)
        gain_map=np.asarray(gain_map)
        if gain_map.dtype!=np.uint8 or gain_map.shape!=result.shape[:2]:
            raise HDROutputError('HDR 增益图必须与输出照片尺寸一致')
        if not math.isfinite(headroom) or not 1<headroom<=16*1.05:
            raise HDROutputError('HDR 峰值范围无效')
        result.gain_map=gain_map
        result.headroom=float(headroom)
        result.hdr_color_space=color_space
        result.hdr_identity=identity
        result.hdr_curve=curve
        return result

    def __array_finalize__(self,source):
        if source is None:return
        for name in ('gain_map','headroom','hdr_color_space','hdr_identity','hdr_curve'):
            setattr(self,name,getattr(source,name,None))


def _check(cancel):
    if cancel is not None and cancel.is_set():
        from .output import ExportCancelled
        raise ExportCancelled('导出已取消')


def validate(settings,recipe):
    from shared.darkroom import BLACK_AND_WHITE
    if recipe.format!='jpeg' or recipe.color_space not in ('sRGB','Display P3'):
        raise HDROutputError('HDR 增益图输出支持 sRGB / Display P3 的 JPEG 配方')
    if not settings.film_enabled or settings.strength<=0:
        raise HDROutputError('HDR 增益图需要开启胶片显影')
    if settings.extended_dynamic_range:
        raise HDROutputError('HDR 增益图不能与相纸 EDR 同时启用')
    if settings.scan_film or settings.digital_intermediate or settings.stock in BLACK_AND_WHITE:
        raise HDROutputError('HDR 增益图适用于彩色印相或反转片显影，不支持底片扫描、数字中间片或黑白胶片')
    peak=getattr(settings,'hdr_peak_stops',2)
    if isinstance(peak,bool) or not isinstance(peak,(int,float)) or not math.isfinite(peak) or not .5<=peak<=4:
        raise HDROutputError('HDR 峰值应为 0.5–4 EV')
    return True


def _source_identity(path):
    path=Path(path).resolve();stat=path.stat()
    return (str(path),stat.st_size,stat.st_mtime_ns)


def _parse_curve(value):
    if isinstance(value,str):value=json.loads(value)
    if not isinstance(value,dict):raise HDROutputError('光谱引擎未返回 HDR 曲线')
    result=dict(value)
    for key in ('headroom','top','kappa','rho_max','detail_clamp'):
        v=value.get(key)
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v):
            raise HDROutputError('HDR 曲线参数无效：'+key)
        result[key]=float(v)
    if not 1<result['headroom']<=16 or abs(math.log2(result['headroom'])-result['top'])>1e-6:
        raise HDROutputError('HDR 曲线峰值不一致')
    domain=np.asarray(value.get('domain_log2_y',[]),dtype=np.float64)
    if domain.shape!=(2,) or not np.isfinite(domain).all() or domain[1]<=domain[0]:
        raise HDROutputError('HDR 曲线亮度范围无效')
    result['domain_log2_y']=domain
    for key in ('log2_gain','ks','rho'):
        samples=np.asarray(value.get(key,[]),dtype=np.float32)
        if samples.shape!=(256,) or not np.isfinite(samples).all():
            raise HDROutputError('HDR 曲线必须包含 256 个有限采样：'+key)
        result[key]=samples
    if abs(float(result['log2_gain'][-1])-result['top'])>1e-5:
        raise HDROutputError('HDR 曲线末端不匹配峰值')
    if result['detail_clamp']<0 or result['rho_max']<0:
        raise HDROutputError('HDR 颗粒恢复参数无效')
    return result


def _log_luminance(pixels,color_space):
    # Same extended sRGB CCTF as HDRMath.swift; both supported gamuts use it.
    values=np.array(pixels,dtype=np.float32,copy=True,order='C')
    if np.asarray(pixels).dtype==np.uint8:values*=np.float32(1/255)
    elif np.asarray(pixels).dtype==np.uint16:values*=np.float32(1/65535)
    if not np.isfinite(values).all():raise HDROutputError('HDR 输入包含无效像素')
    np.maximum(values,0,out=values)
    linear=np.where(values<=.04045,values/np.float32(12.92),((values+np.float32(.055))/np.float32(1.055))**np.float32(2.4))
    weights=(.2289746,.6917385,.0792869) if color_space=='Display P3' else (.2126,.7152,.0722)
    y=linear[:,:,0]*np.float32(weights[0])
    y+=linear[:,:,1]*np.float32(weights[1]);y+=linear[:,:,2]*np.float32(weights[2])
    np.maximum(y,np.float32(1e-30),out=y);np.log2(y,out=y)
    return y


def grain_sigma(pixels,color_space):
    """Port of HDRGrainGain's measured centre-crop autocorrelation (≤256²)."""
    from scipy.ndimage import gaussian_filter
    h,w=pixels.shape[:2];cw,ch=min(w,256),min(h,256)
    if min(cw,ch)<32:return 2.
    x,y=(w-cw)//2,(h-ch)//2
    tone=_log_luminance(pixels[y:y+ch,x:x+cw],color_space)
    base=gaussian_filter(tone,2,mode='nearest',truncate=3)
    residual=tone-base;by,bx=ch//16,cw//16
    def blocks(p):return p[:by*16,:bx*16].reshape(by,16,bx,16).transpose(0,2,1,3).reshape(-1,16,16)
    r,b=blocks(residual),blocks(base)
    r=r-r.mean(axis=(1,2),keepdims=True);b=b-b.mean(axis=(1,2),keepdims=True)
    v=np.mean(r*r,axis=(1,2));bv=np.mean(b*b,axis=(1,2))
    use=(v>1e-9)&(bv<v)
    if np.count_nonzero(use)<8:return 2.
    r,v=r[use],v[use]
    width=0
    for lag in range(1,5):
        c=(np.sum(r[:,:,:-lag]*r[:,:,lag:],axis=(1,2))+np.sum(r[:,:-lag,:]*r[:,lag:,:],axis=(1,2)))/(2*16*(16-lag))
        if float(np.median(c/v))<.2:break
        width=lag
    return float(min(8,max(2,2*max(1,width))))


def gain_map(pixels,curve,color_space='sRGB',*,cancel=None,rows=256):
    """Full-size 8-bit gain, with bounded float scratch and exact Gaussian halo."""
    from scipy.ndimage import gaussian_filter
    if color_space not in ('sRGB','Display P3'):raise HDROutputError('HDR 增益图色彩空间无效')
    values=np.asarray(pixels)
    if values.ndim!=3 or values.shape[2]!=3 or min(values.shape[:2])<1:raise HDROutputError('HDR 需要 RGB 图像')
    table=_parse_curve(curve)
    h,w=values.shape[:2];out=np.empty((h,w),dtype=np.uint8)
    _check(cancel);sigma=grain_sigma(values,color_space);halo=math.ceil(3*sigma)
    lo,hi=table['domain_log2_y'];scale=np.float32(255/(hi-lo))
    for start in range(0,h,rows):
        _check(cancel);stop=min(h,start+rows);a,b=max(0,start-halo),min(h,stop+halo)
        own=_log_luminance(values[a:b],color_space)
        local=gaussian_filter(own,sigma,mode='nearest',truncate=3)
        own=own[start-a:stop-a];local=local[start-a:stop-a]
        delta=np.clip(own-local,-table['detail_clamp'],table['detail_clamp'])
        local=own-delta
        u=np.clip((local-np.float32(lo))*scale,0,255)
        i=np.minimum(u.astype(np.int32),254);f=u-i
        ks=table['ks'][i]+(table['ks'][i+1]-table['ks'][i])*f
        rho=table['rho'][i]+(table['rho'][i+1]-table['rho'][i])*f
        result=ks+np.float32(table['kappa'])*np.clip(rho,0,table['rho_max'])*delta
        result=np.clip(result,0,table['top'])*(255/table['top'])
        out[start:stop]=np.floor(result+.5).astype(np.uint8)
    _check(cancel)
    return out


def _post_active(settings):
    """The slide ratio precedes Layer 2, so an edited picture uses its curve."""
    from .imaging import Settings
    defaults=Settings()
    names=('contrast','brightness','warmth','saturation','vibrance','highlights','shadows','whites','blacks',
           'black_point','white_point','gamma','texture','clarity','dehaze','vignette','strength',
           'masks','curves','grading','channel_mixer','hsl','levels','look_lut')
    return any(getattr(settings,key)!=getattr(defaults,key) for key in names)


def _prophoto_luminance(pixels,*,cancel=None):
    """D50 ProPhoto Y as HDRGain.swift reads the native 16-bit result."""
    result=np.empty(pixels.shape[:2],dtype=np.float32)
    for top in range(0,len(pixels),128):
        _check(cancel)
        block=np.asarray(pixels[top:top+128],dtype=np.float32)
        decoded=np.where(block<np.float32(16/512),block/np.float32(16),np.maximum(block,0)**np.float32(1.8))
        result[top:top+len(block)]=decoded[:,:,0]*np.float32(.2880402)+decoded[:,:,1]*np.float32(.7118741)+decoded[:,:,2]*np.float32(.0000857)
    return result


def _map_geometry(codes,geometry,target_shape,*,cancel=None):
    """The same source-centre mapping/crop/resize as the SDR picture, mono only."""
    from shared.geometry import normalize_geometry,crop_box,geometry_matrix,is_neutral,Geometry
    g=normalize_geometry(geometry);h,w=codes.shape
    left,top,right,bottom=crop_box(w,h,g)
    # Exact quarter turns/crop avoid resampling an otherwise untouched map.
    plain=Geometry(**{**g.__dict__,'quarter_turns':0,'crop':(0.,0.,1.,1.)})
    if is_neutral(plain):
        oriented=np.rot90(codes,-g.quarter_turns) if g.quarter_turns%4 else codes
        result=oriented[top:bottom,left:right]
    else:
        from scipy.ndimage import map_coordinates
        inverse=np.linalg.inv(geometry_matrix(w,h,g));result=np.empty((bottom-top,right-left),dtype=np.uint8)
        columns=np.arange(left,right,dtype=np.float64)[None,:]
        for first in range(top,bottom,96):
            _check(cancel);last=min(bottom,first+96);rows=np.arange(first,last,dtype=np.float64)[:,None]
            denominator=inverse[2,0]*columns+inverse[2,1]*rows+inverse[2,2]
            xx=(inverse[0,0]*columns+inverse[0,1]*rows+inverse[0,2])/denominator
            yy=(inverse[1,0]*columns+inverse[1,1]*rows+inverse[1,2])/denominator
            map_coordinates(codes,(yy,xx),output=result[first-top:last-top],order=1,prefilter=False,mode='constant',cval=0)
    if result.shape!=tuple(target_shape):
        _check(cancel)
        with Image.fromarray(np.asarray(result,dtype=np.float32)) as source:
            with source.resize((target_shape[1],target_shape[0]),Image.Resampling.LANCZOS) as resized:
                result=np.floor(np.clip(np.asarray(resized,dtype=np.float32),0,255)+.5).astype(np.uint8)
    _check(cancel)
    return np.ascontiguousarray(result)


def _slide_map(scene,settings,headroom,target_shape,*,cancel=None):
    from . import native_spectral
    _check(cancel)
    # Sequential RGB -> luminance release: two full RGB renditions never stay
    # resident together merely to calculate their scalar ratio.
    sdr=native_spectral.render_spectral(scene,settings,output_color_space='ProPhoto RGB',
        scan_hdr_overrides=dict(scan_hdr_stretch=True,scan_hdr_headroom=0.,scan_hdr_output_scale=1.,grain_seed=743))
    sdr_y=_prophoto_luminance(sdr,cancel=cancel);del sdr
    _check(cancel)
    hdr=native_spectral.render_spectral(scene,settings,output_color_space='ProPhoto RGB',
        scan_hdr_overrides=dict(scan_hdr_stretch=False,scan_hdr_headroom=headroom,scan_hdr_output_scale=1/headroom,grain_seed=743))
    hdr_y=_prophoto_luminance(hdr,cancel=cancel);del hdr
    peak=1.
    for top in range(0,len(sdr_y),256):
        _check(cancel);ys=sdr_y[top:top+256];yh=hdr_y[top:top+len(ys)]
        gain=np.divide(yh*np.float32(headroom),ys,out=np.ones_like(ys),where=ys>1e-4)
        np.maximum(gain,1,out=gain);peak=max(peak,float(gain.max()));sdr_y[top:top+len(ys)]=gain
    del hdr_y
    peak=max(1.0001,min(peak,headroom*1.05));scale=np.float32(255/math.log2(peak))
    codes=np.empty(sdr_y.shape,dtype=np.uint8)
    for top in range(0,len(sdr_y),256):
        _check(cancel);band=sdr_y[top:top+256]
        codes[top:top+len(band)]=np.floor(np.clip(np.log2(band)*scale,0,255)+.5).astype(np.uint8)
    del sdr_y
    return _map_geometry(codes,settings.geometry,target_shape,cancel=cancel),peak


def prepare_rendition(path,settings,recipe,sdr_pixels,*,max_edge=None,cancel=None):
    """Attach gain of this exact final/proof canvas using its own session medium."""
    if not getattr(settings,'hdr_enabled',False):return sdr_pixels
    validate(settings,recipe);_check(cancel)
    from .full_detail import read_cached_photo
    from .imaging import prepare_photo_source,film_settings
    from .raw_source import source_pixels,source_metadata
    from . import native_spectral
    source_id=_source_identity(path)
    settings=film_settings(settings)
    headroom=2**float(getattr(settings,'hdr_peak_stops',2))
    if not 1<headroom<=16:raise HDROutputError('HDR 峰值应大于 0 且不超过 4 EV')
    original=read_cached_photo(path,max_edge=max_edge,cancel=cancel);prepared=None;codes=None
    try:
        _check(cancel);prepared,_=prepare_photo_source(original,path,settings)
        if prepared is not original:original.close();original=None
        full=tuple(prepared.info.get('source_size',prepared.size));metadata=source_metadata(prepared)
        scene=native_spectral.process_editor(source_pixels(prepared),settings,stage='pre',
            exposure_ev=float(metadata.get('baseline_exposure_ev',0)),
            source_color_space=metadata['source_color_space'],source_linear=metadata['source_linear'],
            source_size=full,pixel_scale=(full[0]/prepared.width,full[1]/prepared.height))
        _check(cancel)
        from shared.darkroom import scans_directly
        if scans_directly(settings.stock) and not _post_active(settings):
            requested=headroom
            codes,headroom=_slide_map(scene,settings,headroom,sdr_pixels.shape[:2],cancel=cancel)
            curve=dict(mode='slide-rendition',requested_headroom=requested,headroom=headroom,grain_seed=743)
        else:
            curve=native_spectral.hdr_curve(scene,settings,{'headroom':headroom},
                source_token=(source_id,'hdr-medium',int(max_edge or 0)))
        del scene
        _check(cancel)
    finally:
        if original is not None:original.close()
        if prepared is not None and prepared is not original:prepared.close()
    if _source_identity(path)!=source_id:raise OSError('照片已变更，请重新载入')
    if codes is None:
        table=_parse_curve(curve)
        if abs(table['headroom']-headroom)>1e-5:raise HDROutputError('HDR 曲线不属于当前峰值设置')
        codes=gain_map(sdr_pixels,curve,recipe.color_space,cancel=cancel)
    if _source_identity(path)!=source_id:raise OSError('照片已变更，请重新载入')
    identity=(source_id,json.dumps(asdict(settings),sort_keys=True,ensure_ascii=False),
              recipe.color_space,int(max_edge or 0),tuple(sdr_pixels.shape),headroom)
    return HDRRendition(sdr_pixels,codes,headroom,color_space=recipe.color_space,identity=identity,curve=curve)


@lru_cache(maxsize=1)
def _codec():
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
    path=root/'native/hdr/runtime/spektrafilm_hdr.dll'
    if not path.is_file():raise HDROutputError('缺少 HDR 输出组件，请修复应用安装')
    library=C.CDLL(str(path))
    library.spk_hdr_version.restype=C.c_char_p
    library.spk_hdr_error.restype=C.c_char_p
    library.spk_hdr_free.argtypes=[C.c_void_p]
    library.spk_hdr_encode.argtypes=[C.c_void_p,C.c_size_t,C.c_void_p,C.c_size_t,C.c_float,C.c_int,C.POINTER(C.c_void_p),C.POINTER(C.c_size_t)]
    library.spk_hdr_encode.restype=C.c_int
    library.spk_hdr_decode.argtypes=[C.c_void_p,C.c_size_t,C.c_float,C.POINTER(C.c_void_p),C.POINTER(C.c_size_t),C.POINTER(C.c_uint),C.POINTER(C.c_uint),C.POINTER(C.c_uint),C.POINTER(C.c_uint),C.POINTER(C.c_float)]
    library.spk_hdr_decode.restype=C.c_int
    return library


def base_jpeg(pixels,recipe,profile):
    from .output import _quantize
    stream=io.BytesIO()
    Image.fromarray(_quantize(np.asarray(pixels),8)).save(stream,format='JPEG',quality=recipe.quality,subsampling=0,icc_profile=profile)
    return stream.getvalue()


def encode_jpeg(target,pixels,recipe,profile,cancel=None):
    """Keep the SDR scan and attach a real full-resolution ISO+Adobe gain image."""
    _check(cancel)
    if not isinstance(pixels,HDRRendition) or pixels.gain_map is None:
        raise HDROutputError('HDR 输出缺少实际增益图')
    if pixels.gain_map.shape!=pixels.shape[:2] or pixels.hdr_color_space!=recipe.color_space:
        raise HDROutputError('HDR 增益图的尺寸或色彩空间已变更，请重新渲染')
    base=base_jpeg(pixels,recipe,profile);_check(cancel)
    stream=io.BytesIO();Image.fromarray(pixels.gain_map).save(stream,format='JPEG',quality=100)
    gain=stream.getvalue();_check(cancel)
    library=_codec();out=C.c_void_p();size=C.c_size_t()
    result=library.spk_hdr_encode(base,len(base),gain,len(gain),pixels.headroom,
        1 if recipe.color_space=='Display P3' else 0,C.byref(out),C.byref(size))
    if result:raise HDROutputError(library.spk_hdr_error().decode('utf-8','replace'))
    try:
        _check(cancel)
        # Bounded copy from native owned memory; avoid a second file-sized bytes.
        for start in range(0,size.value,4<<20):
            _check(cancel);target.write(C.string_at(out.value+start,min(4<<20,size.value-start)))
    finally:library.spk_hdr_free(out)
    _check(cancel)


def decode_jpeg(data,*,display_boost=16):
    """Independent codec read-back: linear HDR half floats and actual map size."""
    if isinstance(data,(str,Path)):data=Path(data).read_bytes()
    library=_codec();out=C.c_void_p();size=C.c_size_t()
    width,height,mw,mh=C.c_uint(),C.c_uint(),C.c_uint(),C.c_uint();headroom=C.c_float()
    status=library.spk_hdr_decode(data,len(data),float(display_boost),C.byref(out),C.byref(size),
        C.byref(width),C.byref(height),C.byref(mw),C.byref(mh),C.byref(headroom))
    if status:raise HDROutputError(library.spk_hdr_error().decode('utf-8','replace'))
    try:
        pixels=np.frombuffer(C.string_at(out,size.value),dtype='<f2').reshape(height.value,width.value,4).copy()
        return pixels,dict(width=width.value,height=height.value,map_width=mw.value,map_height=mh.value,
                          headroom=headroom.value,codec=library.spk_hdr_version().decode('ascii'))
    finally:library.spk_hdr_free(out)
