"""Small, scoped photo styles and explicit partial Adobe XMP conversion."""
from __future__ import annotations
from dataclasses import asdict
import hashlib
import json
import math
import re
from pathlib import Path
import xml.etree.ElementTree as ET

try:
    from .color_tools import (CurveSet, ColorGrading, ChannelMixer, normalize_curves,
                              normalize_grading, normalize_channel_mixer)
    from .hsl import HslSettings, normalize_hsl, BANDS
except ImportError:  # The same module is copied into Android's Python root.
    from color_tools import (CurveSet, ColorGrading, ChannelMixer, normalize_curves,
                             normalize_grading, normalize_channel_mixer)
    from hsl import HslSettings, normalize_hsl, BANDS

STYLE_DEFAULTS = dict(contrast=0.,saturation=0.,vibrance=0.,highlights=0.,shadows=0.,
                      black_point=0.,white_point=100.,gamma=1.,
                      curves=asdict(CurveSet()),grading=asdict(ColorGrading()),
                      channel_mixer=asdict(ChannelMixer()),hsl=asdict(HslSettings()),look_lut='',look_strength=100.)
NONE_STYLE_ID = 'none'
LIMITS = dict(contrast=(-100,100),saturation=(-100,100),vibrance=(-100,100),
              highlights=(-100,100),shadows=(-100,100),black_point=(0,20),white_point=(80,100),gamma=(.5,2),look_strength=(0,100))


def normalize_style(value):
    if not isinstance(value,dict):raise ValueError('预设应为参数文档')
    raw=value.get('settings',{})
    if not isinstance(raw,dict):raise ValueError('预设缺少 settings 参数')
    settings=dict(STYLE_DEFAULTS)
    for key,(low,high) in LIMITS.items():
        item=raw.get(key,settings[key])
        if not isinstance(item,(int,float)) or isinstance(item,bool) or not low<=item<=high:
            raise ValueError(f'预设参数超出范围：{key}')
        settings[key]=float(item)
    settings['curves']=asdict(normalize_curves(raw.get('curves')))
    settings['grading']=asdict(normalize_grading(raw.get('grading')))
    settings['channel_mixer']=asdict(normalize_channel_mixer(raw.get('channel_mixer')))
    settings['hsl']=asdict(normalize_hsl(raw.get('hsl')))
    ident=raw.get('look_lut','')
    if not isinstance(ident,str) or (ident and not re.fullmatch(r'[a-z0-9_-]{1,80}',ident)):
        raise ValueError('预设色彩资源标识无效')
    settings['look_lut']=ident
    return dict(id=str(value.get('id','custom'))[:100],name=str(value.get('name','自定义风格'))[:80],
                category=value.get('category') if value.get('category') in ('portrait','landscape','general') else 'general',
                description=str(value.get('description',''))[:240],author=str(value.get('author',''))[:100],
                kind=str(value.get('kind','imported'))[:40],source=str(value.get('source',''))[:500],settings=settings,
                warnings=[str(w)[:250] for w in value.get('warnings',[])[:24]])


def catalog(path=None):
    if path is None:path=Path(__file__).resolve().parents[1]/'assets/styles/presets.json'
    payload=json.loads(Path(path).read_text(encoding='utf-8'))
    styles=[normalize_style(item) for item in payload['presets']]
    # The JSON order is intentional: the neutral entry stays first, followed
    # by the curated portrait and landscape groups. Do not alphabetize the
    # picker, because that destroys the product's browsing order.
    neutral=[item for item in styles if item['id']==NONE_STYLE_ID]
    remaining=[item for item in styles if item['id']!=NONE_STYLE_ID]
    return neutral[:1]+remaining


def apply_style(mapping,style):
    """Replace only style fields; source geometry, masks, WB and film survive."""
    result=dict(mapping)
    result.update(normalize_style(style)['settings'])
    return result


def import_style_json(data,filename='preset.xmp'):
    """Return canonical JSON for both UIs, with unsupported XMP scope listed.

    Exposure/WB/geometry/masks are deliberately excluded from a style. Adobe
    HSL values map to our eight-band mixer. ProcessVersion, profiles, camera
    calibration and proprietary rendering are not claimed to match.
    """
    if isinstance(data,str):raw=data.encode('utf-8')
    else:raw=bytes(data)
    if len(raw)>2*1024**2:raise ValueError('预设文件过大（上限 2 MiB）')
    suffix=Path(filename).suffix.lower()
    if suffix in ('.json','.sfpreset'):
        document=json.loads(raw.decode('utf-8-sig'))
        preset=normalize_style(document)
        preset.update(id='import-'+hashlib.sha256(raw).hexdigest()[:16],kind='imported',source=Path(filename).name)
        return json.dumps(preset,ensure_ascii=False,separators=(',',':'),allow_nan=False)
    if suffix!='.xmp':raise ValueError('支持 .xmp、.sfpreset 或预设 JSON；尼康 NP3 配方不能直接套用为本引擎参数。')
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise ValueError('不支持包含实体或文档类型的 XML')
    root=ET.fromstring(raw)
    crs='{http://ns.adobe.com/camera-raw-settings/1.0/}'
    # Read the develop description only. A nested Look also contains CRS
    # fields (including Name/UUID); those must never overwrite the preset.
    description=next((node for node in root.iter() if node.tag.endswith('}Description') and
                      (any(key.startswith(crs) for key in node.attrib) or
                       any(child.tag.startswith(crs) for child in node))),None)
    if description is None:raise ValueError('此 XMP 不含可读取的显影参数')
    nodes={child.tag[len(crs):]:child for child in description if child.tag.startswith(crs)}
    scalars={key[len(crs):]:value for key,value in description.attrib.items() if key.startswith(crs)}
    scalars.update({key:node.text.strip() for key,node in nodes.items() if node.text and node.text.strip() and not len(node)})
    settings={};mapped=[]
    for adobe,local in (('Contrast2012','contrast'),('Saturation','saturation'),('Vibrance','vibrance'),
                         ('Highlights2012','highlights'),('Shadows2012','shadows')):
        value=scalars.get(adobe)
        if value is None and adobe in nodes:value=nodes[adobe].text
        if value is not None:
            try:
                number=float(value)
                if not math.isfinite(number):raise ValueError()
                settings[local]=max(-100.,min(100.,number));mapped.append(adobe)
            except (TypeError,ValueError):raise ValueError(f'无法读取 XMP 参数：{adobe}')
    for band in BANDS:
        for adobe,local in (('HueAdjustment','hue'),('SaturationAdjustment','saturation'),('LuminanceAdjustment','luminance')):
            field=adobe+band.capitalize()
            if field not in scalars:continue
            try:number=float(scalars[field])
            except (ValueError,TypeError):raise ValueError(f'无法读取 XMP 参数：{field}')
            if not math.isfinite(number) or not -100<=number<=100:raise ValueError(f'XMP 参数超出范围：{field}')
            settings.setdefault('hsl',{}).setdefault(band,{})[local]=number
            mapped.append(field)
    curves={}
    for adobe,local in (('ToneCurvePV2012','master'),('ToneCurvePV2012Red','red'),
                         ('ToneCurvePV2012Green','green'),('ToneCurvePV2012Blue','blue')):
        node=nodes.get(adobe)
        if node is None:continue
        points=[]
        for item in node.iter():
            if item.tag.endswith('}li') and item.text:
                try:x,y=map(float,item.text.split(','));points.append([x/255.,y/255.])
                except (TypeError,ValueError):raise ValueError(f'无法读取 XMP 曲线：{adobe}')
        if len(points)>=2:curves[local]=points;mapped.append(adobe)
    if curves:settings['curves']=curves
    for adobe,zone in (('Shadow','shadows'),('Midtone','midtones'),('Highlight','highlights')):
        # ColourGrade* fields are newer; SplitToning* are the older two-way schema.
        hue_key='ColorGrade'+adobe+'Hue';sat_key='ColorGrade'+adobe+'Sat'
        if hue_key not in scalars:hue_key='SplitToning'+adobe+'Hue'
        if sat_key not in scalars:sat_key='SplitToning'+adobe+'Saturation'
        if hue_key in scalars and sat_key in scalars:
            try:hue=float(scalars[hue_key]);sat=float(scalars[sat_key])
            except ValueError:raise ValueError('无法读取 XMP 色彩分级')
            if not (0<=hue<=360 and 0<=sat<=100):raise ValueError('XMP 色轮参数超出范围')
            settings.setdefault('grading',{})[zone]=dict(hue=hue,saturation=sat,luminance=0)
            mapped.extend([hue_key,sat_key])
    if not mapped:raise ValueError('此 XMP 没有可转换的基础色调、HSL、点曲线或色轮参数；未应用。')
    name=Path(filename).stem
    if 'Name' in nodes:
        name=next((item.text for item in nodes['Name'].iter() if item.tag.endswith('}li') and item.text),name)
    ignored=sorted((set(scalars)|set(nodes))-set(mapped)-{'Name','Version','HasSettings','SupportsColor','SupportsMonochrome','PresetType','UUID','ProcessVersion','ToneCurveName2012'})
    warnings=['XMP 部分转换：基础参数、HSL、曲线和色轮映射到本引擎，不能等同 Adobe 原版效果。',
              '曝光、白平衡、几何和蒙版保留每张照片原有编辑，不由风格覆盖。']
    profiles=[]
    if scalars.get('CameraProfile'):profiles.append(scalars['CameraProfile'])
    if 'Look' in nodes:
        look=nodes['Look']
        for node in look.iter():
            if node.attrib.get(crs+'Name'):profiles.append(node.attrib[crs+'Name'])
            if node.tag==crs+'Name' and node.text and node.text.strip():profiles.append(node.text.strip())
    if profiles:warnings.append('依赖色彩配置：'+', '.join(dict.fromkeys(profiles))+'；该配置尚未载入，Adobe 配置文件不能仅靠参数还原。')
    elif 'Look' in nodes:warnings.append('此预设包含 Adobe Look 资源依赖，尚未载入；当前仅转换可支持的参数。')
    if ignored:warnings.append('未转换字段：'+', '.join(ignored[:16]))
    preset=normalize_style(dict(id='import-'+hashlib.sha256(raw).hexdigest()[:16],name=name,
        description='XMP 参数转换',author='外部文件',kind='xmp-partial',source=Path(filename).name,
        settings=settings,warnings=warnings))
    return json.dumps(preset,ensure_ascii=False,separators=(',',':'),allow_nan=False)
