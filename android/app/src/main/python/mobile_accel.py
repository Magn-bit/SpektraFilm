"""Portable native-array kernels for upstream Spektrafilm (GPLv3).

PCHIP, Mitchell reflection and Gaussian IIR coefficients retain upstream math.
Random draws use NumPy distributions instead of Numba's approximating sampler.
The decorator executes unaccelerated helpers normally; it never emulates a JIT.
"""
import itertools
import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.signal import lfilter, lfilter_zi
from skimage.transform import rescale as _rescale
import inspect

prange = range

def rescale(image, scale, channel_axis=2, **kwargs):
    if 'channel_axis' in inspect.signature(_rescale).parameters:
        return _rescale(image,scale,channel_axis=channel_axis,**kwargs)
    return _rescale(image,scale,multichannel=channel_axis is not None,**kwargs)

class fft:
    @staticmethod
    def fft2(a, **kwargs):
        return np.fft.fft2(a)

    @staticmethod
    def ifft2(a, **kwargs):
        return np.fft.ifft2(a)

def _interp(image, axis, values):
    out = np.empty_like(image)
    for c in range(3):
        out[..., c] = np.interp(image[..., c], axis if axis.ndim == 1 else axis[:, c], values[:, c])
    return out

def _slopes(lut, axis):
    v = np.moveaxis(lut, axis, 0)
    d = np.diff(v, axis=0)
    m = np.zeros_like(v)
    if len(v) == 1:
        return np.moveaxis(m, 0, axis)
    if len(v) == 2:
        m[:] = d[0]
    else:
        a, b = d[:-1], d[1:]
        np.divide(2*a*b, a+b, out=m[1:-1], where=(a*b > 0))
        for index, first, second in [(0, d[0], d[1]), (-1, d[-1], d[-2])]:
            edge = (3*first-second)/2
            edge = np.where(edge*first <= 0, 0, edge)
            m[index] = np.where((first*second < 0) & (abs(edge) > abs(3*first)), 3*first, edge)
    return np.moveaxis(m, 0, axis).copy()

def _prepare(lut):
    size = len(lut)-1
    corners = [lut[i:i+size, j:j+size, k:k+size] for i,j,k in itertools.product(range(2), repeat=3)]
    return (*[_slopes(lut, axis) for axis in range(3)], np.minimum.reduce(corners), np.maximum.reduce(corners))

def _hermite(a, b, m, n, t):
    return (2*t**3-3*t*t+1)*a + (t**3-2*t*t+t)*m + (-2*t**3+3*t*t)*b + (t**3-t*t)*n

def _pchip(lut, sx, sy, sz, lo, hi, image):
    flat = image.reshape(-1, 3)
    out = np.empty_like(flat, dtype=lut.dtype)
    for start in range(0, len(flat), 8192):
        coord = np.clip(flat[start:start+8192], 0, 1)*(len(lut)-1)
        base = np.minimum(np.floor(coord).astype(int), len(lut)-2)
        i,j,k = base.T
        r,g,b = [v[:,None] for v in (coord-base).T]
        val, ys = {}, {}
        for y,z in itertools.product(range(2), repeat=2):
            val[y,z] = _hermite(lut[i,j+y,k+z], lut[i+1,j+y,k+z], sx[i,j+y,k+z], sx[i+1,j+y,k+z], r)
            ys[y,z] = sy[i,j+y,k+z]*(1-r)+sy[i+1,j+y,k+z]*r
        v0 = _hermite(val[0,0], val[1,0], ys[0,0], ys[1,0], g)
        v1 = _hermite(val[0,1], val[1,1], ys[0,1], ys[1,1], g)
        zs = [sum(sz[i+x,j+y,k+z]*(r if x else 1-r)*(g if y else 1-g)
                  for x,y in itertools.product(range(2), repeat=2)) for z in range(2)]
        out[start:start+8192] = np.clip(_hermite(v0,v1,zs[0],zs[1],b),lo[i,j,k],hi[i,j,k])
    return out.reshape(image.shape)

def _mitchell(t):
    x = abs(t)
    return np.where(x < 1, ((7*x-12)*x*x+16/3)/6,
                    np.where(x < 2, ((-7/3*x+12)*x-20)*x/6+32/18, 0))

def _cubic(lut, image, dimensions):
    flat = image.reshape(-1, image.shape[-1])
    out = np.empty((len(flat),lut.shape[-1]), dtype=np.float64)
    if len(lut) == 1:
        out[:] = lut[(0,)*dimensions]
        return out.reshape((*image.shape[:2],lut.shape[-1]))
    for start in range(0,len(flat),4096):
        coord = np.clip(flat[start:start+4096,:dimensions],0,1)*(len(lut)-1)
        base = np.minimum(np.floor(coord).astype(int),len(lut)-2)
        fraction = coord-base
        value = np.zeros((len(coord),lut.shape[-1])); total = np.zeros((len(coord),1))
        for offsets in itertools.product(range(-1,3),repeat=dimensions):
            index = base+offsets
            index = np.where(index<0,-index,np.where(index>=len(lut),2*(len(lut)-1)-index,index))
            weight = np.prod(_mitchell(fraction-offsets),axis=1)[:,None]
            value += weight*lut[tuple(index.T)]; total += weight
        out[start:start+4096] = value/total
    return out.reshape((*image.shape[:2],lut.shape[-1]))

def _fir(image, sigma, truncate):
    return image.copy() if sigma <= 0 else gaussian_filter(image,sigma,mode='reflect',truncate=truncate)

def _iir(image, output, B, B1, B2, B3, axis):
    a = [1,-B1,-B2,-B3]; b = [B]
    zi = lfilter_zi(b,a)
    first = np.take(image,[0],axis=axis)
    shape = [1]*image.ndim; shape[axis] = 3
    forward,_ = lfilter(b,a,image,axis=axis,zi=zi.reshape(shape)*first)
    reverse = np.flip(forward,axis=axis)
    backward,_ = lfilter(b,a,reverse,axis=axis,zi=zi.reshape(shape)*np.take(reverse,[0],axis=axis))
    output[:] = np.flip(backward,axis=axis)

def _boost(x,y,inv,a,x0,scale):
    dx = np.maximum(x-x0,0)*inv
    y[:] = x+scale*(np.exp(a*dx)-a*dx-1)

def _lognormal(mu,sigma):
    return np.exp(mu+np.where(sigma<1e-6,0,sigma)*np.random.standard_normal(mu.shape))

def _lognormal_mean(mean,std):
    valid = mean>0
    ratio = np.divide(std,mean,out=np.zeros_like(mean),where=valid)
    variance = np.log1p(ratio**2)
    mu = np.where(valid,np.log(np.maximum(mean,1e-300))-variance/2,0)
    return _lognormal(mu,np.sqrt(variance))

_KERNELS = {
    'fast_interp':_interp,
    '_prepare_lut_pchip_3d_impl':_prepare,
    '_apply_lut_pchip_3d_prepared':_pchip,
    '_apply_lut_cubic_3d':lambda lut,image:_cubic(lut,image,3),
    '_apply_lut_cubic_2d':lambda lut,image:_cubic(lut,image,2),
    '_gaussian_filter_2d_small':_fir,
    '_iir_horizontal':lambda image,output,*args:_iir(image,output,*args,axis=1),
    '_iir_vertical':lambda image,output,*args:_iir(image,output,*args,axis=0),
    '_boost_curve_kernel':_boost,
    'fast_binomial':lambda n,p:np.random.binomial(np.maximum(n,0).astype(np.int64),np.clip(p,0,1)),
    'fast_poisson':lambda lam:np.random.poisson(np.maximum(lam,0)),
    'fast_lognormal':_lognormal,
    'fast_lognormal_from_mean_std':_lognormal_mean,
}

def njit(*args, **kwargs):
    def decorate(function):
        return _KERNELS.get(function.__name__,function)
    return decorate(args[0]) if args and callable(args[0]) else decorate
