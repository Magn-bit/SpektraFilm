"""Matrix RGB output conversion and matching matrix/TRC ICC profiles.

Transforms use floating point until quantisation. ProPhoto and Display P3
exports have their actual primaries and transfer curve, not a renamed sRGB ICC.
"""
from functools import lru_cache
import struct
import numpy as np


MATRICES={
    'sRGB':np.array([[.4124564,.3575761,.1804375],[.2126729,.7151522,.0721750],[.0193339,.1191920,.9503041]]),
    'Display P3':np.array([[.4865709486,.2656676932,.1982172852],[.2289745641,.6917385218,.0792869141],[0.,.0451133819,1.0439443689]]),
    'Adobe RGB (1998)':np.array([[.5767309,.1855540,.1881852],[.2973769,.6273491,.0752741],[.0270343,.0706872,.9911085]]),
    'ProPhoto RGB':np.array([[.7976749,.1351917,.0313534],[.2880402,.7118741,.0000857],[0.,0.,.8252100]])}
WHITES={'sRGB':(.95047,1.,1.08883),'Display P3':(.95047,1.,1.08883),
        'Adobe RGB (1998)':(.95047,1.,1.08883),'ProPhoto RGB':(.96422,1.,.82521)}
_BRADFORD=np.array([[.8951,.2664,-.1614],[-.7502,1.7135,.0367],[.0389,-.0685,1.0296]])


def adaptation(source_white,target_white):
    if tuple(source_white)==tuple(target_white):return np.eye(3)
    return np.linalg.solve(_BRADFORD,np.diag((_BRADFORD@target_white)/(_BRADFORD@source_white))@_BRADFORD)


def decode(values,space='sRGB'):
    x=np.asarray(values)
    if space=='Adobe RGB (1998)':return np.copysign(np.abs(x)**(563/256),x)
    if space=='ProPhoto RGB':return np.where(x<=1/32,x/16,np.maximum(x,0)**1.8)
    return np.where(x<=.04045,x/12.92,np.maximum((x+.055)/1.055,0)**2.4)


def encode(values,space='sRGB'):
    x=np.asarray(values)
    if space=='Adobe RGB (1998)':return np.copysign(np.abs(x)**(256/563),x)
    if space=='ProPhoto RGB':return np.where(x<=1/512,x*16,np.maximum(x,0)**(1/1.8))
    return np.where(x<=.0031308,x*12.92,1.055*np.maximum(x,0)**(1/2.4)-.055)


@lru_cache(maxsize=16)
def conversion_matrix(source,target):
    if source not in MATRICES or target not in MATRICES:raise ValueError('不支持的RGB色彩空间')
    return np.linalg.solve(MATRICES[target],adaptation(WHITES[source],WHITES[target])@MATRICES[source]).astype(np.float32)


def convert_pixels(pixels,source='sRGB',target='sRGB',*,linear_output=False,out=None):
    values=np.asarray(pixels)
    if out is None:out=np.empty(values.shape,dtype=np.float32)
    matrix=conversion_matrix(source,target)
    for top in range(0,values.shape[0],96):
        block=decode(values[top:top+96],source)@matrix.T
        out[top:top+len(block)]=block if linear_output else encode(block,target)
    return out


def _fixed(value):return struct.pack('>i',int(round(float(value)*65536)))
def _xyz(values):return b'XYZ '+bytes(4)+b''.join(_fixed(v) for v in values)


@lru_cache(maxsize=4)
def icc_profile(space='sRGB'):
    if space not in MATRICES:raise ValueError('不支持的RGB色彩空间')
    d50=(.96422,1.,.82521)
    matrix=adaptation(WHITES[space],d50)@MATRICES[space]
    def text(value):
        encoded=value.encode('utf-16-be')
        return b'mluc'+bytes(4)+struct.pack('>II',1,12)+b'enUS'+struct.pack('>II',len(encoded),28)+encoded
    if space=='ProPhoto RGB':
        # ICC parametric type4: decode = (a*x+b)^g+e above d, c*x+f below.
        curve=b'para'+bytes(4)+struct.pack('>HH',4,0)+b''.join(_fixed(v) for v in (1.8,1,0,1/16,1/32,0,0))
    elif space=='Adobe RGB (1998)':
        curve=b'para'+bytes(4)+struct.pack('>HH',0,0)+_fixed(563/256)
    else:
        curve=b'para'+bytes(4)+struct.pack('>HH',4,0)+b''.join(_fixed(v) for v in (2.4,1/1.055,.055/1.055,1/12.92,.04045,0,0))
    tags=[(b'desc',text('SpektraFilm '+space)),(b'cprt',text('Public domain matrix RGB profile')),
        (b'wtpt',_xyz(d50)),(b'rXYZ',_xyz(matrix[:,0])),(b'gXYZ',_xyz(matrix[:,1])),(b'bXYZ',_xyz(matrix[:,2])),
        (b'rTRC',curve),(b'gTRC',curve),(b'bTRC',curve)]
    header=bytearray(128);header[4:8]=b'spkf';header[8:12]=bytes([4,0x30,0,0]);header[12:16]=b'mntr'
    header[16:20]=b'RGB ';header[20:24]=b'XYZ ';header[24:36]=struct.pack('>6H',2026,1,1,0,0,0)
    header[36:40]=b'acsp';header[40:44]=b'MSFT';header[64:68]=struct.pack('>I',1)
    header[68:80]=b''.join(_fixed(v) for v in d50);header[80:84]=b'spkf'
    table=bytearray(struct.pack('>I',len(tags)));payload=bytearray();offset=128+4+12*len(tags)
    for name,data in tags:
        table.extend(name+struct.pack('>II',offset+len(payload),len(data)))
        payload.extend(data);payload.extend(bytes((-len(data))%4))
    struct.pack_into('>I',header,0,128+len(table)+len(payload))
    return bytes(header+table+payload)
