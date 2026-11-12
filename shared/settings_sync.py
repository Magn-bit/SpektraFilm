"""Disjoint, explicit edit groups for per-photo, undoable synchronisation."""

from copy import deepcopy
from dataclasses import asdict,is_dataclass
from pathlib import Path

CATEGORIES_V1 = {
    'film': ('stock', 'film_enabled', 'spectral', 'strength', 'grain', 'grain_size',
             'grain_type', 'film_format_mm','film_format_axis', 'halation', 'halation_scatter_amount',
             'halation_scatter_scale', 'halation_spatial_scale', 'halation_boost_ev',
             'halation_protect_ev', 'antihalation_removed', 'dir_couplers_amount',
             'density_curve_gamma', 'halation_headroom_ev'),
    'paper': ('paper', 'print_exposure', 'print_y', 'print_m', 'glare','preflash_exposure','minilab_active'),
    'exposure': ('exposure', 'metering_method', 'scene_latitude_active', 'scene_latitude_norm',
                 'scene_latitude_highlight_knee', 'scene_latitude_highlight_room',
                 'scene_latitude_shadow_knee', 'scene_latitude_shadow_room',
                 'scene_latitude_rolloff', 'scene_latitude_max_lift'),
    'WB': ('temperature', 'tint', 'warmth','scene_curves'),
    'basic': ('contrast', 'saturation', 'vibrance', 'highlights', 'shadows',
              'black_point', 'white_point', 'gamma', 'texture', 'clarity', 'dehaze',
              'vignette', 'lens_correction', 'defringe', 'sharpening', 'noise_luminance', 'noise_color',
              'whites','blacks','levels','brightness'),
    'color': ('calibration_shadow_tint', 'calibration_red_hue', 'calibration_red_saturation',
              'calibration_green_hue', 'calibration_green_saturation', 'calibration_blue_hue',
              'calibration_blue_saturation', 'curves', 'grading', 'hsl', 'look_lut', 'look_strength'),
    'masks': ('masks',),
    'geometry': ('geometry',),
}
# Material choice, capture placement and physical effects are independent.
# The old film/paper IDs remain accepted by scripts, now selecting materials only.
CATEGORIES = {
    'materials': ('stock', 'film_enabled', 'spectral', 'strength', 'paper','scan_film','digital_intermediate'),
    'exposure': ('exposure', 'print_exposure', 'metering_method'),
    'WB': ('temperature', 'tint', 'warmth', 'print_y', 'print_m'),
    'film_effects': CATEGORIES_V1['film'][4:]+('grain_layered','grain_enabled','halation_enabled'),
    'print_effects': ('glare', 'preflash_exposure', 'minilab_active','extended_dynamic_range','print_effects','hdr_enabled','hdr_peak_stops'),
    'scene_placement': tuple(key for key in CATEGORIES_V1['exposure'] if key.startswith('scene_')) + ('scene_curves',),
    **{key:CATEGORIES_V1[key] for key in ('basic','color','masks','geometry')},
    'film': ('stock', 'film_enabled', 'spectral', 'strength'),
    'paper': ('paper','scan_film','digital_intermediate'),
}
CATEGORIES['color']=CATEGORIES['color']+('channel_mixer',)
DEFAULT_CATEGORIES = ('materials','exposure','WB','film_effects','print_effects')
CATEGORY_TITLES = {'materials':'胶片与相纸','film':'胶片','paper':'相纸','exposure':'曝光','WB':'白平衡',
                   'film_effects':'胶片效果','print_effects':'相纸效果','scene_placement':'场景置位',
                   'basic':'基础调整','color':'调色','masks':'蒙版','geometry':'裁切与几何'}
CLIP_FORMAT='SpektraFilm.settings-clip'
CLIP_VERSION=2


def _portable(value):
    if is_dataclass(value):return {key:_portable(item) for key,item in asdict(value).items()}
    if isinstance(value,dict):return {key:_portable(item) for key,item in value.items()}
    if isinstance(value,(list,tuple)):return [_portable(item) for item in value]
    return value


def category_fields(categories):
    if not isinstance(categories, (list, tuple, set)):
        raise ValueError('请选择要同步的分类')
    if any(key not in CATEGORIES for key in categories):
        raise ValueError('未知的调整分类')
    return tuple(dict.fromkeys(field for key in categories for field in CATEGORIES[key]))


def make_clip(settings,categories=DEFAULT_CATEGORIES,source_name=''):
    """Portable category clipboard; no source path or GUI session is included."""
    if is_dataclass(settings):settings=asdict(settings)
    if not isinstance(settings,dict):raise ValueError('调整设置应为参数文档')
    fields=category_fields(categories)
    return dict(format=CLIP_FORMAT,version=CLIP_VERSION,categories=list(dict.fromkeys(categories)),
                source_name=Path(str(source_name)).name[:255],
                settings={key:_portable(settings[key]) for key in fields if key in settings})


def normalize_clip(value):
    if not isinstance(value,dict) or value.get('format')!=CLIP_FORMAT or value.get('version') not in (1,CLIP_VERSION):
        raise ValueError('不支持的参数剪贴板格式')
    categories=value.get('categories')
    if value['version']==1:
        if not isinstance(categories,(list,tuple)) or any(key not in CATEGORIES_V1 for key in categories):
            raise ValueError('未知的调整分类')
        fields=tuple(key for group in categories for key in CATEGORIES_V1[group])
    else:fields=category_fields(categories)
    settings=value.get('settings')
    if not isinstance(settings,dict) or any(key not in fields for key in settings):
        raise ValueError('剪贴板参数与分类不一致')
    if value['version']==1:
        categories=[key for key,group in CATEGORIES.items() if key not in ('film','paper') and set(group).intersection(settings)]
    return make_clip(settings,categories,value.get('source_name',''))


def apply_clip(target,clip,categories=None):
    """Apply only fields captured at copy time, preserving target-only edits.

    Typed settings validation belongs to the renderer/controller; this shared
    transport does not import desktop Qt, a renderer or a camera decoder.
    """
    if is_dataclass(target):target=asdict(target)
    if not isinstance(target,dict):raise ValueError('目标设置应为参数文档')
    clip=normalize_clip(clip)
    selected=clip['categories'] if categories is None else categories
    fields=category_fields(selected)
    result=deepcopy(target)
    for key in fields:
        if key in clip['settings']:result[key]=deepcopy(clip['settings'][key])
    return result
