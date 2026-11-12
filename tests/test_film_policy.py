"""Product boundaries: historical editor state cannot affect film-only output."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from dataclasses import asdict,replace
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image
from PySide6.QtWidgets import QApplication
from desktop.batch import plan_exports
from desktop.controller import Controller,PhotoProvider
from desktop.imaging import Settings,FILM_FIELDS,film_settings,export_photo
from shared.geometry import Geometry, normalize_geometry, apply_geometry_image


def legacy_settings():
    return dict(stock='kodak_gold_200',exposure=.4,grain=26,grain_size=.7,grain_type='fine',
        halation=8,vignette=11,strength=75,spectral=False,film_enabled=False,
        temperature=3000,tint=45,contrast=80,warmth=30,saturation=-80,vibrance=60,
        highlights=50,shadows=-50,black_point=15,white_point=82,gamma=1.8,
        calibration_red_hue=70,calibration_red_saturation=-70,
        calibration_green_hue=60,calibration_green_saturation=-60,
        calibration_blue_hue=50,calibration_blue_saturation=-50,
        curves={'master':[[0,.2],[1,.8]],'red':[[0,.1],[1,.7]]},
        grading={'shadows':{'hue':210,'saturation':70}},
        hsl={'orange':{'hue':80,'saturation':60,'luminance':40}},
        geometry={'rotation':20,'flip_horizontal':True,'crop':[.1,.2,.7,.8]},
        masks=[{'id':'legacy-mask','kind':'radial','exposure':2}],
        look_lut='retired-look',look_strength=30,lens_correction=True,defringe=True)


class FilmPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.source=self.root/'original.png'
        self.pixels=np.random.default_rng(312).integers(20,230,(41,67,3),dtype=np.uint8)
        Image.fromarray(self.pixels).save(self.source)
        self.original_bytes=self.source.read_bytes()
        self.physics=patch('desktop.imaging._spectral',side_effect=lambda rgb,s,**kw:rgb.astype(np.float32)/255)
        self.physics.start();self.addCleanup(self.physics.stop)
        self.ctrl=Controller(PhotoProvider(),self.temp.name)

    def tearDown(self):
        self.ctrl.close();self.app.processEvents();self.temp.cleanup()

    def wait(self,predicate):
        deadline=time.monotonic()+7
        while not predicate() and time.monotonic()<deadline:self.app.processEvents();time.sleep(.003)
        self.assertTrue(predicate(),self.ctrl.status)

    def load(self,dirty=True):
        if dirty:
            self.ctrl._edit_path(str(self.source)).write_text(json.dumps({'version':1,'settings':legacy_settings()}),encoding='utf-8')
        self.ctrl.add_paths([str(self.source)])
        self.wait(lambda:not self.ctrl.busy and bool(self.ctrl.frame))

    def assert_film_only(self,settings):
        actual=asdict(settings) if isinstance(settings,Settings) else settings
        neutral=asdict(Settings(spectral=True,film_enabled=True,lens_correction=False,defringe=False))
        for key,value in neutral.items():
            if key not in FILM_FIELDS:self.assertEqual(actual[key],value,key)
        geometry=normalize_geometry(actual['geometry'])
        self.assertEqual(geometry,Geometry(crop=geometry.crop))

    def test_policy_keeps_film_values_and_removes_all_legacy_editor_values(self):
        dirty=legacy_settings();clean=film_settings(dirty)
        self.assert_film_only(clean)
        for key in FILM_FIELDS:
            expected=Geometry(crop=normalize_geometry(dirty['geometry']).crop) if key=='geometry' else dirty.get(key,getattr(Settings(),key))
            self.assertEqual(getattr(clean,key),expected,key)
        self.assertEqual(film_settings(clean),clean)

    def test_dirty_sidecar_import_switch_and_persistence_are_canonical(self):
        self.load();self.assert_film_only(self.ctrl.settings)
        self.assertEqual((self.ctrl.imageWidth,self.ctrl.imageHeight),(67,41))
        self.assertEqual(self.ctrl.provider.images['original'].size().width(),67)
        self.ctrl._persist()
        record=json.loads(self.ctrl._edit_path(str(self.source)).read_text(encoding='utf-8'))
        self.assertEqual(record['version'],3)
        self.assertEqual(set(record['settings']),set(FILM_FIELDS))
        self.assertEqual(record['settings']['grain_size'],.7)
        second=self.root/'second.png';Image.new('RGB',(35,29),'gray').save(second)
        self.ctrl.add_paths([str(second)]);self.wait(lambda:not self.ctrl.busy)
        self.ctrl.selectPhoto(0);self.wait(lambda:not self.ctrl.busy)
        self.assert_film_only(self.ctrl.settings)
        self.assertEqual(self.ctrl.settings['grain_size'],.7)

    def test_retired_controls_cannot_reenable_hidden_effects(self):
        self.load();before=self.ctrl.settings
        for key,value in [('temperature',2700),('contrast',90),('look_strength',25),('vibrance',80)]:
            self.ctrl.updateParameter(key,value)
        self.ctrl.setFilmEnabled(False);self.ctrl.setSpectral(False)
        self.ctrl.setCorrection('lens_correction',True)
        self.ctrl.setCurvePoints('master',[[0,.2],[1,.8]])
        self.ctrl.updateHslParameter('red','hue',70)
        self.ctrl.updateGradingParameter('shadows','saturation',70)
        self.ctrl.updateGeometry('rotation',25)
        self.ctrl.addMask()
        self.assertEqual(self.ctrl.settings,before)
        self.assertEqual(self.ctrl.maskLayers,[])

    def test_dirty_history_is_sanitized_on_undo_and_redo(self):
        self.load();before=self.ctrl.settings
        self.ctrl._history[self.ctrl.currentIndex]=[Settings.from_mapping(legacy_settings())]
        self.ctrl.undo();self.assert_film_only(self.ctrl.settings)
        self.ctrl.redo();self.assertEqual(self.ctrl.settings,before)

    def test_direct_preview_keeps_explicit_crop_but_rejects_legacy_transforms(self):
        self.load()
        captured=[]
        def render(image,settings,**kwargs):
            captured.append(settings);return apply_geometry_image(image,settings.geometry)
        with patch('desktop.controller.render',side_effect=render):
            original,developed,*_=self.ctrl._render_photo(str(self.source),Settings.from_mapping(legacy_settings()),0)
        self.assertEqual(original.size,(40,25));self.assertEqual(developed.size,(40,25))
        np.testing.assert_array_equal(np.asarray(developed),self.pixels[8:33,7:47])
        self.assert_film_only(captured[0])

    def test_direct_export_sanitizes_before_render_and_keeps_pixels_and_source(self):
        target=self.root/'export.tif';captured=[]
        def render(image,settings,**kwargs):
            captured.append(settings);return np.asarray(apply_geometry_image(image,settings.geometry),dtype=np.float32)/255
        with patch('desktop.imaging.render_pixels',side_effect=render):
            self.assertEqual(export_photo(str(self.source),str(target),Settings.from_mapping(legacy_settings())),(40,25))
        self.assert_film_only(captured[0])
        self.assertEqual(captured[0].grain_size,.7)
        with Image.open(target) as image:
            np.testing.assert_array_equal(np.asarray(image),self.pixels[8:33,7:47])
            self.assertTrue(image.info.get('icc_profile'))
        self.assertEqual(self.source.read_bytes(),self.original_bytes)

    def test_batch_plan_canonicalizes_every_photo_and_names_with_film(self):
        photos=[dict(path=str(self.source),settings=legacy_settings())]
        _,target,settings=plan_exports(photos,[0],'TIFF')[0]
        self.assert_film_only(settings)
        self.assertEqual(Path(target).name,'original_Gold 200.tif')
        self.assertEqual(settings.exposure,.4)

    def test_single_and_batch_export_snapshot_hidden_legacy_state_safely(self):
        self.load();self.ctrl._settings=Settings.from_mapping(legacy_settings())
        captured=[]
        def save(source,target,settings,preset):
            captured.append(settings);Path(target).write_bytes(b'checked')
        with patch('desktop.controller.export_preset',side_effect=save):
            self.assertTrue(self.ctrl.export_to(str(self.root/'single.tif'),preset='TIFF'))
            self.wait(lambda:not self.ctrl.busy)
            self.ctrl._photos[0]['settings']=legacy_settings()
            self.assertTrue(self.ctrl.export_batch('TIFF'))
            self.wait(lambda:not self.ctrl.busy)
        self.assertEqual(len(captured),2)
        for settings in captured:self.assert_film_only(settings)


if __name__=='__main__':unittest.main()
