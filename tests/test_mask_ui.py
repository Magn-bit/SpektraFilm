"""Exercise source-space brush input through the real QML canvas."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import time
import unittest
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QObject, QPoint, QPointF, Qt, QUrl, QMetaObject
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from desktop.controller import Controller, PhotoProvider
from desktop.typography import load_mincho


@unittest.skip('Archived editor UI contract; this product now exposes film development only')
class MaskUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def test_brush_draws_normalized_undoable_stroke_and_compare_disables_paint(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            photo=Path(folder)/'brush-fixture.png'
            Image.new('RGB',(640,480),(115,130,140)).save(photo)
            provider=PhotoProvider();ctrl=Controller(provider,folder)
            engine=QQmlApplicationEngine()
            engine.addImageProvider('photos',provider)
            context=engine.rootContext()
            family=load_mincho(self.app,root)
            for key,value in {'ctrl':ctrl,'minchoFamily':family,
                    'interfaceDisplayFamily':self.app._interface_font_selection['display'],
                    'interfaceEditorialFamily':self.app._interface_font_selection['editorial'],
                    'systemReduceMotion':True,'assetsUrl':QUrl.fromLocalFile(str(root/'assets')+'/').toString(),
                    'interfaceFontDescription':'test'}.items():context.setContextProperty(key,value)
            engine.load(QUrl.fromLocalFile(str(root/'desktop/qml/Studio.qml')))
            self.assertTrue(engine.rootObjects())
            window=engine.rootObjects()[0];window.setVisible(True)
            def wait(predicate):
                limit=time.monotonic()+8
                while not predicate() and time.monotonic()<limit:
                    self.app.processEvents();time.sleep(.005)
                self.assertTrue(predicate(),ctrl.status)
            try:
                ctrl.add_paths([str(photo)]);wait(lambda:bool(ctrl.frame) and not ctrl.busy)
                ctrl.addMask();ctrl.updateMaskParameter('exposure',.7)
                window.setProperty('editTab',3)
                viewport=window.findChild(QObject,'photoViewport')
                wait(lambda:viewport.property('brushEnabled'))
                self.app.processEvents()
                px=viewport.property('imageX')+viewport.property('imageWidth')*.35
                py=viewport.property('imageY')+viewport.property('imageHeight')*.5
                start=viewport.mapToScene(QPointF(px,py)).toPoint()
                end=viewport.mapToScene(QPointF(px+viewport.property('imageWidth')*.2,py)).toPoint()
                QTest.mousePress(window,Qt.LeftButton,Qt.NoModifier,start)
                QTest.mouseMove(window,end,60)
                QTest.mouseRelease(window,Qt.LeftButton,Qt.NoModifier,end)
                self.app.processEvents()
                strokes=ctrl.activeMask['strokes']
                self.assertEqual(len(strokes),1)
                self.assertAlmostEqual(strokes[0]['points'][0][0],.35,delta=.01)
                self.assertAlmostEqual(strokes[0]['points'][0][1],.5,delta=.01)
                self.assertGreater(len(strokes[0]['points']),1)
                self.assertEqual(QQmlExpression(context,viewport,'activeMask.strokes.length').evaluate()[0],1)
                self.assertIsNone(ctrl._before)
                wait(lambda:not ctrl.busy)
                capture=os.environ.get('SPEKTRA_UI_CAPTURE')
                if capture:
                    QTest.qWait(100)
                    Path(capture).parent.mkdir(parents=True,exist_ok=True)
                    self.assertTrue(window.grabWindow().save(capture))
                ctrl.undo();self.assertEqual(ctrl.activeMask['strokes'],[])
                ctrl.redo();self.assertEqual(len(ctrl.activeMask['strokes']),1)
                viewport.setProperty('zoomRatio',4)
                viewport.setProperty('actualSize',True);self.app.processEvents()
                flickable=window.findChild(QObject,'photoFlickable')
                pan_start=viewport.mapToScene(QPointF(viewport.width()/2,viewport.height()/2)).toPoint()
                before_pan=flickable.property('contentX')
                before_masks=ctrl.settings['masks']
                QTest.mousePress(window,Qt.RightButton,Qt.NoModifier,pan_start)
                QTest.mouseMove(window,pan_start-QPoint(40,0),30)
                QTest.mouseRelease(window,Qt.RightButton,Qt.NoModifier,pan_start-QPoint(40,0))
                self.app.processEvents()
                self.assertEqual(viewport.property('zoomRatio'),4)
                self.assertGreater(flickable.property('contentX'),before_pan)
                self.assertEqual(ctrl.settings['masks'],before_masks)
                window.setProperty('comparing',True);self.app.processEvents()
                self.assertFalse(viewport.property('brushEnabled'))
                before=ctrl.settings['masks']
                QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,start)
                self.assertEqual(ctrl.settings['masks'],before)
                window.setProperty('comparing',False);viewport.setProperty('actualSize',False)
                ctrl.addMaskOfKind('radial');self.app.processEvents()
                center=viewport.mapToScene(QPointF(viewport.property('imageX')+viewport.property('imageWidth')*.5,viewport.property('imageY')+viewport.property('imageHeight')*.5)).toPoint()
                QTest.mousePress(window,Qt.LeftButton,Qt.NoModifier,center)
                QTest.mouseMove(window,center+QPoint(32,20),30)
                QTest.mouseRelease(window,Qt.LeftButton,Qt.NoModifier,center+QPoint(32,20))
                self.app.processEvents()
                self.assertGreater(ctrl.activeMask['center'][0],.5)
                self.assertIsNone(ctrl._before)
                ctrl.undo();self.assertEqual(ctrl.activeMask['center'],[.5,.5])
                window.setProperty('editTab',1);self.app.processEvents()
                curve=window.findChild(QObject,'curveEditor');graph=window.findChild(QObject,'curveGraph')
                position=graph.mapToScene(QPointF(graph.width()*.5,graph.height()*.42)).toPoint()
                QTest.mousePress(window,Qt.LeftButton,Qt.NoModifier,position)
                QTest.mouseMove(window,position-QPoint(0,20),30)
                QTest.mouseRelease(window,Qt.LeftButton,Qt.NoModifier,position-QPoint(0,20))
                self.app.processEvents()
                self.assertEqual(len(ctrl.colorCurves['master']),3)
                self.assertGreater(ctrl.colorCurves['master'][1][1],.58)
                # Same input coordinate, distant output: select an existing
                # point instead of introducing duplicate-x interpolation knots.
                same_x=graph.mapToScene(QPointF(graph.width()*.5,graph.height()*.85)).toPoint()
                QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,same_x)
                self.assertEqual(len(ctrl.colorCurves['master']),3)
                from scipy.interpolate import PchipInterpolator
                import numpy as np
                values=[[0,0],[.2,.35],[.7,.6],[1,1]]
                expected=float(PchipInterpolator(np.array(values)[:,0],np.array(values)[:,1])(.43))
                actual=QQmlExpression(context,curve,'interpolate([[0,0],[.2,.35],[.7,.6],[1,1]],.43)').evaluate()[0]
                self.assertAlmostEqual(actual,expected,places=10)
                tools=window.findChild(QObject,'colorToolsPanel');tools.setProperty('openGroup','grading');self.app.processEvents()
                wheel=window.findChild(QObject,'gradingWheelCanvas')
                # Adding another collapsible group changes scroll geometry.
                # Wait for layout and bring the actual target into the viewport
                # rather than clicking through a clipped section off-screen.
                QTest.qWait(80)
                scroll=window.findChild(QObject,'parameterScroll')
                flick=scroll.property('contentItem')
                center_in_view=wheel.mapToItem(flick,QPointF(wheel.width()*.7,wheel.height()*.5))
                if center_in_view.y()>flick.height()-24:
                    flick.setProperty('contentY',min(flick.property('contentHeight')-flick.height(),
                        flick.property('contentY')+center_in_view.y()-flick.height()/2))
                    QTest.qWait(30)
                wheel_point=wheel.mapToScene(QPointF(wheel.width()*.7,wheel.height()*.5)).toPoint()
                QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,wheel_point);self.app.processEvents()
                self.assertGreater(ctrl.settings['grading']['shadows']['saturation'],30)
                self.assertIsNone(ctrl._before)
                while ctrl.activeMaskId:ctrl.deleteMask()
                self.assertTrue(ctrl.requestCropPreview());wait(lambda:not ctrl.cropBusy and bool(ctrl.cropSource))
                dialog=window.findChild(QObject,'cropDialog');QMetaObject.invokeMethod(dialog,'open');self.app.processEvents()
                dialog.setProperty('draft',[.1,.1,.9,.9])
                full=window.findChild(QObject,'cropFullImage')
                crop_start=full.mapToScene(QPointF(full.width()*.9,full.height()*.9)).toPoint()
                crop_end=full.mapToScene(QPointF(full.width()*.75,full.height()*.8)).toPoint()
                QTest.mousePress(window,Qt.LeftButton,Qt.NoModifier,crop_start)
                QTest.mouseMove(window,crop_end,30)
                QTest.mouseRelease(window,Qt.LeftButton,Qt.NoModifier,crop_end);self.app.processEvents()
                bounds=dialog.property('draft').toVariant() if hasattr(dialog.property('draft'),'toVariant') else dialog.property('draft')
                self.assertAlmostEqual(bounds[2],.75,delta=.015)
                self.assertAlmostEqual(bounds[3],.8,delta=.015)
                apply=window.findChild(QObject,'applyCropButton')
                QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,apply.mapToScene(QPointF(apply.width()/2,apply.height()/2)).toPoint())
                self.app.processEvents()
                self.assertLess(ctrl.imageWidth,640)
                self.assertLess(ctrl.imageHeight,480)
                ctrl.undo();self.assertEqual((ctrl.imageWidth,ctrl.imageHeight),(640,480))
            finally:
                window.close();ctrl.close()
                engine.deleteLater();self.app.processEvents()


if __name__=='__main__':unittest.main()
