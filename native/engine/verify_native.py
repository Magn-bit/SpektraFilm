"""Focused ABI/data/cache check; optional one-shot real full-size benchmark."""
from dataclasses import replace
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import numpy as np
from desktop import native_spectral as native
from desktop.imaging import Settings


def verify():
    source = np.broadcast_to(np.linspace(.02, .98, 2048, dtype=np.float32)[None, :, None],
                             (128, 2048, 3)).copy()
    settings = Settings(spectral=True, grain=0, halation=0)
    start = native.render_spectral(source, settings, preview=True, source_token='precision')
    result = {'backend': native.backend_info()['backend'], 'precision': {
        'shape': list(start.shape), 'finite': bool(np.isfinite(start).all()),
        'unique_grey': int(np.unique(start[64, :, 1]).size),
        'range': [float(start.min()), float(start.max())]}}
    printed = native.render_spectral(source, replace(settings, print_exposure=.5),
                                     preview=True, source_token='precision')
    result['print'] = {'mean_delta': float(np.mean(abs(printed - start))),
                       **native.backend_info()['last_render']}
    assert printed.shape == start.shape and result['precision']['unique_grey'] > 1000
    assert result['print']['negative_cached'] and result['print']['mean_delta'] > .01
    paper = native.render_spectral(source, replace(settings, paper='fujifilm_crystal_archive_typeii'),
                                   preview=True, source_token='precision')
    result['paper'] = {'mean_delta': float(np.mean(abs(paper - start))),
                       **native.backend_info()['last_render']}
    assert result['paper']['negative_cached'] and result['paper']['mean_delta'] > .001
    result['bw'] = []
    for stock in ('kodak_tri_x_400', 'kodak_tmax_100', 'ilford_hp5_plus_400', 'fujifilm_neopan_acros_100_ii'):
        output = native.render_spectral(source, replace(settings, stock=stock),
                                         preview=True, source_token='precision')
        row = {'stock': stock, 'finite': bool(np.isfinite(output).all()),
               'channel_spread': float(np.max(np.ptp(output, axis=2))), 'mean': float(output.mean())}
        assert row['finite'] and row['channel_spread'] < .002 and .05 < row['mean'] < .95
        result['bw'].append(row)
    native.clear_sessions()
    return result


def benchmark(path):
    from desktop.imaging import read_photo
    from desktop.raw_source import normalized_pixels, source_pixels
    source = Path(path)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    started = time.perf_counter()
    image = read_photo(str(source))
    decode_seconds = time.perf_counter() - started
    values = normalized_pixels(source_pixels(image))
    started = time.perf_counter()
    output = native.render_spectral(values, Settings(spectral=True), source_token=('benchmark', str(source)))
    render_seconds = time.perf_counter() - started
    info = native.backend_info()
    assert image.size == (output.shape[1], output.shape[0]) and np.isfinite(output).all()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
    result = {'source': str(source), 'source_sha256': digest, 'source_unchanged': True,
              'dimensions': list(image.size), 'decode_seconds': decode_seconds,
              'bridge_render_seconds': render_seconds, 'native': info['last_render'],
              'engine_memory_after': info['memory'], 'output_range': [float(output.min()), float(output.max())]}
    return result


def effects_check():
    """Spatial seams and live effect controls, without another large-frame run."""
    height, width = 512, 384
    source = np.broadcast_to(np.linspace(.04, .85, height, dtype=np.float32)[:, None, None],
                             (height, width, 3)).copy()
    source[59:69, 156:228] = 1.
    settings = Settings(spectral=True, grain=0, halation=40, film_format_mm=16)
    values = native.parameters(settings)
    engine = native._get_engine()
    whole = engine.render(source, dict(values, striped=False), ('seam-whole',))
    striped = engine.render(source, dict(values, striped=True, strip_rows=64), ('seam-striped',))
    seam_error = float(np.max(abs(whole - striped)))
    assert seam_error <= 3. / 65535., seam_error
    glare = engine.render(source, dict(values, striped=False, glare_active=True, glare_percent=5.), ('seam-whole',))
    glare_delta = float(np.mean(abs(glare - whole)))
    assert glare_delta > .001 and native.backend_info()['last_render']['negative_cached']
    native.clear_sessions()
    flat = np.full((768, 1024, 3), .45, dtype=np.float32)
    grain_settings = replace(settings, halation=0, grain=25)
    fine = native.render_spectral(flat, replace(grain_settings, grain_size=.5, grain_type='fine'), source_token='grain')
    coarse = native.render_spectral(flat, replace(grain_settings, grain_size=2., grain_type='coarse'), source_token='grain')
    fine_std = float(fine[..., 1].std())
    coarse_std = float(coarse[..., 1].std())
    # Neutral product profiles share their stochastic field across RGB.  Track
    # chroma deviation separately so a visually fine grain cannot regress to
    # coloured speckle while its luminance standard deviation still passes.
    fine_chroma_std = float(np.stack((fine[..., 0] - fine[..., 1], fine[..., 2] - fine[..., 1]), axis=-1).std())
    coarse_chroma_std = float(np.stack((coarse[..., 0] - coarse[..., 1], coarse[..., 2] - coarse[..., 1]), axis=-1).std())
    assert coarse_std > fine_std * 2., (fine_std, coarse_std)
    assert fine_chroma_std < fine_std * .5, (fine_chroma_std, fine_std)
    native.clear_sessions()
    return {'striped_max_abs': seam_error, 'glare_mean_delta': glare_delta,
            'fine_std': fine_std, 'coarse_std': coarse_std,
            'fine_chroma_std': fine_chroma_std, 'coarse_chroma_std': coarse_chroma_std}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source')
    parser.add_argument('--output', default=str(ROOT / 'output' / 'native-spectral-0.4.0.json'))
    args = parser.parse_args()
    report = verify()
    report['effects'] = effects_check()
    if args.source:
        report['full_frame'] = benchmark(args.source)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
