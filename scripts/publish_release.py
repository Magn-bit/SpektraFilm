"""Mirror the separately verified local Personal build into release/."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release"
PERSONAL = RELEASE / "Personal"
DIGEST = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()

def closed_builds():
    if sys.platform != "win32":
        return
    expression = """@(Get-CimInstance Win32_Process -Filter "Name='SpektraFilm.exe'" | Select-Object -ExpandProperty ExecutablePath) | ConvertTo-Json -Compress"""
    result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", expression], capture_output=True, text=True, check=True)
    paths = json.loads(result.stdout.strip() or "[]")
    if isinstance(paths, str):
        paths = [paths]
    destinations = [PERSONAL / "Windows/SpektraFilm", RELEASE / "Windows/SpektraFilm"]
    for filename in paths:
        if filename:
            running = Path(filename).resolve()
            if any(running.is_relative_to(path.resolve()) for path in destinations):
                raise RuntimeError("An already-published SpektraFilm Windows application is running. Keep it open; publish after closing it normally.")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume-stage", help="Resume a verified .shared-* folder retained by an earlier attempt")
    args = parser.parse_args()
    report_path = ROOT / "output/personal-release-0.2.4/report.json"
    result = json.loads(report_path.read_text(encoding="utf-8"))
    assert result["ok"] and result["version"] == "0.2.4"
    version = result["version"]
    exe = PERSONAL / "Windows/SpektraFilm/SpektraFilm.exe"
    apk_source = PERSONAL / "Android" / f"SpektraFilm-{version}-personal.apk"
    personal_manifest = json.loads((PERSONAL / "manifest.json").read_text(encoding="utf-8"))
    font = personal_manifest["typography"]
    assert DIGEST(exe) == personal_manifest["windows"]["sha256"]
    assert DIGEST(apk_source) == personal_manifest["android"]["sha256"]
    assert font["scripts"]["chinese"].startswith("Zhuque Fangsong")
    assert font["scripts"]["latin_and_numerals"] == "Noto Serif SC Regular"

    if args.resume_stage:
        stage = (RELEASE / args.resume_stage).resolve()
        assert stage.parent == RELEASE.resolve() and stage.name.startswith(".shared-") and stage.is_dir()
    else:
        stage = RELEASE / (".shared-" + uuid.uuid4().hex[:8])
        stage.mkdir()
    closed_builds()
    old_documents = {name: RELEASE / name for name in ("README.md", "manifest.json", "SHA256SUMS.txt")}
    history = RELEASE / "history" / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4])
    installed_folders = []
    previous_folders = []
    try:
        staged_windows = stage / "Windows/SpektraFilm"
        staged_windows.parent.mkdir(exist_ok=True)
        shutil.copytree(PERSONAL / "Windows/SpektraFilm", staged_windows, dirs_exist_ok=True)
        assert DIGEST(staged_windows / "SpektraFilm.exe") == DIGEST(exe)
        staged_apk_dir = stage / "Android"
        staged_apk_dir.mkdir(exist_ok=True)
        apk_name = f"SpektraFilm-{version}-debug.apk"
        staged_apk = staged_apk_dir / apk_name
        if staged_apk.exists():
            assert DIGEST(staged_apk) == DIGEST(apk_source)
        else:
            shutil.copy2(apk_source, staged_apk)
        assert DIGEST(staged_apk) == DIGEST(apk_source)
        assert DIGEST(staged_windows / "_internal/assets/fonts" / font["file"]) == font["sha256"]

        readme = f"""# SpektraFilm {version} · 本地版本

Windows：Windows/SpektraFilm/SpektraFilm.exe，便携版本，请保留整个目录和 _internal。
Android：Android/{apk_name}，arm64-v8a，Android 8+，调试签名。

全界面按语言统一：中文朱雀仿宋；英文及数字 Noto Serif SC。窗口、正文、按钮、参数与应用弹窗统一使用同一套字形。原始字体与 SIL OFL 1.1 授权保留，组合后的 13009 个字形轮廓和水平度量逐字验证。

两端完整光谱渲染；交互期间先显示明确标记的 LUT 近似。Windows EXE 完成导入、显影、撤销/重做和完整光谱导出验证。Android 编译、Lint、字体资源与 APK 签名检查通过；尚未连接设备或模拟器。

全质量 JPG、分享 JPG、无损 TIFF 与原片 RAW 均保留。RAW 原样复制，不执行显影。Windows 拖入、粘贴、多选、批量处理和细节缩放均保留。Windows 尚未正式代码签名。

当前没有可用 Mac，尚未生成或测试 macOS.app。当前尚无 iOS/Xcode 工程，完整光谱内核也尚未移植；没有生成或测试 iOS.ipa。平台构建记录见 docs/apple-builds.md。

本地运行版不代表公开代码签名或开发者 ID 公证。SHA256SUMS.txt 覆盖 Windows、Android、README 与 manifest。
"""
        (stage / "README.md").write_text(readme, encoding="utf-8")
        manifest = json.loads(json.dumps(personal_manifest))
        manifest["variant"] = "shared-local"
        manifest["published_at"] = datetime.now(timezone(timedelta(hours=8))).isoformat()
        manifest["windows"]["executable"] = "Windows/SpektraFilm/SpektraFilm.exe"
        manifest["android"]["apk"] = "Android/" + apk_name
        manifest["android"]["version_name"] = version
        manifest["android"]["version_code"] = 6
        manifest["release_copy_of"] = "Personal/manifest.json; byte-identical Windows EXE and APK"
        manifest["typography"] = font
        (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8")
        files = sorted(path for path in stage.rglob("*") if path.is_file())
        sums = chr(10).join(DIGEST(path) + "  " + path.relative_to(stage).as_posix() for path in files) + chr(10)
        (stage / "SHA256SUMS.txt").write_text(sums, encoding="utf-8")

        closed_builds()
        history.mkdir(parents=True)
        for name in ("Windows", "Android"):
            current = RELEASE / name
            if current.exists():
                current.rename(history / name)
                previous_folders.append(name)
            (stage / name).rename(current)
            installed_folders.append(name)
        for name in ("README.md", "manifest.json", "SHA256SUMS.txt"):
            path = old_documents[name]
            if path.is_file():
                shutil.copy2(path, history / name)
        for name in ("README.md", "manifest.json", "SHA256SUMS.txt"):
            path = old_documents[name]
            if path.exists():
                path.unlink()
            (stage / name).rename(path)
        final = {"ok": True, "version": version,
            "windows": str(RELEASE / "Windows/SpektraFilm/SpektraFilm.exe"),
            "android": str(RELEASE / "Android" / apk_name),
            "history": str(history), "files": len(files)}
        report = ROOT / "output/shared-release-0.2.4.json"
        report.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(final, ensure_ascii=False, indent=2))
    except Exception:
        for name in ("Windows", "Android"):
            current = RELEASE / name
            staged = stage / name
            if name in installed_folders and current.exists():
                current.rename(staged)
        for name in reversed(previous_folders):
            current, saved = RELEASE / name, history / name
            if saved.exists() and not current.exists():
                saved.rename(current)
        for name in ("README.md", "manifest.json", "SHA256SUMS.txt"):
            saved = history / name
            if saved.exists():
                current = old_documents[name]
                if current.exists():
                    current.unlink()
                shutil.copy2(saved, current)
        raise
    finally:
        if not any(stage.iterdir()):
            stage.rmdir()

if __name__ == "__main__":
    main()
