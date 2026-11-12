"""Verify a changed Android APK without repeating unchanged Windows workflows."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.verify_packaged_release import (
    digest, run, verify_film_only_report, verify_native_resources,
    verify_windows_resources,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proof', default='output/release-verification.json')
    parser.add_argument('--android-apk', default='android/app/build/outputs/apk/debug/app-debug.apk')
    parser.add_argument('--device-report', required=True)
    args = parser.parse_args()
    proof_path = (ROOT / args.proof).resolve()
    proof = json.loads(proof_path.read_text(encoding='utf-8'))
    exe = Path(proof['windows_exe']).resolve()
    evidence = Path(proof['evidence']).resolve()
    apk = (ROOT / args.android_apk).resolve()
    if (not proof.get('ok') or proof.get('version') != '0.4.0'
            or not all(p.is_relative_to(ROOT) for p in (exe, evidence, apk, proof_path))
            or digest(exe) != proof['windows_exe_sha256']):
        raise ValueError('The previous Windows candidate is missing or changed')
    resources = verify_windows_resources(exe.parent)
    resources['native_spectral'] = verify_native_resources(exe.parent)
    if resources != proof['windows_resources']:
        raise ValueError('Windows resources changed; run a fresh package verification')
    for flow in proof['windows_flows']:
        verify_film_only_report(flow, expected_stock=flow['smoke_stock'])
    verify_film_only_report(proof['windows_film_policy'], legacy=True)
    device = json.loads((ROOT / args.device_report).read_text(encoding='utf-8'))
    if not device.get('ok') or device.get('apk_sha256') != digest(apk):
        raise ValueError('Device evidence must pass for this exact APK')
    android_path = evidence / 'android-verification.json'
    run([sys.executable, '-X', 'utf8', ROOT / 'android/tools/verify_apk.py', apk, android_path],
        evidence / 'android-resources.log', timeout=90)
    android = json.loads(android_path.read_text(encoding='utf-8'))
    if android.get('sha256') != digest(apk):
        raise ValueError('Android package resource verification identifies another APK')
    signer = ROOT / '.tools/android-sdk/build-tools/35.0.0/apksigner.bat'
    run(['cmd.exe', '/d', '/c', signer, 'verify', '--verbose', apk],
        evidence / 'android-signature.log', timeout=45)
    proof.update(android_apk=str(apk), android_sha256=digest(apk),
                 android_device_runtime=True, android_device_evidence=device,
                 android_refresh_scope='Windows binary/resources unchanged; previous verified workflows retained. Android resource/signature/device checks refreshed for exact APK hash.')
    temporary = proof_path.with_suffix('.tmp')
    temporary.write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(proof_path)
    print('Verified final Android APK; retained unchanged Windows evidence', flush=True)


if __name__ == '__main__':
    main()
