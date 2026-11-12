"""Build the shared desktop application on a native macOS Python environment.

The --check command is read-only and also works on Windows. It never claims
that a macOS application has been produced on another operating system.
"""
from pathlib import Path
import argparse
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.2.7"

def preflight():
    modules = ("PyInstaller", "PySide6", "numpy", "scipy", "PIL", "colour", "skimage", "numba", "pyfftw", "OpenImageIO", "rawpy", "wgpu")
    return {
        "platform": sys.platform,
        "architecture": platform.machine(),
        "python": sys.version.split()[0],
        "can_build_macos": sys.platform == "darwin",
        "xcodebuild": shutil.which("xcodebuild"),
        "missing_python_modules": [name for name in modules if importlib.util.find_spec(name) is None],
        "font_asset_present": (ROOT / "assets/fonts/SpektraBilingualSerif-Regular.ttf").is_file(),
        "ios_project_present": any(ROOT.glob("apple/ios/*.xcodeproj")),
        "scope": "Host preflight only; not compilation or device validation",
    }

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Report host requirements without compiling")
    parser.add_argument("--skip-smoke", action="store_true", help="Build an unverified candidate without opening its isolated test window")
    args = parser.parse_args()
    status = preflight()
    if args.check:
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0
    if not status["can_build_macos"]:
        parser.error("macOS .app builds require a macOS host. This Windows environment has not generated an Apple application.")
    if status["missing_python_modules"]:
        parser.error("Install requirements.txt and PyInstaller in the native Mac Python environment first: " + ", ".join(status["missing_python_modules"]))
    if not status["font_asset_present"]:
        parser.error("The verified bilingual font asset is missing; build it before packaging.")
    architecture = status["architecture"]
    build = ROOT / "build/macos" / architecture
    output = ROOT / "dist/macos" / architecture
    evidence = ROOT / "output/macos" / architecture
    for folder in (build, output, evidence):
        folder.mkdir(parents=True, exist_ok=True)
    from PIL import Image
    icon = build / "spektrafilm.icns"
    with Image.open(ROOT / "assets/icons/spektrafilm.ico") as source:
        source.convert("RGBA").save(icon, format="ICNS")
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--windowed", "--onedir", "--name", "SpektraFilm",
        "--workpath", str(build / "cache"), "--specpath", str(build), "--distpath", str(output),
        "--paths", str(ROOT), "--paths", str(ROOT / "vendor"), "--icon", str(icon),
        "--osx-bundle-identifier", "com.spektra.film",
        "--collect-all", "spektrafilm", "--collect-data", "colour", "--hidden-import", "rawpy",
        # wgpu's installed-wheel hook collects native resources. This only
        # prepares the bundle; desktop.compute still enables Vulkan on Windows.
        "--hidden-import", "wgpu.backends.wgpu_native", "--copy-metadata", "wgpu",
        "--hidden-import", "matplotlib.backends.backend_agg", "--exclude-module", "tkinter",
        "--exclude-module", "IPython", "--exclude-module", "pytest"]
    for relative, target in (("desktop/qml", "desktop/qml"), ("assets", "assets"), ("licenses", "licenses"), ("LICENSE", ".")):
        command += ["--add-data", str(ROOT / relative) + os.pathsep + target]
    command.append(str(ROOT / "desktop/main.py"))
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "vendor")
    with (evidence / "build.log").open("w", encoding="utf-8") as stream:
        subprocess.run(command, cwd=ROOT, env=environment, stdout=stream, stderr=subprocess.STDOUT, check=True)
    bundle = output / "SpektraFilm.app"
    binary = bundle / "Contents/MacOS/SpektraFilm"
    if not binary.is_file():
        raise RuntimeError("PyInstaller did not produce the expected native macOS app bundle")
    smoke_verified = False
    if not args.skip_smoke:
        with (evidence / "smoke.log").open("w", encoding="utf-8") as stream:
            subprocess.run([str(binary), "--smoke-test", "--smoke-spectral", "--verification-report", str(evidence / "smoke.json"), "--screenshot", str(evidence / "editor.png")],
                cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=180)
        smoke_verified = json.loads((evidence / "smoke.json").read_text(encoding="utf-8"))["ok"] is True
        if not smoke_verified:
            raise RuntimeError("The native macOS smoke report did not pass")
    result = dict(version=VERSION, bundle=str(bundle), architecture=architecture, smoke_verified=smoke_verified,
        notarized=False, native_build=True, distribution="Local candidate; no Developer ID or notarization configured")
    (evidence / "build-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
