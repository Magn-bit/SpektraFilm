import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image

from shared.geometry import (Geometry, normalize_geometry, geometry_matrix, matrix_json,
                             apply_geometry_image, apply_geometry_pixels, output_size, normalized_matrices)
from desktop.imaging import Settings, export_photo


class GeometryTests(unittest.TestCase):
    def test_quarter_turn_transposes_exact_pixels_and_preserves_source_mask_coordinates(self):
        # Asymmetric rectangular fixture catches mirrored rotation, hidden zoom,
        # interpolation and crop/source-coordinate confusion in a single check.
        pixels=np.arange(9*13*3,dtype=np.uint16).reshape(9,13,3)%256
        image=Image.fromarray(pixels.astype(np.uint8))
        source_point=np.array([.23,.71,1.])
        mask_point=source_point.copy()
        for turns in range(4):
            expected=np.rot90(pixels,-turns)
            height,width=expected.shape[:2]
            for crop in ((0.,0.,1.,1.),(2/width,1/height,(width-1)/width,(height-2)/height)):
                g=Geometry(quarter_turns=turns,crop=crop)
                left,top,right,bottom=round(crop[0]*width),round(crop[1]*height),round(crop[2]*width),round(crop[3]*height)
                selected=expected[top:bottom,left:right]
                self.assertEqual(output_size(13,9,g),(right-left,bottom-top))
                np.testing.assert_array_equal(apply_geometry_pixels(pixels,g),selected)
                np.testing.assert_array_equal(np.asarray(apply_geometry_image(image,g)),selected.astype(np.uint8))
                forward,inverse=(np.asarray(m).reshape(3,3) for m in normalized_matrices(13,9,g))
                mapped=forward@source_point;mapped/=mapped[2]
                u,v=source_point[:2]
                oriented=((u,v),(1-v,u),(1-u,1-v),(v,1-u))[turns]
                np.testing.assert_allclose(mapped[:2],[(oriented[0]*width-left)/(right-left),
                                                      (oriented[1]*height-top)/(bottom-top)],atol=1e-12)
                restored=inverse@mapped;restored/=restored[2]
                np.testing.assert_allclose(restored,source_point,atol=1e-12)
                np.testing.assert_array_equal(source_point,mask_point)
        self.assertEqual(normalize_geometry({'quarter_turns':-1}).quarter_turns,3)
        self.assertEqual(normalize_geometry({'quarter_turns':1.5}).quarter_turns,0)

    def test_identity_is_exact_and_does_not_copy_pixels(self):
        image=Image.new('RGB',(181,123),(120,83,56))
        self.assertIs(apply_geometry_image(image,Geometry()),image)
        np.testing.assert_array_equal(geometry_matrix(181,123),np.eye(3))
        self.assertEqual(normalize_geometry({'rotation':float('nan'),'scale':50}).scale,100)

    def test_auto_crop_inverse_corners_stay_inside_original(self):
        for width,height in ((1280,1920),(4000,6000),(301,201)):
            for geometry in (Geometry(rotation=17),Geometry(vertical=80,horizontal=-70),
                             Geometry(rotation=-32,aspect=60,vertical=-100,horizontal=100,flip_horizontal=True)):
                forward=geometry_matrix(width,height,geometry)
                points=np.array([[0,0,1],[width-1,0,1],[0,height-1,1],[width-1,height-1,1]],dtype=float).T
                source=np.linalg.inv(forward)@points;source/=source[2:]
                self.assertGreaterEqual(float(source[:2].min()),-1e-5)
                self.assertLessEqual(float(source[0].max()),width-1+1e-5)
                self.assertLessEqual(float(source[1].max()),height-1+1e-5)

    def test_horizontal_flip_reverses_without_resolution_loss(self):
        pixels=np.random.default_rng(7).integers(0,256,(39,57,3),dtype=np.uint8)
        image=Image.fromarray(pixels)
        corrected=apply_geometry_image(image,Geometry(flip_horizontal=True))
        np.testing.assert_array_equal(np.asarray(corrected),pixels[:,::-1])
        np.testing.assert_array_equal(np.asarray(image),pixels)

    def test_canvas_edge_matrix_and_pixel_center_matrix_agree(self):
        g=Geometry(rotation=8,vertical=-45,aspect=10)
        center=geometry_matrix(1280,1920,g)
        edge=np.array(json.loads(matrix_json(1280,1920,json.dumps(g.__dict__)))).reshape(3,3)
        points=np.array([[250.,600.,1.],[900.,1700.,1.]]).T
        expected=center@points;expected/=expected[2:]
        shifted=points.copy();shifted[:2]+=.5
        actual=edge@shifted;actual/=actual[2:];actual[:2]-=.5
        np.testing.assert_allclose(actual,expected,atol=1e-10)

    def test_export_ignores_legacy_flip_but_keeps_explicit_crop_pixels(self):
        pixels=np.random.default_rng(11).integers(20,220,(93,137,3),dtype=np.uint8)
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'original.png';target=Path(folder)/'corrected.tif'
            Image.fromarray(pixels).save(source)
            original_bytes=source.read_bytes()
            settings=Settings(strength=0,film_enabled=False,lens_correction=False,defringe=False,
                              geometry=Geometry(flip_horizontal=True,crop=(.1,.2,.7,.8)))
            self.assertEqual(export_photo(str(source),str(target),settings),(82,55))
            with Image.open(target) as output:
                np.testing.assert_array_equal(np.asarray(output),pixels[19:74,14:96])
            self.assertEqual(source.read_bytes(),original_bytes)

    def test_explicit_crop_keeps_exact_selected_pixels_without_upscaling(self):
        from shared.geometry import crop_box,output_size
        pixels=np.random.default_rng(23).integers(0,256,(100,200,3),dtype=np.uint8)
        image=Image.fromarray(pixels);g=Geometry(crop=(.1,.2,.7,.8))
        self.assertEqual(crop_box(200,100,g),(20,20,140,80))
        self.assertEqual(output_size(200,100,g),(120,60))
        result=apply_geometry_image(image,g)
        np.testing.assert_array_equal(np.asarray(result),pixels[20:80,20:140])
        fwd=np.array(json.loads(matrix_json(200,100,json.dumps(g.__dict__)))).reshape(3,3)
        np.testing.assert_allclose(fwd@np.array([20.5,20.5,1.]),[.5,.5,1.],atol=1e-12)


if __name__=='__main__':unittest.main()
