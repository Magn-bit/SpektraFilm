"""Real source-depth layout output, native cell sizes and cancellation."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from dataclasses import asdict,replace
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import numpy as np
import tifffile
from PySide6.QtWidgets import QApplication
from desktop.controller import Controller,PhotoProvider
from desktop.imaging import Settings
from desktop.output import ExportCancelled
from shared.composition import geometry,crop_box,decoration_spec,normalized_decorations


class CompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_decoration_geometry_is_shared_and_missing_metadata_stays_empty(self):
        spec=decoration_spec(1000,700,48,'film',[{'metadata':{'camera':'Sony A7CR','lens':'50mm','exposure':'1/125 · f/2.8 · ISO 100'}}])
        normalized=normalized_decorations(spec,1000,700)
        self.assertTrue(normalized['holes'])
        self.assertEqual(len(normalized['labels']),1)
        self.assertIn('Sony A7CR',normalized['labels'][0]['text'])
        self.assertEqual(decoration_spec(1000,700,48,'film',[{'metadata':{}}])['labels'],[])
        self.assertEqual(decoration_spec(1000,700,2,'plain',[{'metadata':{'camera':'fixture'}}])['holes'],[])

    def test_frame_styles_have_distinct_shared_structure(self):
        plain=decoration_spec(1000,700,48,'plain')
        instant=decoration_spec(1000,700,48,'instant')
        contact=decoration_spec(1000,700,48,'contact')
        film=decoration_spec(1000,700,48,'film')
        self.assertEqual(plain['bands'],[])
        self.assertTrue(instant['bands'])
        self.assertTrue(contact['bands'] and contact['rules'])
        self.assertTrue(film['holes'])

    def test_half_frame_uses_two_real_photo_gates(self):
        width,height,rects,_=geometry([(240,160),(240,160)],layout='grid',style='half_frame',border=.04,gap=.02)
        self.assertEqual(len(rects),2)
        self.assertLess(rects[0][2],rects[1][0])
        self.assertEqual(decoration_spec(width,height,48,'half_frame')['rules'],[])

    def test_frame_style_can_change_while_preview_is_loading(self):
        """A slow RAW preview must not swallow a layout choice."""
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.tif'
            tifffile.imwrite(path,np.zeros((12,18,3),dtype=np.uint16),photometric='rgb')
            ctrl=Controller(PhotoProvider(),folder)
            try:
                creative=ctrl.composition
                creative.rows=[dict(path=str(path),name=path.name,settings=Settings(),width=18,height=12,
                                    source='',zoom=1.,pan_x=.5,pan_y=.5)]
                creative._busy=True;creative._operation='preview'
                creative.setOption('style','film')
                self.assertEqual(creative.state['style'],'film')
                self.assertEqual(creative.state['styleName'],'胶片片边')
                creative._operation='export'
                creative.setOption('style','instant')
                self.assertEqual(creative.state['style'],'film')
            finally:
                ctrl.close()

    def test_native_cell_layout_does_not_shrink_single_photo(self):
        for style in ('plain','paper','instant','film'):
            w,h,rects,_=geometry([(9564,6376)],style=style)
            l,t,r,b=rects[0]
            self.assertEqual((r-l,b-t),(9564,6376))
            self.assertGreaterEqual(w,9564);self.assertGreaterEqual(h,6376)
        _,_,rects,_=geometry([(90,60),(90,60)],layout='horizontal',ratio=3.,border=0.,gap=0.)
        self.assertEqual(rects,[(0,0,90,60),(90,0,180,60)])
    def test_real_tiff16_source_edits_order_pan_and_atomic_output(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            values=np.linspace(.01,.7,60*90*3,dtype=np.float32).reshape(60,90,3)
            paths=[]
            for name,source in [('a',values),('b',values[...,::-1].copy())]:
                path=folder/(name+'.tif');tifffile.imwrite(path,np.rint(source*65535).astype(np.uint16),photometric='rgb');paths.append(path)
            before=[(p.stat().st_size,p.stat().st_mtime_ns) for p in paths]
            ctrl=Controller(PhotoProvider(),str(folder))
            try:
                creative=ctrl.composition
                settings=replace(Settings(),lens_correction=False,defringe=False)
                rows=[dict(path=str(p),name=p.name,settings=replace(settings,exposure=i*.3),width=90,height=60,source='',zoom=1.,pan_x=.5,pan_y=.5) for i,p in enumerate(paths)]
                creative.rows=rows;creative.layout='horizontal';creative.ratio=3.;creative.gap=0;creative.border=0;creative.style='plain'
                output=folder/'layout.tif'
                with patch.object(ctrl,'_source',side_effect=AssertionError('Final must never use preview cache')):
                    creative._export(rows,creative.state,output)
                actual=tifffile.imread(output)
                self.assertEqual(actual.shape,(60,180,3));self.assertEqual(actual.dtype,np.uint16)
                self.assertGreater(np.unique(actual[...,0]).size,256)
                self.assertNotEqual(float(actual[:,:90].mean()),float(actual[:,90:].mean()))
                self.assertEqual(before,[(p.stat().st_size,p.stat().st_mtime_ns) for p in paths])
                with tifffile.TiffFile(output) as image:self.assertIn(34675,image.pages[0].tags)
                creative._cancel.set()
                cancelled=folder/'cancelled.tif'
                with self.assertRaises(ExportCancelled):creative._export(rows,creative.state,cancelled)
                self.assertFalse(cancelled.exists())
            finally:ctrl.close()


if __name__=='__main__':unittest.main()
