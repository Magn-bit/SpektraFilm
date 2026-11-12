"""GUI subscriptions must follow changed fields, without serializing all edits."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from dataclasses import asdict, replace
import tempfile
import unittest

from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtWidgets import QApplication
from desktop.controller import Controller, PhotoProvider
from desktop.editor_bindings import EditorBindings
from desktop.imaging import Settings
from shared.geometry import Geometry
from shared.local_masks import MaskLayer, MaskStroke


class EditorBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def test_real_qml_updates_only_the_changed_field(self):
        settings=Settings(masks=(MaskLayer(id='paint',strokes=(MaskStroke(points=tuple((i/12000,.5) for i in range(12000))),)),))
        projection=EditorBindings(settings)
        engine=QQmlEngine()
        engine.rootContext().setContextProperty('parameters',projection)
        component=QQmlComponent(engine)
        component.setData(b'''import QtQml
QtObject {
 property real exposure: parameters.exposure
 property real tint: parameters.tint
 property int tintNotifications: 0
 property int maskNotifications: 0
 property var masks: parameters.masks
 onTintChanged: tintNotifications++
 onMasksChanged: maskNotifications++
}''',QUrl())
        root=component.create()
        self.assertIsNotNone(root,component.errors())
        before=(root.property('tintNotifications'),root.property('maskNotifications'))
        for value in (.01,.7,1.234):projection.sync(replace(settings,exposure=value))
        self.assertEqual(root.property('exposure'),1.234)
        self.assertEqual((root.property('tintNotifications'),root.property('maskNotifications')),before)
        root.setParent(engine)

    def test_controller_routes_state_history_and_mask_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            ctrl=Controller(PhotoProvider(),directory)
            try:
                ctrl._photo_model.append([dict(path=directory+'/source.png',name='source.png',width=100,height=80,
                    dimensions='100 × 80',thumbnail='',settings=asdict(Settings()))])
                ctrl._current=0
                ctrl._changed()
                seen=[]
                ctrl.geometryChanged.connect(lambda:seen.append('geometry'))
                ctrl.masksChanged.connect(lambda:seen.append('mask'))
                ctrl.curvesChanged.connect(lambda:seen.append('curves'))
                state_events=[];parameter_events=[]
                ctrl.stateChanged.connect(lambda:state_events.append(1))
                ctrl.parameterChanged.connect(lambda:parameter_events.append(1))
                ctrl.beginEdit()
                ctrl.updateParameter('exposure',.876)
                self.assertEqual(ctrl.parameters.value('exposure'),.876)
                self.assertEqual(state_events,[])
                self.assertEqual(len(parameter_events),1)
                ctrl.endEdit()
                self.assertEqual(ctrl.parameters.value('exposure'),.876)
                self.assertEqual(len(state_events),1)
                self.assertEqual(seen,[])
                ctrl.undo()
                self.assertEqual(ctrl.parameters.value('exposure'),0.)
                ctrl.redo()
                self.assertEqual(ctrl.parameters.value('exposure'),.876)
                ctrl.updateGeometry('rotation',3)
                self.assertEqual(seen,['geometry'])
                first=ctrl.addMaskOfKind('radial')
                second=ctrl.addMaskOfKind('linear')
                ctrl.selectMask(first)
                self.assertNotEqual(first,second)
                self.assertEqual(ctrl.activeMask['id'],first)
                self.assertEqual(seen,['geometry','mask','mask','mask'])
                ctrl.reset()
                self.assertEqual(ctrl.parameters.value('exposure'),0.)
                self.assertFalse(ctrl.parameters.value('masks'))
                # Zoomed detail from the previous settings must never obscure
                # a new live proxy until the pointer is released.
                ctrl._full_detail._ask=(ctrl.currentPath,ctrl._settings)
                ctrl._full_detail._source='image://photos/old-detail'
                ctrl._full_detail._state='ready'
                ctrl.beginEdit()
                ctrl.updateParameter('exposure',.2)
                self.assertFalse(ctrl.fullDetail.ready)
                self.assertEqual(ctrl.fullDetail.source,'')
                ctrl.endEdit()
            finally:ctrl.close()


if __name__=='__main__':unittest.main()
