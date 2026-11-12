import sys
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch
from pathlib import Path
import numpy as np
from PIL import Image
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor'))
from desktop.imaging import *

class ImagingTests(unittest.TestCase):
    def test_spectral_simulator_reuses_pipeline_for_same_film_and_paper(self):
        from desktop import imaging
        simulator=Mock()
        simulator.process.side_effect=lambda values:values+1
        imaging._SPECTRAL_CONTEXTS.clear()
        imaging._SPECTRAL_CONTEXT_SIGNATURES.clear()
        with patch('spektrafilm.Simulator',return_value=simulator) as build, patch('spektrafilm.runtime.params_builder.digest_params',side_effect=lambda params:params):
            first=imaging._process_spectral_cached(np.zeros((2,2,3)),object(),('film','paper'))
            second=imaging._process_spectral_cached(np.ones((2,2,3)),object(),('film','paper'))
        self.assertEqual(build.call_count,1)
        simulator.update_params.assert_called_once()
        np.testing.assert_array_equal(first,np.ones((2,2,3)))
        np.testing.assert_array_equal(second,np.full((2,2,3),2))

    def test_unchanged_spectral_context_skips_parameter_digest_and_update(self):
        from desktop import imaging
        simulator=Mock()
        simulator.process.side_effect=lambda values:values
        imaging._SPECTRAL_CONTEXTS.clear()
        imaging._SPECTRAL_CONTEXT_SIGNATURES.clear()
        signature=('same-render-settings',)
        with patch('spektrafilm.Simulator',return_value=simulator) as build, patch('spektrafilm.runtime.params_builder.digest_params',side_effect=lambda params:params) as digest:
            imaging._process_spectral_cached(np.zeros((2,2,3)),object(),('film','paper'),signature)
            imaging._process_spectral_cached(np.ones((2,2,3)),object(),('film','paper'),signature)
        build.assert_called_once()
        digest.assert_called_once()
        simulator.update_params.assert_not_called()
        self.assertEqual(simulator.process.call_count,2)

    def test_repeated_full_spectral_render_reuses_initialized_context(self):
        from types import SimpleNamespace
        from desktop import imaging
        simulator=Mock()
        simulator.process.side_effect=lambda values:values.copy()
        imaging._SPECTRAL_CONTEXTS.clear()
        imaging._SPECTRAL_CONTEXT_SIGNATURES.clear()
        params=SimpleNamespace(
            film=SimpleNamespace(is_positive=False),
            io=SimpleNamespace(),
            camera=SimpleNamespace(),
            enlarger=SimpleNamespace(),
            print_render=SimpleNamespace(glare=SimpleNamespace()),
            settings=SimpleNamespace(),
            film_render=SimpleNamespace(grain=SimpleNamespace(),halation=SimpleNamespace()),
        )
        image=np.full((3,4,3),.4,dtype=np.float64)
        settings=Settings(spectral=True)
        with patch('spektrafilm.init_params',return_value=params) as init_params, patch('spektrafilm.Simulator',return_value=simulator), patch('spektrafilm.runtime.params_builder.digest_params',side_effect=lambda value:value) as digest:
            first=imaging._spectral(image,settings)
            second=imaging._spectral(image,settings)
            third=imaging._spectral(image,replace(settings,exposure=.5))
        self.assertEqual(init_params.call_count,2)
        init_params.assert_called_with(settings.stock,'kodak_portra_endura')
        self.assertEqual(digest.call_count,2)
        simulator.update_params.assert_called_once()
        self.assertEqual(simulator.process.call_count,3)
        np.testing.assert_array_equal(first,second)
        np.testing.assert_array_equal(second,third)

    def test_full_spectral_preview_uses_upstream_preview_mode(self):
        image=Image.new('RGB',(13,9),(120,80,60))
        with patch('desktop.imaging._spectral',return_value=np.full((9,13,3),.5,dtype=np.float32)) as spectral:
            render(image,Settings(spectral=True),preview=True)
        self.assertTrue(spectral.call_args.kwargs['preview'])

    def test_spectral_preprocess_reuses_normalized_float64_rgb_without_mutating_it(self):
        from spektrafilm import init_params
        from spektrafilm.runtime.params_builder import digest_params
        from spektrafilm.runtime.pipeline import SimulationPipeline
        params=init_params('kodak_portra_400','kodak_portra_endura')
        params.camera.auto_exposure=False
        simulator=SimulationPipeline(digest_params(params))
        source=np.random.default_rng(48).random((12,17,3))
        original=source.copy()
        prepared=simulator._preprocess(source)
        self.assertTrue(np.shares_memory(prepared,source))
        np.testing.assert_array_equal(prepared,source)
        simulator.process(source)
        np.testing.assert_array_equal(source,original)

    def test_preview_grain_change_reuses_exposure_tap_and_matches_cold_render(self):
        from desktop import imaging
        from spektrafilm import Simulator, init_params
        from spektrafilm.runtime.params_builder import digest_params

        rng=np.random.default_rng(71)
        image=Image.fromarray(rng.integers(12,244,(48,64,3),dtype=np.uint8))
        image._spektrafilm_preview_cache={}
        settings=Settings(spectral=True,grain=12,halation=0)
        imaging._SPECTRAL_CONTEXTS.clear()
        imaging._SPECTRAL_CONTEXT_SIGNATURES.clear()
        init_params=imaging.init_film_params
        def deterministic_params(stock,paper):
            params=init_params(stock,paper)
            params.debug.deactivate_stochastic_effects=True
            return params
        with patch('desktop.imaging.init_film_params',side_effect=deterministic_params):
            render(image,settings,preview=True)
            self.assertIn('log_e_film',image._spektrafilm_spectral_stage_cache)

            with patch.object(Simulator,'process_tap',autospec=True,side_effect=Simulator.process_tap) as tapped:
                cached=render(image,replace(settings,grain=28),preview=True)
        self.assertEqual(tapped.call_count,2)
        self.assertEqual(tapped.call_args.kwargs['inject'],'log_e_film')

        image._spektrafilm_preview_cache={}
        image._spektrafilm_spectral_stage_cache={}
        with patch('desktop.imaging.init_film_params',side_effect=deterministic_params):
            cold=render(image,replace(settings,grain=28),preview=True)
        np.testing.assert_array_equal(np.asarray(cached),np.asarray(cold))

    def test_srgb_roundtrip(self):
        rgb=np.linspace(0,1,301)
        np.testing.assert_allclose(srgb_encode(srgb_decode(rgb)),rgb,atol=1e-6)
    def test_white_balance_has_neutral_reference_and_warm_shift(self):
        from desktop import imaging
        matrix=np.asarray(imaging._color_matrix(6500,0,(0,0,0,0,0,0))).reshape(3,3)
        np.testing.assert_allclose(matrix,np.eye(3),atol=1e-12)
        neutral=np.full((3,4,3),128,dtype=np.uint8)
        warmed=imaging._prepare_source(neutral,Settings(temperature=3200))
        self.assertGreater(float(warmed[1,1,0]),float(warmed[1,1,2]))
    def test_interactive_exposure_keeps_white_balance_preparation(self):
        from PIL import ImageFilter
        identity=ImageFilter.Color3DLUT.generate(8,lambda r,g,b:(r,g,b))
        image=Image.new('RGB',(9,7),(128,128,128))
        with patch('desktop.imaging._interactive_filter',return_value=identity),patch('desktop.imaging._halation'):
            balanced=render_interactive(image,Settings(exposure=.8,temperature=3200,grain=0,halation=0))
            neutral=render_interactive(image,Settings(exposure=.8,grain=0,halation=0))
        self.assertFalse(np.array_equal(np.asarray(balanced),np.asarray(neutral)))
    def test_grain_size_changes_spatial_texture_without_changing_size(self):
        image=Image.fromarray(np.full((41,57,3),128,dtype=np.uint8))
        fine=render(image,Settings(grain=70,grain_size=.5,halation=0))
        coarse=render(image,Settings(grain=70,grain_size=2,halation=0))
        self.assertEqual(fine.size,image.size)
        self.assertEqual(coarse.size,image.size)
        self.assertFalse(np.array_equal(np.asarray(fine),np.asarray(coarse)))
    def test_lut_orientation_and_interpolation(self):
        b,g,r=np.meshgrid(*[np.linspace(0,1,3)]*3,indexing='ij')
        lut=np.stack([r,g,b],axis=-1)
        sample=np.random.default_rng(2).random((9,13,3))
        np.testing.assert_allclose(apply_lut(sample,lut),sample,atol=1e-6)
    def test_sampled_stocks_are_distinct_and_finite(self):
        sample=np.array([[[.2,.4,.7],[.8,.6,.4],[.05,.05,.05]]],np.float32)
        outputs=[apply_lut(sample,load_lut(s['id'])) for s in catalog()]
        self.assertGreaterEqual(len(outputs),20)
        for out in outputs: self.assertTrue(np.isfinite(out).all())
        self.assertFalse(np.allclose(outputs[0],outputs[1]))
        self.assertEqual(len({load_lut(s['id']).tobytes() for s in catalog()}),len(catalog()))

    def test_cached_film_base_keeps_each_adjustment_exact(self):
        image=Image.fromarray(np.random.default_rng(4).integers(0,255,(43,67,3),dtype=np.uint8))
        image._spektrafilm_preview_cache={}
        for settings in [Settings(),Settings(grain=43,warmth=13),Settings(contrast=21,saturation=19),Settings(exposure=.7),Settings(halation=37),Settings(strength=52)]:
            expected=render(image.copy(),settings)
            np.testing.assert_array_equal(np.asarray(render(image,settings)),np.asarray(expected))
    def test_export_and_original_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            src=Path(directory)/'input.png'; dst=Path(directory)/'output.jpg'
            Image.new('RGB',(101,79),(175,125,75)).save(src)
            original=src.read_bytes()
            export_photo(str(src),str(dst),Settings(),max_edge=70)
            with Image.open(dst) as im:
                self.assertEqual(im.size,(70,55))
                self.assertIn('icc_profile',im.info)
            self.assertEqual(original,src.read_bytes())
            with self.assertRaises(FileExistsError): export_photo(str(src),str(dst),Settings())
    def test_zero_strength_is_original(self):
        rgb=np.random.default_rng(4).integers(0,255,(23,31,3),dtype=np.uint8)
        result=render(Image.fromarray(rgb),Settings(strength=0,exposure=0,grain=100))
        np.testing.assert_array_equal(result,rgb)
        exposed=render(Image.fromarray(rgb),Settings(strength=0,exposure=1,grain=100))
        self.assertFalse(np.array_equal(exposed,rgb))

    def test_film_can_be_disabled_without_skipping_basic_adjustments(self):
        from desktop import imaging
        rgb=np.zeros((12,16,3),dtype=np.uint8)
        rgb[:,:8]=(75,115,155);rgb[:,8:]=(185,125,65)
        image=Image.fromarray(rgb)
        settings=Settings(film_enabled=False,spectral=True,exposure=.7,contrast=18,
                          saturation=22,vibrance=45,calibration_blue_hue=30,
                          grain=100,halation=100)
        with patch('desktop.imaging._spectral',side_effect=AssertionError('film engine must be bypassed')), \
                patch('desktop.imaging.load_lut',side_effect=AssertionError('film LUT must be bypassed')):
            result=render(image,settings)
            interactive=render_interactive(image,settings)
        self.assertEqual(result.size,image.size)
        self.assertFalse(np.array_equal(np.asarray(result),rgb))
        np.testing.assert_array_equal(np.asarray(interactive),np.asarray(result))

    def test_full_size_export_uses_film_policy_for_legacy_adjustments(self):
        from desktop import imaging
        with tempfile.TemporaryDirectory() as directory:
            src=Path(directory)/'input.png'
            rgb=np.random.default_rng(16).integers(10,246,(29,41,3),dtype=np.uint8)
            Image.fromarray(rgb).save(src)
            original=src.read_bytes()
            legacy=Settings(film_enabled=False,exposure=.6,temperature=4100,tint=17,
                            contrast=19,saturation=-13,vibrance=38,highlights=-12,
                            shadows=21,black_point=3,white_point=96,gamma=.9,
                            calibration_red_hue=15,calibration_blue_saturation=24,
                            vignette=18,lens_correction=True,defringe=True)
            def spectral(pixels,settings,**kwargs):
                self.assertTrue(settings.spectral);self.assertTrue(settings.film_enabled)
                self.assertEqual(settings.temperature,6500);self.assertEqual(settings.contrast,0)
                return pixels.astype(np.float32)/255
            with patch('desktop.imaging._spectral',side_effect=spectral):
                expected=render(read_photo(str(src)),imaging.film_settings(legacy))
                for extension in ('tif','jpg'):
                    dst=Path(directory)/f'output.{extension}'
                    self.assertEqual(imaging.export_photo(str(src),str(dst),legacy,quality=100),(41,29))
                    with Image.open(dst) as exported:
                        exported.load();self.assertEqual(exported.size,(41,29));actual=np.asarray(exported)
                    if extension=='tif':
                        import tifffile
                        with tifffile.TiffFile(dst) as file:
                            self.assertEqual(file.pages[0].bitspersample,16)
                            high=file.asarray().astype(np.float32)/65535
                        expected_float=render_pixels(read_photo(str(src)),imaging.film_settings(legacy))
                        np.testing.assert_allclose(high,expected_float,atol=.5/65535+1e-7,rtol=0)
                    else:self.assertLessEqual(np.abs(actual.astype(np.int16)-np.asarray(expected,dtype=np.int16)).mean(),1.5)
            self.assertEqual(src.read_bytes(),original)

    def test_vignette_remains_a_basic_adjustment_when_film_is_off(self):
        image=Image.new('RGB',(51,37),(180,140,110))
        plain=render(image,Settings(film_enabled=False))
        vignetted=render(image,Settings(film_enabled=False,vignette=80))
        self.assertNotEqual(vignetted.getpixel((0,0)),plain.getpixel((0,0)))
        self.assertEqual(vignetted.getpixel((25,18)),plain.getpixel((25,18)))

    def test_vibrance_changes_muted_colors_and_is_validated(self):
        muted=np.tile(np.array([[[132,126,120],[176,119,65]]],dtype=np.uint8),(16,1,1))
        image=Image.fromarray(muted)
        neutral=render(image,Settings(film_enabled=False))
        vivid=render(image,Settings(film_enabled=False,vibrance=70))
        self.assertFalse(np.array_equal(np.asarray(neutral),np.asarray(vivid)))
        self.assertEqual(Settings.from_mapping({'vibrance':140}).vibrance,100)

    def test_product_settings_always_enable_film_even_for_legacy_disabled_records(self):
        from desktop.controller import _full_settings
        self.assertTrue(_full_settings().film_enabled)
        self.assertTrue(_full_settings({'exposure':.2}).film_enabled)
        self.assertTrue(_full_settings({'film_enabled':False}).film_enabled)

    def test_thumbnail_is_bounded_and_keeps_source_dimensions(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'large.png'
            Image.new('RGB',(2400,1600),(100,140,180)).save(path)
            thumb=read_thumbnail(str(path),180)
            self.assertLessEqual(max(thumb.size),180)
            self.assertEqual(thumb.info['source_size'],(2400,1600))

    def test_lut_chunk_boundaries_and_dtype(self):
        b,g,r=np.meshgrid(*[np.linspace(0,1,3)]*3,indexing='ij')
        lut=np.stack([r,g,b],axis=-1)
        sample=np.random.default_rng(8).uniform(-.2,1.2,(19,27,3))
        result=apply_lut(sample,lut,chunk_pixels=17)
        self.assertEqual(result.dtype,np.float32)
        np.testing.assert_allclose(result,np.clip(sample,0,1),atol=2e-7)

    def test_saved_settings_are_validated(self):
        for invalid in [[],None,'bad',{'exposure':'2','grain':float('nan'),'strength':True}]:
            self.assertEqual(Settings.from_mapping(invalid),Settings())
        s=Settings.from_mapping({'exposure':99,'grain':-5,'spectral':'false','stock':'unknown'})
        self.assertEqual(s.exposure,3)
        self.assertEqual(s.grain,0)
        self.assertFalse(s.spectral)
        self.assertEqual(s.stock,Settings().stock)
        self.assertEqual(Settings.from_mapping({'grain_size':99}).grain_size,2.5)

    def test_failed_export_leaves_no_incomplete_file(self):
        with tempfile.TemporaryDirectory() as directory:
            src=Path(directory)/'input.png';dst=Path(directory)/'output.jpg'
            Image.new('RGB',(11,9)).save(src)
            with patch('PIL.Image.Image.save',side_effect=OSError('encoder failed')):
                with self.assertRaises(OSError): export_photo(str(src),str(dst),Settings())
            self.assertFalse(dst.exists())
            self.assertEqual(list(Path(directory).glob('.spektrafilm-*')),[])

    def test_export_never_overwrites_a_racing_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            src=Path(directory)/'input.png';dst=Path(directory)/'output.png'
            Image.new('RGB',(11,9)).save(src)
            def other_writer(image,settings,**kwargs):
                dst.write_bytes(b'concurrent writer')
                return image
            with patch('desktop.imaging.render',side_effect=other_writer):
                with self.assertRaises(FileExistsError): export_photo(str(src),str(dst),Settings())
            self.assertEqual(dst.read_bytes(),b'concurrent writer')

    def test_exif_orientation_is_applied(self):
        with tempfile.TemporaryDirectory() as directory:
            src=Path(directory)/'rotated.jpg'
            exif=Image.Exif();exif[274]=6
            Image.new('RGB',(101,77),(100,140,180)).save(src,exif=exif)
            self.assertEqual(read_photo(str(src)).size,(77,101))

    def test_all_output_formats_are_readable_and_tagged(self):
        with tempfile.TemporaryDirectory() as directory:
            src=Path(directory)/'input.png'
            Image.new('RGB',(17,13),(100,140,180)).save(src)
            for suffix in ['png','jpg','tif']:
                dest=Path(directory)/('out.'+suffix)
                self.assertEqual(export_photo(str(src),str(dest),Settings()),(17,13))
                with Image.open(dest) as image:
                    image.load()
                    self.assertEqual(image.mode,'RGB')
                    self.assertTrue(image.info.get('icc_profile'))

if __name__=='__main__': unittest.main()
