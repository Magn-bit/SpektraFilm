"""Portable output contracts; every resizing/encoding choice is explicit."""
from dataclasses import dataclass,asdict
import math
import re
import string


COLOR_SPACES=('sRGB','Adobe RGB (1998)','Display P3','ProPhoto RGB')
FORMATS=('jpeg','heif','png','tiff','dng','di','raw')


@dataclass(frozen=True)
class OutputRecipe:
    id:str='jpg-high'
    name:str='高品质 JPG'
    format:str='jpeg'
    bit_depth:int=8
    color_space:str='sRGB'
    quality:int=100
    long_edge:int=0
    naming:str='{name}_{film}'
    subfolder:str='高品质 JPG'
    conflict:str='rename'
    open_after:bool=False
    short_edge:int=0
    megapixels:float=0.0
    di_blue_compensation:bool=False


DEFAULT_RECIPES=(OutputRecipe(),
    OutputRecipe(id='jpg-share',name='分享 JPG',quality=85,subfolder='分享 JPG'),
    OutputRecipe(id='tiff',name='无损 TIFF',format='tiff',bit_depth=16,subfolder='无损 TIFF'),
    OutputRecipe(id='png',name='无损 PNG',format='png',bit_depth=16,subfolder='无损 PNG'),
    OutputRecipe(id='dng',name='线性 DNG',format='dng',bit_depth=16,subfolder='线性 DNG'),
    OutputRecipe(id='cineon-di',name='Cineon DI',format='di',bit_depth=16,color_space='ProPhoto RGB',subfolder='Cineon DI'),
    OutputRecipe(id='raw',name='RAW 原片',format='raw',bit_depth=16,subfolder='RAW 原片'))


def _text(value,default,limit=80):
    if not isinstance(value,str):return default
    return value.strip()[:limit] or default


def normalize_recipe(value):
    if isinstance(value,OutputRecipe):return value
    if not isinstance(value,dict):raise ValueError('导出配方应为参数文档')
    default=OutputRecipe()
    result={key:_text(value.get(key),getattr(default,key)) for key in ('id','name','naming','subfolder')}
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',result['id']):raise ValueError('配方标识无效')
    result['format']=value.get('format',default.format)
    if result['format'] not in FORMATS:raise ValueError('不支持的导出格式')
    result['color_space']=value.get('color_space',default.color_space)
    if result['color_space'] not in COLOR_SPACES:raise ValueError('不支持的输出色彩空间')
    for key,low,high in (('quality',1,100),('long_edge',0,32000),('short_edge',0,32000),('megapixels',0,1000)):
        number=value.get(key,getattr(default,key))
        if isinstance(number,bool) or not isinstance(number,(int,float)) or not math.isfinite(number):
            raise ValueError('导出参数无效：'+key)
        result[key]=max(low,min(high,float(number) if key=='megapixels' else int(number)))
    if sum(bool(result[key]) for key in ('long_edge','short_edge','megapixels'))>1:
        raise ValueError('仅可选择一种输出缩放方式')
    result['bit_depth']=value.get('bit_depth',default.bit_depth)
    if result['bit_depth'] not in (8,16):raise ValueError('位深只能为8或16')
    if result['format'] in ('jpeg','heif') and result['bit_depth']!=8:raise ValueError('JPEG / HEIF输出为8位')
    if result['format']=='dng' and result['bit_depth']!=16:raise ValueError('线性DNG输出为16位')
    resized=any(result[key] for key in ('long_edge','short_edge','megapixels'))
    if result['format']=='di' and (result['bit_depth']!=16 or result['color_space']!='ProPhoto RGB' or resized):
        raise ValueError('Cineon DI 使用16位 ProPhoto原色密度编码与原始像素尺寸')
    if result['format']=='raw' and resized:raise ValueError('RAW原片不能缩放')
    if result['format']=='dng' and result['color_space']!='sRGB':
        raise ValueError('线性DNG使用线性sRGB原色，不能标为其他空间')
    if any(c in result['subfolder'] for c in '/\\:') or result['subfolder'] in ('.','..'):
        raise ValueError('导出子文件夹必须为单个名称')
    try:
        fields=[(field,fmt,conversion) for _,field,fmt,conversion in string.Formatter().parse(result['naming']) if field is not None]
    except ValueError:raise ValueError('文件命名格式无效')
    if any(field not in ('name','film','paper','index','date','year','month','day') or fmt or conversion for field,fmt,conversion in fields):
        raise ValueError('文件名仅支持{name}、{film}、{paper}、{index}、{date}、{year}、{month}、{day}')
    if not fields:raise ValueError('文件名至少包含一个命名字段')
    result['conflict']=value.get('conflict','rename')
    if result['conflict'] not in ('rename','skip'):raise ValueError('冲突策略应为编号或跳过')
    result['open_after']=bool(value.get('open_after',False))
    if not isinstance(value.get('di_blue_compensation',False),bool):raise ValueError('蓝通道补偿需要布尔值')
    result['di_blue_compensation']=value.get('di_blue_compensation',False)
    return OutputRecipe(**result)


def safe_filename(value):
    value=''.join('_' if ord(c)<32 or c in '<>:"/\\|?*' else c for c in str(value)).strip(' .')
    if not value:return '照片'
    if value.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}:
        value='_'+value
    return value[:180]


def recipe_json(recipe):return asdict(normalize_recipe(recipe))


def recipe_size(width,height,recipe):
    """Explicit fit downsampling only; never silently upsample a source."""
    recipe=normalize_recipe(recipe)
    scale=1.
    if recipe.long_edge:scale=min(scale,recipe.long_edge/max(width,height))
    if recipe.short_edge:scale=min(scale,recipe.short_edge/min(width,height))
    if recipe.megapixels:scale=min(scale,math.sqrt(recipe.megapixels*1000000/(width*height)))
    return max(1,round(width*scale)),max(1,round(height*scale))
