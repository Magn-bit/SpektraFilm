"""Runtime adaptation for additional, independently sourced spectral profiles.

The original twenty upstream profiles retain their original configuration.
Additional negative films use their explicitly calibrated paper/filter pair;
unmeasured DIR chemistry is disabled instead of borrowing another stock's data.
Generic user-controlled grain and halation remain separate from calibration.
"""
from functools import lru_cache
from importlib import resources
import json
try:
    from shared.darkroom import BLACK_AND_WHITE, resolve_paper
except ImportError:  # The Android scientific compatibility package is flat.
    from darkroom import BLACK_AND_WHITE, resolve_paper


@lru_cache(maxsize=1)
def extension_profiles():
    package = resources.files('spektrafilm.data')
    manifest = package / 'profile_extensions' / 'manifest.json'
    if not manifest.is_file():
        return {}
    return json.loads(manifest.read_text(encoding='utf-8'))['profiles']


def print_for_stock(stock, fallback='auto'):
    if fallback in ('auto', None, ''):
        return extension_profiles().get(stock, {}).get('paper') or resolve_paper(stock)
    return resolve_paper(stock, fallback)


def init_film_params(stock, paper='auto'):
    from spektrafilm import init_params
    params = init_params(stock, print_for_stock(stock, paper))
    extension = extension_profiles().get(stock)
    if extension:
        params.settings.neutral_print_filters_from_database = False
        params.film_render.dir_couplers.active = False
        # A stock's neutral pack is specific to its calibrated print material.
        neutral = extension.get('neutral_filters_cmy') if params.print.info.stock == extension.get('paper') else None
        if neutral is not None:
            if len(neutral) != 3 or not all(0 <= float(v) <= 250 for v in neutral):
                raise ValueError('Invalid installed spectral neutral-filter calibration')
            params.enlarger.c_filter_neutral, params.enlarger.m_filter_neutral, params.enlarger.y_filter_neutral = neutral
            params.enlarger.illuminant = extension['illuminant']
        params.scanner.black_correction = False
        params.scanner.white_correction = False
    if stock in BLACK_AND_WHITE:
        # These datasets deliberately contain no fitted spectral window/surface.
        params.settings.apply_hanatos2025_adaptation_window = False
        params.settings.apply_hanatos2025_adaptation_surface = False
        params.settings.neutral_print_filters_from_database = False
        params.film_render.dir_couplers.active = False
        params.enlarger.c_filter_neutral = 0
        params.enlarger.m_filter_neutral = 0
        params.enlarger.y_filter_neutral = 68
        params.enlarger.illuminant = 'TH-KG3'
        params.scanner.black_correction = False
        params.scanner.white_correction = False
    return params
