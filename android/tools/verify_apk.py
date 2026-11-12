"""Verify the actual APK resource contract without an Android device."""
from pathlib import Path
import hashlib
import json
import sys
import zipfile
import io

root = Path(__file__).resolve().parents[2]
apk = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else root / 'android/app/build/outputs/apk/debug/app-debug.apk'
digest = lambda value: hashlib.sha256(value).hexdigest()
additional_profiles={'fujifilm_velvia_50','agfa_vista_100','fujifilm_natura_1600'}
local_lut_manifest=json.loads((root/'assets/luts/manifest.json').read_text(encoding='utf-8'))
extension_root=root/'vendor/spektrafilm/data/profile_extensions'
profile_extensions=json.loads((extension_root/'manifest.json').read_text(encoding='utf-8'))['profiles']
assert additional_profiles.issubset(profile_extensions)
with zipfile.ZipFile(apk) as package:
    names = package.namelist()
    assert 'classes.dex' in names
    dex=b''.join(package.read(name) for name in names if name.startswith('classes') and name.endswith('.dex'))
    for symbol in [b'TiffEncoder',b'FullResolutionPhoto',b'decodeRegion',b'JpegStreamEncoder',b'JPG_HIGH',b'JPG_SHARE',b'saveBatch',b'photoPicker',b'renderPreview',b'fonts/SpektraBilingualSerif-Regular.ttf',b'PhotoBrowserDialog',b'removePhotos',b'NativeSpectral',b'nativeRender',b'render16',b'decodeFloatRegion',b'write16',b'renderInteractive',b'filmOnly',b'PhotoEditsStore']:
        assert symbol in dex, f'Missing export implementation: {symbol}'
    for symbol in [b'RawImageDecoder',b'RawPhotoCache',b'Rgb16PixelSource',b'nativeDevelop',b'requireFullRawOutput']:
        assert symbol in dex, f'Missing offline RAW implementation: {symbol}'
    proprietary=[name for name in names if name.startswith('lib/') and name.endswith('.so')
                 and any(token in name.lower() for token in ('liblrandroid','adobe','lightroom','captureone'))]
    assert not proprietary,f'Unexpected proprietary image engine: {proprietary}'
    assert 'lib/arm64-v8a/libspektra_spectral.so' in names
    native_binary=package.read('lib/arm64-v8a/libspektra_spectral.so')
    for symbol in (b'Java_com_spektra_film_NativeSpectral_nativeRender',b'Java_com_spektra_film_NativeSpectral_nativeCreate'):
        assert symbol in native_binary,'Missing native spectral JNI entry point'
    native_resource_hashes={}
    native_root=root/'native/engine/runtime/resources'
    for file in native_root.rglob('*'):
        if not file.is_file():continue
        relative=file.relative_to(native_root).as_posix()
        data=package.read('assets/native_engine/'+relative)
        assert data==file.read_bytes(),f'Stale native resource {relative}'
        native_resource_hashes[relative]=digest(data)
    assert any(name.endswith('.spv') for name in native_resource_hashes)
    assert json.loads(package.read('assets/darkroom.json'))==json.loads((root/'assets/darkroom.json').read_text(encoding='utf-8'))
    for stock in ('kodak_tri_x_400','kodak_tmax_100','ilford_hp5_plus_400','fujifilm_neopan_acros_100_ii'):
        assert f'profiles/{stock}.json' in native_resource_hashes
    assert package.read('assets/native_engine/profile_extensions.json')==(extension_root/'manifest.json').read_bytes()
    assert 'lib/arm64-v8a/libspektra_raw.so' in names
    assert 'lib/arm64-v8a/libspektra_stream_jpeg.so' in names
    assert 'assets/licenses/libjpeg-turbo-LICENSE.md' in names
    assert not any('libpython' in name or 'chaquopy' in name for name in names), 'Unexpected Python runtime in native Android APK'
    python_root=root/'android/app/src/main/python'
    activity=(root/'android/app/src/main/java/com/spektra/film/MainActivity.kt').read_text(encoding='utf-8')
    assert 'FullResolutionPhoto.open(' in activity and 'rawCache' in activity
    assert 'LUT 快速（近似）' not in activity and 'ExportRenderMode' not in activity
    assert 'adjustments.filmOnly()' in activity
    assert '完整光谱 · 原图尺寸' in activity and 'activeExportRaw' in activity
    adjustments=(root/'android/app/src/main/java/com/spektra/film/FilmEngine.kt').read_text(encoding='utf-8')
    edits=(root/'android/app/src/main/java/com/spektra/film/MaskLayer.kt').read_text(encoding='utf-8')
    assert 'fun filmOnly(): Adjustments' in adjustments and 'filmEnabled=true' in adjustments
    assert 'adjustments.filmOnly()' in edits
    full_resolution = (root/'android/app/src/main/java/com/spektra/film/FullResolutionPhoto.kt').read_text(encoding='utf-8')
    assert 'decodeRegion' in full_resolution and 'maxTilePixels' in full_resolution
    assert 'writeJpeg' in full_resolution and 'writeTiff' in full_resolution
    spectral_sources={}  # Scientific reference source is retained in the source release, outside the APK.
    profile=package.read('assets/color/sRGB.icc')
    assert profile==(root/'assets/color/sRGB.icc').read_bytes()
    manifest = json.loads(package.read('assets/luts/manifest.json'))
    assert manifest==local_lut_manifest,'Packaged LUT catalog differs from local catalog'
    assert manifest['size'] == 33 and manifest['order'] == 'r-fastest'
    verified = []
    for stock in manifest['stocks']:
        relative = stock['file'].removeprefix('luts/')
        assert 'assets/luts/'+relative not in names, 'Unused legacy interaction LUT should not ship'
        verified.append(stock['id'])
    expected_ids=[stock['id'] for stock in local_lut_manifest['stocks']]
    assert verified==expected_ids and len(set(verified))==len(verified)
    assert additional_profiles.issubset(verified),'Missing additional spectral profiles in APK catalog'
    camera_profiles={}
    for path in (root/'vendor/spektrafilm/data/profiles').glob('*.json'):
        data=json.loads(path.read_text(encoding='utf-8'))
        if data['info']['stage']=='filming':camera_profiles[data['info']['stock']]=path
    assert set(verified)==set(camera_profiles),'APK camera-film catalog does not match installed spectral data'
    font_manifest = json.loads((root / 'assets/fonts/interface-font.json').read_text(encoding='utf-8'))
    font_path = 'assets/fonts/' + font_manifest['file']
    font = package.read(font_path)
    assert digest(font) == font_manifest['sha256']
    assert digest(font) == digest((root / font_path).read_bytes())
    for license_file in font_manifest['licenses']:
        assert 'assets/fonts/' + license_file in names
    assert 'assets/fonts/ZhuqueFangsong-Regular.ttf' not in names
    assert 'assets/fonts/NotoSerifSC.ttf' not in names
    assert 'assets/licenses/GPL-3.0.txt' in names
    assert 'assets/licenses/CC-BY-SA-4.0-profiles.txt' in names
    additional_notice=package.read('assets/licenses/JanLohse-spectral-data-MIT.txt')
    assert additional_notice==(root/'licenses/JanLohse-spectral-data-MIT.txt').read_bytes()
    for notice in ('LibRaw-COPYRIGHT.txt','LibRaw-LICENSE.CDDL.txt','LibRaw-LICENSE.LGPL.txt'):
        assert package.read('assets/licenses/'+notice)==(root/'licenses'/notice).read_bytes()
    photos = [name for name in names if name.startswith('assets/') and name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.heic'))]
    assert not photos, f'Unexpected bundled photo: {photos}'
result = {'apk': str(apk), 'bytes': apk.stat().st_size, 'sha256': digest(apk.read_bytes()), 'lut_stocks': verified, 'lut_size': 33, 'additional_spectral_profiles':sorted(additional_profiles), 'additional_data_license_sha256':digest(additional_notice), 'font': font_manifest['family'], 'font_sha256': digest(font), 'srgb_icc_sha256':digest(profile), 'export_presets':['JPG_HIGH','JPG_SHARE','TIFF','RAW'], 'export_modes':['FULL_SPECTRAL'], 'product_scope':'film-only', 'bundled_photos': 0, 'engine':'Offline LibRaw RGB16 -> native C++/Vulkan float32 spectral executor -> RGB16 scanlines; low-resolution previews use the same spectral model; TIFF16 lossless Deflate', 'native_resource_sha256':native_resource_hashes,'native_library_sha256':digest(native_binary),'tiff_bits_per_channel':16,'runtime_python':False,'spectral_source_sha256':spectral_sources,'scope': 'APK compilation, packaged-resource and source-policy checks; no device runtime or screenshot test'}
report = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else root / 'output/android/verification.json'
report.parent.mkdir(parents=True, exist_ok=True)
report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
