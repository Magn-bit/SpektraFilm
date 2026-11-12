"""Bounded local preferences and explicit, photo-free diagnostic bundles."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import json
import math
import os
import re
import tempfile
import time
import zipfile

DEFAULTS = {
    'appearance':'light',
    'light_background':'#DEDEDA',
    'dark_background':'#252724',
    'default_stock':'saved',
    'default_paper':'saved',
    'format_unit':'mm',
    'frame_body_seed':0,
    'preview_long_edge': 1920,
    'memory_budget_mb': 768,
    'disk_cache_mb': 2048,
    'ui_scale': 1.0,
    'diagnostic_retention_days': 7,
    'working_cache_mb':5120,
    'preview_cache_mb':10240,
    'full_render_cache_mb':8192,
}
PREVIEW_EDGES = (1080, 1920, 2560, 3840)
LIMITS = {
    'frame_body_seed':(0,2147483647),
    'working_cache_mb':(0,65536),
    'preview_cache_mb':(0,65536),
    'full_render_cache_mb':(0,65536),
    'memory_budget_mb': (256, 4096),
    'disk_cache_mb': (512, 8192),
    'ui_scale': (.8, 1.5),
    'diagnostic_retention_days': (1, 30),
}


def normalize_preference(key: str, value):
    if key not in DEFAULTS:
        raise ValueError('未知设置项')
    if key=='appearance':
        if value not in ('light','dark','system'):raise ValueError('未知外观模式')
        return value
    if key in ('light_background','dark_background'):
        if not isinstance(value,str) or not re.fullmatch('#[0-9a-fA-F]{6}',value):raise ValueError('背景色应为六位HEX色值')
        return value.upper()
    if key=='format_unit':
        if value not in ('mm','cm','in'):raise ValueError('未知尺寸单位')
        return value
    if key in ('default_stock','default_paper'):
        if value in ('saved','last'):return value
        if key=='default_stock':
            from .imaging import catalog
            if value not in {item['id'] for item in catalog()}:raise ValueError('未知默认胶片')
        else:
            from shared.darkroom import PAPER_IDS
            if value not in PAPER_IDS|{'auto'}:raise ValueError('未知默认相纸')
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('设置值必须是有效数字')
    if key == 'preview_long_edge':
        if value not in PREVIEW_EDGES:
            raise ValueError('不支持的预览尺寸')
        return int(value)
    low, high = LIMITS[key]
    value = max(low, min(high, value))
    return round(float(value), 3) if key == 'ui_scale' else int(round(value))


def normalized_preferences(values=None) -> dict:
    result = DEFAULTS.copy()
    if isinstance(values, Mapping):
        for key in DEFAULTS:
            if key in values:
                try:
                    result[key] = normalize_preference(key, values[key])
                except ValueError:
                    pass
    return result


def _atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=path.name+'.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(handle, 'w', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class PreferenceStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        try:
            record = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            record = {}
        self._values = normalized_preferences(record.get('preferences', record) if isinstance(record, dict) else {})

    @property
    def values(self) -> dict:
        return self._values.copy()

    def update(self, key: str, value) -> bool:
        normalized = normalize_preference(key, value)
        if self._values[key] == normalized:
            return False
        updated = {**self._values, key: normalized}
        _atomic_json(self.path, {'version': 1, 'preferences': updated})
        self._values = updated
        return True

    def save(self):
        _atomic_json(self.path, {'version': 1, 'preferences': self._values})


class DiagnosticTimings:
    """Bounded local numeric history, without filenames or arbitrary log text."""
    def __init__(self,path,retention_days=7):
        self.path=Path(path)
        try:record=json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError,ValueError):record=[]
        self.records=[item for item in record[-512:] if isinstance(item,dict)
            and isinstance(item.get('at'),(int,float)) and math.isfinite(item['at'])
            and isinstance(item.get('preview_ms'),(int,float)) and math.isfinite(item['preview_ms'])] if isinstance(record,list) else []
        self.prune(retention_days)

    def prune(self,days):
        threshold=time.time()-max(1,min(30,days))*86400
        self.records=[item for item in self.records if item['at']>=threshold][-512:]

    def append(self,milliseconds,days):
        self.records.append(dict(at=time.time(),preview_ms=max(0,float(milliseconds))))
        self.prune(days)

    def save(self):_atomic_json(self.path,self.records)

    @property
    def samples(self):return [item['preview_ms'] for item in self.records]


_SAFE_TIMING_KEY = re.compile(r'^[A-Za-z][A-Za-z0-9_. -]{0,63}$')


def _numeric_timings(timings):
    """Only aggregate stage numbers; never arbitrary logs or source paths."""
    if not isinstance(timings, Mapping):
        return {}
    result = {}
    for key, value in list(timings.items())[:128]:
        if not isinstance(key, str) or not _SAFE_TIMING_KEY.fullmatch(key):
            continue
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)) and math.isfinite(value):
            result[key] = value
        elif isinstance(value, (list, tuple)):
            result[key] = [v for v in value[:256] if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)]
        elif isinstance(value, Mapping):
            numbers = {k: v for k, v in value.items() if k in ('count', 'mean_ms', 'median_ms', 'p95_ms', 'max_ms', 'min_ms', 'total_ms')
                       and isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)}
            if numbers:
                result[key] = numbers
    return result


def export_diagnostics(destination: str | Path, preferences=None, *, version: str, timings=None) -> Path:
    """Write one explicitly requested ZIP without reading photos or any logs.

    Callers provide aggregate timing data directly. This function intentionally
    has no source-folder, log-folder or recursive archive argument.
    """
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=target.name+'.', suffix='.tmp', dir=target.parent)
    os.close(handle)
    manifest = {'schema': 1, 'application': 'SpektraFilm', 'version': str(version)[:64],
                'preferences': normalized_preferences(preferences), 'includes_photos': False,
                'includes_source_paths': False}
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('diagnostics.json', json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
            numbers = _numeric_timings(timings)
            if numbers:
                archive.writestr('timings.json', json.dumps(numbers, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target
