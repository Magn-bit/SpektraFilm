"""High precision source pixels kept separate from Pillow's display image.

Pillow's RGB image is only a display surface. RAW / RGB16 source samples reach
the film renderer as uint16 or float32, and are quantised only by the encoder.
"""
from __future__ import annotations

from pathlib import Path
import struct

import numpy as np
from PIL import Image, ImageCms


def normalized_pixels(pixels):
    values = np.asarray(pixels)
    if values.dtype == np.uint8:
        return values.astype(np.float32) / np.float32(255)
    if values.dtype == np.uint16:
        return values.astype(np.float32) / np.float32(65535)
    return np.asarray(values, dtype=np.float32)


def source_pixels(image):
    values = getattr(image, '_spektrafilm_source_pixels', image.info.get('_spektrafilm_source_pixels'))
    if values is not None:
        if values.shape != (image.height, image.width, 3):
            # Pillow.copy/thumbnail is also used by the controller cache. Its
            # shallow info copy keeps the source samples; resize once lazily.
            values = resize_pixels(values, image.size)
            image._spektrafilm_source_pixels = values
            image.info['_spektrafilm_source_pixels'] = values
        return values
    return np.asarray(image, dtype=np.uint8)


def source_metadata(image):
    """Describe source samples, independently of the eight-bit display surface."""
    raw = image.info.get('_spektrafilm_source_metadata', {})
    values = dict(raw) if isinstance(raw, dict) else {}
    values.setdefault('source_color_space', 'sRGB')
    values.setdefault('source_linear', False)
    values.setdefault('source_size', tuple(image.info.get('source_size', image.size)))
    return values


def display_image(pixels, *, full_size=None, token=None, metadata=None, display_pixels=None):
    values = np.asarray(pixels)
    # LibRaw's RGB8 output takes the high byte of its RGB16 curve. Preserve
    # that established display brightness without discarding the low byte.
    visible = np.asarray(display_pixels) if display_pixels is not None else values
    display = quantize_display(visible)
    image = Image.fromarray(display)
    image._spektrafilm_source_pixels = values
    image.info['_spektrafilm_source_pixels'] = values
    image.info['source_size'] = tuple(full_size or image.size)
    if metadata is not None:
        image.info['_spektrafilm_source_metadata'] = dict(metadata)
    if token is not None:
        image.info['_spektrafilm_source_token'] = token
    return image


def quantize_display(pixels, *, out=None):
    """Build the RGB8 display surface with bounded conversion scratch.

    A full medium-format float image must not allocate additional full-frame
    float arrays for clip, multiply and round. Source samples remain untouched.
    This is only a display conversion; encoders use the high-precision source.
    """
    values = np.asarray(pixels)
    if values.ndim != 3 or values.shape[2] != 3:
        raise ValueError('display pixels must be H×W×3 RGB')
    if out is None:
        if values.dtype == np.uint8:
            return values
        out = np.empty(values.shape, dtype=np.uint8)
    elif out.shape != values.shape or out.dtype != np.uint8 or not out.flags.writeable:
        raise ValueError('display output must be a same-size writable RGB8 array')
    if values.dtype == np.uint8:
        np.copyto(out, values)
        return out
    for top in range(0, values.shape[0], 256):
        block = values[top:top + 256]
        if values.dtype == np.uint16:
            np.right_shift(block, 8, out=out[top:top + len(block)], casting='unsafe')
        else:
            scratch = np.array(block, dtype=np.float32, order='C', copy=True)
            np.clip(scratch, 0, 1, out=scratch)
            np.multiply(scratch, np.float32(255), out=scratch)
            np.rint(scratch, out=scratch)
            out[top:top + len(block)] = scratch
    return out


def resize_pixels(pixels, size):
    # A 150 MP RGB16 source is already 900 MB. Normalising all three source
    # channels before resizing would add another 1.8 GB just for a proxy.
    # Convert one plane at a time and write directly into the bounded output.
    values = np.asarray(pixels)
    result = np.empty((size[1], size[0], 3), dtype=np.float32)
    for channel in range(3):
        plane = np.array(values[..., channel], dtype=np.float32, order='C')
        if values.dtype == np.uint8:
            plane /= np.float32(255)
        elif values.dtype == np.uint16:
            plane /= np.float32(65535)
        with Image.fromarray(plane) as source:
            with source.resize(size, Image.Resampling.LANCZOS) as resized:
                result[..., channel] = np.asarray(resized, dtype=np.float32)
    return result


def _icc_tags(profile):
    if len(profile) < 132 or profile[16:20] != b'RGB ' or profile[20:24] != b'XYZ ':
        raise ValueError('高位深图片需要 RGB 矩阵型 ICC 配置')
    count = struct.unpack_from('>I', profile, 128)[0]
    if count > 4096 or 132 + count * 12 > len(profile):
        raise ValueError('图片 ICC 配置损坏')
    tags = {}
    for offset in range(132, 132 + count * 12, 12):
        name, start, length = struct.unpack_from('>4sII', profile, offset)
        if length < 8 or start + length > len(profile):
            raise ValueError('图片 ICC 标签越界')
        tags[name] = profile[start:start + length]
    return tags


def _icc_curve(data, values, *, inverse=False):
    if data[:4] == b'curv':
        count = struct.unpack_from('>I', data, 8)[0]
        if count == 0:
            return values
        if count == 1:
            gamma = struct.unpack_from('>H', data, 12)[0] / 256
            return np.maximum(values, 0) ** (1 / gamma if inverse else gamma)
        if len(data) < 12 + count * 2:
            raise ValueError('图片 ICC 曲线损坏')
        samples = np.frombuffer(data, dtype='>u2', count=count, offset=12).astype(np.float64) / 65535
        axis = np.linspace(0, 1, count)
        return np.interp(values, samples, axis) if inverse else np.interp(values, axis, samples)
    if data[:4] != b'para':
        raise ValueError('图片 ICC 曲线不受支持')
    kind = struct.unpack_from('>H', data, 8)[0]
    sizes = (1, 3, 4, 5, 7)
    if kind >= len(sizes) or len(data) < 12 + 4 * sizes[kind]:
        raise ValueError('图片 ICC 参数曲线损坏')
    p = struct.unpack_from('>' + 'i' * sizes[kind], data, 12)
    p = [value / 65536 for value in p]
    g = p[0]
    if g <= 0:
        raise ValueError('图片 ICC gamma 无效')
    if kind == 0:
        return np.maximum(values, 0) ** (1 / g if inverse else g)
    a, b = p[1:3]
    if a <= 0:
        raise ValueError('图片 ICC 曲线斜率无效')
    if kind in (1, 2):
        c = p[3] if kind == 2 else 0
        if inverse:
            return (np.maximum(values - c, 0) ** (1 / g) - b) / a
        return np.where(values >= -b / a, np.maximum(a * values + b, 0) ** g + c, c)
    c, d = p[3:5]
    e, f = p[5:7] if kind == 4 else (0, 0)
    if inverse:
        low = (values - f) / c if c else np.zeros_like(values)
        return np.where(values >= c * d + f, (np.maximum(values - e, 0) ** (1 / g) - b) / a, low)
    return np.where(values >= d, np.maximum(a * values + b, 0) ** g + e, c * values + f)


def convert_icc_pixels(pixels, profile):
    """ICC matrix/TRC conversion in floating point, including Adobe/ProPhoto RGB.

    RGB LUT/device-link profiles are rejected explicitly; they must not silently
    pass through the eight-bit Pillow transform in a high precision workflow.
    XYZ colourants are already D50-adapted PCS values, so both profiles share
    the same PCS without an extra, duplicated chromatic adaptation.
    """
    if not profile:
        return pixels
    target_profile = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    source = _icc_tags(profile)
    target = _icc_tags(target_profile)
    def matrix(tags):
        columns = []
        for channel in (b'r', b'g', b'b'):
            data = tags.get(channel + b'XYZ', b'')
            if data[:4] != b'XYZ ' or len(data) < 20:
                raise ValueError('暂不支持此高位深 LUT 型 ICC；请使用矩阵型 RGB 配置')
            columns.append(np.asarray(struct.unpack_from('>iii', data, 8), dtype=np.float64) / 65536)
        return np.column_stack(columns)
    transform = np.linalg.solve(matrix(target), matrix(source))
    values = np.asarray(pixels)
    result = np.empty(values.shape, dtype=np.float32)
    for top in range(0, values.shape[0], 128):
        block = normalized_pixels(values[top:top + 128])
        linear = np.stack([_icc_curve(source[c + b'TRC'], block[..., i]) for i, c in enumerate((b'r', b'g', b'b'))], axis=-1)
        linear = linear @ transform.T
        for i, channel in enumerate((b'r', b'g', b'b')):
            result[top:top + len(block), ..., i] = _icc_curve(target[channel + b'TRC'], linear[..., i], inverse=True)
    return result


def read_high_precision_raster(path):
    """Return RGB16/float source pixels when the file is above eight bits."""
    if Path(path).suffix.lower() in ('.heic','.heif'):
        return read_heif_pixels(path)
    import OpenImageIO as oiio

    reader = oiio.ImageInput.open(str(path))
    if reader is None:
        oiio.geterror()
        return None
    try:
        spec = reader.spec()
        formats = list(spec.channelformats) or [spec.format]
        if all(fmt == oiio.UINT8 for fmt in formats):
            return None
        if spec.nchannels not in (1, 2, 3, 4):
            raise ValueError('高位深图片需要灰度或 RGB 像素')
        dtype = oiio.UINT16 if all(fmt == oiio.UINT16 for fmt in formats) else oiio.FLOAT
        pixels = reader.read_image(format=dtype)
        if pixels is None:
            raise OSError(reader.geterror() or '高位深图片读取失败')
        pixels = np.asarray(pixels)
        if pixels.shape[-1] < 3:
            pixels = np.repeat(pixels[..., :1], 3, axis=-1)
        else:
            pixels = pixels[..., :3]
        profile = spec.getattribute('ICCProfile')
        if profile is not None:
            pixels = convert_icc_pixels(pixels, bytes(profile))
        elif dtype == oiio.FLOAT and str(spec.getattribute('oiio:ColorSpace') or '').lower() in ('linear', 'lin_srgb', 'linear_srgb'):
            pixels = np.where(pixels <= .0031308, pixels * 12.92, 1.055 * np.maximum(pixels, 0) ** (1 / 2.4) - .055)
        orientation = int(spec.getattribute('Orientation') or 1)
        if orientation == 2: pixels = pixels[:, ::-1]
        elif orientation == 3: pixels = pixels[::-1, ::-1]
        elif orientation == 4: pixels = pixels[::-1]
        elif orientation == 5: pixels = np.swapaxes(pixels, 0, 1)
        elif orientation == 6: pixels = np.rot90(pixels, 3)
        elif orientation == 7: pixels = np.swapaxes(pixels, 0, 1)[::-1, ::-1]
        elif orientation == 8: pixels = np.rot90(pixels, 1)
        return np.ascontiguousarray(pixels)
    finally:
        reader.close()


def read_heif_pixels(path):
    """Decode the primary HEIF image above 8 bits, with ICC/NCLX colour."""
    import pillow_heif
    container=pillow_heif.open_heif(path,convert_hdr_to_8bit=False,hdr_to_16bit=True)
    image=container[container.primary_index]
    values=np.array(image,copy=True)
    if values.ndim==2:values=np.repeat(values[...,None],3,axis=-1)
    values=np.ascontiguousarray(values[...,:3])
    profile=image.info.get('icc_profile')
    if profile:return convert_icc_pixels(values,profile)
    nclx=image.info.get('nclx_profile') or {}
    primaries=int(nclx.get('color_primaries',1));transfer=int(nclx.get('transfer_characteristics',13))
    from shared.color_management import MATRICES,encode
    matrices={1:MATRICES['sRGB'],12:MATRICES['Display P3'],9:np.array([
        [.63695805,.14461690,.16888098],[.26270021,.67799807,.05930172],[0,.02807269,1.06098506]])}
    if primaries not in matrices:raise ValueError('HEIF 使用暂不支持的 NCLX 原色：'+str(primaries))
    transform=np.linalg.solve(MATRICES['sRGB'],matrices[primaries])
    output=np.empty(values.shape,np.float32)
    for top in range(0,len(values),64):
        block=normalized_pixels(values[top:top+64])
        if transfer==13:linear=np.where(block<=.04045,block/12.92,((block+.055)/1.055)**2.4)
        elif transfer in (1,6,14,15):linear=np.where(block<.081,block/4.5,((block+.099)/1.099)**(1/.45))
        elif transfer in (4,5):linear=block**(2.2 if transfer==4 else 2.8)
        elif transfer==8:linear=block
        elif transfer==16:
            p=block**(32/2523);linear=(np.maximum(p-3424/4096,0)/np.maximum(2413/128-2392/128*p,1e-8))**(16384/2610)*(10000/203)
        elif transfer==18:
            scene=np.where(block<=.5,block*block/3,(np.exp((block-.55991073)/.17883277)+.28466892)/12)
            luminance=np.maximum(np.sum(scene*np.array([.2627,.6780,.0593]),axis=-1,keepdims=True),1e-8)
            linear=scene*luminance**.2*(1000/203)
        else:raise ValueError('HEIF 使用暂不支持的传递函数：'+str(transfer))
        output[top:top+len(block)]=encode(linear@transform.T,'sRGB')
    return output


def file_token(path, size):
    source = Path(path)
    try:
        info = source.stat()
        return (str(source.resolve()), info.st_mtime_ns, info.st_size, tuple(size))
    except OSError:
        # Custom/test decoders may supply pixels without an ordinary local
        # file. The actual decoder still owns source validation.
        return (str(source.resolve()), None, None, tuple(size))
