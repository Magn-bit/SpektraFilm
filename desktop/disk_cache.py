"""Owned, independently budgeted array caches; originals are never cache files.

Cache names derive from identities, not photo checksums. Float/uint16 samples
are written losslessly in bounded row bands and mapped read-only on reuse.
Only this cache's flat, generated file pairs can be removed by its cleaner.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
import weakref

import numpy as np


CACHE_VERSION = 'spektrafilm-array-v3-lab232-20261111'
CATEGORIES = ('working', 'preview', 'full')
DEFAULT_BUDGETS = dict(working=5 << 30, preview=10 << 30, full=8 << 30)
_NAME = re.compile(r'^[0-9a-f]{64}$')
_GLOBAL = None
_GLOBAL_LOCK = threading.RLock()


class CacheCancelled(Exception):
    pass


def check_cancel(cancel):
    if cancel is not None and cancel.is_set(): raise CacheCancelled('任务已取消')


def portable(value):
    if is_dataclass(value): return portable(asdict(value))
    if isinstance(value, dict): return {str(k): portable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [portable(v) for v in value]
    if isinstance(value, np.generic): return value.item()
    if isinstance(value, Path): return str(value)
    return value


def source_identity(path):
    source = Path(path).resolve(strict=True)
    stat = source.stat()
    return dict(path=os.path.normcase(str(source)), size=stat.st_size,
                modified_ns=stat.st_mtime_ns, changed_ns=stat.st_ctime_ns)


def identity(path, *, settings=None, domain, **extra):
    return dict(version=CACHE_VERSION, source=source_identity(path),
                settings=portable(settings), domain=str(domain), **portable(extra))


def _document(value):
    return json.dumps(portable(value), ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False)


@dataclass
class ArrayRecord:
    pixels: np.ndarray
    metadata: dict
    hit: bool = False


class DiskCache:
    def __init__(self, root, budgets=None):
        requested_root = Path(root).absolute()
        if requested_root.is_symlink(): raise ValueError('缓存目录不能是符号链接')
        requested_root.mkdir(parents=True, exist_ok=True)
        # Windows package filesystem redirection can change the resolved path
        # only after the directory exists. Own and compare that actual root.
        self.root = requested_root.resolve(strict=True)
        marker = self.root / '.spektrafilm-array-cache'
        if not marker.exists(): marker.write_text('1\n', encoding='ascii')
        if marker.read_text(encoding='ascii').strip() != '1': raise ValueError('缓存目录标识无效')
        self.budgets = {**DEFAULT_BUDGETS, **(budgets or {})}
        self._lock = threading.RLock()
        self._pins = {}
        self._building = set()
        self._pending_clear = set()
        self._key_locks = OrderedDict()
        for category in CATEGORIES:
            folder = self.root/category
            folder.mkdir(exist_ok=True)
            if folder.is_symlink() or folder.resolve().parent != self.root:
                raise ValueError('缓存分类目录必须属于缓存根目录')
        self._sweep_partials()
        self.trim()

    def _sweep_partials(self):
        # Abandoned transactions have no readable manifest. Do not inspect or
        # recurse into user directories, copied-in originals, or unknown names.
        for category in CATEGORIES:
            for path in (self.root/category).glob('.partial-*'):
                if path.is_file() and not path.is_symlink() and path.stat().st_mtime < time.time()-86400:
                    try: path.unlink()
                    except OSError: pass
            for path in (self.root/category).glob('*.npy'):
                if (_NAME.fullmatch(path.stem) and not path.is_symlink()
                        and not path.with_suffix('.json').exists()
                        and path.stat().st_mtime < time.time()-86400):
                    try: path.unlink()
                    except OSError: pass

    def _key(self, value):
        document = _document(value)
        return hashlib.blake2s(document.encode('utf-8')).hexdigest(), document

    def _files(self, category, key):
        if category not in CATEGORIES or not _NAME.fullmatch(key): raise ValueError('无效缓存分类或标识')
        return self.root/category/(key+'.npy'), self.root/category/(key+'.json')

    def _entries(self, category):
        result = []
        for manifest in (self.root/category).glob('*.json'):
            if not _NAME.fullmatch(manifest.stem) or manifest.is_symlink(): continue
            pixels = manifest.with_suffix('.npy')
            try:
                if pixels.is_symlink() or not pixels.is_file(): continue
                result.append((manifest.stem, pixels.stat().st_size+manifest.stat().st_size,
                               manifest.stat().st_mtime_ns))
            except OSError: pass
        return result

    def _remove(self, category, key):
        pixels, manifest = self._files(category, key)
        if self._pins.get((category, key), 0) or (category, key) in self._building: return False
        removed = False
        # Drop the commit marker before data, so an interrupted clean is a miss.
        for path in (manifest, pixels):
            if path.is_symlink(): continue
            try: path.unlink(missing_ok=True); removed = True
            except OSError: pass
        return removed

    def _unpin(self, category, key):
        with self._lock:
            pair = (category, key)
            remaining = self._pins.get(pair, 1)-1
            if remaining > 0: self._pins[pair] = remaining
            else:
                self._pins.pop(pair, None)
                if pair in self._pending_clear:
                    if self._remove(category, key): self._pending_clear.discard(pair)
            self.trim(category)

    def _release_mapping(self, mapping, category, key):
        try: mapping.close()
        finally: self._unpin(category, key)

    def get(self, category, value):
        key, document = self._key(value)
        pixels_path, manifest = self._files(category, key)
        with self._lock:
            try:
                if manifest.is_symlink() or pixels_path.is_symlink(): return None
                record = json.loads(manifest.read_text(encoding='utf-8'))
                if record.get('identity') != document: return None
                pixels = np.load(pixels_path, mmap_mode='r', allow_pickle=False)
                if (pixels.dtype.str != record['dtype'] or list(pixels.shape) != record['shape']
                        or pixels.ndim != 3 or pixels.shape[-1] != 3
                        or pixels.dtype not in (np.uint8, np.uint16, np.float32, np.float64)):
                    return None
                pair = (category, key)
                self._pins[pair] = self._pins.get(pair, 0)+1
                weakref.finalize(pixels, self._release_mapping, pixels._mmap, category, key)
                os.utime(manifest, None)
                return ArrayRecord(pixels, record.get('metadata', {}), True)
            except (OSError, ValueError, KeyError, EOFError): return None

    def _put(self, category, value, pixels, metadata, cancel):
        key, document = self._key(value)
        destination, manifest = self._files(category, key)
        values = np.asarray(pixels)
        if values.ndim != 3 or values.shape[-1] != 3 or values.dtype.hasobject:
            raise ValueError('缓存需要RGB数值像素')
        if self.budgets[category] <= 0 or values.nbytes > self.budgets[category]:
            return ArrayRecord(pixels, metadata)
        # A reserve protects a near-full system disk without changing image size.
        if shutil.disk_usage(self.root).free < values.nbytes+(64 << 20):
            return ArrayRecord(pixels, metadata)
        handle, temporary = tempfile.mkstemp(prefix='.partial-', suffix='.npy', dir=destination.parent)
        os.close(handle)
        mapping = None
        try:
            check_cancel(cancel)
            mapping = np.lib.format.open_memmap(temporary, mode='w+', dtype=values.dtype, shape=values.shape)
            rows = max(1, min(128, (8 << 20)//max(1, values.shape[1]*3*values.dtype.itemsize)))
            for top in range(0, len(values), rows):
                check_cancel(cancel); mapping[top:top+rows] = values[top:top+rows]
            mapping.flush(); del mapping; mapping = None
            check_cancel(cancel)
            record = dict(identity=document, dtype=values.dtype.str, shape=list(values.shape),
                          metadata=portable(metadata))
            with self._lock:
                # The same key is serialized by get_or_create. Readers never
                # see this file before its matching manifest is committed.
                os.replace(temporary, destination)
                descriptor, temp_json = tempfile.mkstemp(prefix='.partial-', suffix='.json', dir=destination.parent)
                try:
                    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                        json.dump(record, stream, ensure_ascii=False, allow_nan=False)
                        stream.flush(); os.fsync(stream.fileno())
                    os.replace(temp_json, manifest)
                finally: Path(temp_json).unlink(missing_ok=True)
                result = self.get(category, value)
                if result is None: raise OSError('缓存写入后无法读取')
                result.hit = False
                return result
        finally:
            if mapping is not None: del mapping
            Path(temporary).unlink(missing_ok=True)

    def get_or_create(self, category, value, producer, *, cancel=None):
        check_cancel(cancel)
        found = self.get(category, value)
        if found is not None: return found
        key, _ = self._key(value); pair = (category, key)
        with self._lock:
            lock = self._key_locks.setdefault(pair, threading.Lock())
            self._key_locks.move_to_end(pair)
            while len(self._key_locks) > 256:
                oldest, candidate = next(iter(self._key_locks.items()))
                if candidate.locked(): break
                self._key_locks.pop(oldest)
        while not lock.acquire(timeout=.05): check_cancel(cancel)
        try:
            check_cancel(cancel)
            found = self.get(category, value)
            if found is not None: return found
            with self._lock: self._building.add(pair)
            try:
                pixels, metadata = producer()
                check_cancel(cancel)
                try: return self._put(category, value, pixels, metadata, cancel)
                except OSError: return ArrayRecord(pixels, metadata)
            finally:
                with self._lock:
                    self._building.discard(pair)
                    if pair in self._pending_clear:
                        if self._remove(category, key): self._pending_clear.discard(pair)
                    self.trim(category)
        finally: lock.release()

    def configure(self, budgets):
        with self._lock:
            for category, size in budgets.items():
                if category in CATEGORIES: self.budgets[category] = max(0, int(size))
            self.trim()

    def trim(self, category=None):
        with self._lock:
            for name in (CATEGORIES if category is None else (category,)):
                entries = sorted(self._entries(name), key=lambda entry: entry[2])
                total = sum(item[1] for item in entries)
                for key, size, _ in entries:
                    if total <= self.budgets[name]: break
                    if self._remove(name, key): total -= size

    def clear(self, category=None):
        with self._lock:
            names = CATEGORIES if category is None else (category,)
            if any(name not in CATEGORIES for name in names): raise ValueError('未知缓存分类')
            for name in names:
                for key, _, _ in self._entries(name):
                    if not self._remove(name, key): self._pending_clear.add((name, key))
                self._pending_clear.update(pair for pair in self._building if pair[0] == name)
        return self.usage()

    def usage(self):
        with self._lock:
            result = {}
            for name in CATEGORIES:
                entries = self._entries(name)
                result[name] = dict(bytes=sum(entry[1] for entry in entries), entries=len(entries),
                    limit=self.budgets[name],
                    pinned=sum(n for (category, _), n in self._pins.items() if category == name))
            return result


def configure_cache(root=None, budgets=None):
    global _GLOBAL
    with _GLOBAL_LOCK:
        if root is None:
            root = os.environ.get('SPEKTRAFILM_ARRAY_CACHE') or str(
                Path(os.environ.get('LOCALAPPDATA', tempfile.gettempdir()))/'SpektraFilm'/'render-cache')
        if _GLOBAL is None or _GLOBAL.root != Path(root).resolve(): _GLOBAL = DiskCache(root, budgets)
        elif budgets is not None: _GLOBAL.configure(budgets)
        return _GLOBAL


def cache():
    with _GLOBAL_LOCK:
        return _GLOBAL if _GLOBAL is not None else configure_cache()
