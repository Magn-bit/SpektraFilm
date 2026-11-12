"""Bounded NumPy reference for the native density-domain grain textures.

Coordinates describe the original film plane; chunks never restart a random
generator. Strength scales density deviations without changing particle size.
"""
from __future__ import annotations
import numpy as np

PROFILES = {'fine': (1, .42, 2.2), 'classic': (2, 1., 4.),
            'coarse': (3, 2.1, 6.), 'clustered': (4, 1.35, 4.5)}


def _random(x, y, seed):
    h = x.astype(np.uint32)*np.uint32(374761393) + y.astype(np.uint32)*np.uint32(668265263)
    h += np.uint32((int(seed)*1442695041) & 0xffffffff)
    h = (h ^ (h >> np.uint32(13))) * np.uint32(1274126177)
    h ^= h >> np.uint32(16)
    return ((h >> np.uint32(8)).astype(np.float32)+np.float32(.5))*np.float32(2./16777216.)-np.float32(1.)


def _field(x, y, seed):
    cx=np.floor(x).astype(np.int32);cy=np.floor(y).astype(np.int32)
    fx=x-cx;fy=y-cy
    fx=fx*fx*fx*(fx*(fx*6.-15.)+10.)
    fy=fy*fy*fy*(fy*(fy*6.-15.)+10.)
    top=_random(cx,cy,seed)*(1.-fx)+_random(cx+1,cy,seed)*fx
    bottom=_random(cx,cy+1,seed)*(1.-fx)+_random(cx+1,cy+1,seed)*fx
    return top*(1.-fy)+bottom*fy


def _particles(x, y, seed):
    cx=np.floor(x).astype(np.int32);cy=np.floor(y).astype(np.int32)
    out=np.zeros(np.broadcast_shapes(x.shape,y.shape),dtype=np.float32)
    for iy in range(-1,2):
        for ix in range(-1,2):
            ax=cx+ix;ay=cy+iy;weight=_random(ax,ay,seed)
            dx=x-(ax+.5+_random(ax,ay,seed+19)*.28)
            dy=y-(ay+.5+_random(ax,ay,seed+37)*.28)
            radius=.20+.09*(_random(ax,ay,seed+53)+1.)
            out += np.where(np.abs(weight)<.38,0.,np.sign(weight)*np.exp(-(dx*dx+dy*dy)/(2.*radius*radius)))
    return out*2.2


def texture(x, y, mode, pitch_px, seed=743):
    x=np.asarray(x,dtype=np.float32);y=np.asarray(y,dtype=np.float32)
    qx=(x+.5)/max(.65,float(pitch_px));qy=(y+.5)/max(.65,float(pitch_px))
    if mode==1:
        return (_field(qx*1.7,qy*1.7,seed)*.62+_field(qx*.8+17.3,qy*.8+8.1,seed+13)*.38)*1.8
    if mode==3:
        return _particles(qx*.62+5.7,qy*.62+9.2,seed)
    if mode==4:
        clump=_field(qx*.25+21.8,qy*.25+5.4,seed+31)*1.65
        detail=_field(qx*1.3,qy*1.3,seed)*1.65
        return clump*.85+detail*.35*(.55+.8*np.abs(clump))
    return (_field(qx,qy,seed)*.78+_field(qx*2.4+9.1,qy*2.4+3.4,seed+7)*.22)*1.8


def noise_chunk(start, stop, width, grain_size, grain_type='classic', pixel_size_um=4.):
    positions=np.arange(start,stop,dtype=np.int64)
    mode,_,pitch=PROFILES.get(grain_type,PROFILES['classic'])
    return texture(positions%width,positions//width,mode,pitch*grain_size/pixel_size_um).astype(np.float32)


def apply_density_grain(density, pixel_size_um, grain, density_max, *, seed=743):
    if not grain.active or grain.amount<=0:
        return density
    h,w=density.shape[:2];out=np.empty_like(density)
    maximum=max(.1,float(np.mean(density_max)))
    area=grain.particle_area_um2/(pixel_size_um*pixel_size_um)
    x=np.arange(w,dtype=np.float32)[None,:]
    for top in range(0,h,64):
        block=density[top:top+64]
        y=np.arange(top,top+len(block),dtype=np.float32)[:,None]
        field=texture(x,y,grain.texture,grain.texture_scale_um/pixel_size_um,seed)
        d=np.clip(block.mean(axis=-1)+.03,.005,maximum*.98)
        sigma=np.sqrt(np.maximum(0.,d*(maximum-d*grain.uniformity[0])*area))*grain.amount*.10
        out[top:top+len(block)] = block+(field*sigma)[...,None]
    return out
