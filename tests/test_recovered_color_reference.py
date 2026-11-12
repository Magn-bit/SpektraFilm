"""Actual intermediate-value replay and standalone pre-ICC domain invariants."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

from native.reference.c1_color_reference import DefaultPreICC, normalize_demosaic, pre_icc_transfer

ROOT=Path(__file__).resolve().parents[1]
PROBE=ROOT/'output/captureone-color-runtime/verify_recovered_color.py'


class ColorReferenceTests(unittest.TestCase):
    def test_linear_primary_curve_still_has_transfer(self):
        pipeline=DefaultPreICC([(0,0),(1,1)])
        self.assertEqual(pipeline(0),0)
        self.assertAlmostEqual(pipeline(65535),1,places=6)
        self.assertGreater(pipeline(65535*.25),.45)
        self.assertGreater(pre_icc_transfer(4),1)
        self.assertEqual(pre_icc_transfer(-1),0)

    def test_rejects_unverified_transfer_and_nonfinite_values(self):
        with self.assertRaises(NotImplementedError):
            pre_icc_transfer(.5,toe_sqrt=False)
        for value in (float('nan'),float('inf'),float('-inf')):
            for function in (normalize_demosaic,pre_icc_transfer):
                with self.subTest(function=function.__name__,value=value):
                    with self.assertRaises(ValueError):function(value)

    @unittest.skipUnless(PROBE.is_file() and
        (PROBE.parent/'runs/pro-auto/raw-render.tiff').is_file() and
        Path(r'C:\Program Files\Capture One\Capture One\Film Curves\SonyA7CR-Auto.fcrv').is_file(),
        'local original stage observations/curve resources required')
    def test_actual_neutral_pre_icc_intermediate_values(self):
        result=subprocess.run([sys.executable,str(PROBE)],cwd=ROOT,
            text=True,capture_output=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        report=json.loads((PROBE.parent/'independent-color-validation.json').read_text('utf-8'))
        self.assertTrue(report['passed'])
        self.assertEqual(sum(t['samples'] for t in report['numeric_tests']),288)
        for case in report['numeric_tests']:
            with self.subTest(stage=case['name']):
                self.assertTrue(case['passed'])
                self.assertLessEqual(case['max_abs_error'],1.2e-7)
