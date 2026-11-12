"""Read-only, exact-match LCP correction for already EXIF-oriented RGB images.

No vendor profiles are shipped. Missing, ambiguous or unsupported calibration
leaves geometry untouched. Call once on import/full-size decode, not per slider.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import json
import tempfile
import threading
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates, maximum_filter, minimum_filter, uniform_filter1d
from shared.photo_formats import RAW_EXTENSIONS
from .raw_source import source_pixels, normalized_pixels, display_image

_ORIENT = {2: Image.Transpose.FLIP_LEFT_RIGHT, 3: Image.Transpose.ROTATE_180,
           4: Image.Transpose.FLIP_TOP_BOTTOM, 5: Image.Transpose.TRANSPOSE,
           6: Image.Transpose.ROTATE_270, 7: Image.Transpose.TRANSVERSE, 8: Image.Transpose.ROTATE_90}
_INDEX_LOCK = threading.RLock()


def _identity_cache():
    """Cache parsed identities; calibration files remain the source of truth."""
    base=Path(os.environ.get('LOCALAPPDATA') or os.environ.get('XDG_CACHE_HOME') or Path.home()/'.cache')
    path=Path(os.environ.get('SPEKTRAFILM_LCP_INDEX_CACHE') or base/'SpektraFilm/lens-identities-v1.json')
    try:
        if path.stat().st_size>16*1024**2:return path,{}
        record=json.loads(path.read_text(encoding='utf-8'))
        entries=record.get('entries') if record.get('version')==1 else None
        return path,entries if isinstance(entries,dict) and len(entries)<=16384 else {}
    except (OSError,ValueError,TypeError,AttributeError):return path,{}


def _write_identity_cache(path,entries):
    temporary=None
    try:
        path.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,
                                         prefix='lens-identities-',suffix='.tmp',delete=False) as stream:
            temporary=Path(stream.name)
            json.dump(dict(version=1,entries=entries),stream,separators=(',',':'))
        os.replace(temporary,path)
    except OSError:pass
    finally:
        if temporary is not None:
            try:temporary.unlink(missing_ok=True)
            except OSError:pass


def _orient_pixels(values,orientation):
    if orientation==2:return values[:,::-1]
    if orientation==3:return values[::-1,::-1]
    if orientation==4:return values[::-1]
    if orientation==5:return np.swapaxes(values,0,1)
    if orientation==6:return np.rot90(values,3)
    if orientation==7:return np.swapaxes(values,0,1)[::-1,::-1]
    if orientation==8:return np.rot90(values,1)
    return values


def _surface(values,original):
    result=display_image(values)
    # Keep source identity and geometry, but never attach the *old* samples.
    result.info.update({key:value for key,value in original.info.items() if key!='_spektrafilm_source_pixels'})
    result.info['_spektrafilm_source_token']=(original.info.get('_spektrafilm_source_token',id(original)),
                                             'optical',id(values))
    return result


def _number(value, default=0.0):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError, OverflowError, ZeroDivisionError):
        return default


def _normal(value):
    return re.sub(r'[^a-z0-9]', '', str(value).casefold())


def _local(tag):
    return tag.rsplit('}', 1)[-1]


def _fields(element):
    result = {_local(k): v for k, v in element.attrib.items()}
    for child in element:
        if _local(child.tag) == 'Description':
            result.update(_fields(child))
        elif not len(child) and child.text and child.text.strip():
            result[_local(child.tag)] = child.text.strip()
    return result


def _profile_roots():
    override = os.environ.get('SPEKTRAFILM_LCP_PATH')
    if override is not None:
        return tuple(str(Path(p).resolve()) for p in override.split(os.pathsep) if p)
    paths = [Path(os.environ.get('PROGRAMDATA', 'C:/ProgramData')) / 'Adobe/CameraRaw/LensProfiles']
    if os.environ.get('APPDATA'):
        paths.append(Path(os.environ['APPDATA']) / 'Adobe/CameraRaw/LensProfiles')
    return tuple(str(p) for p in paths if p.is_dir())


@lru_cache(maxsize=4)
def _profile_paths(roots):
    paths = []
    for root in roots:
        try:
            paths.extend(str(p) for p in Path(root).rglob('*.lcp') if p.is_file())
        except OSError:
            continue
    return tuple(sorted(set(paths)))


@lru_cache(maxsize=1)
def _exiftool():
    import sys
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
    candidates = [str(root/'native/metadata/runtime/exiftool-13.61_64/exiftool.exe'),
                  os.environ.get('SPEKTRAFILM_EXIFTOOL')]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    # PATH may contain disconnected drives or network shares. Do not probe it
    # eagerly when the bundled executable or an explicit override is usable.
    # Windows installations ship ExifTool. Development setups can provide an
    # explicit path; an optional metadata lookup must never traverse arbitrary
    # PATH entries on this platform (including inaccessible mapped drives).
    return shutil.which('exiftool') if os.name != 'nt' else None


@lru_cache(maxsize=128)
def _metadata(path, stamp, size):
    values = {}
    source = 'none'
    try:
        with Image.open(path) as photo:
            exif = photo.getexif()
            entries = dict(exif)
            try:
                entries.update(exif.get_ifd(34665))
            except (KeyError, TypeError, ValueError, SyntaxError):
                pass
            names = {271: 'Make', 272: 'Model', 274: 'Orientation', 42036: 'LensModel',
                     37386: 'FocalLength', 41989: 'FocalLengthIn35mmFormat', 33437: 'FNumber',
                     37382: 'SubjectDistance'}
            values = {name: entries[key] for key, name in names.items() if key in entries}
            source = 'pillow' if values else 'none'
    except (OSError, ValueError, SyntaxError):
        pass
    tool = _exiftool()
    if tool and not (values.get('LensModel') and values.get('FocalLength') and values.get('Make')):
        tags = ['Make', 'Model', 'LensModel', 'Lens', 'FocalLength', 'FocalLengthIn35mmFormat',
                'FNumber', 'FocusDistance', 'SubjectDistance', 'Orientation']
        command = [tool, '-j', '-n', '-charset', 'filename=UTF8'] + ['-' + tag for tag in tags] + ['--', path]
        env = os.environ.copy()
        for name in ('LC_ALL', 'LC_CTYPE', 'LANG'):
            env.pop(name, None)
        try:
            process = subprocess.run(command, capture_output=True, timeout=8, check=False,
                                     creationflags=0x08000000 if os.name == 'nt' else 0, env=env)
            if process.returncode == 0:
                document = json.loads(process.stdout.decode('utf-8-sig', errors='replace'))
                if document and isinstance(document[0], dict):
                    values.update({k: v for k, v in document[0].items() if k in tags})
                    source = 'exiftool'
        except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
            pass
    orientation = int(_number(values.get('Orientation'), 1))
    return dict(make=str(values.get('Make', '')).strip(), model=str(values.get('Model', '')).strip(),
                lens=str(values.get('LensModel') or values.get('Lens') or '').strip(),
                focal_length=_number(values.get('FocalLength')),
                focal_35mm=_number(values.get('FocalLengthIn35mmFormat')),
                aperture=_number(values.get('FNumber')),
                focus_distance=_number(values.get('FocusDistance') or values.get('SubjectDistance')),
                orientation=orientation if 1 <= orientation <= 8 else 1,
                raw=Path(path).suffix.lower() in RAW_EXTENSIONS, metadata_source=source)


@dataclass(frozen=True)
class Model:
    fx: float = 0.0
    fy: float = 0.0
    cx: float = .5
    cy: float = .5
    k1: float = 0.0
    k2: float = 0.0
    k3: float = 0.0
    p1: float = 0.0
    p2: float = 0.0
    scale: float = 1.0


def _model(element):
    values = _fields(element)
    if _number(values.get('Version'), 2) not in (1, 2):
        raise ValueError('unsupported_model_version')
    mapping = dict(fx='FocalLengthX', fy='FocalLengthY', cx='ImageXCenter', cy='ImageYCenter',
                   k1='RadialDistortParam1', k2='RadialDistortParam2', k3='RadialDistortParam3', scale='ScaleFactor')
    defaults = Model()
    fields = {}
    for target, key in mapping.items():
        if key in values:
            value = _number(values[key], float('nan'))
            if not math.isfinite(value):
                raise ValueError('nonfinite_calibration')
            fields[target] = value
        else:
            fields[target] = getattr(defaults, target)
    for name, modern, legacy in (('p1', 'TangentialDistortParam1', 'RadialDistortParam4'),
                                 ('p2', 'TangentialDistortParam2', 'RadialDistortParam5')):
        value = values.get(modern, values.get(legacy, 0))
        fields[name] = _number(value, float('nan'))
        if not math.isfinite(fields[name]):
            raise ValueError('nonfinite_calibration')
    result = Model(**fields)
    if result.fx < 0 or result.fy < 0 or bool(result.fx) != bool(result.fy):
        raise ValueError('invalid_focal_scale')
    if not (0 <= result.cx <= 1 and 0 <= result.cy <= 1 and .8 <= result.scale <= 1.2):
        raise ValueError('invalid_calibration_center_or_scale')
    if max(abs(getattr(result, k)) for k in ('k1', 'k2', 'k3', 'p1', 'p2')) > 100:
        raise ValueError('invalid_calibration_polynomial')
    return result


@lru_cache(maxsize=128)
def _read_profile(path, stamp, size):
    if size > 16 * 1024 * 1024:
        raise ValueError('profile_too_large')
    root = ET.parse(path).getroot()
    samples = []
    for parent in root.iter():
        for element in parent:
            if _local(element.tag) != 'PerspectiveModel':
                continue
            values = _fields(parent)
            # Calibration values belong to the nearest camera record, not other samples.
            try:
                base = _model(element)
                chrom = {}
                for sub in element.iter():
                    name = _local(sub.tag)
                    if name in ('ChromaticGreenModel', 'ChromaticRedGreenModel', 'ChromaticBlueGreenModel'):
                        chrom[name] = _model(sub)
            except ValueError:
                continue
            samples.append(dict(values=values, base=base, chrom=chrom,
                                focal=_number(values.get('FocalLength')),
                                focus=_number(values.get('FocusDistance')),
                                error=_number(_fields(element).get('ResidualMeanError'))))
    if not samples:
        raise ValueError('no_supported_perspective_model')
    values = samples[0]['values']
    raw_value = values.get('CameraRawProfile')
    if raw_value is None:
        raise ValueError('profile_input_type_unspecified')
    names = set()
    for sample in samples:
        for key in ('Lens', 'LensPrettyName'):
            if sample['values'].get(key):
                names.add(_normal(sample['values'][key]))
    for element in root.iter():
        if _local(element.tag) == 'AlternateLensNames':
            names.update(_normal(e.text) for e in element.iter() if _local(e.tag) == 'li' and e.text)
    sensor = _number(values.get('SensorFormatFactor', 1), float('nan'))
    if not math.isfinite(sensor) or not .1 <= sensor <= 10:
        raise ValueError('invalid_sensor_factor')
    return dict(path=path, name=values.get('ProfileName') or values.get('LensPrettyName') or Path(path).stem,
                make=_normal(values.get('Make', '')), camera=_normal(values.get('Model', '')),
                names=frozenset(names), raw=raw_value.casefold() == 'true', sensor=sensor, samples=samples)


def _profile(path):
    info = Path(path).stat()
    return _read_profile(path, info.st_mtime_ns, info.st_size)


@lru_cache(maxsize=4096)
def _profile_header(path, stamp, size):
    """Read identity only, stopping before the first large calibration model."""
    parser = ET.XMLPullParser(events=('start', 'end'))
    fields = {}
    names = set()
    identity = {'Make', 'Model', 'Lens', 'LensPrettyName', 'CameraRawProfile'}
    alternate_depth = 0
    def result():
        raw = fields.get('CameraRawProfile')
        return dict(make=_normal(fields.get('Make', '')), camera=_normal(fields.get('Model', '')),
                    names=frozenset(names), raw=None if raw is None else raw.casefold() == 'true')
    with open(path, 'rb') as stream:
        for _ in range(64):
            chunk = stream.read(2048)
            if not chunk:
                break
            parser.feed(chunk)
            for event, element in parser.read_events():
                tag = _local(element.tag)
                if event == 'start':
                    if tag in ('PerspectiveModel', 'FisheyeModel'):
                        return result()
                    for key, value in element.attrib.items():
                        name = _local(key)
                        if name in identity:
                            fields.setdefault(name, value)
                            if name in ('Lens', 'LensPrettyName'):
                                names.add(_normal(value))
                    if tag == 'AlternateLensNames':
                        alternate_depth += 1
                else:
                    if tag in identity and element.text:
                        fields.setdefault(tag, element.text.strip())
                        if tag in ('Lens', 'LensPrettyName'):
                            names.add(_normal(element.text))
                    elif alternate_depth and tag == 'li' and element.text:
                        names.add(_normal(element.text))
                    if tag == 'AlternateLensNames':
                        alternate_depth -= 1
    return result()


@lru_cache(maxsize=4)
def _identity_index(roots):
    with _INDEX_LOCK:return _build_identity_index(roots)


def _build_identity_index(roots):
    cache_path,records=_identity_cache()
    result = {}
    updated={}
    changed=False
    for path in _profile_paths(roots):
        try:
            info = Path(path).stat()
            saved=records.get(path)
            header=None
            if isinstance(saved,list) and len(saved)==3 and saved[:2]==[info.st_mtime_ns,info.st_size]:
                value=saved[2]
                if (isinstance(value,dict) and isinstance(value.get('make'),str)
                    and isinstance(value.get('camera'),str) and isinstance(value.get('names'),list)
                    and all(isinstance(name,str) for name in value['names'])
                    and (value.get('raw') is None or isinstance(value['raw'],bool))):header=value
            if header is None:
                header=_profile_header(path,info.st_mtime_ns,info.st_size)
                changed=True
            updated[path]=[info.st_mtime_ns,info.st_size,dict(header,names=sorted(header['names']))]
        except (OSError, ET.ParseError, ValueError, TypeError):
            continue
        for name in header['names']:
            key = header['make'], header['raw'], name
            result.setdefault(key, []).append((path, header['camera']))
    if len(updated)<=16384 and (changed or updated.keys()!=records.keys()):
        _write_identity_cache(cache_path,updated)
    return result


@lru_cache(maxsize=128)
def _find_profile(make, camera, lens, raw, roots):
    if not make or not lens:
        return None, 'metadata_missing'
    if not _profile_paths(roots):
        return None, 'profiles_unavailable'
    candidates = []
    for path, profile_camera in _identity_index(roots).get((make, raw, lens), ()):
        if profile_camera and profile_camera != camera:
            continue
        try:
            item = _profile(path)
        except (OSError, ET.ParseError, ValueError, TypeError):
            continue
        if item['make'] == make and lens in item['names'] and item['raw'] == raw:
            candidates.append(item)
    if not candidates:
        return None, 'unmatched'
    # A camera-specific profile takes priority over a generic camera family.
    explicit = [p for p in candidates if p['camera'] and p['camera'] == camera]
    candidates = explicit or candidates
    if len(candidates) != 1:
        return None, 'ambiguous_profile'
    return candidates[0], 'matched'


def inspect_photo(path: str) -> dict:
    """Return serializable metadata and exact local-profile matching status."""
    path = str(Path(path).resolve())
    try:
        info = Path(path).stat()
        metadata = dict(_metadata(path, info.st_mtime_ns, info.st_size))
    except OSError:
        metadata = dict(make='', model='', lens='', focal_length=0., focal_35mm=0., aperture=0.,
                        focus_distance=0., orientation=1, raw=Path(path).suffix.lower() in RAW_EXTENSIONS,
                        metadata_source='none')
    profile, reason = _find_profile(_normal(metadata['make']), _normal(metadata['model']),
                                    _normal(metadata['lens']), metadata['raw'], _profile_roots())
    return dict(metadata, matched=profile is not None, profile=profile['name'] if profile else '',
                profile_path=profile['path'] if profile else '', reason=reason)


def _blend(a, b, fraction):
    if bool(a.fx) != bool(b.fx):
        return a if fraction < .5 else b
    return Model(**{key: getattr(a, key) * (1 - fraction) + getattr(b, key) * fraction
                    for key in Model.__dataclass_fields__})


def _select(profile, metadata):
    focal = metadata['focal_length']
    records = [p for p in profile['samples'] if p['focal'] > 0]
    if not records or focal <= 0:
        raise ValueError('focal_length_missing')
    focals = sorted({p['focal'] for p in records})
    if focal < focals[0] * .98 or focal > focals[-1] * 1.02:
        raise ValueError('focal_outside_calibration')
    low = max((f for f in focals if f <= focal), default=focals[0])
    high = min((f for f in focals if f >= focal), default=focals[-1])
    def best(value):
        items = [r for r in records if r['focal'] == value]
        distance = metadata['focus_distance']
        if distance > 0:
            return min(items, key=lambda r: (abs(math.log(max(r['focus'], .001) / distance)), r['error']))
        return min(items, key=lambda r: (r['error'], -r['focus']))
    a, b = best(low), best(high)
    fraction = 0 if low == high else (math.log(focal) - math.log(low)) / (math.log(high) - math.log(low))
    base = _blend(a['base'], b['base'], fraction)
    names = ('ChromaticRedGreenModel', 'ChromaticGreenModel', 'ChromaticBlueGreenModel')
    chrom = None
    if all(name in a['chrom'] and name in b['chrom'] for name in names):
        chrom = tuple(_blend(a['chrom'][name], b['chrom'][name], fraction) for name in names)
    return base, chrom, [low, high]


def _coordinates(model, width, height, metadata, sensor):
    longest = max(width, height)
    equivalent = metadata['focal_35mm'] or metadata['focal_length'] * sensor
    fallback = equivalent / 35
    fx, fy = (model.fx or fallback) * longest, (model.fy or fallback) * longest
    if min(fx, fy) <= 0 or not math.isfinite(fx + fy):
        raise ValueError('invalid_focal_scale')
    return fx, fy, model.cx * width, model.cy * height


def _polynomial(x, y, model):
    r2 = x * x + y * y
    # Adobe p1 is the y tangential coefficient; p2 is x.
    factor = 1 + r2 * (model.k1 + r2 * (model.k2 + r2 * model.k3)) + 2 * (model.p1 * y + model.p2 * x)
    return x * factor + model.p2 * r2, y * factor + model.p1 * r2


def _mapper(width, height, base, chrom, metadata, sensor):
    fx, fy, x0, y0 = _coordinates(base, width, height, metadata, sensor)
    def mapping(x, y, zoom, channel=1):
        x = ((x - width / 2) / zoom + width / 2 - x0) / fx
        y = ((y - height / 2) / zoom + height / 2 - y0) / fy
        x, y = _polynomial(x, y, base)
        x, y = x * fx + x0, y * fy + y0
        if chrom is not None and channel != 1:
            gfx, gfy, gx0, gy0 = _coordinates(chrom[1], width, height, metadata, sensor)
            model = chrom[channel]
            cfx, cfy, cx0, cy0 = _coordinates(model, width, height, metadata, sensor)
            x, y = _polynomial((x - gx0) / gfx, (y - gy0) / gfy, model)
            x, y = x * model.scale * cfx + cx0, y * model.scale * cfy + cy0
        return x, y
    return mapping


def _auto_zoom(mapping, width, height, chrom):
    x = np.linspace(0, width - 1, 41, dtype=np.float64)
    y = np.linspace(0, height - 1, 41, dtype=np.float64)
    xx, yy = np.meshgrid(x, y)
    def valid(zoom):
        for channel in ((0, 1, 2) if chrom else (1,)):
            px, py = mapping(xx, yy, zoom, channel)
            if not (np.all(np.isfinite(px)) and np.all(np.isfinite(py))):
                return False
            if px.min() < -.005 or py.min() < -.005 or px.max() > width - 1 + .005 or py.max() > height - 1 + .005:
                return False
            if np.min(np.diff(px, axis=1)) <= 0 or np.min(np.diff(py, axis=0)) <= 0:
                return False
        return True
    if valid(1):
        return 1.
    if not valid(1.8):
        raise ValueError('unsafe_or_excessive_geometry')
    low, high = 1., 1.8
    for _ in range(18):
        mid = (low + high) / 2
        if valid(mid):
            high = mid
        else:
            low = mid
    return high


def _optical(image, profile, metadata):
    base, chrom, focal_range = _select(profile, metadata)
    orientation = metadata['orientation']
    inverse = 8 if orientation == 6 else 6 if orientation == 8 else orientation
    source=_orient_pixels(source_pixels(image),inverse)
    height,width=source.shape[:2]
    if min(width, height) < 2:
        raise ValueError('image_too_small')
    mapping = _mapper(width, height, base, chrom, metadata, profile['sensor'])
    zoom = _auto_zoom(mapping, width, height, chrom is not None)
    from . import native_optics
    if native_optics.available():
        values=native_optics.correct_lens(source_pixels(image),base,chrom,metadata,profile['sensor'],zoom)
        return _surface(values,image),chrom is not None,zoom,focal_range
    destination = np.empty_like(source)
    columns = np.arange(width, dtype=np.float32)[None, :]
    for first in range(0, height, 96):
        last = min(height, first + 96)
        rows = np.arange(first, last, dtype=np.float32)[:, None]
        for channel in range(3):
            xx, yy = mapping(columns, rows, zoom, channel)
            xx, yy = np.broadcast_arrays(xx, yy)
            sampled = map_coordinates(source[:, :, channel], [yy, xx], order=1, prefilter=False,
                                      mode='nearest', output=np.float32)
            if source.dtype==np.uint8:sampled=np.clip(np.rint(sampled),0,255)
            elif source.dtype==np.uint16:sampled=np.clip(np.rint(sampled),0,65535)
            destination[first:last, :, channel] = sampled
    result=_surface(np.ascontiguousarray(_orient_pixels(destination,orientation)),image)
    return result, chrom is not None, zoom, focal_range


def _defringe(image,*,in_place=False):
    source = source_pixels(image)
    from . import native_optics
    if native_optics.available():
        result,count=native_optics.defringe(source,out=source if in_place and source.dtype==np.float32 and source.flags.writeable else None)
        return (_surface(result,image) if count else image),count
    result = source.copy()
    count = 0
    height = source.shape[0]
    for first in range(0, height, 128):
        last = min(height, first + 128)
        top, bottom = max(0, first - 4), min(height, last + 4)
        rgb = normalized_pixels(source[top:bottom])
        r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
        luma = .2126 * r + .7152 * g + .0722 * b
        excess = np.minimum(r, b) - g
        purple = (excess > .06) & (r > g * 1.2) & (b > g * 1.2)
        thin = ((uniform_filter1d(purple.astype(np.float32), 7, axis=0, mode='nearest') < .4)
                | (uniform_filter1d(purple.astype(np.float32), 7, axis=1, mode='nearest') < .4))
        contrast = maximum_filter(luma, 5, mode='nearest') - minimum_filter(luma, 5, mode='nearest')
        neutral = maximum_filter((rgb.max(axis=2) - rgb.min(axis=2) < .08).astype(np.uint8), 3, mode='nearest') > 0
        strength = np.clip((excess - .04) / .12, 0, .85) * np.clip((contrast - .30) / .25, 0, 1)
        strength *= purple & thin & neutral
        start, end = first - top, last - top
        active = strength[start:end]
        count += int(np.count_nonzero(active > .02))
        corrected = rgb[start:end] + (luma[start:end, :, None] - rgb[start:end]) * active[:, :, None]
        if source.dtype==np.uint8:corrected=np.clip(np.rint(corrected*255),0,255)
        elif source.dtype==np.uint16:corrected=np.clip(np.rint(corrected*65535),0,65535)
        result[first:last] = corrected
    return (_surface(result,image) if count else image), count


def prepare_photo(image: Image.Image, source_path: str, *, correction=True, defringe=True) -> tuple[Image.Image, dict]:
    """Correct a decoded, already oriented image without touching its source.

    RAW backup exports must continue to copy the source bytes separately.
    The returned status is JSON-safe; defringe is enabled independently of LCP.
    """
    metadata = inspect_photo(source_path)
    status = dict(metadata, correction_enabled=bool(correction), distortion=False, chromatic_aberration=False,
                  defringe=bool(defringe), defringe_pixels=0, crop_scale=1., focal_samples=[], warnings=[])
    result = image
    if correction and metadata['matched']:
        try:
            result, ca, zoom, samples = _optical(image, _profile(metadata['profile_path']), metadata)
            status.update(distortion=True, chromatic_aberration=ca, crop_scale=round(zoom, 6), focal_samples=samples)
        except (OSError, ValueError, ET.ParseError, ArithmeticError) as error:
            status['reason'] = str(error)
            status['warnings'].append('镜头配置无法可靠应用，已保留原始几何')
    elif not correction:
        status['reason'] = 'disabled'
    if defringe:
        # Only freshly remapped data is mutable here. The shared decoded or
        # cached original must remain immutable for comparison/history.
        result, count = _defringe(result,in_place=result is not image)
        status['defringe_pixels'] = count
    status['summary'] = correction_summary(status)
    return result, status


def correction_summary(status: dict) -> str:
    """Describe what was applied, never treat a profile match as a correction."""
    parts = []
    if status['distortion']:
        lens_name = status.get('lens') or status.get('profile') or '已匹配镜头'
        profile_name = status.get('profile')
        parts.append('已矫正 ' + lens_name + (f' · {profile_name}' if profile_name and profile_name != lens_name else ''))
    elif status.get('correction_enabled', True):
        if status.get('matched'):
            parts.append('镜头配置未应用 · ' + (status.get('profile') or status.get('lens') or '已匹配'))
        else:
            parts.append('镜头未匹配' + (f' · {status["lens"]}' if status.get('lens') else ''))
        reason = {
            'metadata_missing': '缺少镜头信息',
            'profiles_unavailable': '未找到本机镜头配置',
            'ambiguous_profile': '匹配到多个镜头配置',
            'focal_outside_calibration': '焦距超出配置范围',
            'unsafe_or_excessive_geometry': '校正范围不可靠',
        }.get(status.get('reason'))
        if reason: parts.append(reason)
    else:
        parts.append('镜头校正已关闭')
    if status.get('chromatic_aberration'):
        parts.append('色差校正')
    if status.get('defringe'):
        parts.append('保守去紫边')
    return ' · '.join(parts)
