"""Bounded physical canvas: global geometry, optical context, pair and cancel."""
import ctypes as ct
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

import numpy as np

from desktop import native_spectral as native
from desktop.imaging import Settings


@unittest.skipUnless(native.available(), 'Windows Vulkan runtime required')
class NativeCanvas(unittest.TestCase):
    def setUp(self):
        self.engine = native._get_engine()
        self.lib = self.engine.lib
        self.lib.spk_canvas_size.argtypes = [ct.c_void_p, ct.POINTER(ct.c_uint32),
            ct.POINTER(ct.c_uint32), ct.POINTER(ct.c_void_p)]
        self.lib.spk_canvas_size.restype = ct.c_int
        self.lib.spk_render_canvas.argtypes = [ct.c_void_p, ct.c_char_p,
            ct.POINTER(ct.c_uint16), ct.c_uint32, ct.c_uint32, ct.POINTER(ct.c_void_p)]
        self.lib.spk_render_canvas.restype = ct.c_int
        self.lib.spk_render_pair.argtypes = [ct.c_void_p, ct.c_char_p, ct.POINTER(native._Result)]
        self.lib.spk_render_pair.restype = ct.c_int
        self.lib.spk_progress.argtypes = [ct.c_void_p, ct.c_char_p, ct.POINTER(ct.c_void_p)]
        self.lib.spk_progress.restype = ct.c_int
        self.sessions = []
        self.values = native.parameters(Settings(stock='kodak_portra_400', grain=0,
            halation=0, glare=0, dir_couplers_amount=0))
        self.values.update(input_cctf_decoding=False, striped=False,
            dir_couplers_active=False, tile_seed=743, overscan_active=True,
            overscan_format='135', overscan_frame_seed=17, overscan_camera_seed=31,
            overscan_frame_number=9, date_imprint_active=True,
            date_imprint_text='2026 11 09')

    def tearDown(self):
        for session in self.sessions:
            self.lib.spk_session_release(session)
        native.clear_sessions()

    def reply(self, pointer):
        try:
            return json.loads(ct.string_at(pointer)) if pointer.value else None
        finally:
            self.engine._free_reply(pointer)

    def fixture(self, width=360, height=240):
        y, x = np.mgrid[:height, :width]
        source = np.stack((.03 + .45*x/width, .06+.3*y/height,
                           .04+.2*(np.sin(x*.04)*.5+.5)), axis=2).astype(np.float32)
        source[height//3:height//3+8, width//2:width//2+9] = [3.5, 2.8, 2.3]
        return source

    def open(self, source, values):
        source = np.ascontiguousarray(source, dtype=np.float32)
        image = native._Image(source.ctypes.data_as(ct.POINTER(ct.c_float)),
                              source.shape[1], source.shape[0], 3)
        reply = ct.c_void_p()
        session = self.lib.spk_open(self.engine.handle, ct.byref(image),
            native._json_bytes(dict(values, product_defaults=True)), ct.byref(reply))
        self.reply(reply)
        self.assertTrue(session, self.engine.error())
        self.sessions.append(session)
        return session

    def normal(self, session, request=None):
        result = native._Result()
        try:
            status = (self.lib.spk_render(session, b'full', ct.byref(result)) if request is None else
                self.lib.spk_render_pair(session, native._json_bytes(request), ct.byref(result)))
            self.assertEqual(status, 0, self.engine.error())
            pixels = np.ctypeslib.as_array(result.rgba16,
                shape=(result.height*result.row_stride_px*4,)).reshape(result.height, result.row_stride_px, 4)
            return pixels[:, :result.width].copy()
        finally:
            self.lib.spk_result_free(ct.byref(result))

    def bounded(self, session, request=None):
        width, height = ct.c_uint32(), ct.c_uint32()
        reply = ct.c_void_p()
        self.assertEqual(self.lib.spk_canvas_size(session, ct.byref(width), ct.byref(height), ct.byref(reply)), 0, self.engine.error())
        size = self.reply(reply)
        with tempfile.TemporaryDirectory(prefix='spektrafilm-canvas-test-') as folder:
            output = np.memmap(Path(folder)/'output.rgba16', dtype=np.uint16, mode='w+',
                shape=(height.value, width.value, 4))
            try:
                status = self.lib.spk_render_canvas(session, native._json_bytes({'region_edge':96, **(request or {})}),
                    output.ctypes.data_as(ct.POINTER(ct.c_uint16)), width, height, ct.byref(reply))
                report = self.reply(reply)
                self.assertEqual(status, 0, (self.engine.error(), report))
                result = np.asarray(output).copy()
            finally:
                output._mmap.close()
        self.assertEqual(size['rgba16_bytes'], result.nbytes)
        self.assertTrue(report['success'])
        self.assertGreaterEqual(report['regions'], 1)
        return result, report

    def test_full_geometry_and_imprints_are_identical_across_region_plans(self):
        for width, height, overscan in ((360,240,True),(240,360,True),(360,240,False)):
            with self.subTest(width=width, overscan=overscan):
                session = self.open(self.fixture(width,height), dict(self.values, overscan_active=overscan))
                expected = self.normal(session)
                result, report = self.bounded(session)
                error = np.abs(result.astype(np.int32)-expected.astype(np.int32))
                self.assertLessEqual(int(error.max()), 2)
                self.assertFalse(report['finite_iir_context'])
                other, _ = self.bounded(session, dict(region_edge=133))
                np.testing.assert_allclose(other, result, atol=2, rtol=0)

    def test_active_optics_uses_one_global_field_and_reports_iir(self):
        values = dict(self.values, grain_active=True, grain_texture=2, grain_amount=.8,
            halation_active=True, halation_amount=1.1, halation_boost_ev=2.,
            halation_protect_ev=0., halation_scatter_amount=.6,
            dir_couplers_active=True, dir_couplers_amount=.7,
            glare_active=True, glare_percent=1., glare_amount=.8, scanner_lens_blur=1.)
        session = self.open(self.fixture(540,360), values)
        expected = self.normal(session)
        result, report = self.bounded(session, dict(region_edge=160))
        error = np.abs(result.astype(np.int32)-expected.astype(np.int32))
        self.assertLessEqual(int(error.max()), 3)
        self.assertFalse(report['finite_iir_context'])
        self.assertTrue(report['exact_iir_sweeps'])
        self.assertGreater(report['complete_line_passes'], 4)
        self.assertGreater(report['frame_boosted_peak'], report['frame_exposure_peak'])
        self.assertEqual(report['halo_pixels'], 0)
        self.assertEqual(report['exposure_checkpoint_bytes'], 0 if report.get('resident_pipeline') else 540*360*12)

    def test_original_grain_clouds_are_full_line_sweeps_with_small_budget(self):
        values = dict(self.values, grain_active=True, grain_texture=0, grain_amount=.75,
            grain_cloud_blur_um=2., grain_blur=3.2, grain_sublayers_active=True,
            scanner_lens_blur=3.1, dir_couplers_active=True, dir_couplers_amount=.8)
        session = self.open(self.fixture(680,460), values)
        expected = self.normal(session)
        result, report = self.bounded(session, dict(region_edge=73,budget_bytes=16<<20))
        np.testing.assert_allclose(result, expected, atol=3, rtol=0)
        self.assertTrue(report['exact_iir_sweeps'])
        self.assertGreater(report['complete_line_passes'], 10)

    def test_pair_independent_print_grade_and_vignette_match_whole_canvas(self):
        values = dict(self.values, output_color_space='ProPhoto RGB', overscan_active=False)
        session = self.open(self.fixture(), values)
        pair = dict(gates=[[0,0,.48,1],[.52,0,1,1]], left=dict(
            print=dict(brightnessStops=.6,yFilterShift=.1,mFilterShift=0,preflashExposure=0),
            adjustments=dict(exposure=.3,vignette=dict(amount=-30,midpoint=35))), right=None)
        request = dict(pair=pair, adjustments=dict(brightness=5))
        expected = self.normal(session, dict(target_space='ProPhoto RGB', **request))
        result, report = self.bounded(session, request)
        np.testing.assert_allclose(result, expected, atol=3, rtol=0)
        self.assertTrue(report['pair_layers_applied'])
        self.assertTrue(report['post_adjustments_applied'])
        restored, _ = self.bounded(session)
        baseline = self.normal(session)
        np.testing.assert_allclose(restored, baseline, atol=2, rtol=0)

    def test_cancel_is_monotone_cleans_checkpoint_and_never_marks_done(self):
        session = self.open(self.fixture(900,600), self.values)
        width, height = ct.c_uint32(), ct.c_uint32()
        self.lib.spk_canvas_size(session,ct.byref(width),ct.byref(height),None)
        output = np.empty((height.value,width.value,4),np.uint16)
        answer = {}
        before = set(Path(tempfile.gettempdir()).glob('spektrafilm-canvas-*.tmp'))
        def work():
            reply=ct.c_void_p()
            answer['status']=self.lib.spk_render_canvas(session,b'{"region_edge":32}',
                output.ctypes.data_as(ct.POINTER(ct.c_uint16)),width,height,ct.byref(reply))
            answer['report']=self.reply(reply)
        thread=threading.Thread(target=work);thread.start()
        progress=[]
        deadline=time.monotonic()+10
        while thread.is_alive() and time.monotonic()<deadline:
            reply=ct.c_void_p();self.lib.spk_progress(session,None,ct.byref(reply))
            state=self.reply(reply)
            if state['progress_id'].startswith('c'):
                progress.append(state['pct'])
                if state['pct']>5:
                    self.lib.spk_cancel(session,None)
                    break
            time.sleep(.002)
        thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertNotEqual(answer['status'],0)
        self.assertFalse(answer['report']['success'])
        reply=ct.c_void_p();self.lib.spk_progress(session,None,ct.byref(reply));state=self.reply(reply)
        self.assertTrue(state['cancelled']);self.assertFalse(state['done'])
        self.assertTrue(all(b>=a for a,b in zip(progress,progress[1:])))
        self.assertEqual(set(Path(tempfile.gettempdir()).glob('spektrafilm-canvas-*.tmp')),before)


if __name__ == '__main__':
    unittest.main()
