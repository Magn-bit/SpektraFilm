"""Integration milestone for restored editing, migration and source fidelity."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from dataclasses import asdict,replace
from pathlib import Path
import json
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image
from PySide6.QtWidgets import QApplication
import tifffile

from desktop.controller import Controller,PhotoProvider
from desktop.imaging import Settings,film_settings,settings_from_record,render_pixels,export_photo
from desktop.raw_source import display_image,source_pixels
from shared.geometry import Geometry,apply_geometry_pixels,normalized_matrices


class FullEditorWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_migration_preserves_film_scope_without_resurrecting_hidden_edits(self):
        record={'version':3,'settings':{'exposure':.7,'temperature':3200,'contrast':75,
            'masks':[{'kind':'radial','exposure':2}], 'geometry':{'rotation':12,'crop':[.1,.2,.8,.9]}}}
        migrated=settings_from_record(record)
        self.assertTrue(migrated.film_enabled)
        self.assertEqual((migrated.temperature,migrated.contrast,migrated.masks),(6500,0,()))
        self.assertEqual(migrated.geometry.rotation,0)
        self.assertEqual(migrated.geometry.crop,(.1,.2,.8,.9))
        settings=replace(Settings(),temperature=4100,texture=17,film_enabled=False)
        self.assertEqual(settings_from_record({'version':4,'settings':asdict(settings)}),settings)
        self.assertIs(film_settings(settings),settings)

    def test_real_state_history_round_trip_for_optional_film_and_masks(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'source.png';Image.new('RGB',(61,43),(146,121,96)).save(path)
            ctrl=Controller(PhotoProvider(),root)
            try:
                ctrl._photos.append(dict(path=str(path),name=path.name,width=61,height=43,
                    dimensions='61 × 43',settings=asdict(Settings())))
                ctrl._current=0
                ctrl._changed=lambda:ctrl.stateChanged.emit()
                self.assertFalse(ctrl.settings['film_enabled'])
                ctrl.beginEdit();ctrl.updateParameter('temperature',5100);ctrl.updateParameter('temperature',4900);ctrl.endEdit()
                self.assertEqual(len(ctrl._history[0]),1)
                ctrl.undo();self.assertEqual(ctrl.settings['temperature'],6500)
                ctrl.redo();self.assertEqual(ctrl.settings['temperature'],4900)
                ctrl.addMaskOfKind('radial');ctrl.updateMaskParameter('exposure',.4)
                self.assertTrue(ctrl.hasMasks)
                ctrl.updateGeometry('rotation',5)
                ctrl.applyCrop([.1,.15,.9,.95])
                self.assertEqual(ctrl.settings['geometry']['rotation'],5)
                ctrl.setFilmEnabled(True);self.assertTrue(ctrl.settings['film_enabled'])
                ctrl.updateParameter('halation_scatter_amount',.2)
                ctrl.resetParameter('halation_scatter_amount')
                self.assertIsNone(ctrl.settings['halation_scatter_amount'])
                saved=json.loads(ctrl._edit_path(str(path)).read_text(encoding='utf-8'))
                self.assertEqual(saved['version'],4)
                self.assertEqual(settings_from_record(saved),ctrl._settings)
            finally:ctrl.close()

    def test_float_source_survives_edits_crop_and_tiff16_boundary(self):
        values=np.linspace(.02,.96,131*193*3,dtype=np.float32).reshape(131,193,3)
        original=values.copy();image=display_image(values)
        edits=replace(Settings(),lens_correction=False,defringe=False,temperature=5300,
            contrast=12,texture=8,geometry=Geometry(crop=(.1,.2,.9,.8)))
        output=render_pixels(image,edits)
        self.assertEqual(output.shape,(79,155,3))
        np.testing.assert_array_equal(source_pixels(image),original)
        self.assertGreater(np.unique(output[...,0]).size,256)
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'original.tif';target=Path(root)/'output.tif'
            tifffile.imwrite(source,(values*65535).astype(np.uint16),photometric='rgb',metadata=None)
            expected=export_photo(str(source),str(target),edits)
            result=tifffile.imread(target)
            self.assertEqual(expected,(155,79));self.assertEqual(result.shape,(79,155,3))
            self.assertEqual(result.dtype,np.uint16)
            self.assertGreater(np.unique(result[...,0]).size,256)

    def test_geometry_inverse_maps_masks_and_exact_crop_is_not_resampled(self):
        values=np.arange(47*61*3,dtype=np.float32).reshape(47,61,3)/10000
        exact=apply_geometry_pixels(values,Geometry(crop=(10/61,9/47,53/61,38/47)))
        np.testing.assert_array_equal(exact,values[9:38,10:53])
        geometry=Geometry(rotation=7,vertical=13,flip_horizontal=True,crop=(.1,.2,.9,.85))
        forward,inverse=normalized_matrices(61,47,geometry)
        points=np.array([[.15,.3,1],[.6,.5,1],[.9,.8,1]]).T
        transformed=np.asarray(forward).reshape(3,3)@points;transformed/=transformed[2:3]
        restored=np.asarray(inverse).reshape(3,3)@transformed;restored/=restored[2:3]
        np.testing.assert_allclose(restored,points,atol=1e-12)
        output=apply_geometry_pixels(values,geometry)
        self.assertEqual(output.dtype,np.float32)
        self.assertTrue(np.isfinite(output).all())

    def test_large_import_queue_is_chunked_and_model_does_not_expose_edit_graphs(self):
        with tempfile.TemporaryDirectory() as root:
            paths=[]
            for i in range(65):
                path=Path(root)/f'{i}.arw';path.write_bytes(b'fixture');paths.append(str(path))
            ctrl=Controller(PhotoProvider(),root)
            try:
                ctrl.add_paths(paths)
                self.assertEqual([len(batch[0]) for batch in ctrl._import_queue],[16,16,16,16,1])
                ctrl._photo_model.append([dict(path=paths[0],name='first',settings={'masks':'private-large-graph'},thumbnail='')])
                row=ctrl._photo_model.data(ctrl._photo_model.index(0),ctrl._photo_model.PHOTO_ROLE)
                self.assertNotIn('settings',row)
                self.assertEqual(ctrl.photoCount,1)
            finally:ctrl.close()


if __name__=='__main__':unittest.main()
