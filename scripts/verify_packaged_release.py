"""Verify the current Windows and Android release candidates."""
from datetime import datetime
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys

from PIL import Image, ImageStat

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release"
ADDITIONAL_PROFILES = {"fujifilm_velvia_50", "agfa_vista_100", "fujifilm_natura_1600"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command, log_path, *, cwd=ROOT, env=None, timeout):
    print("Checking " + log_path.name, flush=True)
    with log_path.open("w", encoding="utf-8") as stream:
        result = subprocess.run(
            [str(value) for value in command], cwd=cwd, stdout=stream,
            stderr=subprocess.STDOUT, env=env, timeout=timeout,
        )
    if result.returncode:
        print(log_path.read_text(encoding="utf-8", errors="replace")[-3000:], flush=True)
        raise RuntimeError(f"{log_path.name} failed: {result.returncode}")


def verify_screenshot(path):
    with Image.open(path) as image:
        image.load()
        assert image.width > 800 and image.height > 500, f"Unexpected screenshot size: {path}"
        gray = image.convert("L")
        assert ImageStat.Stat(gray).stddev[0] > 3, f"Screenshot appears blank: {path}"
        return list(image.size)


def verify_film_only_report(report, *, legacy=False, expected_stock=None):
    settings=report.get('settings',{})
    required={'asynchronous import','rendered preview','grouped undo','redo',
              'full-size export','embedded sRGB profile','source integrity','requested film selected'}
    if legacy:required.update(('film-only policy','legacy edit migration','removed tools rejected'))
    if (not report.get('ok') or settings.get('spectral') is not True
            or settings.get('film_enabled') is not True
            or not required.issubset(report.get('checks',[]))):
        raise ValueError('The packaged application did not complete the film-only spectral workflow.')
    if expected_stock and (settings.get('stock')!=expected_stock or report.get('smoke_stock')!=expected_stock):
        raise ValueError('The packaged application did not render the requested smoke film.')
    # Check the complete neutral editor state, independently of film_settings().
    sys.path.insert(0,str(ROOT))
    from dataclasses import asdict
    from desktop.imaging import Settings,FILM_FIELDS
    neutral=json.loads(json.dumps(asdict(Settings(spectral=True,film_enabled=True,lens_correction=False,defringe=False))))
    if any(settings.get(key)!=value for key,value in neutral.items() if key not in FILM_FIELDS):
        raise ValueError('Removed editor settings remain in the packaged film workflow.')


def verify_windows_resources(candidate):
    """Check every camera profile and preview LUT, including new provenance."""
    packaged=candidate/'_internal'
    source_manifest=ROOT/'assets/luts/manifest.json'
    packaged_manifest=packaged/'assets/luts/manifest.json'
    if not packaged_manifest.is_file() or digest(source_manifest)!=digest(packaged_manifest):
        raise ValueError('Missing or stale packaged Windows film catalog.')
    manifest=json.loads(source_manifest.read_text(encoding='utf-8'))
    ids=[stock['id'] for stock in manifest['stocks']]
    if len(set(ids))!=len(ids) or not ADDITIONAL_PROFILES.issubset(ids):
        raise ValueError('The Windows catalog is missing the additional spectral films.')
    resource_hashes={'assets/luts/manifest.json':digest(packaged_manifest)}
    expected_luts=set()
    for stock in manifest['stocks']:
        relative=Path('assets/luts')/stock['file'].removeprefix('luts/')
        source=ROOT/relative
        target=packaged/relative
        if (not target.is_file() or target.stat().st_size!=manifest['size']**3*3*4
                or digest(source)!=digest(target)):
            raise ValueError('Missing or stale packaged preview LUT: '+stock['id'])
        expected_luts.add(relative.name)
        resource_hashes[relative.as_posix()]=digest(target)
    if {path.name for path in (packaged/'assets/luts').glob('*.f32')}!=expected_luts:
        raise ValueError('Packaged Windows LUT directory contains an incomplete or outdated set.')
    data_root=ROOT/'vendor/spektrafilm/data'
    camera_ids=set()
    for source in (data_root/'profiles').glob('*.json'):
        profile=json.loads(source.read_text(encoding='utf-8'))
        if profile['info']['stage']=='filming':camera_ids.add(profile['info']['stock'])
        relative=Path('spektrafilm/data/profiles')/source.name
        target=packaged/relative
        if not target.is_file() or digest(source)!=digest(target):
            raise ValueError('Missing or stale packaged spectral profile: '+source.name)
        resource_hashes[relative.as_posix()]=digest(target)
    if set(ids)!=camera_ids:
        raise ValueError('Windows camera-film catalog differs from installed spectral profiles.')
    extension_manifest=json.loads((data_root/'profile_extensions/manifest.json').read_text(encoding='utf-8'))
    if not ADDITIONAL_PROFILES.issubset(extension_manifest['profiles']):
        raise ValueError('Missing additional spectral adaptation manifest entries.')
    for source in (data_root/'profile_extensions').glob('*.json'):
        relative=Path('spektrafilm/data/profile_extensions')/source.name
        target=packaged/relative
        if not target.is_file() or digest(source)!=digest(target):
            raise ValueError('Missing or stale packaged spectral provenance: '+source.name)
        resource_hashes[relative.as_posix()]=digest(target)
    notice='JanLohse-spectral-data-MIT.txt'
    target=packaged/'licenses'/notice
    if not target.is_file() or digest(ROOT/'licenses'/notice)!=digest(target):
        raise ValueError('Missing or stale packaged additional-data MIT license.')
    resource_hashes['licenses/'+notice]=digest(target)
    return {'catalog_stocks':ids,'catalog_count':len(ids),'additional_profiles':sorted(ADDITIONAL_PROFILES),
            'resource_sha256':resource_hashes}


def verify_native_resources(candidate):
    packaged = candidate / '_internal'
    runtime = ROOT / 'native/engine/runtime'
    hashes = {}
    for source in sorted(runtime.rglob('*')):
        if not source.is_file():
            continue
        relative = Path('native/engine/runtime') / source.relative_to(runtime)
        target = packaged / relative
        if not target.is_file() or digest(source) != digest(target):
            raise ValueError('Missing or stale native spectral resource: ' + relative.as_posix())
        hashes[relative.as_posix()] = digest(target)
    if not any(name.endswith('.spv') for name in hashes) or not (runtime / 'spektrafilm_engine.dll').is_file():
        raise ValueError('Missing native spectral DLL or Vulkan shaders')
    for relative in ('assets/darkroom.json', 'licenses/SpektraLab-Product-Materials-NOTICE.md'):
        if digest(ROOT / relative) != digest(packaged / relative):
            raise ValueError('Missing or stale darkroom material resource: ' + relative)
        hashes[relative] = digest(packaged / relative)
    return dict(engine='C++/Vulkan complete spectral', resource_sha256=hashes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", default="dist/SpektraFilm")
    parser.add_argument("--android-apk", default="android/app/build/outputs/apk/debug/app-debug.apk")
    parser.add_argument("--evidence-dir")
    parser.add_argument("--manifest", default="release/manifest.json")
    parser.add_argument("--require-gpu", action="store_true", help="Require the complete native Vulkan spectral pipeline")
    parser.add_argument("--android-device-report", help="Successful instrumentation evidence bound to this exact APK")
    args = parser.parse_args()

    manifest = json.loads((ROOT / args.manifest).read_text(encoding="utf-8"))
    version = manifest["version"]
    candidate = (ROOT / args.candidate).resolve()
    apk = (ROOT / args.android_apk).resolve()
    if not candidate.is_relative_to(ROOT) or not (candidate / "SpektraFilm.exe").is_file():
        raise ValueError("Windows candidate must be a packaged application inside this workspace.")
    if not apk.is_relative_to(ROOT) or not apk.is_file():
        raise ValueError("Android APK must be a built package inside this workspace.")

    if args.evidence_dir:
        evidence = (ROOT / args.evidence_dir).resolve()
    else:
        evidence = ROOT / "output" / f"release-{version}"
        if evidence.exists():
            evidence = ROOT / "output" / f"release-{version}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    if not evidence.is_relative_to(ROOT):
        raise ValueError("Evidence directory must stay inside the workspace.")
    evidence.mkdir(parents=True, exist_ok=False)

    system_root = Path(os.environ.get("SYSTEMROOT", "C:/Windows"))
    env = os.environ.copy()
    env["PATH"] = str(system_root / "System32") + ";" + str(system_root)
    for name in ("PYTHONPATH", "PYTHONHOME", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM", "WGPU_LIB_PATH", "SPEKTRAFILM_COMPUTE"):
        env.pop(name, None)

    assert not list(candidate.rglob("icuuc.dll")), "Unexpected bundled ICU DLL"
    qml_root = ROOT / "desktop/qml"
    for source in qml_root.rglob("*.qml"):
        packaged = candidate / "_internal/desktop/qml" / source.relative_to(qml_root)
        assert packaged.is_file() and digest(source) == digest(packaged), f"Stale packaged QML: {source}"
    resources=verify_windows_resources(candidate)
    resources['native_spectral'] = verify_native_resources(candidate)
    flows = []
    screenshots = {}
    for format_name, suffix in (("jpg", "jpg"), ("tiff", "tif")):
        smoke_stock='agfa_vista_100' if format_name=='tiff' else 'kodak_portra_400'
        report_path = evidence / f"spectral-{format_name}-report.json"
        export_path = evidence / f"verified-spectral-{format_name}.{suffix}"
        run(
            [candidate / "SpektraFilm.exe", "--smoke-test", "--smoke-spectral",
             "--smoke-stock", smoke_stock,
             "--verify-export", export_path, "--verification-report", report_path],
            evidence / f"spectral-{format_name}.log", env=env, timeout=180,
        )
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if args.require_gpu and report.get('native_spectral',{}).get('backend',{}).get('render_core')!='native-vulkan':
            raise ValueError('The frozen Windows candidate did not execute the full native spectrum: '+str(report.get('native_spectral')))
        if format_name == 'tiff':
            import tifffile
            with tifffile.TiffFile(export_path) as tiff:
                if tiff.pages[0].bitspersample != 16:
                    raise ValueError('The frozen application did not export a 16-bit TIFF')
        verify_film_only_report(report,expected_stock=smoke_stock)
        if report.get('catalog_stocks')!=resources['catalog_stocks']:
            raise ValueError('The running Windows application did not expose the packaged camera-film catalog.')
        font_family = json.loads((ROOT / "assets/fonts/interface-font.json").read_text(encoding="utf-8"))["family"]
        fonts=report.get('font_selection',{})
        if (fonts.get('display')!=font_family or fonts.get('editorial')!=font_family
                or not fonts.get('primary') or report.get('font_family')!=fonts.get('primary')):
            raise ValueError("Packaged Windows font roles do not match the current UI typography.")
        glyphs=report.get('glyph_families',{})
        if (glyphs.get('display')!=[font_family] or glyphs.get('editorial')!=[font_family]
                or not glyphs.get('body') or not set(glyphs['body']).issubset({fonts['primary'],fonts.get('cjk')})):
            raise ValueError('Packaged Windows actual glyphs differ from the requested body/title fonts.')
        flows.append(report)

    policy_report_path=evidence/'film-policy-report.json'
    run([candidate/'SpektraFilm.exe','--smoke-test','--smoke-film-policy',
         '--verify-export',evidence/'verified-film-policy.tif',
         '--verification-report',policy_report_path,'--screenshot',evidence/'film-policy.png'],
        evidence/'film-policy.log',env=env,timeout=180)
    policy_report=json.loads(policy_report_path.read_text(encoding='utf-8'))
    verify_film_only_report(policy_report,legacy=True,expected_stock='kodak_portra_400')
    screenshots['film-policy']=verify_screenshot(evidence/'film-policy.png')

    for state in ("empty", "export", "library", "grain", "darkroom"):
        screenshot = evidence / f"{state}.png"
        command = [candidate / "SpektraFilm.exe", "--capture-state", state, "--screenshot", screenshot]
        if state in ("export", "grain", "darkroom", "library"):
            command += ["--open", evidence / "verified-spectral-jpg.jpg"]
        run(command, evidence / f"{state}-capture.log", env=env, timeout=45)
        screenshots[state] = verify_screenshot(screenshot)

    metadata = json.loads((ROOT / "android/app/build/outputs/apk/debug/output-metadata.json").read_text(encoding="utf-8"))
    if not any(element.get("versionName") == version
               and element.get("versionCode") == manifest["android"].get("version_code")
               for element in metadata.get("elements", [])):
        raise ValueError("Android APK build metadata does not match release/manifest.json.")

    android_report = evidence / "android-verification.json"
    run([sys.executable, "-X", "utf8", ROOT / "android/tools/verify_apk.py", apk, android_report],
        evidence / "android-resources.log", timeout=90)
    android = json.loads(android_report.read_text(encoding="utf-8"))
    if android.get("sha256") != digest(apk) or "spectral" not in android.get("engine", "").lower():
        raise ValueError("Android resource verification did not match the full spectral APK.")

    signer = ROOT / ".tools/android-sdk/build-tools/35.0.0/apksigner.bat"
    if not signer.is_file():
        raise FileNotFoundError(signer)
    run(["cmd.exe", "/d", "/c", signer, "verify", "--verbose", apk],
        evidence / "android-signature.log", timeout=45)

    adb = ROOT / ".tools/android-sdk/platform-tools/adb.exe"
    devices = None
    if adb.is_file():
        run([adb, "devices", "-l"], evidence / "android-devices.log", timeout=20)
        devices = evidence.joinpath("android-devices.log").read_text(encoding="utf-8", errors="replace")
    device_proof = None
    if args.android_device_report:
        device_proof = json.loads((ROOT / args.android_device_report).read_text(encoding='utf-8'))
        if not device_proof.get('ok') or device_proof.get('apk_sha256') != digest(apk):
            raise ValueError('Android device evidence does not match this successful APK build')
    proof = {
        "ok": True,
        "version": version,
        "verified_at": datetime.now().astimezone().isoformat(),
        "evidence": str(evidence),
        "windows_exe": str(candidate / "SpektraFilm.exe"),
        "windows_exe_sha256": digest(candidate / "SpektraFilm.exe"),
        "windows_flows": flows,
        "windows_resources": resources,
        "windows_film_policy": policy_report,
        "screenshots": screenshots,
        "android_apk": str(apk),
        "android_sha256": digest(apk),
        "android_device_runtime": bool(device_proof),
        "android_device_evidence": device_proof,
    }
    output_report = ROOT / "output/release-verification.json"
    output_report.parent.mkdir(parents=True, exist_ok=True)
    output_report.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (evidence / "windows-smoke.json").write_text(json.dumps(flows[0], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(proof, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
