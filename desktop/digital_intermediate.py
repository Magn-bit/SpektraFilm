"""Native developed-negative Cineon codes, independent of print/display edits."""
from dataclasses import replace
import json
from pathlib import Path
from functools import lru_cache

import numpy as np

from shared.darkroom import scans_directly
from shared.geometry import apply_geometry_pixels
from . import native_spectral
from .raw_source import source_pixels,source_metadata


@lru_cache(maxsize=1)
def view_lut():
    """Upstream Cineon view, RGB-fastest cube stored as [blue, green, red]."""
    path=native_spectral._RUNTIME/'resources/DI/SpektraLab DI view, Cineon to ProPhoto RGB.cube'
    size=0;rows=[]
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        fields=line.split()
        if fields and fields[0]=='LUT_3D_SIZE':size=int(fields[1])
        if len(fields)==3:
            try:rows.append(tuple(float(value) for value in fields))
            except ValueError:pass
    if size<2 or len(rows)!=size**3:raise RuntimeError('Cineon DI 显示 LUT 不完整')
    values=np.asarray(rows,dtype=np.float32).reshape(size,size,size,3)
    if not np.isfinite(values).all():raise RuntimeError('Cineon DI 显示 LUT 无效')
    values.setflags(write=False)
    return values


def view_codes(codes):
    """Decode log once; leave the raw DI encoder's codes untouched."""
    from .imaging import apply_lut
    return apply_lut(codes,view_lut())


def render_codes(image,settings,*,blue_compensation=False):
    if not settings.film_enabled or settings.strength<=0:
        raise ValueError('Cineon DI 需要开启胶片显影')
    if scans_directly(settings.stock):
        raise ValueError('反转片没有负片中间片，请使用普通图像配方')
    metadata=source_metadata(image);full=tuple(image.info.get('source_size',image.size))
    prepared=native_spectral.process_editor(source_pixels(image),settings,stage='pre',
        exposure_ev=float(metadata.get('baseline_exposure_ev',0)),
        source_color_space=metadata['source_color_space'],source_linear=metadata['source_linear'],
        source_size=full,pixel_scale=(full[0]/image.width,full[1]/image.height),clamp_output=False)
    # The capture-side editor returns encoded sRGB float, including headroom.
    # Native DI reverses this stock's printing density through its neutral
    # response; it never passes through the selected paper/display transform.
    codes=native_spectral.render_spectral(prepared,replace(settings,minilab_active=False),
        digital_intermediate=True,output_color_space='ProPhoto RGB',di_blue_compensation=blue_compensation)
    return apply_geometry_pixels(codes,settings.geometry)


def encode(target,pixels,cancel,check):
    import tifffile
    from .output import _quantize
    rows=32
    def strips():
        for top in range(0,len(pixels),rows):
            check(cancel);yield _quantize(pixels[top:top+rows],16).tobytes()
    handle=tifffile.FileHandle(target,mode='wb',name='SpektraFilm-Cineon-DI.tif')
    tifffile.imwrite(handle,data=strips(),shape=pixels.shape,dtype=np.uint16,photometric='rgb',
        rowsperstrip=rows,metadata=None,software='SpektraFilm',description=json.dumps({
            'encoding':'Kodak Cineon','primaries':'ProPhoto RGB',
            'formula':'(685 + 300*log10(L*(1-b)+b))/1023; b=10^((95-685)/300)',
            'black_code':95,'rgb_icc':False,'view_lut':'Cineon to Rec709 / ProPhoto RGB'},ensure_ascii=False))


def companion_luts(directory):
    """Install common upstream view tables without overwriting user files."""
    from .imaging import _publish_export
    names=[]
    for source in sorted((native_spectral._RUNTIME/'resources/DI').glob('*.cube')):
        data=source.read_bytes();target=Path(directory)/source.name
        if target.exists() and target.read_bytes()==data:
            names.append(target.name);continue
        def write(stream,data=data):stream.write(data);return len(data)
        _publish_export(target,write)
        # A different existing table is rejected, never overwritten.
        names.append(source.name)
    if len(names)!=2:raise RuntimeError('缺少 Cineon DI 专用显示 LUT')
    return names
