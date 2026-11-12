"""Crash-recoverable, single active batch export journal."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import time
import uuid

from shared.output_recipes import normalize_recipe


MAX_BATCH_ITEMS = 20000
MAX_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_EVENT_BYTES = 16 * 1024 * 1024
STATUSES = {'queued', 'completed', 'failed', 'cancelled', 'present', 'changed'}


def source_identity(path: str) -> dict:
    stat = Path(path).stat()
    return {'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns}


def source_matches(path: str, identity: dict) -> bool:
    try:
        current = source_identity(path)
    except OSError:
        return False
    return current == {'size': identity.get('size'), 'mtime_ns': identity.get('mtime_ns')}


class BatchExportJournal:
    """Keep the immutable job plan separate from its small append-only event log."""

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.manifest_path = self.directory / 'active.json'
        self._job_id = ''
        self._lock = threading.Lock()

    def _events_path(self, job_id: str) -> Path:
        return self.directory / f'events-{job_id}.jsonl'

    @staticmethod
    def _write_atomic(path: Path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
        try:
            with os.fdopen(handle, 'w', encoding='utf-8', newline='\n') as stream:
                json.dump(value, stream, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
                stream.write('\n')
                stream.flush()
                if stream.tell() > MAX_MANIFEST_BYTES:
                    raise ValueError('批量任务快照超过恢复记录大小限制，请减少本次照片数量')
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def create(self, recipe, planned) -> dict:
        if not planned or len(planned) > MAX_BATCH_ITEMS:
            raise ValueError('批量照片数量超出任务记录范围')
        job_id = uuid.uuid4().hex
        items = []
        for source, target, settings in planned:
            items.append({
                'source': str(Path(source).resolve()),
                'output': str(Path(target).resolve()),
                'settings': asdict(settings) if is_dataclass(settings) else dict(settings),
                'source_identity': source_identity(source),
            })
        document = {
            'schema': 1,
            'job_id': job_id,
            'created_at': int(time.time()),
            'recipe': asdict(recipe) if is_dataclass(recipe) else dict(recipe),
            'items': items,
        }
        self.directory.mkdir(parents=True, exist_ok=True)
        events = self._events_path(job_id)
        with events.open('wb'):
            pass
        try:
            self._write_atomic(self.manifest_path, document)
        except Exception:
            events.unlink(missing_ok=True)
            raise
        self._job_id = job_id
        return document

    def load(self):
        if not self.manifest_path.is_file():
            self._job_id = ''
            return None
        if self.manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ValueError('批量任务记录超过大小限制')
        document = json.loads(self.manifest_path.read_text(encoding='utf-8'))
        if not isinstance(document, dict) or document.get('schema') != 1:
            raise ValueError('批量任务记录版本不受支持')
        job_id = document.get('job_id')
        items = document.get('items')
        if not isinstance(job_id, str) or not re.fullmatch(r'[0-9a-f]{32}', job_id) or not isinstance(items, list) or not 0 < len(items) <= MAX_BATCH_ITEMS:
            raise ValueError('批量任务记录格式无效')
        recipe = normalize_recipe(document.get('recipe'))
        normalized = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError('批量任务项目无效')
            source, output = item.get('source'), item.get('output')
            settings, identity = item.get('settings'), item.get('source_identity')
            if not all(isinstance(value, str) and value for value in (source, output)):
                raise ValueError('批量任务路径无效')
            if not isinstance(settings, dict) or not isinstance(identity, dict):
                raise ValueError('批量任务快照无效')
            normalized.append({**item, 'source': source, 'output': output,
                               'settings': settings, 'source_identity': identity,
                               'status': 'queued', 'error': ''})
        events = self._events_path(job_id)
        if events.is_file():
            if events.stat().st_size > MAX_EVENT_BYTES:
                raise ValueError('批量任务状态记录超过大小限制')
            with events.open('r', encoding='utf-8', errors='replace') as stream:
                for line in stream:
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(event, dict) or event.get('job_id') != job_id:
                        continue
                    index = event.get('index')
                    status = event.get('status')
                    if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(normalized):
                        continue
                    if status not in STATUSES:
                        continue
                    normalized[index]['status'] = status
                    normalized[index]['error'] = str(event.get('error', ''))[:2048]
                    output = event.get('output')
                    if isinstance(output, str) and output:
                        normalized[index]['output'] = output
        self._job_id = job_id
        return {'job_id': job_id, 'created_at': document.get('created_at', 0),
                'recipe': recipe, 'items': normalized}

    def record(self, job_id: str, index: int, status: str, *, error: str = '', output: str = ''):
        if status not in STATUSES:
            raise ValueError('未知批量任务状态')
        if job_id != self._job_id:
            raise ValueError('批量任务已更换')
        event = {'job_id': job_id, 'index': int(index), 'status': status,
                 'error': str(error)[:2048], 'at': int(time.time())}
        if output:
            event['output'] = str(output)
        payload = (json.dumps(event, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')
        path = self._events_path(job_id)
        with self._lock, path.open('ab') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())

    def clear(self, job_id: str | None = None):
        if job_id and self._job_id and job_id != self._job_id:
            return False
        active = self._job_id
        try:
            document = json.loads(self.manifest_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            document = {}
        if active and document.get('job_id') != active:
            return False
        self.manifest_path.unlink(missing_ok=True)
        if active:
            self._events_path(active).unlink(missing_ok=True)
        self._job_id = ''
        return True
