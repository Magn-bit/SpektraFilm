"""Bounded integration checks for absolute metering and safe latitude edits."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from dataclasses import asdict, replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image
from PySide6.QtWidgets import QApplication

from desktop.controller import Controller, PhotoProvider
from desktop.imaging import Settings
from desktop import native_spectral
from desktop.raw_source import display_image


@unittest.skipUnless(native_spectral.available(), 'native runtime required')
class DarkroomAnalysis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setup_photo(self, folder, settings):
        path = Path(folder) / 'scene.png'
        Image.new('RGB', (127, 79), 'grey').save(path)
        linear = np.geomspace(.0001, 6., 79 * 127, dtype=np.float32).reshape(79, 127)
        source = display_image(np.repeat(linear[..., None], 3, axis=2),
            metadata={'source_color_space': 'sRGB', 'source_linear': True, 'baseline_exposure_ev': .7})
        ctrl = Controller(PhotoProvider(), folder)
        ctrl._photos.append(dict(path=str(path), name=path.name, width=127, height=79,
            dimensions='127 × 79', settings=asdict(settings)))
        ctrl._current = 0
        ctrl._settings = settings
        ctrl._source = lambda *_: source
        ctrl._sync_editor_bindings()
        return ctrl

    def analyze(self, ctrl, target, stale=False):
        work = []
        with patch.object(ctrl, '_submit', side_effect=lambda fn, ctx, **_: work.append((fn, ctx))):
            ctrl._analyze_scene(target, 'balanced')
        fn, context = work.pop()
        value = fn()
        if stale:
            ctrl._generation += 1
        ctrl._done(dict(context, job=-1, ok=True, value=value))
        ctrl.timer.stop()
        ctrl.fast_timer.stop()
        return value

    def test_product_neutral_and_meter_are_atomic_and_repeatable(self):
        settings = Settings(stock='kodak_vision3_500t', exposure=.4, print_y=17., print_m=-11.,
                            lens_correction=False, defringe=False)
        with tempfile.TemporaryDirectory() as folder:
            ctrl = self.setup_photo(folder, settings)
            try:
                with patch.object(native_spectral, 'solve_spectral', wraps=native_spectral.solve_spectral) as solve:
                    first = self.analyze(ctrl, 'both')
                    applied = ctrl._settings
                    self.assertEqual(applied.print_y, 0.)
                    self.assertEqual(applied.print_m, 0.)
                    self.assertEqual(len(ctrl._history[0]), 1)
                    self.analyze(ctrl, 'both')
                    self.assertEqual(ctrl._settings, applied)
                    self.assertEqual(solve.call_count, 1, 'absolute source metering must reuse unchanged analysis')
                    self.assertEqual(len(ctrl._history[0]), 1)
                base = native_spectral.parameters(settings)
                for key in ('c_filter_neutral', 'm_filter_neutral', 'y_filter_neutral'):
                    self.assertEqual(first['solved_params'][key], base[key])
                ctrl.undo()
                ctrl.timer.stop(); ctrl.fast_timer.stop()
                self.assertEqual(ctrl._settings, settings)
                before = ctrl._settings
                self.analyze(ctrl, 'both', stale=True)
                self.assertEqual(ctrl._settings, before, 'late suggestions must not change current edits')
            finally:
                ctrl.close()

    def test_filter_only_does_not_decode_photo_or_change_exposure(self):
        settings = Settings(print_y=20., print_m=-20., exposure=.8,
                            lens_correction=False, defringe=False)
        with tempfile.TemporaryDirectory() as folder:
            ctrl = self.setup_photo(folder, settings)
            try:
                ctrl._source = lambda *_: (_ for _ in ()).throw(AssertionError('neutral material lookup must not decode'))
                self.analyze(ctrl, 'filter_pack')
                self.assertEqual(ctrl._settings.exposure, settings.exposure)
                self.assertEqual((ctrl._settings.print_y, ctrl._settings.print_m), (0., 0.))
            finally:
                ctrl.close()

    def test_latitude_keeps_scene_headroom_and_rejects_stale_fit(self):
        settings = Settings(lens_correction=False, defringe=False, exposure=.3)
        with tempfile.TemporaryDirectory() as folder:
            ctrl = self.setup_photo(folder, settings)
            try:
                result = self.analyze(ctrl, 'latitude')
                # 6.0 scene-linear plus RAW baseline is well above encoded
                # display white. Analysis must not silently clip to 1.0.
                self.assertGreater(result['scene']['p99_9'], 4.)
                self.assertGreater(result['medium']['latitude_stops'], 0.)
                ctrl.updateParameter('exposure', .5)
                ctrl.timer.stop(); ctrl.fast_timer.stop()
                previous = ctrl._settings
                ctrl.applyLatitude()
                self.assertEqual(ctrl._settings, previous)
            finally:
                ctrl.close()

    def test_late_analysis_rejects_same_path_source_rewrite_before_applying(self):
        settings = Settings(lens_correction=False,defringe=False)
        with tempfile.TemporaryDirectory() as folder:
            ctrl = self.setup_photo(folder,settings)
            try:
                work=[]
                with patch.object(ctrl,'_submit',side_effect=lambda fn,ctx,**_:work.append((fn,ctx))):
                    ctrl._analyze_scene('both','balanced')
                _,context=work.pop()
                path=Path(ctrl.currentPath);stamp=path.stat()
                os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns+1_000_000_000))
                ctrl._done(dict(context,job=-1,ok=True,value={'solved_params':{'exposure_compensation_ev':1.4}}))
                self.assertEqual(ctrl._settings,settings)
                self.assertFalse(ctrl.analysisBusy)
                self.assertFalse(ctrl.analysis)
                self.assertFalse(ctrl._history.get(0))
            finally:ctrl.close()


if __name__ == '__main__':
    unittest.main()
