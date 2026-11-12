import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'vendor'))
sys.path.insert(0, str(ROOT / 'android/app/src/main/python'))

import studio_spectral


class TapSimulator:
    """Model a stateful resize service and a development stage that mutates input."""
    def __init__(self, params):
        self.params = params
        self.pixel_size = None
        self.exposure_calls = 0
        self.preprocess_calls = 0
        self.develop_calls = 0
        self.full_calls = 0
        self.updates = 0
        self._pipeline = SimpleNamespace(process=self.process_tap)

    def update_params(self, params):
        self.params = params
        self.pixel_size = None
        self.updates += 1

    def process(self, values):
        self.full_calls += 1
        exposed = self.process_tap(values, inject='rgb_in', collect='log_e_film')
        return self.process_tap(exposed, inject='log_e_film', collect='rgb_out')

    def process_tap(self, values, *, inject, collect):
        if inject == 'rgb_in':
            self.pixel_size = 1.0
            if collect == 'rgb_pre':
                self.preprocess_calls += 1
                return values
            if collect != 'log_e_film':
                raise AssertionError(collect)
            self.exposure_calls += 1
            return values * .75
        if inject != 'log_e_film' or collect != 'rgb_out':
            raise AssertionError((inject, collect))
        if self.pixel_size is None:
            raise AssertionError('development requires initialized pixel size')
        self.develop_calls += 1
        values *= .7 + self.params['grain']*.1 + self.params['grain_size']*.01
        if self.params['grain_type'] != 'classic':
            values += .01
        return values


def tap_params(stock, width, height, source_width, source_height,
               exposure, grain, grain_size, grain_type, halation, preview_mode):
    return {'grain':grain, 'grain_size':grain_size, 'grain_type':grain_type}


class MobileSpectralBridgeTests(unittest.TestCase):
    def setUp(self):
        self.clear_caches()

    def tearDown(self):
        self.clear_caches()

    @staticmethod
    def clear_caches():
        studio_spectral._SIMULATORS.clear()
        studio_spectral._SIMULATOR_SIGNATURES.clear()
        studio_spectral._PREVIEW_FILM_BASES.clear()
        studio_spectral._PREVIEW_EXPOSURES.clear()

    @staticmethod
    def preview(pixels, **changes):
        settings=dict(stock='stock',exposure=0,grain=.18,halation=.2,strength=1,
                      preview_mode=True)
        settings.update(changes)
        return studio_spectral.render_argb(pixels.tobytes(),pixels.shape[1],pixels.shape[0],**settings)

    def test_preview_grain_edits_reuse_exposure_and_restore_resize_state(self):
        pixels=np.array([[0xff123456,0xffabcdef],[0xff654321,0xff987654]],dtype='<u4')
        variants=({}, {'grain':.6}, {'grain':.6,'grain_type':'fine'},
                  {'grain':.6,'grain_type':'coarse','grain_size':1.8})
        with patch.object(studio_spectral,'_make_params',side_effect=tap_params), \
                patch.object(studio_spectral,'Simulator',side_effect=TapSimulator):
            cached=[self.preview(pixels,**variant) for variant in variants]
            simulator=next(iter(studio_spectral._SIMULATORS.values()))
            self.assertEqual(simulator.exposure_calls,1)
            self.assertEqual(simulator.preprocess_calls,3)
            self.assertEqual(simulator.develop_calls,4)
            self.assertEqual(simulator.updates,3)
            self.assertEqual(simulator.full_calls,0)
            self.assertNotEqual(cached[0],cached[1])
            self.assertNotEqual(cached[1],cached[2])
            self.clear_caches()
            with patch.object(studio_spectral,'_MAX_PREVIEW_CACHE_PIXELS',0):
                complete=[self.preview(pixels,**variant) for variant in variants]
        self.assertEqual(cached,complete)

    def test_exposure_cache_invalidates_for_every_input_dependency(self):
        original=np.array([[0xff123456,0xffabcdef],[0xff654321,0xff987654]],dtype='<u4')
        variants=[{'stock':'other'}, {'exposure':.5}, {'halation':.4},
                  {'temperature':3200}, {'tint':20}, {'red_hue':15},
                  {'red_saturation':15}, {'green_hue':15}, {'green_saturation':15},
                  {'blue_hue':15}, {'blue_saturation':15},
                  {'source_width':20}, {'source_height':20}]
        for changes in variants:
            with self.subTest(changes=changes):
                self.clear_caches()
                created=[]
                def create(params):
                    simulator=TapSimulator(params)
                    created.append(simulator)
                    return simulator
                with patch.object(studio_spectral,'_make_params',side_effect=tap_params), \
                        patch.object(studio_spectral,'Simulator',side_effect=create):
                    self.preview(original)
                    self.preview(original,grain=.6,**changes)
                self.assertEqual(sum(s.exposure_calls for s in created),2)
        for changed in (original.copy(),original.reshape(1,4)):
            self.clear_caches()
            if changed.shape==original.shape:
                changed[-1,-1] ^= np.uint32(1)
            with patch.object(studio_spectral,'_make_params',side_effect=tap_params), \
                    patch.object(studio_spectral,'Simulator',side_effect=TapSimulator):
                self.preview(original)
                self.preview(changed,grain=.6)
                self.assertEqual(next(iter(studio_spectral._SIMULATORS.values())).exposure_calls,2)
        self.clear_caches()
        created=[]
        def create(params):
            created.append(TapSimulator(params))
            return created[-1]
        with patch.object(studio_spectral,'_make_params',side_effect=tap_params), \
                patch.object(studio_spectral,'Simulator',side_effect=create), \
                patch.object(studio_spectral,'print_for_stock',side_effect=['paper-a','paper-b']):
            self.preview(original)
            self.preview(original,grain=.6)
        self.assertEqual(sum(s.exposure_calls for s in created),2)

    def test_export_and_offset_tiles_never_read_or_populate_preview_cache(self):
        pixels=np.full((2,2),0xff808080,dtype='<u4')
        with patch.object(studio_spectral,'_make_params',side_effect=tap_params), \
                patch.object(studio_spectral,'Simulator',side_effect=TapSimulator):
            self.preview(pixels)
            before=tuple((key,id(value)) for cache in
                         (studio_spectral._PREVIEW_EXPOSURES,studio_spectral._PREVIEW_FILM_BASES)
                         for key,value in cache.items())
            for changes in ({'preview_mode':False}, {'origin_x':1}, {'origin_y':1}, {'seed_offset':1}):
                self.preview(pixels,**changes)
            simulator=next(iter(studio_spectral._SIMULATORS.values()))
            self.assertEqual(simulator.full_calls,4)
            after=tuple((key,id(value)) for cache in
                        (studio_spectral._PREVIEW_EXPOSURES,studio_spectral._PREVIEW_FILM_BASES)
                        for key,value in cache.items())
            self.assertEqual(before,after)

    def test_preview_planes_are_owned_immutable_and_share_a_strict_budget(self):
        pixels=np.full((2,2),0xff808080,dtype='<u4')
        with patch.object(studio_spectral,'_make_params',side_effect=tap_params), \
                patch.object(studio_spectral,'Simulator',side_effect=TapSimulator), \
                patch.object(studio_spectral,'_MAX_PREVIEW_CACHE_BYTES',192):
            for grain in (.1,.2,.3,.4,.5):
                self.preview(pixels,grain=grain)
                caches=(studio_spectral._PREVIEW_EXPOSURES,studio_spectral._PREVIEW_FILM_BASES)
                values=[value for cache in caches for value in cache.values()]
                self.assertLessEqual(sum(value.nbytes for value in values),192)
                self.assertLessEqual(len(caches[0]),1)
                self.assertLessEqual(len(caches[1]),2)
                self.assertTrue(all(not value.flags.writeable for value in values))
            self.assertEqual(next(iter(studio_spectral._SIMULATORS.values())).exposure_calls,1)

    def test_actual_64px_preview_taps_match_complete_bridge(self):
        # Real bridge and seeded grain; unseeded paper glare is disabled only
        # for this deterministic cache comparison.
        y,x=np.mgrid[:48,:64]
        pixels=(np.uint32(0xff000000)|((x*255//63).astype(np.uint32)<<16)
                |((y*255//47).astype(np.uint32)<<8)|((x+y)*255//110).astype(np.uint32))
        variants=({}, {'grain':.6,'grain_type':'fine'},
                  {'grain':.6,'grain_type':'coarse','grain_size':1.8})
        def sequence():
            result=[]
            for variant in variants:
                # Paper glare remains stochastic in preview mode. Repeat its
                # real draw sequence on both paths without changing production.
                np.random.seed(127)
                result.append(self.preview(pixels,stock='kodak_portra_400',**variant))
            return result
        state=np.random.get_state()
        make_params=studio_spectral._make_params
        def deterministic_params(*args,**kwargs):
            params=make_params(*args,**kwargs)
            params.print_render.glare.active=False
            return params
        try:
            with patch.object(studio_spectral,'_make_params',side_effect=deterministic_params):
                cached=sequence()
                self.clear_caches()
                with patch.object(studio_spectral,'_MAX_PREVIEW_CACHE_PIXELS',0):
                    complete=sequence()
        finally:
            np.random.set_state(state)
        self.assertEqual(cached,complete)

    def test_tile_calls_reuse_pipeline_until_render_settings_change(self):
        params = SimpleNamespace(
            film=SimpleNamespace(is_positive=False),
            camera=SimpleNamespace(),
            io=SimpleNamespace(),
            settings=SimpleNamespace(),
            film_render=SimpleNamespace(
                grain=SimpleNamespace(),
                halation=SimpleNamespace(),
            ),
        )
        simulator = Mock()
        simulator.process.side_effect = lambda values: values.copy()
        pixels = np.array([0xFF123456, 0xFFABCDEF], dtype='<u4')
        source = pixels.tobytes()

        with patch.object(studio_spectral, 'init_film_params', return_value=params) as init_params, \
                patch.object(studio_spectral, 'Simulator', return_value=simulator) as create_simulator, \
                patch.object(studio_spectral, 'digest_params', side_effect=lambda value: value):
            first = studio_spectral.render_argb(source, 2, 1, 'stock', 0, .18, .2, 1)
            second = studio_spectral.render_argb(source, 2, 1, 'stock', 0, .18, .2, 1, seed_offset=4)
            changed = studio_spectral.render_argb(source, 2, 1, 'stock', .5, .18, .2, 1)

        self.assertEqual(first, second)
        self.assertEqual(first, changed)
        np.testing.assert_array_equal(np.frombuffer(first,dtype='<u4'),pixels)
        self.assertEqual(init_params.call_count, 2)
        create_simulator.assert_called_once()
        self.assertEqual(simulator.update_params.call_count, 1)
        self.assertEqual(simulator.process.call_count, 3)

    def test_color_matrix_uses_neutral_reference_and_applies_white_balance(self):
        matrix=studio_spectral._color_matrix(6500.0,0.0,(0,0,0,0,0,0))
        np.testing.assert_allclose(matrix,np.eye(3),atol=1e-12)
        image=np.full((3,4,3),128/255,dtype=np.float64)
        original=image.copy()
        studio_spectral._prepare_rgb(image,3200,0,(0,0,0,0,0,0))
        self.assertGreater(float(image[1,1,0]),float(image[1,1,2]))
        np.testing.assert_array_equal(original,np.full((3,4,3),128/255,dtype=np.float64))

    def test_lut_pipeline_applies_new_tone_controls_and_preserves_default(self):
        packed=np.array([[0xff808080,0xffc08040]],dtype='<u4')
        b,g,r=np.meshgrid(np.linspace(0,1,2,dtype=np.float32),np.linspace(0,1,2,dtype=np.float32),np.linspace(0,1,2,dtype=np.float32),indexing='ij')
        identity=np.stack((r,g,b),axis=-1).astype('<f4').tobytes()
        args=(packed.tobytes(),2,1,identity,2,0,0,0,1)
        baseline=studio_spectral.render_lut_argb(*args)
        changed=studio_spectral.render_lut_argb(*args,temperature=3200,contrast=20,highlights=30)
        np.testing.assert_array_equal(np.frombuffer(baseline,dtype='<u4'),packed.reshape(-1))
        self.assertFalse(np.array_equal(np.frombuffer(changed,dtype='<u4'),packed.reshape(-1)))

    def test_film_off_bypasses_spectral_and_lut_but_keeps_base_controls(self):
        packed=np.array([[0xff808080,0xffc08040]],dtype='<u4')
        with patch.object(studio_spectral,'Simulator',side_effect=AssertionError('film simulator must be bypassed')):
            spectral=studio_spectral.render_argb(packed.tobytes(),2,1,'stock',.7,.8,.8,1,
                contrast=18,saturation=20,vibrance=50,film_enabled=False)
            lut=studio_spectral.render_lut_argb(packed.tobytes(),2,1,b'',2,.7,.8,.8,1,
                contrast=18,saturation=20,vibrance=50,film_enabled=False)
        self.assertFalse(np.array_equal(np.frombuffer(spectral,dtype='<u4'),packed.reshape(-1)))
        np.testing.assert_array_equal(np.frombuffer(spectral,dtype='<u4'),np.frombuffer(lut,dtype='<u4'))

    def test_grain_size_changes_mobile_preview_pattern(self):
        packed=np.full((24,32),0xff808080,dtype='<u4')
        b,g,r=np.meshgrid(np.linspace(0,1,2,dtype=np.float32),np.linspace(0,1,2,dtype=np.float32),np.linspace(0,1,2,dtype=np.float32),indexing='ij')
        identity=np.stack((r,g,b),axis=-1).astype('<f4').tobytes()
        args=(packed.tobytes(),32,24,identity,2,0,.8,0,1)
        fine=studio_spectral.render_lut_argb(*args,grain_size=.5)
        coarse=studio_spectral.render_lut_argb(*args,grain_size=2)
        self.assertFalse(np.array_equal(np.frombuffer(fine,dtype='<u4'),np.frombuffer(coarse,dtype='<u4')))


if __name__ == '__main__':
    unittest.main()
