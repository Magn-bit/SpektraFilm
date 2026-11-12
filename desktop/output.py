"""Recipe encoders: source-resolution rendering and bounded precision encoding."""
from pathlib import Path
import struct
import zlib

import numpy as np
from PIL import Image

from shared.color_management import icc_profile, convert_pixels, MATRICES
from shared.output_recipes import normalize_recipe,recipe_size
from .imaging import read_photo, prepare_photo_source, render_pixels, _publish_export, _tiff_strips, export_preset
from .raw_source import resize_pixels


class ExportCancelled(Exception):
    pass


def _check(cancel):
    if cancel is not None and cancel.is_set():
        raise ExportCancelled('导出已取消')


def _quantize(pixels, depth):
    output=np.empty(pixels.shape,dtype=np.uint8 if depth==8 else np.uint16)
    for top in range(0,len(pixels),64):
        values=np.array(pixels[top:top+64],dtype=np.float32,copy=True,order='C')
        np.nan_to_num(values,copy=False,nan=0,posinf=1,neginf=0)
        np.clip(values,0,1,out=values)
        values*=255 if depth==8 else 65535
        np.rint(values,out=values)
        output[top:top+len(values)]=values
    return output


def _png(target,pixels,depth,profile,cancel):
    """RGB PNG8/16, no RGB8 intermediate; stream one bounded group of rows."""
    def chunk(kind,data):
        target.write(struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(data,zlib.crc32(kind))))
    height,width=pixels.shape[:2]
    target.write(b'\x89PNG\r\n\x1a\n')
    chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,depth,2,0,0,0))
    chunk(b'iCCP',b'SpektraFilm RGB\0\0'+zlib.compress(profile))
    encoder=zlib.compressobj(1)
    bpp=3*depth//8
    for top in range(0,height,16):
        _check(cancel)
        samples=_quantize(pixels[top:top+16],depth)
        if depth==16:samples=samples.astype('>u2')
        rows=samples.view(np.uint8).reshape(len(samples),width*bpp)
        filtered=np.empty((len(rows),rows.shape[1]+1),dtype=np.uint8)
        filtered[:,0]=1 # Sub filter; modulo arithmetic is defined for uint8.
        filtered[:,1:1+bpp]=rows[:,:bpp]
        np.subtract(rows[:,bpp:],rows[:,:-bpp],out=filtered[:,1+bpp:])
        data=encoder.compress(filtered.tobytes())
        if data:chunk(b'IDAT',data)
    data=encoder.flush()
    if data:chunk(b'IDAT',data)
    chunk(b'IEND',b'')


def _linear_dng(target,pixels,cancel):
    """Processed linear RGB DNG; explicitly distinct from original RAW copy."""
    import tifffile
    height,width=pixels.shape[:2]
    rows=32
    matrix=np.linalg.inv(MATRICES['sRGB'])
    rational=tuple(v for item in matrix.flat for v in (int(round(item*1000000)),1000000))
    tags=[(50706,'B',4,(1,4,0,0),False),(50707,'B',4,(1,3,0,0),False),
          (50708,'s',0,'SpektraFilm processed linear RGB',False),
          (50714,'H',3,(0,0,0),False),(50717,'I',3,(65535,65535,65535),False),
          (50719,'I',2,(0,0),False),(50720,'I',2,(width,height),False),
          (50721,'2i',9,rational,False),(50728,'2I',3,(1,1,1,1,1,1),False),
          (50778,'H',1,21,False),(274,'H',1,1,False)]
    def strips():
        for top in range(0,height,rows):
            _check(cancel)
            linear=convert_pixels(pixels[top:top+rows],linear_output=True)
            yield _quantize(linear,16).tobytes()
    handle=tifffile.FileHandle(target,mode='wb',name='SpektraFilm.dng')
    tifffile.imwrite(handle,data=strips(),shape=pixels.shape,dtype=np.uint16,
        photometric=34892,planarconfig='contig',rowsperstrip=rows,metadata=None,extratags=tags,
        software='SpektraFilm',description='Processed linear RGB; original camera RAW is unchanged')


def export_recipe(path,destination,settings,recipe,*,cancel=None,progress=None,encoded_proof=None):
    recipe=normalize_recipe(recipe)
    _check(cancel)
    if recipe.format=='raw':return export_preset(path,destination,settings,'RAW')
    expected={'jpeg':('.jpg','.jpeg'),'heif':('.heic','.heif'),'png':('.png',),'tiff':('.tif','.tiff'),'di':('.tif','.tiff'),'dng':('.dng',)}
    if Path(destination).suffix.lower() not in expected[recipe.format]:
        raise ValueError('文件扩展名与配方不一致')
    if encoded_proof is not None and encoded_proof.matches(path,settings,recipe):
        if progress:progress('encode')
        return encoded_proof.publish(destination,recipe,cancel)
    pixels=render_recipe_pixels(path,settings,recipe,cancel=cancel,progress=progress)
    return export_pixels(pixels,destination,recipe,cancel=cancel,progress=progress,metadata_source=path)


def render_recipe_pixels(path,settings,recipe,*,max_edge=None,cancel=None,progress=None):
    """One render contract for an encoded proof and the final output.

    max_edge is exclusively an explicitly labelled proof proxy. Final callers
    leave it unset; a recipe's own resize always follows development/cropping.
    """
    recipe=normalize_recipe(recipe)
    if recipe.format=='raw':raise ValueError('RAW原片不经过显影')
    if settings.hdr_enabled:
        from .hdr_output import validate
        validate(settings,recipe)
    if max_edge is None:
        from .full_detail import render_full_pixels
        pixels=render_full_pixels(path,settings,color_space=recipe.color_space,
            digital_intermediate=recipe.format=='di',di_blue_compensation=recipe.di_blue_compensation,cancel=cancel,progress=progress)
        _check(cancel)
        size=recipe_size(pixels.shape[1],pixels.shape[0],recipe)
        if size!=(pixels.shape[1],pixels.shape[0]):pixels=resize_pixels(pixels,size)
        if settings.hdr_enabled:
            from .hdr_output import prepare_rendition
            pixels=prepare_rendition(path,settings,recipe,pixels,cancel=cancel)
        return pixels
    if progress:progress('decode')
    # Always decode the source; recipe resizing is applied after edits/crop.
    # A preview or embedded thumbnail can never enter this encoder.
    original=read_photo(path,max_edge=max_edge)
    prepared=None
    try:
        _check(cancel)
        prepared,_=prepare_photo_source(original,path,settings)
        if prepared is not original:
            # Pillow's context manager would retain the original RAW owner
            # until after rendering, despite having a distinct corrected source.
            original.close();original=None
        if progress:progress('render')
        if recipe.format=='di':
            from .digital_intermediate import render_codes
            pixels=render_codes(prepared,settings,blue_compensation=recipe.di_blue_compensation)
        else:pixels=render_pixels(prepared,settings,preview=bool(max_edge),output_color_space=recipe.color_space)
    finally:
        if original is not None:original.close()
        if prepared is not None and prepared is not original:prepared.close()
        del original,prepared
    _check(cancel)
    size=recipe_size(pixels.shape[1],pixels.shape[0],recipe)
    if size!=(pixels.shape[1],pixels.shape[0]):
        pixels=resize_pixels(pixels,size)
    if settings.hdr_enabled:
        from .hdr_output import prepare_rendition
        pixels=prepare_rendition(path,settings,recipe,pixels,max_edge=max_edge,cancel=cancel)
    return pixels


def export_pixels(pixels,destination,recipe,*,cancel=None,progress=None,metadata_source=None):
    """Encode an already developed high precision canvas, with real ICC."""
    recipe=normalize_recipe(recipe)
    if recipe.format=='raw':raise ValueError('排版画布不能导出为原始相机RAW')
    from .hdr_output import HDRRendition
    if isinstance(pixels,HDRRendition) and recipe.format!='jpeg':
        raise ValueError('HDR 增益图输出需要 JPEG 配方')
    height,width=pixels.shape[:2]
    profile=None if recipe.format=='di' else icc_profile(recipe.color_space)
    if recipe.format=='di':
        from .digital_intermediate import companion_luts
        companion_luts(Path(destination).parent)
    if progress:progress('encode')
    def encode(target):
        _check(cancel)
        if recipe.format=='png':_png(target,pixels,recipe.bit_depth,profile,cancel)
        elif recipe.format=='heif':
            import pillow_heif
            pillow_heif.register_heif_opener()
            Image.fromarray(_quantize(pixels,8)).save(target,format='HEIF',quality=recipe.quality,icc_profile=profile)
        elif recipe.format=='dng':_linear_dng(target,pixels,cancel)
        elif recipe.format=='di':
            from .digital_intermediate import encode as encode_di
            encode_di(target,pixels,cancel,_check)
        elif recipe.format=='tiff':
            import tifffile
            if recipe.bit_depth==16:
                rows,compressed=_tiff_strips(pixels)
                def strips():
                    for data in compressed:
                        _check(cancel);yield data
                handle=tifffile.FileHandle(target,mode='wb',name='SpektraFilm.tif')
                tifffile.imwrite(handle,data=strips(),shape=pixels.shape,dtype=np.uint16,
                    photometric='rgb',compression='deflate',rowsperstrip=rows,metadata=None,iccprofile=profile)
            else:
                Image.fromarray(_quantize(pixels,8)).save(target,format='TIFF',compression='tiff_adobe_deflate',icc_profile=profile)
        else:
            if isinstance(pixels,HDRRendition):
                from .hdr_output import encode_jpeg
                encode_jpeg(target,pixels,recipe,profile,cancel)
            else:Image.fromarray(_quantize(pixels,8)).save(target,format='JPEG',quality=recipe.quality,subsampling=0,icc_profile=profile)
        _check(cancel)
        return width,height
    def metadata(path,dimensions):
        _check(cancel)
        if metadata_source:
            from .export_metadata import copy_capture_metadata
            copy_capture_metadata(metadata_source,path,dimensions)
        _check(cancel)
    return _publish_export(Path(destination),encode,postprocess=metadata)
