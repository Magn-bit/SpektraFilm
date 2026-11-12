"""Research operator contracts plus optional shipped-kernel parity.

Only the optional test reads local research artifacts; the application never
imports them. SPEKTRA_HIGHLIGHT_REFERENCE_REPORT can retain actual GPU results.
"""
import hashlib
import json
import os
from pathlib import Path
import unittest

import numpy as np

from native.reference.c1_highlight_reference import HighlightParameters, recover_highlights

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'output/captureone-camera-profile/opencl-selected/40814992_z03df67c650.cl'


class HighlightReferenceTests(unittest.TestCase):
    def test_unclipped_alpha_and_source_are_preserved(self):
        source = np.array([[0, 0, 0, -4], [.6, .7, .8, 13],
                           [-.1, .2, .3, .3]], np.float32)
        original = source.copy()
        params = HighlightParameters((.6, .7, .8), 2.4, (.4, .5, .6), (1.1, .9, 1.2), .7)
        actual = recover_highlights(source, params)
        np.testing.assert_array_equal(actual, original)
        np.testing.assert_array_equal(source, original)
        self.assertFalse(np.shares_memory(actual, source))

    def test_unsupported_domain_is_rejected(self):
        valid = HighlightParameters((.6, .7, .8), 2.4, (.4, .5, .6), (1.1, .9, 1.2), .7)
        for source in (np.zeros((2, 3), np.float32), np.zeros((2, 4), np.float64),
                       np.full((2, 4), np.nan, np.float32)):
            with self.assertRaises(ValueError):
                recover_highlights(source, valid)
        invalid = HighlightParameters((0, .7, .8), 2.4, (.4, .5, .6), (1.1, .9, 1.2), .7)
        with self.assertRaises(ValueError):
            recover_highlights(np.zeros((2, 4), np.float32), invalid)

    @unittest.skipUnless(SOURCE.is_file(), 'local research kernel required')
    def test_actual_gpu_operator(self):
        try:
            import pyopencl as cl
            device = next(d for platform in cl.get_platforms() for d in platform.get_devices()
                          if d.type & cl.device_type.GPU)
        except (ImportError, StopIteration) as exc:
            self.skipTest(str(exc))
        context = cl.Context([device])
        queue = cl.CommandQueue(context)
        source_bytes = SOURCE.read_bytes()
        program = cl.Program(context, source_bytes.decode('ascii')).build(options=['-cl-std=CL1.2'])
        kernel = cl.Kernel(program, 'z03df67c650')
        rng = np.random.default_rng(92391)
        records = []
        region = np.array([3, 4, 123, 61], np.int32)
        x, y, w, h = map(int, region)
        for index in range(12):
            threshold = rng.uniform(.2, 1.2, 3).astype(np.float32)
            params = HighlightParameters(tuple(threshold), float(rng.uniform(0, 3)),
                tuple(rng.uniform(.2, 1.5, 3)), tuple(rng.uniform(.2, 1.6, 3)),
                float(rng.uniform(0, 1.2)))
            source = rng.uniform(-.05, 2.5, (69, 131, 4)).astype(np.float32)
            source[y, x:x+7, :3] = np.array([
                [0, 0, 0], threshold, threshold*np.float32(.999),
                threshold*np.float32(1.001), [2, .2, .3], [.2, 2, .3], [.2, .3, 2]], np.float32)
            before = source.copy()
            result = np.full((71, 135, 4), -123.125, np.float32)
            p = np.zeros(16, np.float32)
            p[:11] = params.values()
            flags = cl.mem_flags
            src = cl.Buffer(context, flags.READ_ONLY | flags.COPY_HOST_PTR, hostbuf=source)
            dst = cl.Buffer(context, flags.READ_WRITE | flags.COPY_HOST_PTR, hostbuf=result)
            kernel.set_args(src, dst, region, np.int32(source.shape[1]*4),
                            np.int32(result.shape[1]*4), p)
            cl.enqueue_nd_range_kernel(queue, kernel, (128, 64), None).wait()
            cl.enqueue_copy(queue, result, dst).wait()
            cl.enqueue_copy(queue, source, src).wait()
            actual = result[y:y+h, x:x+w]
            expected = recover_highlights(before[y:y+h, x:x+w], params)
            np.testing.assert_allclose(expected, actual, rtol=3e-6, atol=1e-6)
            np.testing.assert_array_equal(actual[..., 3], before[y:y+h, x:x+w, 3])
            np.testing.assert_array_equal(source, before)
            guards = np.ones(result.shape[:2], bool)
            guards[y:y+h, x:x+w] = False
            self.assertTrue(np.all(result[guards] == -123.125))
            self.assertTrue(np.isfinite(actual).all())
            error = abs(expected.astype(np.float64)-actual.astype(np.float64))
            records.append({'case': index, 'params': p.tolist(), 'pixels': w*h,
                            'max_abs': float(error.max()), 'mean_abs': float(error.mean())})
        report_path = os.environ.get('SPEKTRA_HIGHLIGHT_REFERENCE_REPORT')
        if report_path:
            path = Path(report_path).resolve()
            if not path.is_relative_to((ROOT/'output').resolve()):
                raise ValueError('research report must stay under output/')
            path.parent.mkdir(parents=True, exist_ok=True)
            report = {'ok': True, 'device': device.name, 'driver': device.driver_version,
                'source_sha256': hashlib.sha256(source_bytes).hexdigest(),
                'scope': 'isolated clipping operator with explicit artificial parameters; not complete RAW',
                'cases': records, 'pixels_compared': sum(r['pixels'] for r in records),
                'max_abs': max(r['max_abs'] for r in records),
                'alpha_exact': True, 'source_unchanged': True, 'guards_unchanged': True}
            path.write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    unittest.main()
