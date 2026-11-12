"""Reference colours, neutral protection and spatial invariance for the mixer."""
import colorsys
from dataclasses import asdict
import json
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PIL import Image
from shared.hsl import BANDS, HslBand, HslSettings, apply_hsl, normalize_hsl
from shared.style_presets import import_style_json
from desktop.imaging import Settings, render, read_photo


class HslTests(unittest.TestCase):
    def test_neutral_exact_and_gray_is_never_tinted(self):
        original = np.random.default_rng(506).random((11, 32, 3), dtype=np.float32)
        copy = original.copy()
        self.assertIs(apply_hsl(copy), copy)
        np.testing.assert_array_equal(copy, original)
        gray = np.repeat(np.linspace(0, 1, 257, dtype=np.float32)[None, :, None], 3, axis=2)
        aggressive = HslSettings(**{band: HslBand(100, 100, 100) for band in BANDS})
        np.testing.assert_array_equal(apply_hsl(gray.copy(), aggressive), gray)

    def test_reference_anchor_rotation_saturation_and_lightness(self):
        # Python's standard-library HLS conversion is the independent oracle.
        for band, hue in zip(BANDS, (0, 30, 60, 120, 180, 240, 270, 300)):
            pixel = np.array([[colorsys.hls_to_rgb(hue/360, .4, .6)]], np.float64)
            for key, expected in (
                ('hue', colorsys.hls_to_rgb(((hue+15)%360)/360, .4, .6)),
                ('saturation', colorsys.hls_to_rgb(hue/360, .4, .8)),
                ('luminance', colorsys.hls_to_rgb(hue/360, .52, .6))):
                with self.subTest(band=band,key=key):
                    output = apply_hsl(pixel.copy(), HslSettings(**{band: HslBand(**{key: 50})}))
                    np.testing.assert_allclose(output[0, 0], expected, atol=1e-12)

    def test_selected_orange_does_not_change_blue_and_does_change_skin(self):
        source = np.array([[[.75, .45, .3], [.15, .35, .8]]], np.float32)
        output = apply_hsl(source.copy(), HslSettings(orange=HslBand(20, -35, 35)))
        self.assertGreater(float(np.max(abs(output[0, 0]-source[0, 0]))), .05)
        np.testing.assert_array_equal(output[0, 1], source[0, 1])

    def test_wrap_and_band_boundaries_are_continuous(self):
        settings = HslSettings(red=HslBand(80, -50, 30), orange=HslBand(-40, 40, -20))
        for boundary in (0, 30, 60, 120, 180, 240, 270, 300):
            colors = [[colorsys.hls_to_rgb(((boundary+delta)%360)/360, .45, .7) for delta in (-.0001, .0001)]]
            output = apply_hsl(np.array(colors), settings)
            self.assertLess(float(np.max(abs(output[0, 0]-output[0, 1]))), 1e-5)

    def test_tiles_strided_regions_and_float_precision(self):
        source = np.random.default_rng(507).random((139, 211, 3), dtype=np.float32)
        settings = HslSettings(green=HslBand(-65, 80, -40), red=HslBand(55, -80, 45))
        full = apply_hsl(source.copy(), settings)
        tiled = source.copy()
        for y0,y1 in ((0,1),(1,73),(73,139)):
            for x0,x1 in ((0,6),(6,111),(111,211)):
                apply_hsl(tiled[y0:y1,x0:x1], settings)
        np.testing.assert_array_equal(tiled, full)
        double = apply_hsl(source.astype(np.float64), settings)
        np.testing.assert_allclose(full, double, atol=8e-7, rtol=0)
        self.assertTrue(np.isfinite(full).all());self.assertGreaterEqual(full.min(),0);self.assertLessEqual(full.max(),1)

    def test_sanitize_old_settings_and_sidecar_roundtrip(self):
        normalized = normalize_hsl({'red': {'hue': float('nan'), 'saturation': 900, 'luminance': True}, 'orange': []})
        self.assertEqual(normalized.red,HslBand(0,100,0));self.assertEqual(normalized.orange,HslBand())
        settings = Settings.from_mapping({'hsl': asdict(normalized)})
        self.assertEqual(Settings.from_mapping(json.loads(json.dumps(asdict(settings)))),settings)
        self.assertEqual(Settings.from_mapping({}).hsl,HslSettings())

    def test_raw_preview_keeps_full_source_metadata_before_libraw_mutates_sizes(self):
        sizes=SimpleNamespace(width=6000,height=4000,flip=6)
        raw=SimpleNamespace(sizes=sizes)
        def develop(**options):
            self.assertTrue(options['half_size'])
            sizes.width=3000;sizes.height=2000
            return np.zeros((3000,2000,3),np.uint8)
        raw.postprocess=develop
        class Source:
            def __enter__(self):return raw
            def __exit__(self,*args):pass
        with patch('rawpy.imread',return_value=Source()):
            photo=read_photo('fixture.arw',960)
        self.assertEqual(photo.info['source_size'],(4000,6000))
        self.assertEqual(photo.size,(640,960))

    def test_xmp_all_24_fields_and_nested_look_do_not_overwrite_preset(self):
        attributes=' '.join(f'crs:{field}{band.capitalize()}="{index+1}"' for index,band in enumerate(BANDS)
                            for field in ('HueAdjustment','SaturationAdjustment','LuminanceAdjustment'))
        xmp=f'''<x:xmpmeta xmlns:x="adobe:ns:meta/" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/">
        <rdf:RDF><rdf:Description {attributes}><crs:Name><rdf:Alt><rdf:li>Actual preset</rdf:li></rdf:Alt></crs:Name>
        <crs:Look><rdf:Description crs:Name="Adobe Color" crs:Saturation="99"/></crs:Look>
        </rdf:Description></rdf:RDF></x:xmpmeta>'''
        preset=json.loads(import_style_json(xmp))
        self.assertEqual(preset['name'],'Actual preset');self.assertEqual(preset['settings']['saturation'],0)
        for index,band in enumerate(BANDS):
            self.assertEqual(preset['settings']['hsl'][band],dict(hue=index+1,saturation=index+1,luminance=index+1))
        self.assertIn('Adobe Color',' '.join(preset['warnings']));self.assertEqual(preset['kind'],'xmp-partial')

    def test_desktop_and_android_use_same_mixer_and_order(self):
        root=Path(__file__).resolve().parents[1]
        sys.path.insert(0,str(root/'android/app/src/main/python'))
        try:
            from studio_spectral import _apply_color_tools
            source=np.random.default_rng(508).integers(0,256,(31,43,3),dtype=np.uint8)
            hsl=HslSettings(orange=HslBand(40,-30,20),blue=HslBand(-25,35,-20))
            settings=Settings(film_enabled=False,lens_correction=False,defringe=False,hsl=hsl)
            desktop=np.asarray(render(Image.fromarray(source),settings))
            mobile=source.astype(np.float32)/255.
            _apply_color_tools(mobile,json.dumps(dict(hsl=asdict(hsl))))
            np.testing.assert_array_equal(desktop,np.clip(mobile*255+.5,0,255).astype(np.uint8))
        finally:sys.path.pop(0)


if __name__=='__main__':unittest.main()
