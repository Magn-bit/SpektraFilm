"""Native optics keep the established LCP geometry and fringe selection."""
import unittest
import sys
import numpy as np
from scipy.ndimage import map_coordinates

from desktop.lens import Model, _orient_pixels, _mapper, _defringe
from desktop.native_optics import correct_lens, defringe
from desktop.raw_source import display_image, source_pixels
from desktop.raw_development import available as raw_available
from desktop.native_spectral import available as gpu_available


@unittest.skipUnless(sys.platform=='win32' and raw_available() and gpu_available(), 'native Windows optics runtime required')
class NativeOpticsIntegration(unittest.TestCase):
    def test_lcp_double_geometry_matches_reference_in_all_orientations(self):
        source=np.random.default_rng(4).uniform(-.03,1.15,(103,147,3)).astype(np.float32)
        base=Model(fx=.94,fy=.96,k1=-.08,k2=.015,p1=.0008,p2=-.0003)
        chrom=(Model(fx=.94,fy=.96,k1=.002,scale=1.0003),Model(fx=.94,fy=.96),Model(fx=.94,fy=.96,k1=-.002,scale=.9998))
        for orientation in range(1,9):
            with self.subTest(orientation=orientation):
                oriented=np.ascontiguousarray(_orient_pixels(source,orientation))
                metadata=dict(orientation=orientation,focal_length=35,focal_35mm=35)
                mapper=_mapper(147,103,base,chrom,metadata,1)
                xx,yy=np.meshgrid(np.arange(147,dtype=np.float64),np.arange(103,dtype=np.float64))
                expected=np.empty_like(source)
                for channel in range(3):
                    x,y=mapper(xx,yy,1.08,channel)
                    expected[:,:,channel]=map_coordinates(source[:,:,channel],[y,x],order=1,prefilter=False,mode='nearest',output=np.float32)
                expected=np.ascontiguousarray(_orient_pixels(expected,orientation))
                actual=correct_lens(oriented,base,chrom,metadata,1,1.08)
                np.testing.assert_allclose(actual,expected,atol=2e-6,rtol=2e-6)
                self.assertEqual(actual.shape,oriented.shape)

    def test_defringe_matches_reference_across_strip_boundary_and_inplace(self):
        source=np.zeros((1067,79,3),dtype=np.float32)+.05
        source[:,39:]=.95
        source[7:1060,38,:]=[.8,.1,.85]
        source[508:516,37,:]=[1.2,.1,1.15]
        source[811:814,39,:]=[-.02,.11,.21]
        reference,count=_defringe(display_image(source))
        output,changed=defringe(source)
        self.assertGreater(count,0)
        self.assertEqual(count,changed)
        np.testing.assert_allclose(output,source_pixels(reference),atol=2e-7,rtol=2e-6)
        inplace=source.copy();same,changed2=defringe(inplace,out=inplace)
        self.assertEqual(count,changed2)
        np.testing.assert_allclose(same,output,atol=2e-7,rtol=2e-6)


if __name__=='__main__':unittest.main()
