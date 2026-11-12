"""CPU refinement independently compared to bounded original scalar/Run data."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

import numpy as np

from native.reference.c1_bayer_reference import refine_green_cpu

ROOT=Path(__file__).resolve().parents[1]
PROBE=ROOT/'output/captureone-bayer-cpu-stage2/probe_refine.py'
DLL=Path(r'C:\Program Files\Capture One\Capture One\ImgCoreDll.dll')
SHA256='ca02b6ac2786e9a100f63221df7340e5df210416eb0bd53a4bb1bfc2306a44a4'


class CpuStage2Tests(unittest.TestCase):
    def test_retains_negative_missing_components_and_sensor_samples(self):
        image=np.full((24,24,3),-2048,np.float32)
        image[...,1]=33
        image[::2,::2,0]=103
        image[1::2,1::2,2]=57
        original=image.copy()
        result,_=refine_green_cpu(image,(6,6,12,12))
        np.testing.assert_array_equal(result,image[6:18,6:18])
        np.testing.assert_array_equal(image,original)

    def test_rejects_unreconstructed_auxiliary_path(self):
        with self.assertRaises(NotImplementedError):
            refine_green_cpu(np.zeros((24,24,3),np.float32),(6,6,12,12),auxiliary=np.zeros((1,1)))

    @unittest.skipUnless(os.name=='nt' and DLL.is_file() and PROBE.is_file(),
        'inspected local DLL and bounded research oracle required')
    def test_native_scalar_and_two_normal_cpu_tiles_exactly_match(self):
        if hashlib.sha256(DLL.read_bytes()).hexdigest()!=SHA256:
            self.skipTest('DLL differs from inspected build')
        result=subprocess.run([sys.executable,str(PROBE)],cwd=ROOT,
            text=True,capture_output=True,timeout=45)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        report=json.loads((PROBE.parent/'cpu-refine-comparison.json').read_text('utf-8'))
        self.assertTrue(report['passed'])
        directions=set()
        real=0
        for case in report['cases']:
            self.assertEqual(case['independent_vs_scalar']['max_abs'],0)
            self.assertTrue(case['input_preserved'])
            directions.update(case['decisions']['direction_counts_at_chroma'])
            if 'reference_vs_normal_run' in case:
                real+=1
                self.assertEqual(case['reference_vs_normal_run']['max_abs'],0)
        self.assertEqual(directions,set(map(str,range(8))))
        self.assertEqual(real,2)
