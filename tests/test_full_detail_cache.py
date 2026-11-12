"""One small high-precision cache/detail/export integration node, no RAW rebench."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import gc
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from desktop.disk_cache import DiskCache, CacheCancelled, configure_cache, identity
from desktop.full_detail import read_cached_photo, read_detail_pixels
from desktop.imaging import Settings, read_photo, prepare_photo_source, render_pixels
from desktop.native_spectral import available, parameters
from desktop.output import render_recipe_pixels, ExportCancelled
from shared.output_recipes import OutputRecipe


class FullCacheIntegration(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='spektrafilm-cache-check-')
        self.root = Path(self.folder.name)
        self.source = self.root/'source.png'
        y, x = np.mgrid[0:97, 0:131]
        self.samples = np.stack((x/130, y/96, (x+y)/226), axis=-1).astype(np.float32)
        Image.fromarray(np.rint(self.samples*255).astype(np.uint8)).save(self.source)
        self.store = configure_cache(self.root/'cache', {name: 8 << 20 for name in ('working','preview','full')})

    def tearDown(self):
        gc.collect(); self.store.clear(); gc.collect(); self.folder.cleanup()

    def test_exact_arrays_independent_budgets_pins_lru_and_safe_clean(self):
        tiny = DiskCache(self.root/'tiny', dict(working=2500, preview=2500, full=2500))
        data = self.samples[:9,:11]
        a = tiny.get_or_create('full', {'id':'A'}, lambda:(data, {}))
        b = tiny.get_or_create('full', {'id':'B'}, lambda:(data*.5, {}))
        self.assertTrue(a.pixels.flags.c_contiguous)
        self.assertFalse(a.pixels.flags.writeable)
        np.testing.assert_array_equal(a.pixels, data)
        self.assertEqual(tiny.usage()['full']['entries'], 2) # active readers may exceed budget
        del a; gc.collect(); tiny.trim()
        self.assertEqual(tiny.usage()['full']['entries'], 1)
        before = self.source.read_bytes()
        unknown = tiny.root/'full'/'do-not-touch.txt'; unknown.write_text('not a cache entry')
        tiny.clear('full')
        self.assertEqual(tiny.usage()['full']['entries'], 1) # still pinned
        del b; gc.collect()
        self.assertEqual(tiny.usage()['full']['entries'], 0)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertTrue(unknown.exists())
        self.assertEqual(tiny.usage()['working']['bytes'], 0)

    def test_coalesces_one_producer_and_cancellation_never_commits_partial(self):
        started, release = threading.Event(), threading.Event()
        calls = []
        def produce():
            calls.append(1); started.set(); self.assertTrue(release.wait(5))
            return self.samples, {}
        with ThreadPoolExecutor(2) as pool:
            first = pool.submit(self.store.get_or_create, 'full', {'same':1}, produce)
            self.assertTrue(started.wait(5))
            second = pool.submit(self.store.get_or_create, 'full', {'same':1}, produce)
            release.set(); a, b = first.result(5), second.result(5)
        self.assertEqual(len(calls), 1)
        np.testing.assert_array_equal(a.pixels, b.pixels)
        cancel = threading.Event()
        def cancelled(): cancel.set(); return self.samples, {}
        with self.assertRaises(CacheCancelled):
            self.store.get_or_create('full', {'cancelled':1}, cancelled, cancel=cancel)
        self.assertIsNone(self.store.get('full', {'cancelled':1}))
        self.assertFalse(list((self.store.root/'full').glob('.partial-*')))

    def test_source_stamp_proxy_and_full_decodes_are_separate_and_persistent(self):
        with patch('desktop.imaging.read_photo', wraps=read_photo) as decode:
            a = read_cached_photo(str(self.source), 64)
            b = read_cached_photo(str(self.source), 64)
            self.assertEqual(decode.call_count, 1)
            self.assertEqual(a.size, b.size)
            from desktop.raw_source import source_pixels
            np.testing.assert_array_equal(source_pixels(a), source_pixels(b))
            full = read_cached_photo(str(self.source))
            self.assertEqual(decode.call_count, 2)
            self.assertEqual(full.size, (131,97))
            a.close(); b.close(); full.close(); del a,b,full
            stat = self.source.stat()
            os.utime(self.source, ns=(stat.st_atime_ns, stat.st_mtime_ns+1_000_000_000))
            changed = read_cached_photo(str(self.source), 64)
            self.assertEqual(decode.call_count, 3); changed.close()
        usage = self.store.usage()
        self.assertEqual(usage['working']['entries'], 1)
        self.assertEqual(usage['preview']['entries'], 2)

    def test_clear_during_active_production_removes_after_the_returned_reader_releases(self):
        started, release = threading.Event(), threading.Event()
        def produce():
            started.set(); self.assertTrue(release.wait(5)); return self.samples, {}
        with ThreadPoolExecutor(1) as pool:
            task = pool.submit(self.store.get_or_create,'full',{'clear_while_writing':True},produce)
            self.assertTrue(started.wait(5)); self.store.clear('full'); release.set()
            record = task.result(5)
        np.testing.assert_array_equal(record.pixels,self.samples)
        self.assertEqual(self.store.usage()['full']['entries'],1)
        del task,record;gc.collect()
        self.assertEqual(self.store.usage()['full']['entries'],0)

    def test_viewport_1_to_1_reads_true_source_pixels_and_caps_texture(self):
        result, rect = read_detail_pixels(self.samples, [40/131,35/97,30/131,20/97], (30,20))
        np.testing.assert_array_equal(result, self.samples[35:55,40:70])
        self.assertEqual(result.shape, (20,30,3))
        np.testing.assert_allclose(rect, [40/131,35/97,30/131,20/97])
        capped, _ = read_detail_pixels(self.samples, [0,0,1,1], (4000,3000), max_pixels=1200)
        self.assertLessEqual(capped.shape[0]*capped.shape[1], 1200)

    @unittest.skipUnless(available(), 'Actual Windows Vulkan runtime required')
    def test_same_domain_recipes_share_exact_float_output_without_resizing_source(self):
        settings = Settings(lens_correction=False, defringe=False, grain=0, halation=0,
                            exposure=.16, highlights=-18)
        image = read_photo(str(self.source))
        expected = render_pixels(image, settings, preview=False, output_color_space='sRGB')
        image.close()
        with patch('desktop.imaging.render_pixels', wraps=render_pixels) as render:
            jpeg = render_recipe_pixels(str(self.source), settings, OutputRecipe())
            tiff = render_recipe_pixels(str(self.source), settings, OutputRecipe(format='tiff',bit_depth=16))
            small = render_recipe_pixels(str(self.source), settings, OutputRecipe(long_edge=80))
            self.assertEqual(render.call_count, 1)
            self.assertEqual(jpeg.shape, (97,131,3)); self.assertEqual(small.shape[1], 80)
            np.testing.assert_array_equal(jpeg, expected)
            np.testing.assert_array_equal(tiff, expected)
            self.assertEqual(jpeg.dtype, np.float32)
            self.assertFalse(jpeg.flags.writeable)
            render_recipe_pixels(str(self.source), replace(settings,exposure=.17), OutputRecipe())
            self.assertEqual(render.call_count, 2)
        cancel = threading.Event(); cancel.set()
        with self.assertRaises(ExportCancelled):
            render_recipe_pixels(str(self.source), settings, OutputRecipe(), cancel=cancel)

    def test_effect_bypass_keeps_amounts_and_gates_scatter(self):
        settings = Settings(grain=57,halation=31,halation_scatter_amount=.7,
                            grain_enabled=False,halation_enabled=False)
        wire = parameters(settings)
        self.assertFalse(wire['grain_active']); self.assertFalse(wire['halation_active'])
        self.assertEqual(wire['halation_scatter_amount'], 0)
        self.assertEqual((settings.grain,settings.halation,settings.halation_scatter_amount), (57,31,.7))

    def test_async_detail_pan_comparison_export_resume_and_source_identity(self):
        from PySide6.QtCore import QObject, Signal, qInstallMessageHandler
        from PySide6.QtGui import QGuiApplication
        from desktop.full_detail import FullDetail
        app = QGuiApplication.instance() or QGuiApplication([])
        class Provider:
            def __init__(self): self.images = {}
            def publish(self, name, image): self.images[name] = image
        class Display:
            def snapshot(self): return None
        class Controller(QObject):
            stateChanged = Signal()
            toast = Signal(str)
        ctrl = Controller(); ctrl._store = self.root/'async-store'/'edits'
        ctrl.preferences = dict(working_cache_mb=8,preview_cache_mb=8,full_render_cache_mb=8)
        ctrl._current = 0; ctrl.currentPath = str(self.source)
        ctrl._settings = Settings(lens_correction=False,defringe=False)
        ctrl._exporting = False; ctrl._before = None; ctrl._color_display = Display(); ctrl.provider = Provider()
        detail = FullDetail(ctrl); detail.set_enabled(True)
        started, release = threading.Event(), threading.Event()
        calls, warnings = [], []
        def render(path, settings, **kwargs):
            calls.append(settings)
            if len(calls) == 1:
                started.set(); self.assertTrue(release.wait(5))
                self.assertFalse(kwargs['cancel'].is_set(), 'panning must not cancel the full producer')
            return self.samples
        def wait_ready():
            deadline = time.monotonic()+5
            while not detail.ready and time.monotonic()<deadline:
                app.processEvents(); time.sleep(.001)
            self.assertTrue(detail.ready, detail.state)
        handler = qInstallMessageHandler(lambda kind, context, message: warnings.append(message))
        try:
            with patch('desktop.full_detail.render_full_pixels', side_effect=render):
                detail.request(0,0,.5,.5,40,30); detail.timer.stop(); detail._start()
                self.assertTrue(started.wait(5))
                detail.request(.25,.25,.5,.5,40,30,True); release.set(); wait_ready()
                self.assertTrue(detail.originalSource)
                self.assertEqual(ctrl.provider.images['full-detail'].size().toTuple(), (40,30))
                self.assertFalse(calls[-1].film_enabled)
                self.assertEqual(calls[-1].geometry, ctrl._settings.geometry)
                ctrl._exporting = True
                with ThreadPoolExecutor(1) as pool: pool.submit(detail.pause).result(5)
                app.processEvents()
                before = len(calls)
                detail.request(.3,.25,.5,.5,40,30,True); detail._start()
                self.assertEqual(len(calls), before)
                ctrl._exporting = False; ctrl.stateChanged.emit(); wait_ready()
                before = len(calls); serial = detail._serial
                stamp = self.source.stat()
                os.utime(self.source,ns=(stamp.st_atime_ns,stamp.st_mtime_ns+1_000_000_000))
                detail.request(.3,.25,.5,.5,40,30,True)
                self.assertGreater(detail._serial, serial); wait_ready(); self.assertGreater(len(calls), before)
                ctrl._settings = replace(ctrl._settings,exposure=.2); ctrl.stateChanged.emit()
                self.assertFalse(detail.source); self.assertIsNone(detail._ask)
                detail.request(.3,.25,.5,.5,40,30); wait_ready()
                self.assertEqual(calls[-1].exposure,.2)
                self.assertFalse(detail.originalSource)
            self.assertFalse([message for message in warnings if 'timer' in message.lower()], warnings)
        finally:
            release.set(); detail.close(); qInstallMessageHandler(handler)


if __name__ == '__main__': unittest.main()
