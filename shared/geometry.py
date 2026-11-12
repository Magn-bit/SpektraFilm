"""Exact quarter turns followed by bounded corrections on the oriented grid."""
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
    quarter_turns: int = 0


def normalize_geometry(value):
    if isinstance(value, Geometry): return value
    if isinstance(value, str):
        try: value=json.loads(value)
        except (TypeError, ValueError): value={}
    if not isinstance(value, dict): return Geometry()
    result={}
    turns=value.get('quarter_turns',0)
    if (isinstance(turns,(int,float)) and not isinstance(turns,bool)
            and math.isfinite(turns) and turns==int(turns)):
        result['quarter_turns']=int(turns)%4
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
    return (not any((g.quarter_turns,g.rotation,g.vertical,g.horizontal,g.aspect,g.flip_horizontal,g.flip_vertical))
            and g.scale==100. and g.crop==(0.,0.,1.,1.))


def oriented_size(width,height,geometry=None):
    """Uncropped output grid; source dimensions always remain unchanged."""
    if width<1 or height<1:raise ValueError('Invalid source dimensions')
    return (height,width) if normalize_geometry(geometry).quarter_turns%2 else (width,height)


def crop_box(width,height,geometry=None):
    g=normalize_geometry(geometry)
    width,height=oriented_size(width,height,g)
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


def _quarter_matrix(width,height,turns):
    # Clockwise in image coordinates, with exact integer pixel-centre mapping.
    return np.array((
        ((1,0,0),(0,1,0),(0,0,1)),
        ((0,-1,height-1),(1,0,0),(0,0,1)),
        ((-1,0,width-1),(0,-1,height-1),(0,0,1)),
        ((0,1,0),(-1,0,width-1),(0,0,1)),
    )[turns%4],dtype=np.float64)


def _quarter_only(geometry):
    return is_neutral(Geometry(**{**geometry.__dict__,'quarter_turns':0,'crop':(0.,0.,1.,1.)}))


def geometry_matrix(width,height,geometry=None):
    """Source pixel-centre -> uncropped oriented output pixel-centre homography.

    Quarter turns transpose the full grid without interpolation. Fine geometry
    then operates in that grid; auto crop never zooms merely for a quarter turn.
    """
    g=normalize_geometry(geometry)
    if width<1 or height<1: raise ValueError('Invalid source dimensions')
    if is_neutral(g): return np.eye(3,dtype=np.float64)
    quarter=_quarter_matrix(width,height,g.quarter_turns)
    width,height=oriented_size(width,height,g)
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
    return matrix(zoom)@quarter


def matrix_json(width,height,geometry_json='{}'):
    # Android Canvas works in pixel-edge coordinates rather than centre indices.
    forward=geometry_matrix(int(width),int(height),geometry_json)
    forward=_translation(.5,.5)@forward@_translation(-.5,-.5)
    left,top,_,_=crop_box(int(width),int(height),geometry_json)
    forward=_translation(-left,-top)@forward
    return json.dumps(forward.reshape(-1).tolist(),separators=(',',':'))


def normalized_matrices(width,height,geometry=None):
    """Source [0,1] edge coordinates ↔ final displayed [0,1] coordinates."""
    if width<1 or height<1:
        identity=np.eye(3).reshape(-1).tolist();return identity,identity
    g=normalize_geometry(geometry)
    left,top,right,bottom=crop_box(width,height,g)
    edge=_translation(.5,.5)@geometry_matrix(width,height,g)@_translation(-.5,-.5)
    forward=np.diag([1/(right-left),1/(bottom-top),1.])@_translation(-left,-top)@edge@np.diag([width,height,1.])
    return forward.reshape(-1).tolist(),np.linalg.inv(forward).reshape(-1).tolist()


GUIDE_LINES = {
    'horizontals': ((0,1,True),(2,3,True)),
    'verticals': ((0,1,False),(2,3,False)),
    'rectangle': ((0,1,True),(3,2,True),(0,3,False),(1,2,False)),
}


def solve_guided_geometry(width,height,geometry,mode,points):
    """Fit the existing render geometry to source-normalized user guides.

    Only the selected perspective axes and straighten are solved. Crop,
    aspect, flips, scale and exact quarter turns keep their existing meaning;
    no new transform bypasses the shared full-resolution render path.
    A guide drag is local UI state, so this function runs only on Apply.
    """
    if mode not in GUIDE_LINES:raise ValueError('请选择水平、垂直或矩形参考线')
    if width<2 or height<2:raise ValueError('照片尺寸不可用')
    try:values=np.asarray(points,dtype=np.float64)
    except (TypeError,ValueError):raise ValueError('参考点无效') from None
    if values.shape!=(4,2) or not np.isfinite(values).all() or np.any((values<0)|(values>1)):
        raise ValueError('四个参考点必须位于原照片内')
    source=values*np.array([width,height])-0.5
    lines=GUIDE_LINES[mode]
    if any(np.linalg.norm(source[b]-source[a])<4 for a,b,_ in lines):
        raise ValueError('参考线太短，请把控制点拉开')
    if mode=='rectangle':
        sides=np.roll(values,-1,axis=0)-values
        cross=sides[:,0]*np.roll(sides,-1,axis=0)[:,1]-sides[:,1]*np.roll(sides,-1,axis=0)[:,0]
        if not (np.all(cross>1e-7) or np.all(cross<-1e-7)):
            raise ValueError('矩形四角请按顺序放置，边线不能交叉')
    from dataclasses import replace
    from scipy.optimize import least_squares
    original=normalize_geometry(geometry)
    # Auto-fill is a uniform zoom and does not alter line directions. Keeping
    # it out of the solve avoids forty inverse-map fits per residual sample.
    base=replace(original,auto_crop=False,crop=(0.,0.,1.,1.))
    names=('horizontal','rotation') if mode=='horizontals' else ('vertical','rotation') if mode=='verticals' else ('vertical','horizontal','rotation')
    homogeneous=np.c_[source,np.ones(4)].T
    def residual(parameters):
        candidate=replace(base,**dict(zip(names,parameters)))
        mapped=geometry_matrix(width,height,candidate)@homogeneous
        mapped=(mapped[:2]/mapped[2:3]).T
        result=[]
        for a,b,level in lines:
            dx,dy=mapped[b]-mapped[a]
            angle=math.atan2(dy,dx) if level else math.atan2(dx,dy)
            result.append((angle+math.pi/2)%math.pi-math.pi/2)
        return np.asarray(result)
    initial=np.array([getattr(base,name) for name in names])
    lower=np.array([-45. if name=='rotation' else -100. for name in names])
    upper=-lower
    fit=least_squares(residual,initial,bounds=(lower,upper),diff_step=1e-4,
                      xtol=1e-10,ftol=1e-10,gtol=1e-10,max_nfev=100,x_scale='jac')
    errors=residual(fit.x)
    if not np.isfinite(fit.x).all() or np.max(np.abs(errors))>math.radians(1.5):
        raise ValueError('这些参考线无法在校正范围内对齐，请重新放置')
    updated=replace(original,**dict(zip(names,(float(number) for number in fit.x))))
    return updated,{'mode':mode,'error_degrees':float(np.degrees(np.max(np.abs(errors))))}


def apply_geometry_image(image,geometry=None):
    from PIL import Image
    g=normalize_geometry(geometry)
    if is_neutral(g):return image
    box=crop_box(image.width,image.height,g)
    if _quarter_only(g):
        operation=(None,Image.Transpose.ROTATE_270,Image.Transpose.ROTATE_180,Image.Transpose.ROTATE_90)[g.quarter_turns%4]
        oriented=image.transpose(operation) if operation is not None else image
        cropped=oriented.crop(box);cropped.info.update(image.info);return cropped
    forward=geometry_matrix(image.width,image.height,g)
    forward=_translation(.5,.5)@forward@_translation(-.5,-.5)
    forward=_translation(-box[0],-box[1])@forward
    inverse=np.linalg.inv(forward);inverse/=inverse[2,2]
    corrected=image.transform((box[2]-box[0],box[3]-box[1]),Image.Transform.PERSPECTIVE,
                              tuple(inverse.reshape(-1)[:8]),Image.Resampling.BICUBIC,
                              fillcolor=0 if image.mode in ('F','L','I','1') else (0,0,0))
    corrected.info.update(image.info)
    return corrected


def apply_geometry_pixels(pixels,geometry=None,*,strip_rows=96):
    """Transform RGB samples once without an eight-bit display intermediate.

    Quarter-turn/crop edits are exact reindexing. Projective correction samples
    once into the quarter-turned grid, followed by the explicit crop.
    Coordinates are bounded to a strip so large camera files do not allocate
    an additional full-image mesh.
    """
    values=np.asarray(pixels)
    if values.ndim!=3 or values.shape[2]!=3:raise ValueError('RGB pixels required')
    g=normalize_geometry(geometry)
    height,width=values.shape[:2]
    left,top,right,bottom=crop_box(width,height,g)
    if _quarter_only(g):
        oriented=np.rot90(values,-g.quarter_turns) if g.quarter_turns%4 else values
        if not g.quarter_turns and (left,top,right,bottom)==(0,0,width,height):return values
        return oriented[top:bottom,left:right].copy(order='C')
    from scipy.ndimage import map_coordinates
    inverse=np.linalg.inv(geometry_matrix(width,height,g))
    output=np.empty((bottom-top,right-left,3),dtype=values.dtype)
    columns=np.arange(left,right,dtype=np.float64)[None,:]
    for first in range(top,bottom,max(1,int(strip_rows))):
        last=min(bottom,first+max(1,int(strip_rows)))
        rows=np.arange(first,last,dtype=np.float64)[:,None]
        denominator=inverse[2,0]*columns+inverse[2,1]*rows+inverse[2,2]
        xx=(inverse[0,0]*columns+inverse[0,1]*rows+inverse[0,2])/denominator
        yy=(inverse[1,0]*columns+inverse[1,1]*rows+inverse[1,2])/denominator
        for channel in range(3):
            map_coordinates(values[...,channel],(yy,xx),output=output[first-top:last-top,:,channel],
                            order=1,prefilter=False,mode='constant',cval=0.)
    return output
