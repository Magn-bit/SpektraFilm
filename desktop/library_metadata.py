"""Bounded catalog header enrichment. Never demosaic or allocate photo pixels."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

from PySide6.QtCore import QObject, QRunnable, Signal


def read_headers(rows):
    from .lens import _exiftool
    results = {}
    tool = _exiftool()
    if tool:
        tags = ['-json', '-n', '-Make', '-Model', '-LensModel', '-DateTimeOriginal',
                '-ImageWidth', '-ImageHeight', '-ExifImageWidth', '-ExifImageHeight',
                '-ISO', '-FNumber', '-ExposureTime', '-FocalLength', '-ExposureCompensation']
        try:
            process = subprocess.run(
                [str(tool), '-charset', 'filename=UTF8', '-@', '-'],
                input='\n'.join(tags + [row['path'] for row in rows]) + '\n',
                capture_output=True, text=True, encoding='utf-8', errors='replace',
                timeout=30, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if process.returncode in (0, 1):
                for record in json.loads(process.stdout or '[]'):
                    results[str(Path(record.get('SourceFile', '')).resolve()).casefold()] = record
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    items = []
    keys = {'Make': 'camera_make', 'Model': 'camera_model', 'LensModel': 'lens',
            'ISO': 'iso', 'FNumber': 'aperture', 'ExposureTime': 'shutter',
            'FocalLength': 'focal_length', 'ExposureCompensation': 'exposure_comp'}
    for row in rows:
        record = results.get(str(Path(row['path']).resolve()).casefold(), {})
        metadata = {target: record[source] for source, target in keys.items()
                    if record.get(source) is not None and isinstance(record[source], (str, int, float))}
        captured = str(record.get('DateTimeOriginal') or '')
        if len(captured) >= 19:
            metadata['captured_local'] = captured[:10].replace(':', '-') + 'T' + captured[11:19]
        for key, names in (('width', ('ExifImageWidth', 'ImageWidth')),
                           ('height', ('ExifImageHeight', 'ImageHeight'))):
            value = next((record.get(name) for name in names if record.get(name)), None)
            if isinstance(value, (int, float)) and value > 0: metadata[key] = int(value)
        if not record:
            try:
                from PIL import Image
                with Image.open(row['path']) as image:
                    metadata.update(width=image.width, height=image.height)
                    exif = image.getexif()
                    for tag, key in ((271, 'camera_make'), (272, 'camera_model'), (42036, 'lens')):
                        if isinstance(exif.get(tag), str): metadata[key] = exif[tag]
                    captured = str(exif.get(36867) or '')
                    if len(captured) >= 19:
                        metadata['captured_local'] = captured[:10].replace(':', '-') + 'T' + captured[11:19]
            except (OSError, ValueError):
                pass
        items.append({'image': row['uuid'], 'metadata': metadata})
    return items


class HeaderSignals(QObject):
    finished = Signal(int, str, list)


class HeaderJob(QRunnable):
    def __init__(self, epoch, handle, rows):
        super().__init__()
        self.epoch, self.handle, self.rows = epoch, handle, rows
        self.signals = HeaderSignals()

    def run(self):
        self.signals.finished.emit(self.epoch, self.handle, read_headers(self.rows))
