from dataclasses import asdict, replace
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from shared.style_luts import apply_lut, lut_for_id, manifest, LUT_ROOT
from shared.style_presets import catalog, apply_style, normalize_style
from desktop.imaging import Settings, render

ROOT=Path(__file__).resolve().parents[1]


class AuthorLutTests(unittest.TestCase):
    def test_identity_corners_clamps_and_nonseparable_interpolation(self):
        b,g,r=np.meshgrid(np.arange(2),np.arange(2),np.arange(2),indexing='ij')
        cube=(np.stack((r,g,b),axis=-1)*255).astype(np.uint8)
        pixels=np.random.default_rng(312).uniform(-.1,1.1,(13,31,3)).astype(np.float32)
        np.testing.assert_allclose(apply_lut(pixels.copy(),cube),np.clip(pixels,0,1),atol=2e-7)
        # Trilinear interpolation exactly reproduces this cross-channel polynomial.
        cube[...,0]=r*g*255;cube[...,1]=g*b*255;cube[...,2]=b*r*255
        src=np.clip(pixels,0,1)
        expected=np.stack((src[...,0]*src[...,1],src[...,1]*src[...,2],src[...,2]*src[...,0]),axis=-1)
        np.testing.assert_allclose(apply_lut(src.copy(),cube),expected,atol=2e-7)
        np.testing.assert_array_equal(apply_lut(src.copy(),cube,7),apply_lut(src.copy(),cube,30000))

    def test_original_hald_samples_axes_hashes_and_license_are_preserved(self):
        index=json.loads((LUT_ROOT.parent/'source-manifest.json').read_text(encoding='utf-8'))
        for license in index['licenses']:
            self.assertEqual(hashlib.sha256((LUT_ROOT/license['file']).read_bytes()).hexdigest(),license['sha256'])
        self.assertTrue(all(e['settings']['look_lut']=='' for e in catalog()))
        self.assertEqual(len(manifest()['luts']),0)
        for entry in manifest()['luts']:
            cube=lut_for_id(entry['id']);size=entry['size'];self.assertEqual(cube.shape,(size,size,size,3))
            self.assertEqual(cube.dtype,np.uint8);self.assertFalse(cube.flags.writeable)
            self.assertEqual(hashlib.sha256(cube).hexdigest(),entry['sha256'])
            # Fixed decoded-source hash is preserved; optionally inspect the original PNG.
            original=ROOT/'output/preset-research/creative-source'/entry['source_file']
            if original.is_file():
                with Image.open(original) as image:
                    np.testing.assert_array_equal(cube.reshape(-1,3),np.asarray(image).reshape(-1,3))
            ri,gi,bi=[int((size-1)*v) for v in (.13,.49,.85)]
            sample=np.array([[[ri/(size-1),gi/(size-1),bi/(size-1)]]],dtype=np.float32)
            np.testing.assert_allclose(apply_lut(sample,cube)[0,0],cube[bi,gi,ri]/255,atol=2e-6)
        with self.assertRaises(ValueError):lut_for_id('../bad')
        with self.assertRaises(ValueError):normalize_style(dict(settings=dict(look_lut='C:/x.rgb8')))

    def test_mix_strength_zero_and_partial_preserve_dimensions(self):
        cube=np.zeros((2,2,2,3),np.uint8);cube[...,0]=255
        pixels=np.random.default_rng(41).random((13,31,3),dtype=np.float32)
        np.testing.assert_array_equal(apply_lut(pixels.copy(),cube,strength=0),pixels)
        full=apply_lut(pixels.copy(),cube)
        half=apply_lut(pixels.copy(),cube,strength=.5)
        np.testing.assert_allclose(half,(pixels+full)/2,atol=6e-8)

    def test_android_paths_and_both_render_modes_match_windows(self):
        import tempfile
        import json
        directory=str(ROOT/'android/app/src/main/python');sys.path.insert(0,directory)
        self.addCleanup(lambda:sys.path.remove(directory))
        spec=importlib.util.spec_from_file_location('author_lut_android',Path(directory)/'studio_spectral.py')
        bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
        source=np.random.default_rng(51).integers(15,235,(19,29,3),dtype=np.uint8)
        argb=((source[:,:,0].astype(np.uint32)<<16)|(source[:,:,1].astype(np.uint32)<<8)|source[:,:,2]|0xff000000).astype('<u4')
        b,g,r=np.meshgrid(np.arange(2),np.arange(2),np.arange(2),indexing='ij')
        cube=np.stack((g*255,b*255,r*255),axis=-1).astype(np.uint8)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'test.rgb8';path.write_bytes(cube.tobytes())
            payload=json.dumps(dict(look_lut_path=str(path),look_strength=50))
            settings=Settings(film_enabled=False,look_lut='test',look_strength=50)
            with patch('desktop.imaging.lut_for_id',return_value=cube):
                expected=np.asarray(render(Image.fromarray(source),settings)).astype(np.int32)
            for run in (
                lambda:bridge.render_argb(argb.tobytes(),29,19,'kodak_portra_400',0,0,0,1,film_enabled=False,color_json=payload),
                lambda:bridge.render_lut_argb(argb.tobytes(),29,19,b'',2,0,0,0,1,film_enabled=False,color_json=payload)):
                packed=np.frombuffer(run(),dtype='<u4').reshape(19,29)
                actual=np.stack([((packed>>shift)&255) for shift in (16,8,0)],axis=-1).astype(np.int32)
                self.assertLessEqual(int(np.abs(actual-expected).max()),1)


if __name__=='__main__':unittest.main()
