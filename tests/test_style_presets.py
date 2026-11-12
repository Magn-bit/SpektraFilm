from dataclasses import asdict
import json
from pathlib import Path
import unittest

import numpy as np
from PIL import Image

from desktop.imaging import Settings,render
from shared.local_masks import MaskLayer
from shared.geometry import Geometry
from shared.style_presets import STYLE_DEFAULTS,catalog,apply_style,import_style_json


XMP='''<x:xmpmeta xmlns:x="adobe:ns:meta/" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/">
<rdf:RDF><rdf:Description crs:Contrast2012="12" crs:Saturation="-8" crs:Exposure2012="1.4" crs:CameraProfile="Adobe Color">
<crs:Name><rdf:Alt><rdf:li xml:lang="x-default">Custom Look</rdf:li></rdf:Alt></crs:Name>
<crs:ToneCurvePV2012><rdf:Seq><rdf:li>0, 10</rdf:li><rdf:li>128, 140</rdf:li><rdf:li>255, 255</rdf:li></rdf:Seq></crs:ToneCurvePV2012>
</rdf:Description></rdf:RDF></x:xmpmeta>'''


class StylePresetTests(unittest.TestCase):
    def test_originals_are_named_and_distinct_and_preserve_photo_specific_edits(self):
        all_entries=catalog();self.assertEqual(all_entries[0]['id'],'none')
        neutral=apply_style(asdict(Settings(exposure=.8)),all_entries[0])
        for key,value in STYLE_DEFAULTS.items():self.assertEqual(neutral[key],value,key)
        self.assertEqual(neutral['exposure'],.8)
        entries=[entry for entry in all_entries if entry['kind']=='original'];self.assertEqual(len(entries),18)
        self.assertEqual(len({entry['id'] for entry in all_entries}),19)
        self.assertEqual(sum(e['category']=='portrait' for e in entries),8)
        self.assertEqual(sum(e['category']=='landscape' for e in entries),10)
        self.assertEqual([entry['category'] for entry in entries[:8]],['portrait']*8)
        self.assertEqual([entry['category'] for entry in entries[8:]],['landscape']*10)
        source=asdict(Settings(exposure=.8,temperature=4100,masks=(MaskLayer(id='mine'),),
                               geometry=Geometry(crop=(.1,.2,.9,.8))))
        outputs=[]
        pixels=np.random.default_rng(18).integers(30,220,(29,43,3),dtype=np.uint8)
        for entry in entries:
            self.assertEqual(entry['kind'],'original')
            self.assertEqual(entry['author'],'SpektraFilm')
            result=apply_style(source,entry)
            for key in ('exposure','temperature','tint','masks','geometry','stock','spectral','film_enabled'):
                self.assertEqual(result[key],source[key])
            self.assertEqual(apply_style(result,entry),result)
            outputs.append(render(Image.fromarray(pixels),Settings.from_mapping(dict(result,film_enabled=False))).tobytes())
        self.assertEqual(len(set(outputs)),len(entries))

    def test_xmp_conversion_is_scoped_and_has_honest_unsupported_warning(self):
        imported=json.loads(import_style_json(XMP,'look.xmp'))
        self.assertEqual(imported['name'],'Custom Look')
        self.assertEqual(imported['kind'],'xmp-partial')
        self.assertEqual(imported['settings']['contrast'],12)
        self.assertNotIn('exposure',imported['settings'])
        self.assertAlmostEqual(imported['settings']['curves']['master'][1][1],140/255)
        self.assertIn('CameraProfile',' '.join(imported['warnings']))
        self.assertIn('Exposure2012',' '.join(imported['warnings']))

    def test_wrong_or_unsafe_documents_never_turn_into_a_successful_style(self):
        for raw,filename in ((b'','empty.xmp'),(b'<no-settings/>','unknown.xmp'),
                             (b'<!DOCTYPE x><x/>','entity.xmp'),(b'abc','nikon.np3'),
                             (b'{}','unknown.cube'),(b'x'*(2*1024**2+1),'large.xmp')):
            with self.assertRaises((ValueError,Exception)):
                import_style_json(raw,filename)

    def test_imported_json_cannot_overwrite_geometry_masks_or_run_commands(self):
        data=json.dumps(dict(name='Safe parameters',settings=dict(contrast=5,exposure=3,
            geometry=dict(rotation=20),masks=[],command='unexpected')))
        imported=json.loads(import_style_json(data,'look.sfpreset'))
        self.assertEqual(set(imported['settings']),set(STYLE_DEFAULTS))
        original=asdict(Settings(exposure=-1,masks=(MaskLayer(id='mine'),)))
        updated=apply_style(original,imported)
        self.assertEqual(updated['exposure'],-1)
        self.assertEqual(updated['masks'],original['masks'])

    def test_android_parser_and_packaged_catalog_match_shared_data(self):
        root=Path(__file__).resolve().parents[1]
        self.assertEqual((root/'shared/style_presets.py').read_bytes(),
                         (root/'android/app/src/main/python/style_presets.py').read_bytes())
        for entry in catalog():
            self.assertEqual(set(entry['settings']),set(STYLE_DEFAULTS))


if __name__=='__main__':unittest.main()
