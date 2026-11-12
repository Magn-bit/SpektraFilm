"""Research-only native CPU oracle comparison; no production DLL dependency."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from native.reference.c1_bayer_reference import (
    InitialGreenParameters, initial_green, initial_green_cpu)

PROBE = ROOT/'output/captureone-bayer-cpu-reference/probe_cpu_reference.py'
DLL = Path(r'C:\Program Files\Capture One\Capture One\ImgCoreDll.dll')
SHA256 = 'ca02b6ac2786e9a100f63221df7340e5df210416eb0bd53a4bb1bfc2306a44a4'
REPORT = PROBE.parent/'report.json'


class RecoveredBayerCpuReferenceTests(unittest.TestCase):
    def test_cpu_and_gpu_are_explicit_separate_contracts(self):
        raw = np.random.default_rng(29).integers(0, 65536, (64, 64), dtype=np.uint16)
        parameters = InitialGreenParameters(2.512, 1.676, 166.69566, 2048)
        gpu, _ = initial_green(raw, (12, 12, 40, 40), parameters)
        cpu, metadata = initial_green_cpu(raw, (12, 12, 40, 40), parameters, diagnostics=True)
        self.assertGreater(float(np.max(abs(gpu-cpu))), 1)
        self.assertEqual(metadata['chroma_direction_map'].shape, (40, 20))
        self.assertEqual(metadata['chroma_forced_green'].shape, (40, 20, 3))
        self.assertTrue(np.isfinite(cpu).all())
        yy, xx = np.indices((40, 40))
        channels = np.where(yy % 2 == 0, np.where(xx % 2 == 0, 0, 1), np.where(xx % 2 == 0, 1, 2))
        samples = np.take_along_axis(cpu[..., :3], channels[..., None], axis=2)[..., 0]
        np.testing.assert_array_equal(samples, raw[12:52, 12:52])

    def test_cpu_rejects_unrecovered_variants(self):
        raw = np.zeros((64, 64), np.uint16)
        params = InitialGreenParameters(1, 1, 1, 0)
        for options in ({'auxiliary_stride': 1}, {'auxiliary': np.zeros((1, 4))},
                        {'local_memory': True}, {'cfa': 'BGGR'}):
            with self.subTest(options=list(options)):
                with self.assertRaises(NotImplementedError):
                    initial_green_cpu(raw, (12, 12, 40, 40), params, **options)

    @unittest.skipUnless(os.name == 'nt' and DLL.is_file() and PROBE.is_file(),
                         'local inspected Capture One DLL and isolated research oracle required')
    def test_isolated_native_scalar_oracle_exact_parity(self):
        if hashlib.sha256(DLL.read_bytes()).hexdigest() != SHA256:
            self.skipTest('local DLL differs from inspected build; worker RVAs cannot be reused')
        completed = subprocess.run([sys.executable, str(PROBE)], cwd=ROOT,
            text=True, capture_output=True, timeout=60, check=False)
        self.assertEqual(completed.returncode, 0, completed.stdout+completed.stderr)
        report = json.loads(REPORT.read_text(encoding='utf8'))
        self.assertEqual(report['module_sha256'], SHA256)
        self.assertGreaterEqual(report['summary']['scenario_count'], 27)
        self.assertEqual(report['summary']['strict_failures'], [])
        self.assertEqual(report['summary']['max_abs'], 0)
        self.assertEqual(report['summary']['forced_max_abs'], 0)
        self.assertEqual(report['summary']['direction_mismatches'], 0)
        covered = set()
        for case in report['cases']:
            with self.subTest(case=case['case'], params=case['parameters']):
                self.assertTrue(case['strict_pass'])
                self.assertTrue(case['input_preserved'])
                self.assertTrue(case['original_cfa_preserved'])
                self.assertTrue(case['finite'])
                self.assertEqual(case['native_vs_reference']['max_abs'], 0)
                self.assertEqual(case['forced_interpolation_vs_reference']['max_abs'], 0)
                self.assertEqual(case['direction_mismatch_count'], 0)
                covered.update(case['branches']['direction_counts_at_chroma'])
                if 'native_vs_captured_cpu' in case:
                    self.assertEqual(case['native_vs_captured_cpu']['max_abs'], 0)
                    self.assertEqual(case['reference_vs_captured_cpu']['max_abs'], 0)
        self.assertEqual(covered, {'1', '2', '3'})


if __name__ == '__main__':
    unittest.main()
