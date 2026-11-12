"""Portable .spektrapair schema 1, retaining unrelated/forward JSON fields.

Uses SpektraLab HalfFramePair keys; complete SpektraFilm edits live in a
namespaced extension so a round trip does not silently lose local tools.
"""
from copy import deepcopy
from dataclasses import asdict
import json
import math
import os
from pathlib import Path
import tempfile


def number(value, default, low, high):
    if not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value):
        return default
    return max(low,min(high,float(value)))


def read_pair(path):
    path=Path(path)
    if path.stat().st_size>8*1024**2:raise ValueError('半格文件过大')
    value=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value,dict) or value.get('schemaVersion',1)!=1:raise ValueError('不支持此半格文件版本')
    for key in ('left','right'):
        hole=value.get(key)
        if hole is not None and (not isinstance(hole,dict) or not isinstance(hole.get('path'),str)):
            raise ValueError('半格照片记录不完整')
    return value


def pair_document(rows, options, original=None):
    if len(rows)!=2:raise ValueError('半格文件需要两个片位')
    value=deepcopy(original) if isinstance(original,dict) else {}
    value.update(schemaVersion=1,folder=str(Path(next((row['path'] for row in rows if row.get('path')),'' )).parent),
                 spacingMM=number(options.get('pair_spacing_mm'),1.,.5,2.),
                 onStrip=bool(options.get('pair_on_strip',True)),turned=options.get('pair_axis')=='vertical')
    for key,row in zip(('left','right'),rows):
        if row.get('_empty'):
            value[key]=deepcopy(value.get(key)) if row.get('missing_path') else None
            continue
        settings=row['settings'];data=asdict(settings)
        hole=deepcopy(value.get(key)) if isinstance(value.get(key),dict) else {}
        hole.update(path=str(Path(row['path']).resolve()),
                    placement=dict(scale=number(row.get('zoom'),1.,1.,5.),
                                   x=number(row.get('pan_x'),.5,0,1)*2-1,
                                   y=number(row.get('pan_y'),.5,0,1)*2-1,
                                   quarterTurns=(int(row.get('rotation',0))//90)%4),
                    exposureEV=settings.exposure,
                    decode=dict(whiteBalance='custom' if (settings.temperature!=6500 or settings.tint) else 'asShot',
                                temperature=settings.temperature,tint=settings.tint,
                                lensCorrection=settings.lens_correction,defringe=settings.defringe),
                    geometry=dict(crop=dict(x=settings.geometry.crop[0],y=settings.geometry.crop[1],
                        width=settings.geometry.crop[2]-settings.geometry.crop[0],height=settings.geometry.crop[3]-settings.geometry.crop[1]),
                        quarterTurns=settings.geometry.quarter_turns,flipH=settings.geometry.flip_horizontal,flipV=settings.geometry.flip_vertical,
                        angle=settings.geometry.rotation,vertical=settings.geometry.vertical,horizontal=settings.geometry.horizontal),
                    autoExposure=False,print=dict(brightnessStops=-settings.print_exposure,yFilterShift=settings.print_y/100,
                        mFilterShift=settings.print_m/100,preflashExposure=settings.preflash_exposure),
                    printScope=hole.get('printScope','frame'),exposureScope=hole.get('exposureScope','frame'),
                    dated=bool(row.get('dated',True)))
        extension=deepcopy(hole.get('spektrafilm')) if isinstance(hole.get('spektrafilm'),dict) else {}
        extension['settings']=data;hole['spektrafilm']=extension;value[key]=hole
    extension=deepcopy(value.get('spektrafilm')) if isinstance(value.get('spektrafilm'),dict) else {}
    # Options are primitive UI state only; never include prepared pixels.
    extension['options']={key:item for key,item in options.items() if isinstance(item,(str,int,float,bool))}
    value['spektrafilm']=extension
    return value


def write_pair(path, value):
    path=Path(path)
    if path.suffix.lower()!='.spektrapair':path=path.with_suffix('.spektrapair')
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,prefix=path.name+'.',suffix='.tmp',delete=False) as output:
            temporary=output.name;json.dump(value,output,ensure_ascii=False,indent=2,allow_nan=False);output.flush();os.fsync(output.fileno())
        os.replace(temporary,path)
    finally:
        if temporary and Path(temporary).exists():Path(temporary).unlink()
    return path


def hole_settings(hole, defaults):
    """Mirror the portable decode/geometry fields when no native edit is present."""
    data=deepcopy(defaults)
    extension=hole.get('spektrafilm') or {}
    if isinstance(extension,dict) and isinstance(extension.get('settings'),dict):
        return deepcopy(extension['settings'])
    data['exposure']=number(hole.get('exposureEV'),0.,-5,5)+number(hole.get('meteredEV'),0.,-20,20)
    decode=hole.get('decode') or {}
    if decode.get('whiteBalance')!='asShot':
        data.update(temperature=number(decode.get('temperature'),6500,2000,15000),tint=number(decode.get('tint'),0,-100,100))
    geometry=hole.get('geometry') or {};crop=geometry.get('crop') or {}
    if isinstance(crop,dict):
        x=number(crop.get('x'),0,0,1);y=number(crop.get('y'),0,0,1)
        right=min(1.,x+number(crop.get('width'),1,.001,1));bottom=min(1.,y+number(crop.get('height'),1,.001,1))
        data['geometry']=dict(crop=[x,y,right,bottom],quarter_turns=int(number(geometry.get('quarterTurns'),0,0,3)),
            flip_horizontal=bool(geometry.get('flipH')),flip_vertical=bool(geometry.get('flipV')),
            rotation=number(geometry.get('angle'),0,-45,45),vertical=number(geometry.get('vertical'),0,-100,100),
            horizontal=number(geometry.get('horizontal'),0,-100,100))
    trim=hole.get('print') or {}
    if isinstance(trim,dict):
        data.update(print_exposure=-number(trim.get('brightnessStops'),0,-5,5),print_y=number(trim.get('yFilterShift'),0,-1,1)*100,
                    print_m=number(trim.get('mFilterShift'),0,-1,1)*100,preflash_exposure=number(trim.get('preflashExposure'),0,0,1))
    return data
