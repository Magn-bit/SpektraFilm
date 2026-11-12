"""Film-space frame geometry and manufacturer edge-print drawing primitives.

Adapted from SpektraLab 2.2.0 (2201f5fa4d256b0c742b46b8e31f8176a12ca6ea),
engine/src/pipeline/overscan.cpp and app/.../FilmEdge/{FilmLayout,FilmEdgeStock}.swift.
Copyright SpektraLab contributors. GPL-3.0; see licenses/spektralab-composition/.
The measured geometry and DX encoder are retained. These are output decoration
primitives, not an assertion that the post-render border re-exposes the film.
"""
from __future__ import annotations
import math


FORMATS={
    '135':dict(name='135',film=35.,along=36.25,across=24.3,perf=True),
    '135_half':dict(name='135 半格',film=35.,along=18.,across=24.,perf=True),
    '135_xpan':dict(name='XPan',film=35.,along=65.,across=24.,perf=True),
    '120_645':dict(name='120 · 6×4.5',film=61.,along=41.5,across=56.,perf=False),
    '120_6x6':dict(name='120 · 6×6',film=61.,along=56.,across=56.,perf=False),
    '120_6x7':dict(name='120 · 6×7',film=61.,along=69.5,across=56.,perf=False),
    '120_6x8':dict(name='120 · 6×8',film=61.,along=76.,across=56.,perf=False),
    '120_6x9':dict(name='120 · 6×9',film=61.,along=84.,across=56.,perf=False),
    '120_6x12':dict(name='120 · 6×12',film=61.,along=112.,across=56.,perf=False),
    '120_6x17':dict(name='120 · 6×17',film=61.,along=168.,across=56.,perf=False),
}
# The words on a real rebate differ from the marketing/display name.
WORDS={
    'kodak_gold_200':('KODAK GB 200-7','KODAK 200'),
    'kodak_portra_160':('KODAK PORTRA 160','KODAK PORTRA 160'),
    'kodak_portra_400':('KODAK PORTRA 400','KODAK PORTRA 400'),
    'kodak_portra_800':('KODAK PORTRA 800-3','KODAK PORTRA 800'),
    'kodak_ultramax_400':('KODAK GC 400','KODAK GC 400'),
    'kodak_ektar_100':('KODAK EKTAR 100','KODAK EKTAR 100'),
    'kodak_ektachrome_100':('KODAK E100','KODAK E100'),
    'fujifilm_c200':('FUJI 200','FUJI 200'),
    'fujifilm_xtra_400':('S-400','FUJI S-400'),
    'fujifilm_pro_400h':('PRO400H','FUJI PRO400H'),
    'fujifilm_provia_100f':('FUJI RDPIII','FUJI RDPIII'),
    'fujifilm_velvia_100':('RVP100','FUJI RVP100'),
    'kodak_vision3_50d':('EASTMAN 5203','EASTMAN 5203'),
    'kodak_vision3_250d':('EASTMAN 5207','EASTMAN 5207'),
    'kodak_vision3_200t':('EASTMAN 5213','EASTMAN 5213'),
    'kodak_vision3_500t':('EASTMAN 5219','EASTMAN 5219'),
    'kodak_tri_x_400':('KODAK 400TX','KODAK 400TX'),
    'kodak_tmax_100':('KODAK 100TMX','KODAK 100TMX'),
    'fujifilm_neopan_acros_100_ii':('FUJI 100 ACROS II','FUJI 100 ACROS II'),
    'ilford_hp5_plus_400':('ILFORD HP5 PLUS','ILFORD HP5 PLUS'),
    'cinestill_800t':('CINESTILL 800T','CINESTILL 800T'),
}
DX={'kodak_portra_400':1277,'kodak_portra_800':1278,'kodak_portra_160':1534,
    'kodak_gold_200':1548,'kodak_ektar_100':1307,'kodak_ultramax_400':1313,
    'kodak_ektachrome_100':382,'fujifilm_c200':1550,'fujifilm_xtra_400':628,
    'fujifilm_pro_400h':584,'ilford_hp5_plus_400':1753}

# Upstream StockGauges records gauges manufactured at any time, rather than
# current shop availability. Unknown is deliberately not treated as "never".
_BOTH={'kodak_gold_200','kodak_portra_160','kodak_portra_400','kodak_portra_800',
       'kodak_ektar_100','kodak_ektachrome_100','kodak_kodachrome_64',
       'fujifilm_xtra_400','fujifilm_pro_400h','fujifilm_provia_100f','fujifilm_velvia_100',
       'kodak_tri_x_400','kodak_tmax_100','fujifilm_neopan_acros_100_ii',
       'ilford_hp5_plus_400','cinestill_800t'}
_ONLY_135={'fujifilm_c200','kodak_ultramax_400','kodak_vision3_50d',
           'kodak_vision3_250d','kodak_vision3_200t','kodak_vision3_500t'}


def stock_format_choices(stock):
    base=stock.replace('_push1','').replace('_push2','')
    gauges=('135',) if base in _ONLY_135 else ('135','120') if base in _BOTH else None
    names={'135':'135 · 36×24','135_half':'135 · 半格 18×24','135_xpan':'135 · XPan'}
    return [dict(id=key,name=names.get(key,value['name'])) for key,value in FORMATS.items()
            if gauges is None or ('135' if value['perf'] else '120') in gauges]


def stock_look(stock,perforated=True):
    stock=stock.replace('_push1','').replace('_push2','')
    if stock not in WORDS:
        # Extended profiles still carry their own model name. This is a
        # descriptive label, not an invented manufacturer inscription or DX.
        words=' '.join(stock.replace('_',' ').upper().split()) or 'FILM'
        return dict(stock=stock,family='generic',ink='#C5C7BD',base='#141713',words=words,dx=None)
    bw=stock in ('kodak_tri_x_400','kodak_tmax_100','fujifilm_neopan_acros_100_ii','ilford_hp5_plus_400')
    family=('cine' if 'vision3' in stock else 'cinestill' if stock.startswith('cinestill') else
            'ilford' if stock.startswith('ilford') else 'fuji_slide' if stock in
            ('fujifilm_provia_100f','fujifilm_velvia_100','fujifilm_neopan_acros_100_ii') else
            'fuji_neg' if stock in ('fujifilm_xtra_400','fujifilm_pro_400h') else 'kodak')
    if not perforated:family='fuji_120' if family.startswith('fuji') else 'cinestill_120' if family=='cinestill' else 'kodak_120'
    ink='#D7D6CC' if bw else '#BCC4DF' if family=='cine' else '#D9A653' if family.startswith('fuji') else '#D8AE6B'
    return dict(stock=stock,family=family,ink=ink,base='#161915' if bw else '#141713',
                words=WORDS.get(stock,(stock.replace('_',' ').upper(),)*2)[0 if perforated else 1],dx=DX.get(stock))


def native_overscan_options(options,stock='kodak_portra_400',*,f_number=0.,camera_seed=1,frame_seed=1):
    """Exact flat native parameter names; does not render or post-paint pixels.

    A caller must gate-crop the linear source before spk_open. For a pair it
    must combine the two linear ProPhoto holes BEFORE film development, use
    one common stock, and obtain final gates from spk_overscan_geometry.
    Seeds describe camera/frame identity and must survive preview/export.
    """
    style=options.get('style','plain');pair=style=='half_frame'
    name='135_half' if pair else options.get('frame_format','135')
    if name not in {choice['id'] for choice in stock_format_choices(stock)}:
        raise ValueError('所选胶片没有这个片幅，请使用 135 片幅')
    fmt=FORMATS.get(name,FORMATS['135']);look=stock_look(stock,fmt['perf'])
    return dict(overscan_active=style in ('film','half_frame'),overscan_format=name,
        overscan_mode=options.get('edge_view','strip'),
        overscan_camera_seed=max(0,min(2147483647,int(camera_seed))),
        overscan_frame_seed=max(0,min(2147483647,int(frame_seed))),
        overscan_fog=max(0.,min(4.,float(options.get('fog',1.)))),
        overscan_leaks=max(0.,min(4.,float(options.get('leaks',0.)))),
        overscan_edge_text=look['words'] if options.get('edge_print',True) else '',
        overscan_f_number=max(0.,min(64.,float(f_number))),
        overscan_gate=options.get('gate','auto'),
        overscan_holes='black' if options.get('holes')=='black' else 'white',
        overscan_frame_number=max(0,min(99,int(options.get('frame_number',0)))),
        overscan_carrier=options.get('carrier','none'),overscan_pair=pair,
        film_format_mm=37. if pair else max(fmt['along'],fmt['across']))


def dx_tracks(dx,frame,half=False):
    """ISO 1007 frame-number barcode, matching upstream's 23-bit encoder."""
    bits=[0]*23
    for i in range(7):bits[1+i]=((dx>>4)>>(6-i))&1
    for i in range(4):bits[9+i]=((dx&15)>>(3-i))&1
    for i in range(6):bits[13+i]=(max(0,min(63,frame))>>(5-i))&1
    bits[19]=int(half);bits[21]=sum(bits[:21])%2
    return ([1 if i<5 or i>=28 else (i-5)%2 for i in range(31)],
            [i%2==0 if i<5 else (i-28)%2==0 if i>=28 else bits[i-5] for i in range(31)])


def rotate_rect(rect,width,height,turn):
    x,y,w,h=rect
    turn%=4
    if turn==1:return [height-y-h,x,h,w]
    if turn==2:return [width-x-w,height-y-h,w,h]
    if turn==3:return [y,width-x-w,h,w]
    return list(rect)


def rotate_marks(marks,width,height,turn):
    if not turn%4:return marks
    transformed=[]
    for mark in marks:
        out=dict(mark,rect=rotate_rect(mark['rect'],width,height,turn))
        out['turn']=(int(mark.get('turn',0))+turn)%4
        transformed.append(out)
    return transformed


def physical_plan(dimensions,layout='grid',gap=.015,frame_format='135',view='strip',pair=False,pair_axis='horizontal',group_turn=0,pair_on_strip=True,pair_spacing_mm=1.):
    """Return film-space canvas in millimetres, with independent gate boxes."""
    fmt=FORMATS.get('135_half' if pair else frame_format,FORMATS['135'])
    along,across=fmt['along'],fmt['across'];margin=.48 if pair else .85 if fmt['perf'] else 1.7
    cross=fmt['film'] if view=='strip' else across+2.2
    gate_y=(cross-across)/2
    if pair:
        # Native's physical half-frame advance is fixed at 19 mm: a 1 mm
        # unexposed gap. A general collage gap must not change that mechanism.
        spacing=1. if pair_on_strip else max(.5,min(2.,float(pair_spacing_mm)))
        if not pair_on_strip:margin=gate_y=0.;cross=across
        tw=along*2+spacing+margin*2;th=cross
        gates=[[margin,gate_y,along,across],[margin+along+spacing,gate_y,along,across]]
        tiles=[dict(rect=[0.,0.,tw,th],gates=gates,indices=[0,1],format='135_half',view=view)]
    else:
        # Every tile is a piece of the selected gauge, rather than a generic
        # border stretched to the image. Portraits turn the whole film strip.
        vertical=bool(dimensions and dimensions[0][1]>dimensions[0][0])
        nominal_vertical=across>along
        local_turn=1 if vertical!=nominal_vertical else 0
        cw,ch=along+margin*2,cross
        tw,th=(ch,cw) if local_turn else (cw,ch)
        n=len(dimensions);cols=n if layout=='horizontal' else 1 if layout=='vertical' else math.ceil(math.sqrt(n))
        rows=math.ceil(n/cols);g=max(tw,th)*max(0.,float(gap))
        tiles=[];gates=[]
        for i in range(n):
            x,y=(i%cols)*(tw+g),(i//cols)*(th+g)
            box=rotate_rect([margin,gate_y,along,across],cw,ch,local_turn)
            gate=[x+box[0],y+box[1],box[2],box[3]];gates.append(gate)
            tiles.append(dict(rect=[x,y,tw,th],gates=[gate],indices=[i],format=frame_format,view=view,local_turn=local_turn,canonical=[cw,ch]))
        tw,ch=cols*tw+(cols-1)*g,rows*th+(rows-1)*g
        th=ch
    turn=(-int(group_turn)+(1 if pair and pair_axis=='vertical' else 0))%4
    output_gates=[rotate_rect(box,tw,th,turn) for box in gates]
    return dict(width=th if turn%2 else tw,height=tw if turn%2 else th,
                gates=output_gates,tiles=tiles,base_width=tw,base_height=th,turn=turn,
                photo_turn=((-turn)%4)*90,pair=pair,format=fmt)


def film_marks(plan,scale,photos,frame_number=12,holes='light',edge_print=True):
    """Same stock-specific physical marks for both preview and full export."""
    all_marks=[]
    for tile in plan['tiles']:
        index=tile['indices'][0];photo=photos[index] if index<len(photos) else {}
        stock=photo.get('stock','kodak_portra_400');fmt=FORMATS[tile['format']]
        look=stock_look(stock,fmt['perf']);ink=look['ink'];family=look['family']
        local_turn=tile.get('local_turn',0);ox,oy,tw,th=tile['rect']
        width,height=tile.get('canonical',(tw,th));marks=[]
        def shape(kind,rect,**props):marks.append(dict(kind=kind,rect=rect,**props))
        def rect(x,y,w,h,color=ink):shape('rect',[x,y,w,h],color=color)
        def text(value,x,y,w,h,font='sans',turn=0):shape('text',[x,y,w,h],text=str(value),color=ink,font=font,turn=turn)
        def arrow(x,y,w=1.8,h=.65,left=False):shape('arrow',[x,y,w,h],color=ink,left=left)
        shape('rect',[0.,0.,width,height],color=look['base'],background=True)
        # Full-width strip and filed carrier share their gate, but filed crops
        # most of the perforation and the factory edge print away.
        offset=(fmt['film']-height)/2
        if fmt['perf']:
            # Kodak-standard 135 still film: 4.75 mm pitch, 1.98 × 2.80 mm,
            # 0.50 mm corner radius and 2.00 mm to the film edge.
            for sy in (2.-offset,fmt['film']-4.8-offset):
                x=-2.85
                while x<width:
                    shape('roundrect',[x,sy,1.98,2.8],radius=.5,color='#EEE9D8' if holes=='light' else '#050605')
                    x+=4.75
        if edge_print and tile['view']=='strip':
            n=max(1,int(frame_number))+index
            if fmt['perf']:
                # Film data is registered to half-frame (19 mm) intervals,
                # not distributed to fit whichever output pixels we have.
                count=max(1,math.ceil(width/19.))
                for j in range(count):
                    s=j*19.;half=j%2==1;num=n+j//2
                    if family=='cine':
                        if j%2==0:
                            rect(s+1.5,fmt['film']-.91,1.16,.22)
                            text(look['words'],s+3.5,fmt['film']-1.36,min(28.,width-s-3.5),.88,'matrix')
                        continue
                    if family=='cinestill':
                        if j%2==0:text(look['words'],s+1.,.2,min(34.,width-s-1.),1.47,'matrix')
                        text(str(num)+('A' if half else ''),s+2.,fmt['film']-1.78,3.2,1.68,'mono')
                        if half:arrow(s+.3,fmt['film']-1.5,1.5,.97)
                        continue
                    turned=family=='ilford'
                    upper=fmt['film']-1.9 if turned else .28
                    lower=.15 if turned else fmt['film']-1.8
                    font='matrix' if family=='ilford' else 'dots' if family.startswith('fuji') else 'sans'
                    if j%2==0:
                        text(str(num),s+1.,upper,3.2,1.25,font,2 if turned else 0)
                        text(look['words'],s+5.2,upper,min(28.,width-s-5.2),1.22,font,2 if turned else 0)
                    text(str(num)+('A' if half else ''),s+15.3,lower,3.4,1.2,font,2 if turned else 0)
                    if half:arrow(s+13.2,lower+.55,1.7,.55)
                    code=look['dx'] if family not in ('fuji_slide',) else None
                    if code:
                        length=14.1 if family=='fuji_neg' else 13.06 if turned else 12.7
                        a,b=dx_tracks(code,num,half)
                        for track,row in enumerate((a,b)):
                            for k,bit in enumerate(row):
                                if bit:rect(s+k*length/31.,(.12 if turned else fmt['film']-2.17)+track*1.03,length/31.+.006,1.02)
            elif family=='fuji_120':
                for j in range(max(1,math.ceil(width/41.1))):
                    s=j*41.1+.8;text(str(n+j),s,.32,3.,1.05,'dots');arrow(s+3.5,.52,2.15,1.15,left=True)
                    text(look['words'],s+6.4,.32,min(30.,width-s-6.4),1.05,'dots')
            elif family=='cinestill_120':
                text(str(n),1.,.32,4.,1.35,'mono');arrow(5.,.55,5.,1.,left=True)
                text(look['words'],5.,height-1.8,min(38.,width-5.),1.4,'matrix')
            else:
                text(str(n),1.3,.28,3.,1.4);text(look['words'],6.,.28,min(40.,width-7.),1.35)
                arrow(2.,height-1.7,2.6,1.1);text(str(n),6.,height-1.7,3.,1.4)
                if width>58.:text(str(n+1)+'A',width-9.,height-1.7,6.,1.3)
        if local_turn:marks=rotate_marks(marks,width,height,local_turn)
        for mark in marks:
            mark['rect']=[mark['rect'][0]+ox,mark['rect'][1]+oy,*mark['rect'][2:]]
            all_marks.append(mark)
    all_marks=rotate_marks(all_marks,plan['base_width'],plan['base_height'],plan['turn'])
    for mark in all_marks:
        mark['rect']=[v*scale for v in mark['rect']]
        if 'radius' in mark:mark['radius']*=scale
    return all_marks
