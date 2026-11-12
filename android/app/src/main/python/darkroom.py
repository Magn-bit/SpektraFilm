"""Small, shared material catalogue; selections refer to real spectral profiles."""
import json
from importlib import resources
from functools import lru_cache

BLACK_AND_WHITE = frozenset({
    'kodak_tri_x_400', 'kodak_tmax_100',
    'fujifilm_neopan_acros_100_ii', 'ilford_hp5_plus_400',
})
PAPERS = (
    {'id': 'kodak_portra_endura', 'name': 'Portra Endura', 'kind': 'color'},
    {'id': 'kodak_endura_premier', 'name': 'Endura Premier', 'kind': 'color'},
    {'id': 'kodak_ektacolor_edge', 'name': 'Ektacolor Edge', 'kind': 'color'},
    {'id': 'kodak_supra_endura', 'name': 'Supra Endura', 'kind': 'color'},
    {'id': 'kodak_ultra_endura', 'name': 'Ultra Endura', 'kind': 'color'},
    {'id': 'fujifilm_crystal_archive_typeii', 'name': 'Crystal Archive II', 'kind': 'color'},
    {'id': 'kodak_2383', 'name': 'Vision 2383', 'kind': 'color'},
    {'id': 'kodak_2393', 'name': 'Vision Premier 2393', 'kind': 'color'},
    {'id': 'ilford_multigrade_iv_rc', 'name': 'Multigrade IV RC', 'kind': 'bw'},
)
PAPER_IDS = frozenset(item['id'] for item in PAPERS)
FILM_FORMATS = (
    {'name': '135', 'mm': 35.0}, {'name': '半格', 'mm': 24.0},
    {'name': '645', 'mm': 56.0}, {'name': '6 × 6', 'mm': 60.0},
    {'name': '6 × 7', 'mm': 70.0}, {'name': '6 × 9', 'mm': 90.0},
    {'name': '4 × 5', 'mm': 120.0},
)


@lru_cache(maxsize=64)
def _profile_info(stock):
    path = resources.files('spektrafilm.data') / 'profiles' / (stock + '.json')
    return json.loads(path.read_text(encoding='utf-8'))['info']


def default_paper_for_stock(stock):
    if stock in BLACK_AND_WHITE:
        return 'ilford_multigrade_iv_rc'
    target = _profile_info(stock).get('target_print')
    return target if target in PAPER_IDS else 'kodak_portra_endura'


def paper_choices(stock):
    kind = 'bw' if stock in BLACK_AND_WHITE else 'color'
    return [dict(item) for item in PAPERS if item['kind'] == kind]


def resolve_paper(stock, paper='auto'):
    if stock in BLACK_AND_WHITE:
        return 'ilford_multigrade_iv_rc'
    if paper == 'auto' or paper not in {item['id'] for item in paper_choices(stock)}:
        return default_paper_for_stock(stock)
    return paper


def scans_directly(stock):
    return _profile_info(stock).get('type') == 'positive'
