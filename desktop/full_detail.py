"""Full-precision, source-size render reuse and bounded viewport detail.

The GUI retains only a screen-sized patch. Full results remain read-only disk
maps, shared with output recipes of the same rendering colour domain.
"""
from __future__ import annotations

import math
import os
import threading

import numpy as np
from PySide6.QtCore import QObject, Property, QRunnable, QThreadPool, QTimer, Signal, Slot
from PySide6.QtGui import QImage

from .disk_cache import (CacheCancelled, cache, configure_cache, identity, source_identity,
                         check_cancel)


def _visible_source(pixels, metadata, cancel=None):
    from .raw_source import quantize_display
    if not (metadata.get('source_linear') or metadata.get('source_color_space', 'sRGB') != 'sRGB'
            or metadata.get('baseline_exposure_ev', 0)):
        return quantize_display(pixels)
    from .native_spectral import process_editor
    visible = np.empty(pixels.shape, dtype=np.uint8)
    for top in range(0, len(pixels), 128):
        check_cancel(cancel)
        block = process_editor(pixels[top:top+128], {}, stage='pre',
            source_color_space=metadata.get('source_color_space', 'sRGB'),
            source_linear=bool(metadata.get('source_linear')),
            exposure_ev=float(metadata.get('baseline_exposure_ev', 0)), clamp_output=True)
        quantize_display(block, out=visible[top:top+len(block)])
    return visible


def read_cached_photo(path, max_edge=None, *, cancel=None, reader=None):
    """Persistent exact decoded samples; bounded proxies never fulfil full asks."""
    from .imaging import read_photo
    from .raw_source import source_pixels, source_metadata, display_image, file_token
    edge = max(0, int(max_edge or 0))
    request = identity(path, domain='decoded-source', edge=edge,
                       decoder_policy=os.environ.get('SPEKTRAFILM_COMPUTE', 'auto'))
    original = []
    def produce():
        check_cancel(cancel)
        image = (reader or read_photo)(path, edge or None)
        original.append(image)
        pixels = source_pixels(image)
        info = dict(source_size=list(image.info.get('source_size', image.size)),
                    source_metadata=source_metadata(image))
        if source_identity(path) != request['source']: raise OSError('照片已变更，请重新载入')
        return pixels, info
    try:
        record = cache().get_or_create('preview' if edge else 'working', request, produce, cancel=cancel)
        check_cancel(cancel)
        if original:
            # Reuse the original's already prepared display on its first decode.
            return original.pop()
        metadata = record.metadata.get('source_metadata', {})
        full_size = tuple(record.metadata.get('source_size', record.pixels.shape[1::-1]))
        visible = _visible_source(record.pixels, metadata, cancel)
        return display_image(record.pixels, full_size=full_size, metadata=metadata,
                             token=file_token(path, full_size), display_pixels=visible)
    finally:
        for image in original: image.close()


def render_full_pixels(path, settings, *, color_space='sRGB', digital_intermediate=False,
                       cancel=None, progress=None, renderer=None,di_blue_compensation=False):
    """Exact final pipeline, before recipe resize/encoding, reusable on disk.

    Output colour domain is part of the identity. The engine's sRGB and wide
    gamut compression differ, so a matrix transform must never pass off a
    ProPhoto render as the existing direct sRGB render. Containers, bit depths,
    compression quality and recipe sizes share a same-domain render.
    """
    from .imaging import film_settings, prepare_photo_source, render_pixels
    settings = film_settings(settings)
    request = identity(path, settings=settings,
        domain='Cineon-DI-float32' if digital_intermediate else color_space+':encoded-final-float32',
        compute=os.environ.get('SPEKTRAFILM_COMPUTE', 'auto'),
        di_blue_compensation=bool(di_blue_compensation) if digital_intermediate else False)
    def produce():
        if progress: progress('decode')
        original = read_cached_photo(path, cancel=cancel)
        prepared = None
        try:
            check_cancel(cancel)
            prepared, _ = prepare_photo_source(original, path, settings)
            if prepared is not original: original.close(); original = None
            if progress: progress('render')
            if digital_intermediate:
                from .digital_intermediate import render_codes
                pixels = render_codes(prepared, settings,blue_compensation=di_blue_compensation)
            else:
                pixels = (renderer or render_pixels)(prepared, settings, preview=False,
                                                    output_color_space=color_space)
            check_cancel(cancel)
            if source_identity(path) != request['source']: raise OSError('照片已变更，请重新载入')
            return pixels, dict(color_space=color_space, source_size=prepared.info.get('source_size', prepared.size),
                                output_size=[pixels.shape[1], pixels.shape[0]])
        finally:
            if original is not None: original.close()
            if prepared is not None and prepared is not original: prepared.close()
    try:
        record = cache().get_or_create('full', request, produce, cancel=cancel)
        check_cancel(cancel)
        if record.hit and progress: progress('render')
        return record.pixels
    except CacheCancelled as error:
        from .output import ExportCancelled
        raise ExportCancelled(str(error)) from error


def read_detail_pixels(pixels, rect, screen_size, *, max_pixels=4_194_304):
    """Read only touched source rows/columns; never materialize the full map."""
    height, width = pixels.shape[:2]
    x, y, w, h = [float(value) for value in rect]
    if not all(math.isfinite(value) for value in (x, y, w, h)): raise ValueError('视口坐标无效')
    x0 = min(width-1, max(0, int(math.floor(x*width+1e-7))))
    y0 = min(height-1, max(0, int(math.floor(y*height+1e-7))))
    x1 = min(width, max(x0+1, int(math.ceil((x+w)*width-1e-7))))
    y1 = min(height, max(y0+1, int(math.ceil((y+h)*height-1e-7))))
    target_w, target_h = [max(1, int(value)) for value in screen_size]
    # A pathological viewport/zoom ask cannot allocate a giant GUI texture.
    ratio = min(1., math.sqrt(max_pixels/(target_w*target_h)))
    target_w, target_h = max(1, int(target_w*ratio)), max(1, int(target_h*ratio))
    region = pixels[y0:y1, x0:x1]
    # At 1:1 the requested footprint equals the screen; keep every source pixel.
    # At smaller scales, row-bounded float resampling avoids a full image copy.
    if region.shape[1] > target_w*2 or region.shape[0] > target_h*2:
        stride_x = max(1, int(region.shape[1]/target_w))
        stride_y = max(1, int(region.shape[0]/target_h))
        region = region[::stride_y, ::stride_x]
    region = np.array(region, dtype=np.float32, copy=True, order='C')
    if region.shape[1] != target_w or region.shape[0] != target_h:
        from .raw_source import resize_pixels
        region = resize_pixels(region, (target_w, target_h))
    return region, [x0/width, y0/height, (x1-x0)/width, (y1-y0)/height]


class _Signals(QObject):
    done = Signal(object)


class _Task(QRunnable):
    def __init__(self, function, token):
        super().__init__(); self.function = function; self.token = token; self.signals = _Signals()
    def run(self):
        try: result = dict(token=self.token, value=self.function(), error='')
        except Exception as error: result = dict(token=self.token, value=None, error=str(error))
        self.signals.done.emit(result)


class FullDetail(QObject):
    changed = Signal()
    storageChanged = Signal()
    _stopRequested = Signal()

    def __init__(self, controller):
        super().__init__(controller); self.controller = controller
        self.pool = QThreadPool(self); self.pool.setMaxThreadCount(1)
        self._state = 'off'; self._source = ''; self._original_source = ''; self._rect = [0,0,0,0]
        self._enabled = False; self._closed = False; self._serial = 0; self._busy = False; self._paused = False
        self._ask = None; self._job = None; self._cancel = threading.Event(); self._usage = {}
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(160)
        self.timer.timeout.connect(self._start)
        self._stopRequested.connect(self.timer.stop)
        configure_cache(controller._store.parent/'render-cache')
        self.configureBudgets(controller.preferences)
        controller.stateChanged.connect(self._edited)

    @Property(str, notify=changed)
    def source(self): return self._source
    @Property(str, notify=changed)
    def originalSource(self): return self._original_source
    @Property('QVariantList', notify=changed)
    def rect(self): return self._rect
    @Property(str, notify=changed)
    def state(self): return self._state
    @Property(bool, notify=changed)
    def ready(self): return self._state == 'ready' and bool(self._source)
    @Property('QVariantMap', notify=storageChanged)
    def storageUsage(self): return self._usage

    @Slot('QVariantMap')
    def configureBudgets(self, preferences):
        mapping = {'working':'working_cache_mb', 'preview':'preview_cache_mb', 'full':'full_render_cache_mb'}
        cache().configure({category: int(preferences.get(key, {'working':5120,'preview':10240,'full':8192}[category]))*1024**2
                           for category, key in mapping.items()})
        self.refreshStorage()

    @Slot()
    def refreshStorage(self):
        self._usage = cache().usage(); self.storageChanged.emit()

    @Slot(str)
    def clearCategory(self, category):
        try: self._usage = cache().clear(category or None); self.storageChanged.emit()
        except (ValueError, OSError) as error: self.controller.toast.emit(str(error))

    def set_enabled(self, value):
        self._enabled = bool(value)
        if not self._enabled:
            self._serial += 1; self._cancel.set(); self._ask = None; self.timer.stop()
            self._source = self._original_source = ''; self._state = 'off'; self.changed.emit()
        elif self._ask is not None and not self._paused: self.timer.start()

    def pause(self):
        # Export drains workers from its own thread. QTimer belongs to the GUI
        # thread, so stop it through the queued Qt connection, never directly.
        self._paused = True; self._serial += 1; self._cancel.set(); self._stopRequested.emit()

    @Slot()
    def resume(self):
        self._paused = False
        if self._enabled and self._ask is not None: self.timer.start()

    @Slot(float, float, float, float, int, int)
    @Slot(float, float, float, float, int, int, bool)
    def request(self, x, y, width, height, pixel_width, pixel_height, comparing=False):
        if self._closed or not self._enabled or self.controller._current < 0: return
        if width <= 0 or height <= 0 or pixel_width <= 0 or pixel_height <= 0: return
        path = self.controller.currentPath
        try: stamp = source_identity(path)
        except OSError: return
        ask = (path, self.controller._settings,
               (float(x),float(y),float(width),float(height)), (int(pixel_width),int(pixel_height)),
               self.controller._color_display.snapshot(), bool(comparing), stamp)
        if self._ask == ask and self._state in ('ready','rendering'): return
        self._ask = ask; self._serial += 1
        # A pan does not cancel/restart the same full render; the next viewport
        # waits behind its one producer and reads from that completed result.
        self._source = self._original_source = ''; self._state = 'waiting' if self._busy else 'rendering'
        self.changed.emit()
        if not self._paused: self.timer.start()

    def _edited(self):
        if self._closed: return
        if self._ask and (self.controller.currentPath, self.controller._settings) != self._ask[:2]:
            self._cancel.set(); self._serial += 1; self._source = self._original_source = ''
            self._state = 'off'; self._ask = None; self.changed.emit()
        if self._paused and not self.controller._exporting: self.resume()

    def _start(self):
        if self._closed or not self._enabled or self._paused or self._busy or self._ask is None: return
        if self.controller._exporting or self.controller._before is not None:
            self.timer.start(240); return
        self._busy = True; self._state = 'rendering'; self.changed.emit()
        ask, serial = self._ask, self._serial
        cancel = threading.Event(); self._cancel = cancel
        def work():
            path, settings, rect, size, color_config, comparing, stamp = ask
            pixels = render_full_pixels(path, settings, color_space='ProPhoto RGB',cancel=cancel)
            check_cancel(cancel)
            patch, actual_rect = read_detail_pixels(pixels, rect, size)
            del pixels
            if color_config:
                from .color_display import transform_pixels,canvas_pixels
                patch,space=canvas_pixels(patch,'ProPhoto RGB',color_config)
                patch = transform_pixels(patch, space, color_config)
            else:
                from shared.color_management import convert_pixels
                patch=convert_pixels(patch,'ProPhoto RGB','sRGB')
            from .raw_source import quantize_display
            visible = quantize_display(patch)
            image = QImage(visible.data, visible.shape[1], visible.shape[0], visible.strides[0], QImage.Format_RGB888).copy()
            original_image = None
            if comparing:
                from .imaging import Settings
                # Comparison remains the natural source and shares the exact
                # current optical preparation/crop, without the edited look.
                natural = Settings(film_enabled=False, geometry=settings.geometry,
                                   lens_correction=settings.lens_correction, defringe=settings.defringe)
                original_pixels = render_full_pixels(path, natural, color_space='ProPhoto RGB',cancel=cancel)
                original_patch, _ = read_detail_pixels(original_pixels, rect, size)
                del original_pixels
                if color_config:
                    original_patch,space=canvas_pixels(original_patch,'ProPhoto RGB',color_config)
                    original_patch = transform_pixels(original_patch, space, color_config)
                else:original_patch=convert_pixels(original_patch,'ProPhoto RGB','sRGB')
                original_visible = quantize_display(original_patch)
                original_image = QImage(original_visible.data, original_visible.shape[1], original_visible.shape[0],
                                        original_visible.strides[0], QImage.Format_RGB888).copy()
            check_cancel(cancel)
            if source_identity(path) != stamp: raise OSError('照片已变更，请重新载入')
            return image, actual_rect, original_image
        job = _Task(work, serial); self._job = job; job.signals.done.connect(self._done); self.pool.start(job)

    @Slot(object)
    def _done(self, result):
        self._busy = False; self._job = None
        if self._closed: return
        if result['token'] == self._serial and self._enabled and not self._paused:
            if result['value'] is not None:
                image, self._rect, original_image = result['value']
                self.controller.provider.publish('full-detail', image)
                self._source = 'image://photos/full-detail?v='+str(self._serial)
                if original_image is not None:
                    self.controller.provider.publish('full-detail-original', original_image)
                    self._original_source = 'image://photos/full-detail-original?v='+str(self._serial)
                self._state = 'ready'
            else: self._state = 'failed'
            self.changed.emit(); self.refreshStorage()
        elif self._enabled and self._ask is not None and not self._paused: self.timer.start(0)

    def close(self):
        self._closed = True; self._cancel.set(); self.timer.stop(); self.pool.waitForDone()
        self._job=None;self._ask=None
