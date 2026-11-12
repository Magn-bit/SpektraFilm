"""Visible-only, latest-request scene measurements from the render's own nodes.

The scene proxy is at most 256 px. A cold decode waits for foreground work;
warm curve/exposure asks try the shared engine lock without queuing behind it.
There is one worker and one scene buffer, never a batch of full-resolution RAWs.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import threading

import numpy as np
from PySide6.QtCore import QObject, Property, QRunnable, QThreadPool, QTimer, Signal, Slot, Qt

from .native_spectral import _PRE_EDITOR_FIELDS


_DEFER = object()
_SCENE_FIELDS = (
    'stock', 'paper', 'exposure', 'print_exposure', 'print_y', 'print_m',
    'scan_film', 'extended_dynamic_range', 'film_format_mm', 'film_format_axis',
    'density_curve_gamma', 'dir_couplers_amount', 'metering_method',
    'scene_latitude_active', 'scene_latitude_norm',
    'scene_latitude_highlight_knee', 'scene_latitude_highlight_room',
    'scene_latitude_shadow_knee', 'scene_latitude_shadow_room',
    'scene_latitude_rolloff', 'scene_latitude_max_lift', 'scene_curves',
)
_PRE_FIELDS = _PRE_EDITOR_FIELDS + ('lens_correction', 'defringe')


def _stamp(path):
    stat = Path(path).stat()
    return stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


class _Measure(QRunnable):
    def __init__(self, owner, request):
        super().__init__()
        self.owner, self.request = owner, request

    def run(self):
        try:
            result = self.owner._measure(self.request)
            self.owner.completed.emit((self.request, result, ''))
        except Exception as error:
            self.owner.completed.emit((self.request, None, str(error)))


class SceneHistogram(QObject):
    changed = Signal()
    completed = Signal(object)

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._dispatch)
        self.completed.connect(self._done, Qt.QueuedConnection)
        controller.stateChanged.connect(self.refresh)
        controller.frameChanged.connect(self._foreground_finished)
        self._active = self._closed = self._inflight = False
        self._state = 'inactive'
        self._desired = None
        self._data = {}
        self._published_key = None
        self._serial = 0
        self._cancel = threading.Event()
        # Worker-owned immutable proxy/prepared scene; at most one of each.
        self._raw_key = self._pre_key = None
        self._raw = self._scene = None
        self._measurements = self._source_reads = self._discarded = 0

    @Property('QVariantMap', notify=changed)
    def data(self):
        return dict(self._data, current=self._desired is not None and self._published_key == self._desired['key']) if self._data else {}

    @Property(str, notify=changed)
    def state(self):
        return self._state

    @Property(bool, notify=changed)
    def busy(self):
        return self._state == 'waiting' or self._inflight

    @Property('QVariantMap', notify=changed)
    def statistics(self):
        return dict(measurements=self._measurements, source_reads=self._source_reads,
                    discarded=self._discarded, in_flight=int(self._inflight), proxy_edge=256)

    @Slot(bool)
    def setActive(self, value):
        value = bool(value)
        if value == self._active:
            return
        self._active = value
        if not value:
            self._timer.stop()
            self._desired = None
            self._serial += 1
            self._state = 'inactive'
            self.changed.emit()
        else:
            self.refresh()

    def _set_state(self, value, clear=False):
        if clear:
            self._data = {}
            self._published_key = None
        if self._state != value or clear:
            self._state = value
            self.changed.emit()

    @Slot()
    def refresh(self):
        if self._closed or not self._active:
            return
        ctrl = self.controller
        if ctrl.currentIndex < 0:
            self._desired = None
            self._set_state('empty', True)
            return
        settings = replace(ctrl._settings)
        if not settings.film_enabled:
            self._desired = None
            self._set_state('disabled', True)
            return
        path = ctrl.currentPath
        try:
            source_key = (path, _stamp(path), ctrl._render_epochs.get(path, 0))
        except OSError:
            self._desired = None
            self._set_state('error', True)
            return
        pre_key = (source_key, tuple(getattr(settings, key) for key in _PRE_FIELDS))
        key = (pre_key, tuple(getattr(settings, name) for name in _SCENE_FIELDS))
        if self._desired is not None and key == self._desired['key']:
            if not self._inflight and key != self._published_key and not self._timer.isActive():
                self._timer.start(24)
            return
        self._serial += 1
        self._desired = dict(key=key, pre_key=pre_key, source_key=source_key,
                             path=path, settings=settings, serial=self._serial)
        if self._published_key == key:
            self._set_state('ready')
            return
        # A source change cannot briefly show another picture's distribution.
        if self._data.get('source_key') != source_key:
            self._data = {}
            self._published_key = None
        self._state = 'waiting'
        self.changed.emit()
        # Throttle, rather than debounce: dragging does not restart this timer.
        if not self._inflight and not self._timer.isActive():
            self._timer.start(24)

    @Slot()
    def _foreground_finished(self):
        if self._active and not self._closed and self._desired is not None:
            if self._published_key != self._desired['key'] and not self._inflight and not self._timer.isActive():
                self._timer.start(24)

    def _dispatch(self):
        if self._closed or not self._active or self._inflight or self._desired is None:
            return
        if self.controller.exporting:
            self._timer.start(100)
            return
        self._inflight = True
        self.changed.emit()
        self.pool.start(_Measure(self, self._desired), -1)

    def _measure(self, request):
        if self._cancel.is_set():
            return _DEFER
        ctrl = self.controller
        source_key = request['source_key']
        if self._raw_key != source_key:
            if ctrl.busy or ctrl.exporting:
                return _DEFER
            # Decode outside the engine lock. This is a bounded source copy,
            # not the photograph's rendered/quantised display preview.
            from .raw_source import display_image, source_metadata, source_pixels
            source = ctrl._source(request['path'], 256)
            pixels = np.array(source_pixels(source), order='C', copy=True)
            if max(pixels.shape[:2]) > 256:
                raise ValueError('场景采样尺寸无效')
            self._raw = display_image(pixels, full_size=source.info.get('source_size', source.size),
                                      metadata=source_metadata(source))
            self._raw_key = source_key
            self._pre_key = None
            self._source_reads += 1
        if self._cancel.is_set() or ctrl.exporting:
            return _DEFER
        from .native_spectral import _LOCK, process_editor, scene_latitude
        # Never sit in the GPU lock queue ahead of a newly queued preview.
        if not _LOCK.acquire(blocking=False):
            return _DEFER
        try:
            if self._cancel.is_set() or ctrl.exporting:
                return _DEFER
            settings = request['settings']
            if self._pre_key != request['pre_key']:
                if ctrl.busy:
                    return _DEFER
                from .imaging import prepare_photo_source
                from .raw_source import source_metadata, source_pixels
                source, _ = prepare_photo_source(self._raw, request['path'], settings)
                metadata = source_metadata(source)
                full = tuple(source.info.get('source_size', source.size))
                self._scene = process_editor(source_pixels(source), settings, stage='pre',
                    source_color_space=metadata['source_color_space'], source_linear=metadata['source_linear'],
                    exposure_ev=metadata.get('baseline_exposure_ev', 0), source_size=full,
                    pixel_scale=(full[0] / source.width, full[1] / source.height))
                self._pre_key = request['pre_key']
            reply = scene_latitude(self._scene, settings)
            self._measurements += 1
        finally:
            _LOCK.release()
        if self._cancel.is_set() or _stamp(request['path']) != source_key[1]:
            return _DEFER
        histogram = reply.get('scene', {}).get('histogram', {})
        from .native_spectral import scene_curve_samples
        transformed = bool(scene_curve_samples(settings.scene_curves)) or (
            settings.scene_latitude_active and
            (settings.scene_latitude_highlight_room > 0 or settings.scene_latitude_shadow_room > 0))
        if transformed and 'curved_fractions' not in histogram:
            # An older runtime must not quietly present the uncurved input as
            # though it had measured the current render's scene transform.
            raise ValueError('暂无场景数据')
        # Only actual node output is used; placed_* is a proposed fit, not the
        # committed picture. Missing curved_* means an identity scene transform.
        prefix = 'curved_' if 'curved_fractions' in histogram else ''
        rows = {}
        for channel, suffix in (('master', ''), ('red', '_r'), ('green', '_g'), ('blue', '_b')):
            values = histogram.get(prefix + 'fractions' + suffix)
            if isinstance(values, list) and len(values) == 128 and np.isfinite(values).all():
                rows[channel] = [max(0., float(value)) for value in values]
        if not rows.get('master'):
            raise ValueError('暂无场景数据')
        return dict(rows=rows, low=float(histogram.get('lo_ev', -16)), high=float(histogram.get('hi_ev', 16)),
                    exposure=float(histogram.get('exposure_ev', settings.exposure)),
                    medium=reply.get('medium', {}), exact=True, source_key=source_key)

    @Slot(object)
    def _done(self, message):
        self._inflight = False
        request, result, error = message
        if self._closed:
            return
        try:
            current_stamp = _stamp(request['path'])
        except OSError:
            current_stamp = None
        if current_stamp != request['source_key'][1]:
            self._discarded += 1
            self._desired = None
            self.refresh()
        elif not self._active or self._desired is None or request['key'] != self._desired['key']:
            self._discarded += 1
        elif result is not _DEFER:
            if error:
                self._set_state('error', True)
                return
            self._published_key = request['key']
            self._data = result
            self._set_state('ready')
            self.changed.emit()
        if self._active and self._desired is not None and self._published_key != self._desired['key']:
            self._timer.start(32 if not self.controller.exporting else 100)
        self.changed.emit()

    def close(self):
        self._closed = True
        self._active = False
        self._cancel.set()
        self._timer.stop()
        self.pool.clear()
        self.pool.waitForDone()
        self._raw = self._scene = None
