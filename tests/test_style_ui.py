"""Styles replace a scoped colour recipe without overwriting photo edits."""
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
from PySide6.QtCore import QObject,QPointF,Qt,QUrl
from PySide6.QtQml import QQmlApplicationEngine,QQmlExpression
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from desktop.controller import Controller,PhotoProvider,STYLE_FIELDS
from desktop.imaging import Settings
from desktop.typography import load_mincho


@unittest.skip('Archived editor UI contract; this product now exposes film development only')
class StyleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.ctrl=Controller(PhotoProvider(),self.temp.name)
        self.paths=[]
        for index in range(2):
            path=self.folder/f'photo-{index}.png';Image.new('RGB',(60,40),(80+index*20,110,140)).save(path);self.paths.append(str(path))
        self.ctrl.add_paths(self.paths);self.wait(lambda:not self.ctrl.busy and bool(self.ctrl.frame))
    def tearDown(self):self.ctrl.close();self.app.processEvents();self.temp.cleanup()
    def wait(self,predicate):
        limit=time.monotonic()+8
        while not predicate() and time.monotonic()<limit:self.app.processEvents();time.sleep(.005)
        self.assertTrue(predicate(),self.ctrl.status)
    def make_xmp(self):
        path=self.folder/'local-contrast.xmp'
        path.write_text('<x:xmpmeta xmlns:x="adobe:ns:meta/" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"><rdf:RDF><rdf:Description crs:Contrast2012="17" crs:Exposure2012="2" crs:Vibrance="8"/></rdf:RDF></x:xmpmeta>',encoding='utf-8')
        return path

    def author_fixture(self):
        """Exercise optional LUT controls without shipping a LUT in the library."""
        cube=np.zeros((2,2,2,3),dtype=np.uint8)
        for b in range(2):
            for g in range(2):
                for r in range(2):cube[b,g,r]=[r*255,g*255,b*255]
        for target,replacement in (('desktop.controller.known_lut',lambda ident:{'id':ident,'name':'测试色彩资源'} if ident=='test-identity' else None),
                ('desktop.imaging.known_lut',lambda ident:{'id':ident} if ident=='test-identity' else None),
                ('desktop.imaging.lut_for_id',lambda ident:cube if ident=='test-identity' else None)):
            fixture=patch(target,side_effect=replacement);fixture.start();self.addCleanup(fixture.stop)
        style=dict(self.ctrl._styles[0],id='test-author',name='测试色彩资源',kind='creative-hald',settings=dict(self.ctrl._styles[0]['settings'],look_lut='test-identity'))
        self.ctrl._styles.append(style)
        self.ctrl.applyStyle(style['id'])
        return style

    def test_batch_styles_preserve_photo_edits_replace_recipe_and_each_undo(self):
        preserved=('exposure','temperature','tint','warmth','film_enabled','stock','geometry','masks','lens_correction','defringe')
        originals=[]
        for index in range(2):
            self.ctrl.selectPhoto(index);self.ctrl.updateParameter('exposure',.3+index*.2)
            self.ctrl.updateParameter('temperature',5200+index*300)
            self.ctrl.updateGeometry('rotation',index+1)
            self.ctrl.addMaskOfKind('radial');self.ctrl.updateMaskParameter('exposure',.2+index*.1)
            originals.append(self.ctrl.settings)
        self.ctrl.selectPhoto(0);self.ctrl.selectAllPhotos()
        first,last=self.ctrl._styles[0],self.ctrl._styles[-1]
        self.assertTrue(self.ctrl.applyStyle(first['id']))
        first_results=[dict(photo['settings']) for photo in self.ctrl.photos]
        self.assertTrue(self.ctrl.applyStyle(last['id']))
        for index,photo in enumerate(self.ctrl.photos):
            for key in preserved:self.assertEqual(photo['settings'][key],originals[index][key],key)
            expected=Settings.from_mapping(dict(originals[index],**last['settings']))
            for key in STYLE_FIELDS:
                if key in last['settings']:self.assertEqual(photo['settings'][key],asdict(expected)[key],key)
            self.ctrl.selectPhoto(index);self.ctrl.undo()
            self.assertEqual(self.ctrl.settings,first_results[index])

    def test_xmp_import_is_reviewed_before_apply_and_persisted(self):
        original=self.ctrl.settings
        with patch('desktop.controller.QFileDialog.getOpenFileNames',return_value=([str(self.make_xmp())],'')):
            self.assertTrue(self.ctrl.importStyle())
        self.assertEqual(self.ctrl.settings,original)
        preset=next(item for item in self.ctrl.stylePresets if item['id']==self.ctrl.importedStyleId)
        self.assertEqual(preset['kind'],'xmp-partial');self.assertTrue(preset['warnings'])
        self.assertTrue(self.ctrl.applyStyle(preset['id']))
        self.assertEqual(self.ctrl.settings['contrast'],17)
        self.assertEqual(self.ctrl.settings['exposure'],original['exposure'])
        other=Controller(PhotoProvider(),self.temp.name)
        try:self.assertTrue(any(item['id']==preset['id'] for item in other.stylePresets))
        finally:other.close()

    def test_unknown_author_resource_is_rejected_and_original_style_clears_lut(self):
        unknown=self.folder/'missing.sfpreset'
        unknown.write_text(json.dumps({'name':'missing','settings':{'look_lut':'not-installed'}}),encoding='utf-8')
        count=len(self.ctrl.stylePresets)
        self.assertFalse(self.ctrl.import_style_path(unknown));self.assertEqual(len(self.ctrl.stylePresets),count)
        self.author_fixture();self.assertTrue(self.ctrl.settings['look_lut'])
        original=next(item for item in self.ctrl.stylePresets if item['kind']=='original')
        self.ctrl.applyStyle(original['id']);self.assertEqual(self.ctrl.settings['look_lut'],'')

    def test_style_strength_drag_and_remove_are_scoped_undo_steps(self):
        self.ctrl.updateParameter('exposure',.7);author=self.author_fixture()
        ident=self.ctrl.settings['look_lut'];self.assertEqual(self.ctrl.currentStyleName,author['name'])
        self.ctrl.beginEdit()
        for value in (80,45,23):self.ctrl.updateParameter('look_strength',value)
        self.ctrl.endEdit();self.assertEqual(self.ctrl.settings['look_strength'],23)
        self.ctrl.undo();self.assertEqual(self.ctrl.settings['look_strength'],100)
        self.ctrl.redo();self.assertEqual(self.ctrl.settings['look_strength'],23)
        before=self.ctrl.settings;self.ctrl.clearStyleLut()
        self.assertEqual(self.ctrl.settings['look_lut'],'');self.assertEqual(self.ctrl.currentStyleName,'')
        self.assertEqual(self.ctrl.settings['exposure'],.7)
        self.assertEqual(self.ctrl.settings['look_strength'],23)
        self.ctrl.undo();self.assertEqual(self.ctrl.settings,before);self.assertEqual(self.ctrl.settings['look_lut'],ident)

    def test_hsl_continuous_edit_is_one_undo_and_retains_photo_edits(self):
        self.ctrl.updateParameter('exposure',.7)
        before=self.ctrl.settings
        self.ctrl.beginEdit()
        for value in (10,30,-50,45):self.ctrl.updateHslParameter('orange','saturation',value)
        self.ctrl.endEdit()
        self.assertEqual(self.ctrl.settings['hsl']['orange']['saturation'],45)
        self.assertEqual(self.ctrl.settings['exposure'],.7)
        self.ctrl.undo();self.assertEqual(self.ctrl.settings,before)
        self.ctrl.redo();self.assertEqual(self.ctrl.settings['hsl']['orange']['saturation'],45)
        self.ctrl.resetHsl('orange');self.assertEqual(self.ctrl.settings['hsl']['orange']['saturation'],0)

    def test_live_popup_entry_selection_apply_and_xmp_scope(self):
        root=Path(__file__).resolve().parents[1];engine=QQmlApplicationEngine();engine.addImageProvider('photos',self.ctrl.provider)
        family=load_mincho(self.app,root);context=engine.rootContext()
        for key,value in {'ctrl':self.ctrl,'minchoFamily':family,'interfaceDisplayFamily':self.app._interface_font_selection['display'],
                'interfaceEditorialFamily':self.app._interface_font_selection['editorial'],'systemReduceMotion':True,
                'assetsUrl':QUrl.fromLocalFile(str(root/'assets')+'/').toString(),'interfaceFontDescription':'test'}.items():context.setContextProperty(key,value)
        engine.load(QUrl.fromLocalFile(str(root/'desktop/qml/Studio.qml')));self.assertTrue(engine.rootObjects())
        window=engine.rootObjects()[0];window.setVisible(True);window.setProperty('editTab',1);self.app.processEvents()
        def click(item):QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,item.mapToScene(QPointF(item.width()/2,item.height()/2)).toPoint());self.app.processEvents()
        try:
            strength=window.findChild(QObject,'lookStrengthControl');self.assertFalse(strength.property('visible'))
            colour_panel=window.findChild(QObject,'colorToolsPanel')
            if colour_panel:
                colour_panel.setProperty('openGroup','hsl');self.app.processEvents()
                hsl_capture=os.environ.get('SPEKTRA_HSL_CAPTURE')
                if hsl_capture:QTest.qWait(150);self.assertTrue(window.grabWindow().save(hsl_capture))
            self.author_fixture();self.ctrl.stateChanged.emit();self.app.processEvents();self.assertTrue(strength.property('visible'))
            click(window.findChild(QObject,'clearStyleButton'));self.assertFalse(strength.property('visible'))
            self.ctrl._styles=[item for item in self.ctrl._styles if item['id']!='test-author']
            click(window.findChild(QObject,'openStylesButton'))
            popup=window.findChild(QObject,'styleLibrary');self.assertTrue(popup.property('opened'))
            self.assertEqual(QQmlExpression(context,popup,'chosenPreset.kind').evaluate()[0],self.ctrl.stylePresets[0]['kind'])
            popup.setProperty('category','portrait');self.app.processEvents()
            self.assertEqual(QQmlExpression(context,popup,'filteredPresets.length').evaluate()[0],9)
            popup.setProperty('category','landscape');self.app.processEvents()
            self.assertEqual(QQmlExpression(context,popup,'filteredPresets.length').evaluate()[0],11)
            capture=os.environ.get('SPEKTRA_STYLE_CAPTURE')
            if capture:QTest.qWait(100);self.assertTrue(window.grabWindow().save(capture))
            self.assertTrue(self.ctrl.import_style_path(self.make_xmp()));self.app.processEvents()
            self.assertEqual(popup.property('chosenId'),self.ctrl.importedStyleId)
            self.assertEqual(QQmlExpression(context,popup,'chosenPreset.kind').evaluate()[0],'xmp-partial')
            click(window.findChild(QObject,'applyStyleButton'))
            self.assertFalse(popup.property('opened'));self.assertEqual(self.ctrl.settings['contrast'],17)
        finally:window.close();engine.deleteLater();self.app.processEvents()


if __name__=='__main__':unittest.main()
