"""One bounded native desktop node: canvas gamut and viewed/raw Cineon DI.

Uses an existing real sunset photograph, not a RAW benchmark or a UI fixture.
No runtime resources or application settings are changed.
"""
from dataclasses import replace
from pathlib import Path
import json
import os
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'vendor')]
OUT = ROOT / 'output/lab-232-desktop-review'
OUT.mkdir(parents=True, exist_ok=True)
os.environ['SPEKTRAFILM_ARRAY_CACHE'] = str(OUT / 'array-cache')

import colour
import numpy as np
import tifffile
from PIL import Image, ImageDraw

from desktop import native_spectral as native
from desktop.digital_intermediate import render_codes, view_codes, view_lut
from desktop.imaging import Settings, render_pixels
from desktop.output import export_pixels, render_recipe_pixels
from shared.geometry import Geometry, apply_geometry_pixels, output_size
from shared.output_recipes import OutputRecipe


def difference(a, b):
    delta = np.abs(np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64))
    return {'max': float(delta.max()), 'mean': float(delta.mean())}


def finite(values):
    assert values.dtype == np.float32 and np.isfinite(values).all()


def picture(pixels):
    return Image.fromarray(np.rint(np.clip(pixels, 0, 1) * 255).astype(np.uint8))


def run(report):
    assert native.available(), native._INITIALIZATION_ERROR
    source = ROOT / 'output/current-ui/source-preview.jpg'
    with Image.open(source) as original:
        image = original.convert('RGB')
        image.thumbnail((320, 320), Image.Resampling.LANCZOS)
    image.info.clear()
    fixture = OUT / 'source.png'
    image.save(fixture)
    report['source'] = {'path': str(source), 'fixture': str(fixture), 'size': list(image.size),
                        'kind': 'existing real sunset photograph; bounded RGB proxy'}

    # Independent colour-science CAT02/CCTF reference. Do not compare a native
    # matrix with a second copy of the same native matrix.
    srgb = np.asarray(image, dtype=np.float32) / np.float32(255)
    wide = np.ascontiguousarray(colour.RGB_to_RGB(
        srgb, 'sRGB', 'ProPhoto RGB', chromatic_adaptation_transform='CAT02',
        apply_cctf_decoding=True, apply_cctf_encoding=True), dtype=np.float32)
    source_snapshot = wide.copy()
    spaces = ('sRGB', 'Display P3', 'Adobe RGB (1998)', 'ProPhoto RGB')
    canvas = {}
    for space in spaces:
        off = native.transform_color(wide, 'ProPhoto RGB', space, compress=False)
        expected_linear = colour.RGB_to_RGB(
            wide, 'ProPhoto RGB', space, chromatic_adaptation_transform='CAT02',
            apply_cctf_decoding=True, apply_cctf_encoding=False)
        # Colour's ordinary Adobe encoding intentionally returns NaN below
        # zero. The canvas ABI uses a signed extension for out-of-gamut RGB.
        if space == 'Adobe RGB (1998)':
            expected = np.copysign(np.abs(expected_linear)**(256/563), expected_linear)
        else:
            expected = colour.RGB_COLOURSPACES[space].cctf_encoding(expected_linear)
        finite(off)
        error = difference(off, expected)
        assert error['max'] < 2e-4, (space, 'CAT02/CCTF reference', error)
        if space == 'ProPhoto RGB':
            # Published ProPhoto matrices are rounded; colour-science has the
            # same ~4.3e-5 roundtrip residual on this photo. Bound by the
            # independent roundtrip rather than demanding an exact shortcut.
            reference_residual = difference(expected, wide)['max']
            assert difference(off, wide)['max'] < reference_residual + 2e-6, 'identity transform'
        compressed = native.transform_color(wide, 'ProPhoto RGB', space)
        finite(compressed)
        assert compressed.shape == wide.shape
        canvas[space] = {'off_vs_independent_reference': error,
                         'cam16_vs_off': difference(compressed, off),
                         'cam16_range': [float(compressed.min()), float(compressed.max())]}
    np.testing.assert_array_equal(wide, source_snapshot)
    # A real sRGB photo may never reach a wide-gamut boundary. These diagnostic
    # patches prove that selecting CAM16 actually executes a different route.
    chips = np.array([[[.90, .05, .10], [.05, .90, .10], [.05, .10, .90],
                       [.80, .80, .02], [.02, .80, .80]]], dtype=np.float32)
    cam = native.transform_color(chips, 'ProPhoto RGB', 'sRGB')
    off = native.transform_color(chips, 'ProPhoto RGB', 'sRGB', compress=False)
    finite(cam)
    finite(off)
    assert difference(cam, off)['max'] > .01
    report['canvas'] = {'spaces': canvas, 'source_unchanged': True,
                         'saturated_chips_cam16_vs_off': difference(cam, off)}
    adobe = np.array([[[-.003, .25, .1], [.12, -.001, .04]]], dtype=np.float32)
    adobe_linear = np.copysign(np.abs(adobe.astype(np.float64))**(563/256), adobe)
    expected = colour.RGB_to_RGB(adobe_linear, 'Adobe RGB (1998)', 'sRGB',
        chromatic_adaptation_transform='CAT02', apply_cctf_encoding=True)
    extended = native.transform_color(adobe, 'Adobe RGB (1998)', 'sRGB', compress=False)
    finite(extended)
    negative_error = difference(extended, expected)['max']
    assert negative_error < 3e-6, 'signed Adobe source decode'
    report['canvas']['extended_adobe_negative_decode_max_error'] = negative_error

    settings = Settings(film_enabled=True, digital_intermediate=True,
        stock='kodak_portra_400', paper='kodak_portra_endura',
        grain=0, grain_enabled=False, halation=0, halation_enabled=False,
        glare=0, dir_couplers_amount=0, lens_correction=False, defringe=False)
    raw = render_codes(image, settings)
    finite(raw)
    viewed = render_pixels(image, settings, preserve_headroom=True)
    finite(viewed)
    ordinary = render_pixels(image, replace(settings, digital_intermediate=False), preserve_headroom=True)
    finite(ordinary)
    assert difference(viewed, ordinary)['mean'] > .005, 'DI selection did not alter image'
    assert difference(viewed, raw)['mean'] > .03, 'Cineon codes mistaken for viewed RGB'
    lut = view_lut()
    assert lut.shape == (65, 65, 65, 3)
    primaries = np.array([[[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]], dtype=np.float32)
    np.testing.assert_array_equal(view_codes(primaries)[0], np.stack((lut[0, 0, -1], lut[0, -1, 0], lut[-1, 0, 0])))

    # Independent raw DI API + view transform must land on the regular image
    # route exactly once. The raw API intentionally ignores display-side edits.
    manual = native.process_editor(view_codes(raw), {}, stage='pre',
        source_color_space='ProPhoto RGB', clamp_output=False)
    manual = native.process_editor(manual, settings, stage='post', clamp_output=False)
    manual_error = difference(viewed, manual)
    assert manual_error['max'] < 3e-5, ('DI view applied missing/twice', manual_error)
    geometry = Geometry(quarter_turns=1, crop=(.1, .1, .9, .9))
    edited = replace(settings, contrast=8, brightness=5, saturation=6, geometry=geometry)
    actual = render_pixels(image, edited, preserve_headroom=True)
    expected = native.process_editor(view_codes(raw), {}, stage='pre',
        source_color_space='ProPhoto RGB', clamp_output=False)
    expected = native.process_editor(expected, edited, stage='post', clamp_output=False)
    expected = apply_geometry_pixels(expected, geometry)
    finite(actual)
    post_error = difference(actual, expected)
    assert post_error['max'] < 3e-5, ('DI post/geometry order', post_error)
    assert actual.shape[1::-1] == output_size(*image.size, geometry)
    raw_edited = render_codes(image, edited)
    np.testing.assert_array_equal(raw_edited, apply_geometry_pixels(raw, geometry))

    recipes = {
        'jpeg': OutputRecipe(quality=100),
        'tiff': OutputRecipe(id='tiff', format='tiff', bit_depth=16),
        'di': OutputRecipe(id='di', format='di', bit_depth=16, color_space='ProPhoto RGB'),
    }
    recipe_pixels = {}
    for name, recipe in recipes.items():
        values = render_recipe_pixels(fixture, edited, recipe)
        finite(values)
        recipe_pixels[name] = values
    np.testing.assert_array_equal(recipe_pixels['jpeg'], recipe_pixels['tiff'])
    np.testing.assert_array_equal(recipe_pixels['di'], raw_edited)
    ordinary_sdr = render_pixels(image, edited)
    np.testing.assert_allclose(recipe_pixels['tiff'], ordinary_sdr, atol=3e-5, rtol=0)
    paths = {'jpeg': OUT/'viewed.jpg', 'tiff': OUT/'viewed.tif', 'di': OUT/'raw-cineon-di.tif'}
    for name, path in paths.items():
        # This directory belongs exclusively to this node. _publish_export
        # rejects an existing filename, so repeat nodes choose a sibling name.
        if path.exists():
            path = path.with_stem(path.stem + '-' + str(time.time_ns()))
            paths[name] = path
        export_pixels(recipe_pixels[name], path, recipes[name])
    with tifffile.TiffFile(paths['di']) as handle:
        assert 34675 not in handle.pages[0].tags, 'raw Cineon must not claim RGB ICC'
        assert json.loads(handle.pages[0].description)['encoding'] == 'Kodak Cineon'
        raw_decoded = handle.asarray()
    np.testing.assert_array_equal(raw_decoded, np.rint(np.clip(raw_edited, 0, 1)*65535).astype(np.uint16))
    with tifffile.TiffFile(paths['tiff']) as handle:
        assert 34675 in handle.pages[0].tags, 'viewed TIFF missing RGB ICC'
        tiff_decoded = handle.asarray()
    np.testing.assert_array_equal(tiff_decoded, np.rint(np.clip(recipe_pixels['tiff'], 0, 1)*65535).astype(np.uint16))
    with Image.open(paths['jpeg']) as handle:
        assert handle.info.get('icc_profile'), 'viewed JPEG missing RGB ICC'
        jpeg_decoded = np.asarray(handle, dtype=np.float32)/255
    jpeg_error = difference(jpeg_decoded, np.clip(recipe_pixels['jpeg'], 0, 1))
    assert jpeg_error['mean'] < .008, jpeg_error
    assert difference(jpeg_decoded, raw_edited)['mean'] > .03
    report['digital_intermediate'] = {
        'lut_size': 65, 'raw_codes_not_viewed': True,
        'single_view_vs_independent_raw_api': manual_error,
        'post_then_geometry': post_error,
        'viewed_vs_paper_mean_delta': difference(viewed, ordinary)['mean'],
        'viewed_vs_raw_code_mean_delta': difference(viewed, raw)['mean'],
        'raw_ignores_display_adjustments': True,
        'output_size': list(actual.shape[1::-1]),
        'jpeg_and_tiff_share_viewed_pixels': True,
        'jpeg_readback_error': jpeg_error,
        'tiff16_exact_quantisation': True,
        'raw_di_exact_codes_no_rgb_icc': True,
        'output_paths': {name: str(path) for name, path in paths.items()},
    }
    tiles = [picture(srgb), picture(ordinary), picture(viewed), picture(raw)]
    montage = Image.new('RGB', (image.width*2, (image.height+24)*2), '#eeece6')
    draw = ImageDraw.Draw(montage)
    for index, (tile, title) in enumerate(zip(tiles, ('Source', 'Paper rendering', 'DI viewed once', 'Raw Cineon codes (not display RGB)'))):
        x = index % 2 * image.width
        y = index // 2 * (image.height+24)
        montage.paste(tile, (x, y+24))
        draw.text((x+8, y+5), title, fill='#222222')
    montage.save(OUT/'di-comparison.png')


report = {'ok': False, 'scope': 'small real-photo desktop native gamut/DI node; no RAW speed or monitor HDR claims'}
started = time.perf_counter()
try:
    run(report)
    report['ok'] = True
except Exception as error:
    report['error'] = repr(error)
    report['traceback'] = traceback.format_exc()
    raise
finally:
    report['elapsed_seconds'] = time.perf_counter()-started
    (OUT/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False), flush=True)
    native._shutdown()
