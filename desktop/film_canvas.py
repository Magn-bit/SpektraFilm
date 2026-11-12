"""Original-source physical film canvases, separate from graphic paper layouts.

Gate placement precedes exposure. Two half frames share one negative, and the
native engine exposes the rebate/date before halation and grain. No painted
film-edge image or enlarged preview participates in final output.
"""
from __future__ import annotations

from dataclasses import replace
import math
import zlib

import numpy as np

from shared.color_management import decode
from shared.composition import crop_box
from shared.composition_edge import FORMATS, native_overscan_options
from shared.geometry import apply_geometry_pixels, normalized_matrices
from shared.date_back import imprint_options
from shared.darkroom import scans_directly
from . import native_spectral
from .raw_source import source_pixels, source_metadata, resize_pixels


_POST_FIELDS = ('contrast','brightness','warmth','saturation','vibrance',
    'highlights','shadows','whites','blacks','black_point','white_point','gamma',
    'texture','clarity','dehaze','calibration_shadow_tint','vignette',
    'masks','curves','grading','channel_mixer','hsl','levels','look_lut','look_strength')


def _rotation(turn):
    matrix=np.eye(3,dtype=np.float64)
    quarter=np.array([[0,1,0],[-1,0,1],[0,0,1]],np.float64)
    for _ in range(turn%4):matrix=quarter@matrix
    return matrix


def _prepare(image,settings,placement,pair):
    """Return unclipped linear ProPhoto gate samples and original coordinates."""
    metadata=source_metadata(image)
    full_size=tuple(image.info.get('source_size',image.size))
    pre=native_spectral.process_editor(source_pixels(image),settings,stage='pre',
        exposure_ev=float(metadata.get('baseline_exposure_ev',0))+(settings.exposure if pair else 0),
        source_color_space=metadata['source_color_space'],source_linear=metadata['source_linear'],
        source_size=full_size,pixel_scale=(full_size[0]/image.width,full_size[1]/image.height),
        clamp_output=False)
    scene=apply_geometry_pixels(pre,settings.geometry)
    turn=(int(placement.get('rotation',0))//90)%4
    if turn:scene=np.rot90(scene,turn)
    if pair:ratio=18/24
    else:
        fmt=FORMATS.get(placement.get('frame_format','135'),FORMATS['135'])
        long,short=max(fmt['along'],fmt['across']),min(fmt['along'],fmt['across'])
        ratio=short/long if scene.shape[0]>scene.shape[1] else long/short
    box=crop_box(scene.shape[1],scene.shape[0],ratio,placement.get('zoom',1.),
                 placement.get('pan_x',.5),placement.get('pan_y',.5))
    left,top,right,bottom=box
    geometry=np.array(normalized_matrices(image.width,image.height,settings.geometry)[0]).reshape(3,3)
    crop=np.array([[scene.shape[1]/(right-left),0,-left/(right-left)],
                   [0,scene.shape[0]/(bottom-top),-top/(bottom-top)],[0,0,1]],np.float64)
    mapping=crop@_rotation(turn)@geometry
    selected=scene[top:bottom,left:right]
    gate=_mapped(selected.shape)
    matrix=native_spectral.source_color_matrix('sRGB','ProPhoto RGB')
    for first in range(0,selected.shape[0],96):gate[first:first+96]=decode(selected[first:first+96],'sRGB')@matrix.T
    return gate,dict(image=image,settings=settings,mapping=mapping,pre=pre,full_size=full_size,
                     density_scale=min(full_size[0]/image.width,full_size[1]/image.height))


def _date_options(options,placements):
    return imprint_options(options,placements)


def _quad_matrix(quad,vertical):
    points=np.asarray(quad,np.float64).reshape(4,2)
    zero=points[0];x=points[3] if vertical else points[1];y=points[1] if vertical else points[3]
    return np.array([[x[0]-zero[0],y[0]-zero[0],zero[0]],
                     [x[1]-zero[1],y[1]-zero[1],zero[1]],[0,0,1]],np.float64)


def _mapped(shape):
    return native_spectral._mapped_result(shape) if math.prod(shape)>16_000_000*3 else np.empty(shape,np.float32)


def _finish_gate(canvas,quad,vertical,record):
    """Apply existing post tools in their original photo coordinate system.

    Reproject only the adjustment delta. An unchanged photo never goes through
    another resample, and masks retain their source-space geometry after crop.
    Strip meshes keep scratch bounded even for medium-format sources.
    """
    settings=record['settings'];defaults=type(settings)()
    if settings.strength>=100 and not any(getattr(settings,k)!=getattr(defaults,k) for k in _POST_FIELDS):return
    from scipy.ndimage import map_coordinates
    image=record['image'];ih,iw=image.height,image.width;ch,cw=canvas.shape[:2]
    source_to_canvas=_quad_matrix(quad,vertical)@record['mapping']
    sampled=_mapped((ih,iw,3))
    columns=(np.arange(iw,dtype=np.float64)+.5)[None,:]/iw
    for top in range(0,ih,96):
        ys=(np.arange(top,min(ih,top+96),dtype=np.float64)+.5)[:,None]/ih
        den=source_to_canvas[2,0]*columns+source_to_canvas[2,1]*ys+source_to_canvas[2,2]
        xx=(source_to_canvas[0,0]*columns+source_to_canvas[0,1]*ys+source_to_canvas[0,2])/den*cw-.5
        yy=(source_to_canvas[1,0]*columns+source_to_canvas[1,1]*ys+source_to_canvas[1,2])/den*ch-.5
        for channel in range(3):map_coordinates(canvas[...,channel],(yy,xx),
            output=sampled[top:top+len(ys),:,channel],order=1,prefilter=False,mode='nearest')
    before=sampled
    if settings.strength<100:
        base=record['pre']
        if not record.get('pair'):
            base=native_spectral.process_editor(base,{},stage='pre',exposure_ev=settings.exposure,clamp_output=False)
        sampled=_mapped(before.shape)
        for top in range(0,ih,96):sampled[top:top+96]=base[top:top+96]+(before[top:top+96]-base[top:top+96])*(settings.strength/100)
    full=record['full_size']
    adjusted=native_spectral.process_editor(sampled,settings,stage='post',source_size=full,
        pixel_scale=(full[0]/iw,full[1]/ih),out=_mapped(sampled.shape))
    # Delta stays in the same float buffer and is normally sparse/zero.
    for top in range(0,ih,96):adjusted[top:top+96]-=before[top:top+96]
    inverse=np.linalg.inv(source_to_canvas);gate_inverse=np.linalg.inv(_quad_matrix(quad,vertical))
    points=np.asarray(quad,np.float64).reshape(4,2)
    left=max(0,int(np.floor(points[:,0].min()*cw)));right=min(cw,int(np.ceil(points[:,0].max()*cw)))
    top=max(0,int(np.floor(points[:,1].min()*ch)));bottom=min(ch,int(np.ceil(points[:,1].max()*ch)))
    columns=(np.arange(left,right,dtype=np.float64)+.5)[None,:]/cw
    for y0 in range(top,bottom,96):
        ys=(np.arange(y0,min(bottom,y0+96),dtype=np.float64)+.5)[:,None]/ch
        den=inverse[2,0]*columns+inverse[2,1]*ys+inverse[2,2]
        xx=(inverse[0,0]*columns+inverse[0,1]*ys+inverse[0,2])/den*iw-.5
        yy=(inverse[1,0]*columns+inverse[1,1]*ys+inverse[1,2])/den*ih-.5
        gx=gate_inverse[0,0]*columns+gate_inverse[0,1]*ys+gate_inverse[0,2]
        gy=gate_inverse[1,0]*columns+gate_inverse[1,1]*ys+gate_inverse[1,2]
        inside=(gx>=0)&(gx<=1)&(gy>=0)&(gy<=1)
        for channel in range(3):
            delta=map_coordinates(adjusted[...,channel],(yy,xx),order=1,prefilter=False,mode='nearest')
            area=canvas[y0:y0+len(ys),left:right,channel];area+=delta*inside
    np.clip(canvas,0,1,out=canvas)


def rotate_canvas(pixels,geometry,turn):
    turn=int(turn)%4
    if not turn:return pixels,geometry
    result=np.rot90(pixels,turn).copy(order='C');geometry=dict(geometry)
    matrix=_rotation(turn)
    gates=[]
    for quad in geometry.get('gates',[]):
        points=np.asarray(quad,np.float64).reshape(4,2)
        mapped=np.c_[points,np.ones(4)]@matrix.T
        gates.append(mapped[:,:2].reshape(-1).tolist())
    geometry.update(canvas_w=result.shape[1],canvas_h=result.shape[0],gates=gates,
                    vertical=bool(geometry.get('vertical'))^(turn%2==1))
    if turn%2 and 'source_canvas_w' in geometry:geometry['source_canvas_w'],geometry['source_canvas_h']=geometry['source_canvas_h'],geometry['source_canvas_w']
    return result,geometry


def render_film_edge(source_prepared,settings,options,preview=False,progress=None):
    """Render one strip or a physical half-frame pair from prepared sources.

    ``source_prepared``/``settings`` are either one PIL source/Settings or two
    sequences for a pair. Placement dicts carry source crop and metadata;
    explicit ``edge`` limits are honoured, while zero retains source density.
    """
    pair=options.get('style')=='half_frame'
    images=list(source_prepared) if isinstance(source_prepared,(list,tuple)) else [source_prepared]
    settings_list=list(settings) if isinstance(settings,(list,tuple)) else [settings]
    if any(getattr(value,'digital_intermediate',False) for value in settings_list):
        raise ValueError('数字中间片请使用照片输出配方；物理片边请先选择相纸或直接扫描')
    if len(images)!=(2 if pair else 1) or len(settings_list)!=len(images):raise ValueError('半格需要两张独立照片')
    placements=list(options.get('placements') or [{} for _ in images])
    if len(placements)!=len(images):raise ValueError('胶片取景数量不匹配')
    gates=[];records=[]
    for image,setting,placement in zip(images,settings_list,placements):
        gate,record=_prepare(image,setting,dict(placement,frame_format=options.get('frame_format','135')),pair)
        record['pair']=pair;gates.append(gate);records.append(record)
    pair_on_strip=bool(options.get('pair_on_strip',True))
    plain_geometry=None
    if pair:
        density=max(min(gate.shape[1]/18,gate.shape[0]/24) for gate in gates)
        # An explicit output size may reduce the source, but a preview never
        # becomes the basis for an original-size export.
        edge=float(options.get('edge') or 0)
        spacing=1. if pair_on_strip else max(.5,min(2.,float(options.get('pair_spacing_mm',1.))))
        if edge:density=min(density,edge/(36+spacing))
        w,h=max(1,round(18*density)),max(1,round(24*density));gap=max(1,round(spacing*density))
        source=_mapped((h,w*2+gap,3));source[:]=0
        for index,gate in enumerate(gates):source[:,index*(w+gap):index*(w+gap)+w]=gate if gate.shape[:2]==(h,w) else resize_pixels(gate,(w,h))
        width=w*2+gap
        quads=[[0.,0.,w/width,0.,w/width,1.,0.,1.],[(w+gap)/width,0.,1.,0.,1.,1.,(w+gap)/width,1.]]
        plain_geometry=dict(valid=True,canvas_w=width,canvas_h=h,gates=quads,vertical=False,mm_per_px=24/h)
        if options.get('pair_axis')=='vertical':
            source,plain_geometry=rotate_canvas(source,plain_geometry,3)
    else:source=gates[0]
    first=settings_list[0];placement=placements[0]
    camera_seed=int(options.get('camera_seed',1));identity='|'.join(str(p.get('path') or i) for i,p in enumerate(placements))
    frame_seed=int(options.get('frame_seed',zlib.crc32(identity.encode('utf-8'))&0x7fffffff))
    overrides=native_overscan_options(options,first.stock,f_number=float((placement.get('metadata') or {}).get('f_number',0)),camera_seed=camera_seed,frame_seed=frame_seed)
    if pair and not pair_on_strip:
        overrides.update(overscan_active=False,film_format_mm=36+spacing)
    overrides.update(_date_options(options,placements),input_color_space='ProPhoto RGB',input_cctf_decoding=False)
    if pair:overrides['exposure_compensation_ev']=0.
    request=None
    if pair:
        prints=not first.scan_film and not scans_directly(first.stock)
        request=dict(turned=options.get('pair_axis')=='vertical',printEffects=bool(first.print_effects and prints))
        if not pair_on_strip:request['gates']=plain_geometry['gates']
        for name,setting in zip(('left','right'),settings_list):
            request[name]=dict(print=dict(brightnessStops=-setting.print_exposure,
                yFilterShift=setting.print_y/100,mFilterShift=setting.print_m/100,
                preflashExposure=float(setting.preflash_exposure) if first.print_effects and setting.print_effects else 0.) if prints else None,
                adjustments={'enabled':False})
    kwargs=dict(overrides=overrides,preview=preview,
        progress=progress,
        source_token=tuple((p.get('path'),id(image),image.size,s,tuple(sorted((k,str(v)) for k,v in p.items() if k!='metadata'))) for p,image,s in zip(placements,images,settings_list)))
    layered=request is not None
    if request is not None:kwargs['pair']=request
    pixels,geometry=native_spectral.render_film_canvas(source,first,**kwargs)
    if pair and not pair_on_strip:geometry=plain_geometry
    if not geometry.get('valid') or len(geometry.get('gates',[]))!=len(images):raise ValueError('原生片门几何与照片不一致')
    for quad,record in zip(geometry['gates'],records):_finish_gate(pixels,quad,bool(geometry.get('vertical')),record)
    if pair:
        source_density=max(min(g.shape[1]/18,g.shape[0]/24)*r['density_scale'] for g,r in zip(gates,records))
    else:source_density=max(gates[0].shape[:2])/float(overrides['film_format_mm'])*records[0]['density_scale']
    scale=source_density*geometry['mm_per_px']
    geometry=dict(geometry,pair_layered=layered,source_dimensions=[[image.width,image.height] for image in images],
        source_canvas_w=round(pixels.shape[1]*scale),source_canvas_h=round(pixels.shape[0]*scale))
    return rotate_canvas(pixels,geometry,int(options.get('group_turn',0)))
