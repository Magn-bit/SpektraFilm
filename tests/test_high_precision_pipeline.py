"""Precision and source-size checks at the actual decoder/encoder boundaries."""
import hashlib
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image, ImageCms
import rawpy
import tifffile

from desktop.imaging import Settings, read_photo, render_pixels, export_photo, SRGB
from desktop.raw_source import source_pixels, convert_icc_pixels, display_image
from test_raw_brightness import _synthetic_dng


class HighPrecisionPipelineTests(unittest.TestCase):
    def test_real_cfa_raw_keeps_low_bits_through_full_tiff_export(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source.dng';target=Path(directory)/'result.tif'
            _synthetic_dng(source,orientation=6)
            before=hashlib.sha256(source.read_bytes()).digest()
            with rawpy.imread(str(source)) as raw:
                expected=raw.postprocess(use_camera_wb=True,output_color=rawpy.ColorSpace.sRGB,
                    gamma=(2.4,12.92),highlight_mode=rawpy.HighlightMode.Blend,
                    demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,no_auto_bright=False,
                    auto_bright_thr=.01,output_bps=16,half_size=False)
            with read_photo(str(source)) as image:
                np.testing.assert_array_equal(source_pixels(image),expected)
                self.assertEqual(image.size,(64,96))
                self.assertEqual(source_pixels(image).dtype,np.uint16)
                self.assertTrue(np.any(expected%257))
                processed=render_pixels(image,Settings(strength=0))
                np.testing.assert_allclose(processed,expected.astype(np.float32)/65535,atol=0,rtol=0)
            self.assertEqual(export_photo(str(source),str(target),Settings(strength=0)),(64,96))
            with tifffile.TiffFile(target) as file:
                page=file.pages[0]
                self.assertEqual(page.bitspersample,16)
                self.assertEqual(bytes(page.tags[34675].value),SRGB)
                np.testing.assert_array_equal(page.asarray(),expected)
            self.assertEqual(hashlib.sha256(source.read_bytes()).digest(),before)

    def test_rgb16_gradient_survives_load_copy_resize_and_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'gradient.tif';target=Path(directory)/'output.tif'
            x=np.arange(1024,dtype=np.uint16)*61
            # Three strips with a partial last strip exercises the iterator
            # contract; a tiny single-strip image cannot detect frame/strip
            # confusion in the TIFF encoder.
            values=np.tile(x[None,:,None],(263,1,3));values[...,1]+=17;values[...,2]+=31
            tifffile.imwrite(source,values,photometric='rgb',metadata=None,iccprofile=SRGB)
            with read_photo(str(source)) as image:
                precise=source_pixels(image)
                self.assertGreater(np.unique(precise[...,0]).size,256)
                clone=image.copy();clone.thumbnail((513,513))
                self.assertEqual(source_pixels(clone).shape,(132,513,3))
            export_photo(str(source),str(target),Settings(strength=0))
            output=tifffile.imread(target)
            self.assertEqual(output.dtype,np.uint16)
            self.assertEqual(output.shape,values.shape)
            self.assertLessEqual(int(np.abs(output.astype(np.int32)-values.astype(np.int32)).max()),2)
            self.assertGreater(np.unique(output[...,0]).size,256)

    def test_matrix_icc_identity_is_float_and_preserves_more_than_eight_bits(self):
        values=np.linspace(0,1,4096,dtype=np.float32).reshape(1,-1,1).repeat(3,axis=2)
        result=convert_icc_pixels(values,SRGB)
        self.assertEqual(result.dtype,np.float32)
        np.testing.assert_allclose(result,values,atol=2e-6,rtol=0)
        self.assertGreater(np.unique(result).size,256)

    def test_repeated_adjustments_do_not_mutate_float_source(self):
        values=np.linspace(0,1,48*64*3,dtype=np.float32).reshape(48,64,3)
        original=values.copy()
        image=display_image(values)
        settings=Settings(film_enabled=False,contrast=18,vignette=24)
        first=render_pixels(image,settings)
        second=render_pixels(image,settings)
        np.testing.assert_array_equal(source_pixels(image),original)
        np.testing.assert_array_equal(first,second)
        self.assertFalse(np.array_equal(first,original))


if __name__=='__main__':
    unittest.main()
