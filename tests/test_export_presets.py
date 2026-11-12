import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image, JpegImagePlugin
from desktop.imaging import Settings, export_preset


class ExportPresetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.source=self.root/'input.png'
        self.pixels=np.random.default_rng(22).integers(0,256,(101,2301,3),dtype=np.uint8)
        Image.fromarray(self.pixels).save(self.source)
        self.settings=Settings(strength=0,lens_correction=False,defringe=False)

    def tearDown(self): self.temp.cleanup()

    def test_high_quality_jpeg_is_full_size_444_and_quality_100(self):
        target=self.root/'high.jpg'
        export_preset(str(self.source),str(target),self.settings,'JPG_HIGH')
        with Image.open(target) as image:
            image.load()
            self.assertEqual(image.size,(2301,101))
            self.assertEqual(JpegImagePlugin.get_sampling(image),0)
            self.assertTrue(all(v==1 for table in image.quantization.values() for v in table))
            self.assertTrue(image.info.get('icc_profile'))

    def test_share_jpeg_preserves_dimensions_and_uses_share_quality(self):
        high=self.root/'high.jpg';share=self.root/'share.jpg'
        export_preset(str(self.source),str(high),self.settings,'JPG_HIGH')
        export_preset(str(self.source),str(share),self.settings,'JPG_SHARE')
        with Image.open(share) as image:
            self.assertEqual(image.size,(2301,101))
            self.assertTrue(any(v>1 for table in image.quantization.values() for v in table))
            self.assertTrue(image.info.get('icc_profile'))
        self.assertLess(share.stat().st_size,high.stat().st_size)
        small=self.root/'small.png';Image.new('RGB',(90,60)).save(small)
        export_preset(str(small),str(self.root/'small.jpg'),self.settings,'JPG_SHARE')
        with Image.open(self.root/'small.jpg') as image:self.assertEqual(image.size,(90,60))

    def test_tiff_preserves_pixels_and_srgb(self):
        target=self.root/'lossless.tif'
        export_preset(str(self.source),str(target),self.settings,'TIFF')
        with Image.open(target) as image:
            np.testing.assert_array_equal(np.asarray(image),self.pixels)
            self.assertIn(image.tag_v2[259],(8,32946))
            self.assertTrue(image.info.get('icc_profile'))
        import tifffile
        with tifffile.TiffFile(target) as file:
            self.assertEqual(file.pages[0].bitspersample,16)
            np.testing.assert_array_equal(file.asarray(),self.pixels.astype(np.uint16)*257)

    def test_raw_is_byte_exact_without_render_or_decode(self):
        source=self.root/'camera.CR3';source.write_bytes(bytes(range(256))*4097)
        target=self.root/'backup.CR3'
        with patch('desktop.imaging.render',side_effect=AssertionError('RAW must not render')),patch('desktop.imaging.read_photo',side_effect=AssertionError('RAW must not decode')):
            export_preset(str(source),str(target),Settings(exposure=3),'RAW')
        self.assertEqual(target.read_bytes(),source.read_bytes())
        with self.assertRaises(FileExistsError):export_preset(str(source),str(source),self.settings,'RAW')

    def test_raw_rejects_conversion_and_changed_extension(self):
        with self.assertRaises(ValueError):export_preset(str(self.source),str(self.root/'fake.dng'),self.settings,'RAW')
        source=self.root/'camera.nef';source.write_bytes(b'raw data')
        with self.assertRaises(ValueError):export_preset(str(source),str(self.root/'fake.dng'),self.settings,'RAW')
        self.assertFalse((self.root/'fake.dng').exists())

    def test_failed_raw_copy_leaves_no_partial_file(self):
        source=self.root/'camera.dng';source.write_bytes(b'raw data')
        target=self.root/'backup.dng'
        with patch('desktop.imaging.shutil.copyfileobj',side_effect=OSError('copy failed')):
            with self.assertRaises(OSError):export_preset(str(source),str(target),self.settings,'RAW')
        self.assertFalse(target.exists())
        self.assertEqual(list(self.root.glob('.spektrafilm-*')),[])

    def test_preset_cannot_silently_change_format(self):
        for preset,suffix in [('JPG_HIGH','tif'),('JPG_SHARE','png'),('TIFF','jpg'),('unknown','jpg')]:
            with self.assertRaises(ValueError):export_preset(str(self.source),str(self.root/('invalid.'+suffix)),self.settings,preset)


if __name__=='__main__':unittest.main()
