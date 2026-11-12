"""Output milestone: independent colour reference, real encoders and batch history."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import io
import tempfile
import unittest
from dataclasses import asdict,replace
from pathlib import Path

import numpy as np
from PIL import Image,ImageCms
from PySide6.QtWidgets import QApplication
import tifffile

from desktop.controller import Controller,PhotoProvider
from desktop.imaging import Settings
from desktop.output import export_recipe
from desktop.raw_source import read_high_precision_raster
from shared.color_management import convert_pixels,icc_profile
from shared.geometry import Geometry
from shared.output_recipes import OutputRecipe,recipe_json


class OutputWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_output_profiles_match_lcms_and_round_trip(self):
        rgb=np.random.default_rng(9).uniform(.1,.8,(19,23,3)).astype(np.float32)
        for space in ('Display P3','ProPhoto RGB','Adobe RGB (1998)'):
            wide=convert_pixels(rgb,target=space)
            np.testing.assert_allclose(convert_pixels(wide,space,'sRGB'),rgb,atol=2e-6)
            encoded=Image.fromarray(np.rint(wide*255).astype(np.uint8))
            result=ImageCms.profileToProfile(encoded,ImageCms.ImageCmsProfile(io.BytesIO(icc_profile(space))),
                ImageCms.createProfile('sRGB'),outputMode='RGB')
            # Compare the same quantised source. ProPhoto8 rounding alone can
            # amplify several sRGB codes near a saturated, dark channel.
            expected=convert_pixels(np.asarray(encoded).astype(np.float32)/255,space,'sRGB')
            self.assertLessEqual(np.abs(np.asarray(result).astype(int)-np.rint(np.clip(expected,0,1)*255)).max(),1)

    def test_real_png16_tiff_wide_and_processed_linear_dng(self):
        values=np.linspace(.01,.9,59*73*3,dtype=np.float32).reshape(59,73,3)
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'source.tif'
            tifffile.imwrite(source,np.rint(values*65535).astype(np.uint16),photometric='rgb')
            settings=replace(Settings(),lens_correction=False,defringe=False)
            png=Path(root)/'out.png'
            export_recipe(str(source),str(png),settings,OutputRecipe(format='png',bit_depth=16))
            self.assertEqual(png.read_bytes()[24],16)
            decoded=read_high_precision_raster(str(png))
            self.assertEqual(decoded.shape,values.shape)
            self.assertGreater(np.unique(decoded[...,0]).size,256)
            self.assertLess(np.max(np.abs(decoded-values)),.001)
            wide=Path(root)/'wide.tif'
            export_recipe(str(source),str(wide),settings,OutputRecipe(format='tiff',bit_depth=16,color_space='ProPhoto RGB'))
            with tifffile.TiffFile(wide) as handle:
                self.assertIn(b'ProPhoto',handle.pages[0].tags[34675].value.replace(b'\0',b''))
            dng=Path(root)/'linear.dng'
            export_recipe(str(source),str(dng),settings,OutputRecipe(format='dng',bit_depth=16))
            with tifffile.TiffFile(dng) as handle:
                page=handle.pages[0]
                self.assertEqual(page.photometric,34892)
                self.assertEqual(page.tags[50706].value,b'\x01\x04\x00\x00')
                self.assertEqual(page.asarray().shape,values.shape)
            import rawpy
            with rawpy.imread(str(dng)) as raw:
                actual=raw.postprocess(output_bps=16,use_camera_wb=True,no_auto_bright=True)
                self.assertEqual(actual.shape,values.shape)

    def test_category_sync_preserves_composition_and_per_photo_undo(self):
        with tempfile.TemporaryDirectory() as root:
            ctrl=Controller(PhotoProvider(),root)
            try:
                first=replace(Settings(),exposure=.6,temperature=4900)
                second=replace(Settings(),geometry=Geometry(crop=(.1,.2,.8,.9)))
                ctrl._photo_model.append([dict(path=str(Path(root)/f'{i}.jpg'),name=str(i),width=73,height=59,
                    dimensions='',settings=asdict(s)) for i,s in enumerate((first,second))])
                ctrl._current=0;ctrl._selected={0,1};ctrl._settings=first
                ctrl._changed=lambda:ctrl.stateChanged.emit()
                ctrl.copySettings(['exposure','WB']);ctrl.pasteSettings(['exposure','WB'])
                self.assertEqual(ctrl._photos[1]['settings']['temperature'],4900)
                self.assertEqual(ctrl._photos[1]['settings']['geometry']['crop'],(.1,.2,.8,.9))
                ctrl._current=1;ctrl._settings=Settings.from_mapping(ctrl._photos[1]['settings'])
                ctrl.undo();self.assertEqual(ctrl._settings,second)
                recipe=OutputRecipe(id='mine',name='我的配方',format='png',bit_depth=16)
                ctrl.saveOutputRecipe(recipe_json(recipe))
                self.assertEqual(ctrl.outputRecipes[-1]['id'],'mine')
                self.assertTrue((Path(root)/'output-recipes.json').is_file())
            finally:ctrl.close()


if __name__=='__main__':unittest.main()
