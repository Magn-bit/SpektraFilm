"""Bake actual upstream spectral transforms. Never substitute hand-tuned filters."""
from pathlib import Path
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'vendor'))
sys.path.insert(0, str(ROOT))
import numpy as np
from spektrafilm import init_params, simulate
from shared.film_profiles import init_film_params, extension_profiles

STOCKS = [
    ('kodak_portra_400', 'Portra 400', 'Kodak', '柔和肤色 · 日常叙事', '#C4B995'),
    ('kodak_gold_200', 'Gold 200', 'Kodak', '温暖日光 · 复古记忆', '#C7A869'),
    ('kodak_ektar_100', 'Ektar 100', 'Kodak', '细腻颗粒 · 浓郁风景', '#B87A68'),
    ('fujifilm_pro_400h', 'Pro 400H', 'Fujifilm', '清透绿色 · 轻盈人像', '#91A690'),
    ('fujifilm_c200', 'C200', 'Fujifilm', '自然鲜活 · 旅行日常', '#A2AD7D'),
    ('kodak_vision3_500t', 'Vision3 500T', 'Kodak', '钨丝灯光 · 电影夜色', '#7D9B9F'),
    ('fujifilm_velvia_100', 'Velvia 100', 'Fujifilm', '鲜明反转片 · 风景', '#9B8C9E'),
    ('kodak_ektachrome_100', 'Ektachrome E100', 'Kodak', '冷静高光 · 精确色彩', '#8F9FB3'),
    ('kodak_portra_160', 'Portra 160', 'Kodak', '上游彩色负片 · ISO 160', '#BEB49C'),
    ('kodak_portra_800', 'Portra 800', 'Kodak', '上游彩色负片 · ISO 800', '#BDA78D'),
    ('kodak_portra_800_push1', 'Portra 800 · Push +1', 'Kodak', '上游增感曲线 · 一档', '#AC9982'),
    ('kodak_portra_800_push2', 'Portra 800 · Push +2', 'Kodak', '上游增感曲线 · 两档', '#998A79'),
    ('kodak_ultramax_400', 'Ultramax 400', 'Kodak', '上游彩色负片 · ISO 400', '#B9A370'),
    ('kodak_kodachrome_64', 'Kodachrome 64', 'Kodak', '上游彩色反转片 · ISO 64', '#AA7867'),
    ('kodak_vision3_50d', 'Vision3 50D', 'Kodak', '电影负片 · 日光型', '#A9AD94'),
    ('kodak_vision3_250d', 'Vision3 250D', 'Kodak', '电影负片 · 日光型', '#9EA696'),
    ('kodak_vision3_200t', 'Vision3 200T', 'Kodak', '电影负片 · 钨光型', '#87999B'),
    ('kodak_verita_200d', 'Verita 200D', 'Kodak', '上游电影负片配置 · 日光型', '#A7A08B'),
    ('fujifilm_provia_100f', 'Provia 100F', 'Fujifilm', '上游彩色反转片 · ISO 100', '#9BA6A3'),
    ('fujifilm_xtra_400', 'Superia X-Tra 400', 'Fujifilm', '上游彩色负片 · ISO 400', '#91A087'),
    ('fujifilm_velvia_50', 'Velvia 50', 'Fujifilm', '低感反转片 · 层次与浓郁色彩', '#9F786F'),
    ('agfa_vista_100', 'Vista 100', 'Agfa', '日光负片 · 温暖日常', '#AD8062'),
    ('fujifilm_natura_1600', 'Natura 1600', 'Fujifilm', '高感负片 · 弱光与夜色', '#9A8B78'),
    ('kodak_tri_x_400', 'Tri-X 400', 'Kodak', '黑白负片 · D-76', '#858981'),
    ('kodak_tmax_100', 'T-Max 100', 'Kodak', '黑白负片 · D-76', '#989C94'),
    ('fujifilm_neopan_acros_100_ii', 'Neopan Acros II', 'Fujifilm', '黑白负片 · D-76', '#8D9688'),
    ('ilford_hp5_plus_400', 'HP5 Plus 400', 'Ilford', '黑白负片 · ILFOTEC HC', '#82877E'),
]

def main():
    dest = ROOT / 'assets/luts'
    dest.mkdir(parents=True, exist_ok=True)
    n = 33
    # C order [b,g,r,channel] so red is the fastest-changing sample.
    b, g, r = np.meshgrid(*[np.linspace(0, 1, n)] * 3, indexing='ij')
    rgb = np.stack([r, g, b], axis=-1).reshape(n, n*n, 3)
    stocks = []
    for ident, name, maker, desc, color in STOCKS:
        info=json.loads((ROOT/'vendor/spektrafilm/data/profiles'/f'{ident}.json').read_text(encoding='utf-8'))['info']
        if info['support']!='film' or info['stage']!='filming':
            raise ValueError(f'Not a camera film profile: {ident}')
        path = dest / f'{ident}.f32'
        if not path.exists():
            t = time.perf_counter()
            p = init_film_params(ident)
            p.io.input_color_space = 'sRGB'
            p.io.input_cctf_decoding = True
            p.io.output_color_space = 'sRGB'
            p.io.output_cctf_encoding = True
            p.io.scan_film = p.film.is_positive
            p.debug.lut_mode = True
            p.settings.use_enlarger_lut = True
            p.settings.use_scanner_lut = True
            result = np.clip(simulate(rgb, p), 0, 1).astype('<f4')
            if not np.isfinite(result).all():
                raise ValueError(f'Nonfinite output for {ident}')
            temporary=path.with_suffix('.tmp')
            result.tofile(temporary)
            temporary.replace(path)
            print(f'{ident}: {time.perf_counter()-t:.1f}s', flush=True)
        kind='bw' if info.get('channel_model')=='bw' else 'slide' if info['type']=='positive' else 'negative'
        stocks.append(dict(id=ident, name=name, maker=maker, description=desc,
                           color=color, type=kind, category='cinema' if info['use']=='cine' else kind, file=path.name))
        if ident in extension_profiles():
            stocks[-1].update(model_status='estimated', source='Jan Lohse / spectral_film_lut',
                             profile_license='MIT', profile_sha256=extension_profiles()[ident]['profile_sha256'])
    manifest = dict(size=n, input='srgb', output='srgb', order='r-fastest',
                    paper='kodak_portra_endura', stocks=stocks,
                    source='https://github.com/andreavolpato/spektrafilm',
                    author='Andrea Volpato; additional datasets Jan Lohse', license='CC BY-SA 4.0 (upstream); MIT (additional profiles)')
    temporary=dest/'manifest.tmp'
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(dest/'manifest.json')
    (dest / 'CHANGELOG.txt').write_text(
        '2026-11-05: Expanded to 20 actual camera-film profiles, including upstream push variants. Sampled by SpektraFilm Windows/Android from spektrafilm commit '
        '3bb2c2d2801ff68b92019cf1dbcbb133d60832bc by Andrea Volpato.\n'
        '33^3 sRGB encoded input/output, lut_mode=True (no spatial/stochastic effects, '
        'auto exposure or scanner corrections), Kodak Portra Endura paper, '
        'slide films scanned directly. 17^3 internal enlarger/scanner acceleration.\n'
        'Derived upstream LUTs remain CC BY-SA 4.0. Original profiles unchanged.\n'
        '2026-11-07: Added Velvia 50, Agfa Vista 100 and Natura 1600 spectral models from pinned Jan Lohse MIT numerical data. '
        'LUTs are interaction proxies sampled from the spectral engine, never final export substitutes. '
        'Negative extensions use the recorded Crystal Archive Type II neutral calibration, with uncalibrated DIR disabled. '
        'See spektrafilm/data/profile_extensions and docs/film-profile-expansion.md for source, fitting and modeling assumptions.\n', encoding='utf-8')

if __name__ == '__main__':
    main()
