"""One bounded milestone: ExifTool discovery and the exact Windows RAW/ico path."""
from pathlib import Path
import argparse
import ctypes as ct
from ctypes import wintypes as wt
import json
import os
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'vendor'), str(ROOT / 'scripts')]
from desktop import lens
from publish_windows_update import candidate_metadata


def discover_without_path_scan():
    with tempfile.TemporaryDirectory(prefix='spektrafilm-discovery-') as folder:
        root = Path(folder)
        bundled = root / 'native/metadata/runtime/exiftool-13.61_64/exiftool.exe'
        bundled.parent.mkdir(parents=True)
        bundled.write_bytes(b'not executed: discovery fixture')
        override = root / 'explicit-exiftool.exe'
        override.write_bytes(b'not executed: discovery fixture')
        with patch.object(sys, '_MEIPASS', str(root), create=True), \
             patch.object(lens.shutil, 'which', side_effect=AssertionError('PATH must not be scanned')), \
             patch.dict(os.environ, {'SPEKTRAFILM_EXIFTOOL': str(override)}):
            try:
                lens._exiftool.cache_clear()
                assert lens._exiftool() == str(bundled.resolve())
                bundled.unlink()
                lens._exiftool.cache_clear()
                assert lens._exiftool() == str(override.resolve())
                override.unlink()
                lens._exiftool.cache_clear()
                if os.name == 'nt':
                    assert lens._exiftool() is None
            finally:
                lens._exiftool.cache_clear()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--windows', type=Path, required=True)
    parser.add_argument('--photo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    artifacts = candidate_metadata(args.windows.resolve())
    discover_without_path_scan()
    user32 = ct.WinDLL('user32', use_last_error=True)
    callback_type = ct.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ct.POINTER(wt.DWORD)]
    user32.IsWindowVisible.argtypes = [wt.HWND]
    user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    user32.SendMessageW.restype = ct.c_ssize_t
    icons = {'small': False, 'big': False}
    started = time.monotonic()
    before = (args.photo.stat().st_size, args.photo.stat().st_mtime_ns)
    with (out / 'startup.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen([str(args.windows.resolve() / 'SpektraFilm.exe'),
            '--capture-state', 'editor', '--open', str(args.photo.resolve()),
            '--screenshot', str(out / 'packaged-raw.png')],
            cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)

        @callback_type
        def window_callback(hwnd, _):
            owner = wt.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ct.byref(owner))
            if owner.value == process.pid and user32.IsWindowVisible(hwnd):
                icons['small'] |= bool(user32.SendMessageW(hwnd, 0x7f, 0, 0))
                icons['big'] |= bool(user32.SendMessageW(hwnd, 0x7f, 1, 0))
            return True

        while process.poll() is None and time.monotonic() - started < 90:
            user32.EnumWindows(window_callback, 0)
            time.sleep(.02)
        if process.poll() is None:
            process.kill()
            process.wait()
            raise RuntimeError('Exact-build RAW preview timed out')
    assert process.returncode == 0, (out / 'startup.log').read_text(encoding='utf-8', errors='replace')[-3000:]
    assert (out / 'packaged-raw.png').is_file()
    assert all(icons.values()), icons
    assert before == (args.photo.stat().st_size, args.photo.stat().st_mtime_ns)
    report = dict(ok=True, version='0.8.3', seconds=round(time.monotonic()-started, 3),
        checks=['bundled ExifTool wins without PATH enumeration',
                'explicit ExifTool override works when bundled tool is absent',
                'missing Windows optional tool does not scan PATH',
                'exact packaged executable imports and displays the supplied RAW',
                'Windows native small and large taskbar/window icons are present',
                'source size and modification time unchanged'],
        icons=icons, photo=args.photo.name,
        windows=dict(artifacts=artifacts, smoke_ok=True),
        scope='Startup/RAW preview/icon milestone only; no full-resolution export or repeated benchmark')
    (out / 'startup-resources.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k != 'windows'}, indent=2))


if __name__ == '__main__':
    main()
