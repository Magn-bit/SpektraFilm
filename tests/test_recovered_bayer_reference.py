"""Research-only comparisons to kernels extracted from the user's C1 install.

Normal source checkouts without those local artifacts/OpenCL skip this suite.
To retain evidence, set SPEKTRA_BAYER_REFERENCE_REPORT to an output directory.
The application does not import this reference or the proprietary oracle.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from native.reference.c1_bayer_reference import (
    InitialGreenParameters, initial_green,
    ChromaParameters, refine_green, fill_opposite_chroma, fill_chroma_at_green)

try:
    import pyopencl as cl
    import pyopencl.cltypes as ct
except ImportError:
    cl = None

SOURCE = ROOT / 'output/captureone-camera-profile/opencl-selected'
FILES = [('41165392_zb4a41b922a.cl', 'zb4a41b922a'),
         ('40790064_z13bff1d853.cl', 'z13bff1d853'),
         ('41208528_z95ba5a4538.cl', 'z95ba5a4538'),
         ('41214464_z48dd14e643.cl', 'z48dd14e643')]
CANARY = np.float32(-123456.25)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def crop(image, rect):
    x, y, width, height = rect
    return image[y:y+height, x:x+width]


def error(reference, actual):
    difference = abs(reference.astype(np.float64)-actual.astype(np.float64))
    return {'max_abs': float(difference.max()), 'mean_abs': float(difference.mean()),
            'rms_abs': float(np.sqrt(np.mean(difference*difference)))}


@unittest.skipUnless(cl is not None and all((SOURCE/f).is_file() for f, _ in FILES),
                     'local Capture One kernel artifacts and pyopencl required')
class RecoveredBayerReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.device = next(d for p in cl.get_platforms() for d in p.get_devices()
                              if d.type & cl.device_type.GPU)
        except Exception as exc:
            raise unittest.SkipTest(f'OpenCL GPU unavailable: {exc}')
        cls.context = cl.Context([cls.device])
        cls.queue = cl.CommandQueue(cls.context)
        cls.kernels = []
        cls.sources = []
        for filename, entry in FILES:
            path = SOURCE/filename
            program = cl.Program(cls.context, path.read_text(encoding='utf-8')).build(
                options=['-Dzbc6516e8d5=0', '-Dz3dbd1ff682=6'])
            cls.kernels.append(cl.Kernel(program, entry))
            cls.sources.append({'path': str(path), 'sha256': digest(path.read_bytes()), 'entry': entry})
        cls.records = []

    @classmethod
    def tearDownClass(cls):
        destination = os.environ.get('SPEKTRA_BAYER_REFERENCE_REPORT')
        if destination:
            path = Path(destination).resolve()
            if not path.is_relative_to((ROOT/'output').resolve()):
                raise ValueError('Evidence output must be under project output/')
            path.mkdir(parents=True, exist_ok=True)
            directions = {str(index): 0 for index in range(8)}
            first_directions = {str(index): 0 for index in (1, 2, 3)}
            other_branches = {}
            for case in cls.records:
                for stage in case['stages']:
                    for key, count in stage['branches'].get('direction_counts_at_chroma', {}).items():
                        (first_directions if stage['stage'] == 1 else directions)[key] += count
                    for key, count in stage['branches'].items():
                        if isinstance(count, int):
                            name = f"stage{stage['stage']}_{key}"
                            other_branches[name] = other_branches.get(name, 0)+count
            maximums = {str(stage): max(row['error']['max_abs'] for case in cls.records
                                      for row in case['stages'] if row['stage'] == stage)
                        for stage in (1, 2, 3, 4)}
            report = {'scope': 'readable full four-stage global-memory/no-aux RGGB research reference',
                'production_integration': False, 'synthetic_parameters': True,
                'pyopencl': cl.VERSION_TEXT, 'device': cls.device.name,
                'driver': cls.device.driver_version, 'sources': cls.sources, 'cases': cls.records,
                'summary': {'scenario_count': len(cls.records), 'stage_comparisons': len(cls.records)*4,
                    'stage_max_abs_errors': maximums,
                    'three_stage_cascaded_max_abs_error': max(case['three_stage_cascaded_reference_vs_gpu']['max_abs'] for case in cls.records),
                    'full_four_stage_cascaded_max_abs_error': max(case['cascaded_reference_vs_gpu']['max_abs'] for case in cls.records),
                    'full_four_stage_tight_parity_failures': [case['case']+' '+str(case['initial_green_parameters'])
                        for case in cls.records if not case['full_four_stage_tight_parity']],
                    'stage1_direction_counts': first_directions,
                    'stage2_direction_counts': directions, 'branch_counts': other_branches},
                'limitations': ['No auxiliary direction-map branch', 'No C1 host parameter/default recovery',
                    'No local-memory variant, CA branch, sensor calibration or RAW color rendering',
                    'Tiny ROI numerical comparisons do not establish whole-image speed or perceived image quality']}
            (path/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')

    def oracle(self, image, stage, rect, parameters, initial_parameters=None):
        height, width = image.shape[:2]
        x, y, rw, rh = rect
        source = cl.Buffer(self.context, cl.mem_flags.READ_WRITE | cl.mem_flags.COPY_HOST_PTR, hostbuf=image)
        actual = np.full((height, width, 4), CANARY, np.float32)
        target = cl.Buffer(self.context, cl.mem_flags.READ_WRITE | cl.mem_flags.COPY_HOST_PTR, hostbuf=actual)
        if stage == 0:
            red_gain, blue_gain, regularizer, bias = initial_parameters.values()
            auxiliary = cl.Buffer(self.context, cl.mem_flags.READ_WRITE | cl.mem_flags.COPY_HOST_PTR,
                                  hostbuf=np.full((1, 4), CANARY, np.float32))
            args = (source, target, ct.make_int4(*rect), np.int32(width), np.int32(width*4),
                    ct.make_float2(red_gain, blue_gain), regularizer, bias, auxiliary,
                    ct.make_int4(0, 0, 0, 0))
            size = rw//2, rh
        elif stage == 1:
            args = source, target, ct.make_int4(*rect), np.int32(width*4), np.int32(width*4)
            size = rw//2, rh
        else:
            args = (source, target, ct.make_int8(x, y, rw, rh, x, y, 0, 0),
                    np.int32(width), np.int32(width), ct.make_float4(*parameters.values()))
            size = rw//2, rh//2
        self.kernels[stage](self.queue, size, None, *args).wait()
        cl.enqueue_copy(self.queue, actual, target).wait()
        unchanged = np.empty_like(image)
        cl.enqueue_copy(self.queue, unchanged, source).wait()
        np.testing.assert_array_equal(unchanged, image)
        written = np.zeros((height, width), bool)
        written[y:y+rh, x:x+rw] = True
        self.assertTrue(np.all(actual[~written] == CANARY))
        self.assertTrue(np.isfinite(crop(actual, rect)).all())
        return actual

    def compare_case(self, raw, label, parameters, initial_parameters=None):
        if initial_parameters is None:
            initial_parameters = InitialGreenParameters(1, 1, 1, 0)
        height, width = raw.shape
        regions = [(margin, margin, width-2*margin, height-2*margin) for margin in (12, 16, 20, 24)]
        original = raw.copy()
        current = self.oracle(raw, 0, regions[0], parameters, initial_parameters)
        reference_first, decisions = initial_green(raw, regions[0], initial_parameters)
        first_error = error(reference_first, crop(current, regions[0]))
        first_difference = abs(reference_first.astype(np.float64)-crop(current, regions[0]))
        max_y, max_x, max_channel = np.unravel_index(np.argmax(first_difference), first_difference.shape)
        first_max_location = {'sensor_xy': [int(regions[0][0]+max_x), int(regions[0][1]+max_y)],
            'channel': int(max_channel), 'reference_value': float(reference_first[max_y, max_x, max_channel]),
            'gpu_value': float(crop(current, regions[0])[max_y, max_x, max_channel])}
        np.testing.assert_allclose(reference_first, crop(current, regions[0]), rtol=2e-6, atol=.03)
        np.testing.assert_array_equal(raw, original)
        self.assertTrue(np.isfinite(reference_first).all())
        functions = (refine_green, fill_opposite_chroma, fill_chroma_at_green)
        records = [{'stage': 1, 'region': regions[0], 'error': first_error,
                    'max_error_location': first_max_location,
                    'branches': decisions, 'input_preserved': True,
                    'oracle_guard_preserved': True, 'finite': True}]
        cascade = np.full_like(current, CANARY)
        x, y, rw, rh = regions[0]
        cascade[y:y+rh, x:x+rw] = reference_first
        three_stage_cascade = current.copy()
        full_chain_trace = []
        yy, xx = np.indices(raw.shape)
        channels = np.where((yy & 1) == 0, np.where((xx & 1) == 0, 0, 1), np.where((xx & 1) == 0, 1, 2))
        sampled_first = np.take_along_axis(reference_first[..., :3], crop(channels, regions[0])[..., None], axis=2)[..., 0]
        np.testing.assert_array_equal(sampled_first, crop(raw, regions[0]))
        records[0]['cfa_preserved'] = True
        for stage, function in enumerate(functions, 1):
            rect = regions[stage]
            before = current.copy()
            kwargs = {} if stage == 1 else {'parameters': parameters}
            reference, decisions = function(current, rect, **kwargs)
            actual = self.oracle(current, stage, rect, parameters)
            np.testing.assert_array_equal(current, before)
            measured = error(reference, crop(actual, rect))
            # Both sides output float32 in sensor-amplitude units. Allow a
            # handful of ULP from OpenCL FMA/contraction vs NumPy operations.
            np.testing.assert_allclose(reference, crop(actual, rect), rtol=2e-6, atol=.03)
            sampled = np.take_along_axis(reference[..., :3], crop(channels, rect)[..., None], axis=2)[..., 0]
            np.testing.assert_array_equal(sampled, crop(raw, rect))
            x, y, rw, rh = rect
            if stage == 1:
                cascaded, reference_decisions = function(cascade, rect, diagnostics=True)
                _, oracle_decisions = function(current, rect, diagnostics=True)
                cfa_chroma = crop(channels, rect) != 1
                changed = (reference_decisions['direction_map'] != oracle_decisions['direction_map']) & cfa_chroma
                positions = np.argwhere(changed)
                direction_changes = {'count': int(len(positions)), 'examples': []}
                for py, px in positions[:8]:
                    direction_changes['examples'].append({
                        'sensor_xy': [int(x+px), int(y+py)],
                        'gpu_input_direction': int(oracle_decisions['direction_map'][py, px]),
                        'reference_input_direction': int(reference_decisions['direction_map'][py, px]),
                        'gpu_input_score_margin': float(oracle_decisions['score_margin'][py, px]),
                        'reference_input_score_margin': float(reference_decisions['score_margin'][py, px]),
                        'gpu_input_scores': oracle_decisions['scores'][:, py, px].tolist(),
                        'reference_input_scores': reference_decisions['scores'][:, py, px].tolist()})
            else:
                cascaded, _ = function(cascade, rect, **kwargs)
                direction_changes = None
            three_cascaded, _ = function(three_stage_cascade, rect, **kwargs)
            three_stage_cascade[y:y+rh, x:x+rw] = three_cascaded
            full_chain_trace.append({'after_stage': stage+1,
                'error': error(cascaded, crop(actual, rect)),
                'stage2_direction_changes_from_stage1_rounding': direction_changes})
            cascade[y:y+rh, x:x+rw] = cascaded
            records.append({'stage': stage+1, 'region': rect, 'error': measured,
                            'branches': decisions, 'cfa_preserved': True, 'input_preserved': True,
                            'oracle_guard_preserved': True, 'finite': bool(np.isfinite(reference).all())})
            current = actual
        cascade_error = error(crop(cascade, regions[-1]), crop(current, regions[-1]))
        three_stage_error = error(crop(three_stage_cascade, regions[-1]), crop(current, regions[-1]))
        np.testing.assert_allclose(crop(three_stage_cascade, regions[-1]), crop(current, regions[-1]), rtol=4e-6, atol=.06)
        close = np.isclose(crop(cascade, regions[-1]), crop(current, regions[-1]), rtol=4e-6, atol=.06)
        difference = abs(crop(cascade, regions[-1]).astype(np.float64)-crop(current, regions[-1]))
        failing_examples = []
        violating = np.argwhere(~close)
        if len(violating):
            order = np.argsort(difference[tuple(violating.T)])[::-1]
            violating = violating[order[:8]]
        for py, px, channel in violating:
            failing_examples.append({'sensor_xy': [int(regions[-1][0]+px), int(regions[-1][1]+py)],
                'channel': int(channel), 'reference_value': float(crop(cascade, regions[-1])[py, px, channel]),
                'gpu_value': float(crop(current, regions[-1])[py, px, channel]),
                'abs_error': float(difference[py, px, channel])})
        np.testing.assert_array_equal(raw, original)
        self.records.append({'case': label, 'sensor_shape': list(raw.shape),
            'parameters': parameters.values().tolist(),
            'initial_green_parameters': initial_parameters.values().tolist(), 'stages': records,
            'cascaded_reference_vs_gpu': cascade_error,
            'full_four_stage_tight_parity': bool(close.all()),
            'full_four_stage_tight_parity_mismatched_values': int(np.count_nonzero(~close)),
            'full_four_stage_failing_examples': failing_examples, 'full_four_stage_trace': full_chain_trace,
            'three_stage_cascaded_reference_vs_gpu': three_stage_error,
            'single_stages_and_three_stage_cascade_passed': True})

    def test_synthetic_boundaries_patterns_and_parameters(self):
        height, width = 96, 128
        yy, xx = np.indices((height, width))
        channels = np.where((yy & 1) == 0, np.where((xx & 1) == 0, 0, 1), np.where((xx & 1) == 0, 1, 2))
        patterns = {'black': np.zeros((height, width, 3)),
            'constant': np.broadcast_to([1200, 2400, 800], (height, width, 3)),
            'white_65535': np.full((height, width, 3), 65535),
            'horizontal_edge': np.where((yy[..., None] < 48), [400, 900, 700], [8000, 3500, 1400]),
            'vertical_edge': np.where((xx[..., None] < 64), [400, 900, 700], [8000, 3500, 1400]),
            'diagonal_edge': np.where(((xx+yy)[..., None] < 110), [400, 900, 700], [8000, 3500, 1400]),
            'highlight': np.where((((xx-64)**2+(yy-48)**2)[..., None] < 500),
                                   [65535, 58000, 41000], [700, 900, 500]),
            'independent_random': np.random.default_rng(713).integers(300, 65536, (height, width, 3)),
            'slope': np.stack((1000+xx*9+yy*3, 1800+xx*4+yy*7, 700+xx*3+yy*6), axis=2)}
        for weights in ((1, 1, 1, 1), (.65, 1.2, 16, 2)):
            parameters = ChromaParameters(*weights)
            initial_parameters = (InitialGreenParameters(1, 1, 1, 0) if weights[0] == 1
                                  else InitialGreenParameters(.75, 1.25, 16, 512))
            for label, scene in patterns.items():
                with self.subTest(case=label, weights=weights):
                    raw = np.take_along_axis(np.asarray(scene, np.uint16), channels[..., None], axis=2)[..., 0].copy()
                    self.compare_case(raw, label, parameters, initial_parameters)

    def test_unsupported_initial_variants_are_rejected(self):
        raw = np.zeros((64, 64), np.uint16)
        parameters = InitialGreenParameters(1, 1, 1, 0)
        for options in ({'auxiliary_stride': 1}, {'auxiliary': np.zeros((1, 4))},
                        {'local_memory': True}, {'cfa': 'BGGR'}):
            with self.subTest(options=list(options)):
                with self.assertRaises(NotImplementedError):
                    initial_green(raw, (12, 12, 40, 40), parameters, **options)

    @unittest.expectedFailure
    def test_z_full_four_stage_tight_parity_known_rounding_instability(self):
        # Preserve a visible strict parity failure until first-stage rounding
        # is resolved. Do not increase tolerances to hide discrete downstream
        # direction changes; a future fix becomes unexpectedSuccess here.
        self.assertTrue(self.records, 'No scenarios were measured')
        failures = [(record['case'], record['initial_green_parameters'], record['cascaded_reference_vs_gpu'])
                    for record in self.records if not record['full_four_stage_tight_parity']]
        self.assertFalse(failures, failures)

    def test_actual_a7cr_unpacked_sensor_crop(self):
        source = Path(r'M:\2026\2026-06 #北京\DSC06823.ARW')
        if not source.is_file() or importlib.util.find_spec('rawpy') is None:
            self.skipTest('authorized A7CR fixture unavailable')
        import rawpy
        with source.open('rb') as stream:
            before = hashlib.file_digest(stream, 'sha256').hexdigest()
        with rawpy.imread(str(source)) as raw:
            pattern = raw.raw_pattern.tolist()
            self.assertEqual(pattern, [[0, 1], [3, 2]])
            self.assertEqual(raw.color_desc, b'RGBG')
            sensor = raw.raw_image_visible
            left, top = ((sensor.shape[1]-512)//2) & ~1, ((sensor.shape[0]-512)//2) & ~1
            pixels = sensor[top:top+512, left:left+512].copy()
        self.compare_case(pixels, 'a7cr_sensor_crop_synthetic_weights', ChromaParameters(1, 1, 1, 1))
        with source.open('rb') as stream:
            after = hashlib.file_digest(stream, 'sha256').hexdigest()
        self.assertEqual(before, after)
        self.records[-1]['source'] = {'path': str(source), 'sha256_before': before, 'sha256_after': after,
            'sensor_crop_offset_xy': [left, top], 'raw_pattern': pattern,
            'unpack_only': True, 'black_wb_matrix_transfer_not_applied': True}


if __name__ == '__main__':
    unittest.main()
