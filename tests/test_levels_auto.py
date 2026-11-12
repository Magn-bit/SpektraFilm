"""One bounded integration fixture for levels, HDR and automatic proposals."""
from dataclasses import asdict, replace
import unittest
from unittest.mock import patch

import numpy as np

from desktop import native_spectral
from desktop.imaging import Settings, render_pixels
from desktop.raw_source import display_image, source_pixels
from shared.auto_adjust import analyze_auto, _wb_matrix
from shared.color_management import encode
from shared.levels import LevelChannel, LevelsSet, normalize_levels, apply_levels, apply_hdr_endpoints


@unittest.skipUnless(native_spectral.available(), 'Windows Vulkan runtime required')
class LevelsAutoIntegration(unittest.TestCase):
    def test_levels_hdr_proposals_cache_source_and_reset(self):
        source = np.random.default_rng(17).uniform(.015,.985,(73,127,3)).astype(np.float32)
        original = source.copy()
        levels = LevelsSet(master=LevelChannel(.04,.94,1.2,.03,.96),
                           red=LevelChannel(.02,.98,.9,.01,.99),
                           green=LevelChannel(gamma=1.1),blue=LevelChannel(output_white=.94))
        edits = Settings(levels=levels, whites=-32, blacks=18, lens_correction=False, defringe=False)
        cpu = apply_levels(apply_hdr_endpoints(source.copy(),edits.whites,edits.blacks),levels)
        gpu = native_spectral.process_editor(source,edits,stage='post')
        np.testing.assert_allclose(gpu,cpu,atol=3e-6,rtol=3e-6)
        np.testing.assert_array_equal(source,original)
        self.assertEqual(Settings.from_mapping(asdict(edits)),edits)
        self.assertGreater(normalize_levels({'master':{'black':1,'white':0}}).master.white,
                           normalize_levels({'master':{'black':1,'white':0}}).master.black)
        # Identity is a strict bypass, including the otherwise out-of-range
        # float values needed by later exposure/colour operations.
        extreme = np.array([[[-.03,1.8,.5]]],np.float32)
        np.testing.assert_array_equal(apply_levels(extreme.copy(),LevelsSet()),extreme)
        np.testing.assert_array_equal(native_spectral.process_editor(extreme,{},clamp_output=False),extreme)
        image = display_image(source)
        image._spektrafilm_preview_cache = {}
        film = replace(edits,film_enabled=True,grain=0,halation=0,levels=LevelsSet(),whites=0,blacks=0)
        from desktop import imaging
        real_spectral = imaging._spectral
        with patch.object(imaging,'_spectral',wraps=real_spectral) as calls:
            neutral = render_pixels(image,film,preview=True)
            changed = render_pixels(image,replace(film,levels=levels,whites=-32,blacks=18),preview=True)
            reset = render_pixels(image,film,preview=True)
        self.assertEqual(calls.call_count,1,'post-only levels/HDR reuse the cached film result')
        self.assertGreater(float(np.max(np.abs(changed-neutral))),.01)
        np.testing.assert_array_equal(reset,neutral)
        np.testing.assert_array_equal(source_pixels(image),original)

        # A known cast is inverted with the exact public Bradford adjustment
        # model; the estimator must propose a neutral result without editing it.
        neutral_linear = np.repeat(np.linspace(.04,.6,73*127,dtype=np.float32).reshape(73,127,1),3,axis=2)
        cast = neutral_linear @ np.linalg.inv(_wb_matrix(4800,18)).T
        wb = analyze_auto(cast,'white_balance',Settings(),source_linear=True)
        self.assertGreater(wb['confidence'],.4)
        corrected = cast @ _wb_matrix(wb['changes']['temperature'],wb['changes']['tint']).T
        self.assertLess(float(np.std(corrected.mean((0,1))/corrected.mean())),.005)
        for kind in ('levels','tone'):
            proposal = analyze_auto(encode(neutral_linear),'levels' if kind=='levels' else kind,edits)
            self.assertGreater(proposal['confidence'],.5)
            self.assertTrue(proposal['changes'])
        flat = np.full((240,320,3),.4,np.float32)
        self.assertEqual(analyze_auto(flat,'geometry',Settings())['changes'],{})
        # Multiple long near-horizontal and vertical lines provide agreement.
        from PIL import Image, ImageDraw
        grid = Image.new('RGB',(480,360),'white'); draw=ImageDraw.Draw(grid)
        for y in range(40,340,50):draw.line((15,y,465,y),fill='black',width=3)
        for x in range(40,460,70):draw.line((x,15,x,345),fill='black',width=3)
        tilted=np.asarray(grid.rotate(3, resample=Image.Resampling.BILINEAR,fillcolor='white'))
        geometry=analyze_auto(tilted,'geometry',Settings())
        self.assertGreater(geometry['confidence'],.5,geometry)
        self.assertAlmostEqual(abs(geometry['changes']['geometry']['rotation']),3,delta=.3)

    def test_brightness_is_independent_from_exposure_and_preserves_post_cache(self):
        from desktop import imaging
        from shared.levels import apply_brightness
        source=np.linspace(.015,.985,47*83*3,dtype=np.float32).reshape(47,83,3)
        original=source.copy();settings=Settings(brightness=63,lens_correction=False,defringe=False)
        gpu=render_pixels(display_image(source),settings)
        with patch.dict('os.environ',{'SPEKTRAFILM_COMPUTE':'cpu'}):
            cpu=render_pixels(display_image(source),settings)
        np.testing.assert_allclose(gpu,cpu,atol=2e-6,rtol=2e-6)
        self.assertEqual(Settings.from_mapping(asdict(settings)),settings)
        np.testing.assert_array_equal(source,original)
        patches=np.array([[[0.,0.,0.],[.5,.5,.5],[1.5,1.5,1.5]]],np.float32)
        bright=native_spectral.process_editor(patches,{'brightness':80},stage='post',clamp_output=False)
        exposed=native_spectral.process_editor(patches,{},stage='all',exposure_ev=.8,clamp_output=False)
        self.assertGreater(float(bright[0,1,0]),.6)
        np.testing.assert_allclose(bright[0,2],patches[0,2],atol=2e-6)
        self.assertGreater(float(exposed[0,2,0]),float(bright[0,2,0])+.1)
        np.testing.assert_array_equal(bright[0,0],patches[0,0])
        self.assertGreater(float(np.max(np.abs(bright-exposed))),.1)
        film=replace(settings,film_enabled=True,grain=0,halation=0,brightness=0)
        image=display_image(source);image._spektrafilm_preview_cache={}
        with patch.object(imaging,'_spectral',wraps=imaging._spectral) as calls:
            neutral=render_pixels(image,film,preview=True)
            changed=render_pixels(image,replace(film,brightness=63),preview=True)
            reset=render_pixels(image,film,preview=True)
        self.assertEqual(calls.call_count,1)
        self.assertGreater(float(np.max(np.abs(changed-neutral))),.02)
        np.testing.assert_array_equal(reset,neutral)


if __name__=='__main__':unittest.main()
