"""Verify isolated chroma interpolation, not all native stage3 Run branches."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

import numpy as np

from native.reference.c1_bayer_reference import fill_opposite_chroma_cpu, fill_chroma_at_green_cpu

ROOT=Path(__file__).resolve().parents[1]
PROBE=ROOT/'output/captureone-bayer-stage3/probe_chroma_workers.py'
DLL=Path(r'C:\Program Files\Capture One\Capture One\ImgCoreDll.dll')
SHA256='ca02b6ac2786e9a100f63221df7340e5df210416eb0bd53a4bb1bfc2306a44a4'


class CpuStage3Tests(unittest.TestCase):
    def test_chroma_workers_preserve_measured_green_and_existing_color(self):
        image=np.full((32,32,3),-2048,np.float32)
        image[...,1]=2000
        image[::2,::2,0]=1000
        image[1::2,1::2,2]=3000
        original=image.copy()
        diagonal,_=fill_opposite_chroma_cpu(image,(6,6,20,20),regularizer=640)
        full=image.copy();full[6:26,6:26]=diagonal
        final,_=fill_chroma_at_green_cpu(full,(8,8,16,16),regularizer=640)
        np.testing.assert_array_equal(final[...,1],image[8:24,8:24,1])
        np.testing.assert_array_equal(final[::2,::2,0],1000)
        np.testing.assert_array_equal(final[1::2,1::2,2],3000)
        np.testing.assert_array_equal(image,original)
        self.assertTrue(np.isfinite(final).all())

    @unittest.skipUnless(os.name=='nt' and DLL.is_file() and PROBE.is_file(),
        'inspected local DLL and isolated scalar oracle required')
    def test_two_original_scalar_workers_exactly_match_independent_math(self):
        if hashlib.sha256(DLL.read_bytes()).hexdigest()!=SHA256:
            self.skipTest('DLL differs from inspected build')
        result=subprocess.run([sys.executable,str(PROBE)],cwd=ROOT,
            text=True,capture_output=True,timeout=45)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        report=json.loads((PROBE.parent/'chroma-worker-comparison.json').read_text('utf-8'))
        self.assertEqual(len(report['cases']),15)
        for case in report['cases']:
            with self.subTest(case=case['case'],epsilon=case['epsilon']):
                self.assertEqual(case['diagonal']['max_abs'],0)
                self.assertEqual(case['green']['max_abs'],0)
