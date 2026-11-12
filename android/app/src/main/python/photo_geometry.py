"""Bounded projective corrections on the original oriented pixel grid."""
from __future__ import annotations
from dataclasses import dataclass
import json
import math
import numpy as np


@dataclass(frozen=True)
class Geometry:
    rotation: float = 0.
    vertical: float = 0.
    horizontal: float = 0.
    aspect: float = 0.
    scale: float = 100.
    flip_horizontal: bool = False
    flip_vertical: bool = False
    auto_crop: bool = True
    crop: tuple = (0.,0.,1.,1.)


def normalize_geometry(value):
    if isinstance(value, Geometry): return value
    if isinstance(value, str):
        try: value=json.loads(value)
        except (TypeError, ValueError): value={}
    if not isinstance(value, dict): return Geometry()
    result={}
    for key, (low, high, default) in {
        'rotation':(-45.,45.,0.),'vertical':(-100.,100.,0.),'horizontal':(-100.,100.,0.),
        'aspect':(-100.,100.,0.),'scale':(100.,200.,100.)}.items():
        number=value.get(key, default)
        if isinstance(number,(int,float)) and not isinstance(number,bool) and math.isfinite(number):
            result[key]=max(low,min(high,float(number)))
    for key in ('flip_horizontal','flip_vertical','auto_crop'):
        if isinstance(value.get(key),bool): result[key]=value[key]
    crop=value.get('crop')
    if (isinstance(crop,(list,tuple)) and len(crop)==4
            and all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in crop)):
        left,right=sorted((max(0.,min(1.,float(crop[0]))),max(0.,min(1.,float(crop[2])))))
        top,bottom=sorted((max(0.,min(1.,float(crop[1]))),max(0.,min(1.,float(crop[3])))))
        if right-left>1e-5 and bottom-top>1e-5:result['crop']=(left,top,right,bottom)
    return Geometry(**result)


def is_neutral(geometry):
    g=normalize_geometry(geometry)
    return (not any((g.rotation,g.vertical,g.horizontal,g.aspect,g.flip_horizontal,g.flip_vertical))
            and g.scale==100. and g.crop==(0.,0.,1.,1.))


def crop_box(width,height,geometry=None):
    g=normalize_geometry(geometry)
    if width<1 or height<1:raise ValueError('Invalid source dimensions')
    left=max(0,min(width-1,round(g.crop[0]*width)))
    top=max(0,min(height-1,round(g.crop[1]*height)))
    right=max(left+1,min(width,round(g.crop[2]*width)))
    bottom=max(top+1,min(height,round(g.crop[3]*height)))
    return left,top,right,bottom


def output_size(width,height,geometry=None):
    left,top,right,bottom=crop_box(width,height,geometry)
    return right-left,bottom-top


def crop_box_json(width,height,geometry_json='{}'):
    return json.dumps(crop_box(int(width),int(height),geometry_json))


def output_size_json(width,height,geometry_json='{}'):
    return json.dumps(output_size(int(width),int(height),geometry_json))


def _translation(x,y):
    return np.array([[1.,0.,x],[0.,1.,y],[0.,0.,1.]],dtype=np.float64)


def geometry_matrix(width,height,geometry=None):
    """Source pixel-centre -> output pixel-centre homography; size is unchanged.

    Auto crop finds the least uniform enlargement which puts every output
    corner inside the source. It changes field of view, never output resolution.
    """
    g=normalize_geometry(geometry)
    if width<1 or height<1: raise ValueError('Invalid source dimensions')
    if is_neutral(g): return np.eye(3,dtype=np.float64)
    cx,cy=(width-1)/2.,(height-1)/2.
    angle=math.radians(g.rotation);c,s=math.cos(angle),math.sin(angle)
    rotate=np.array([[c,-s,0.],[s,c,0.],[0.,0.,1.]])
    aspect=2**(g.aspect/100.)
    shape=np.diag([aspect*(-1 if g.flip_horizontal else 1),
                   (-1 if g.flip_vertical else 1)/aspect,1.])
    perspective=np.eye(3)
    perspective[2,0]=g.horizontal*.003/max(cx,.5)
    perspective[2,1]=g.vertical*.003/max(cy,.5)
    origin=_translation(-cx,-cy);destination=_translation(cx,cy)
    core=rotate@shape@perspective@origin
    corners=np.array([[0.,0.,1.],[width-1.,0.,1.],[0.,height-1.,1.],[width-1.,height-1.,1.]]).T
    def matrix(zoom):return destination@np.diag([zoom,zoom,1.])@core
    def fits(zoom):
        mapped=np.linalg.inv(matrix(zoom))@corners
        mapped/=mapped[2:3]
        return bool(np.all((mapped[0]>=-1e-8)&(mapped[0]<=width-1+1e-8)
                           &(mapped[1]>=-1e-8)&(mapped[1]<=height-1+1e-8)))
    zoom=g.scale/100.
    if g.auto_crop and not fits(zoom):
        low,high=zoom,16.
        for _ in range(40):
            midpoint=(low+high)/2
            if fits(midpoint):high=midpoint
            else:low=midpoint
        zoom=high*(1+1e-8)
    return matrix(zoom)


def matrix_json(width,height,geometry_json='{}'):
    # Android Canvas works in pixel-edge coordinates rather than centre indices.
    forward=geometry_matrix(int(width),int(height),geometry_json)
    forward=_translation(.5,.5)@forward@_translation(-.5,-.5)
    left,top,_,_=crop_box(int(width),int(height),geometry_json)
    forward=_translation(-left,-top)@forward
    return json.dumps(forward.reshape(-1).tolist(),separators=(',',':'))


def apply_geometry_image(image,geometry=None):
    from PIL import Image
    g=normalize_geometry(geometry)
    if is_neutral(g):return image
    box=crop_box(image.width,image.height,g)
    if is_neutral(Geometry(**{**g.__dict__,'crop':(0.,0.,1.,1.)})):
        cropped=image.crop(box);cropped.info.update(image.info);return cropped
    forward=geometry_matrix(image.width,image.height,g)
    forward=_translation(.5,.5)@forward@_translation(-.5,-.5)
    forward=_translation(-box[0],-box[1])@forward
    inverse=np.linalg.inv(forward);inverse/=inverse[2,2]
    corrected=image.transform((box[2]-box[0],box[3]-box[1]),Image.Transform.PERSPECTIVE,
                              tuple(inverse.reshape(-1)[:8]),Image.Resampling.BICUBIC,fillcolor=(0,0,0))
    corrected.info.update(image.info)
    return corrected
