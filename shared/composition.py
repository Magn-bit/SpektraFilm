"""Non-destructive layout coordinates, independent of preview resolution."""
import math
from .composition_edge import physical_plan,film_marks,rotate_rect


LAYOUTS=('grid','horizontal','vertical','feature')
# These are presentation treatments, not measured manufacturer film stocks.
# The renderer owns the same style token used by the preview and final export.
STYLES=('plain','paper','instant','film','contact','half_frame')
STYLE_COLORS={'plain':'#FCF9F2','paper':'#FCF9F2','instant':'#F8F4E9',
              'film':'#191D18','contact':'#252B23','half_frame':'#191D18'}


def cells(count,layout='grid'):
    count=max(1,min(9,int(count)))
    if layout=='feature' and count>2:
        rows=count-1
        return [(0.,0.,.64,1.)]+[(.64,i/rows,.36,1/rows) for i in range(rows)]
    columns=count if layout=='horizontal' else 1 if layout=='vertical' else math.ceil(math.sqrt(count))
    rows=math.ceil(count/columns)
    return [(i%columns/columns,i//columns/rows,1/columns,1/rows) for i in range(count)]


def crop_box(width,height,ratio,zoom=1.,pan_x=.5,pan_y=.5):
    """Cover a cell. Panning is normalized within actual cropped overflow."""
    zoom=max(1.,min(5.,float(zoom)));ratio=max(.01,float(ratio))
    cw,ch=(height*ratio,height) if width/height>ratio else (width,width/ratio)
    cw,ch=cw/zoom,ch/zoom
    left=(width-cw)*max(0.,min(1.,pan_x));top=(height-ch)*max(0.,min(1.,pan_y))
    left,top=round(left),round(top)
    return left,top,min(width,left+max(1,round(cw))),min(height,top+max(1,round(ch)))


def geometry(dimensions,layout='grid',ratio=1.5,gap=.015,border=.035,style='paper',edge=0,**options):
    """Automatic canvas preserves every cell's selected crop pixel density.

    An explicit edge is the only way to reduce output dimensions. Adding a
    frame expands a single image; it never shrinks the photograph inside it.
    """
    if options.get('frame_format') and style in ('film','half_frame'):
        plan=composition_plan(dimensions,layout,ratio,gap,border,style,edge,**options)
        return plan['width'],plan['height'],plan['rects'],plan['margin']
    # A half frame means two real 18:24 image gates, not a divider painted
    # across one image. The workspace only offers it for a two-photo pair.
    pair=style=='half_frame' and len(dimensions)==2
    bounds=cells(len(dimensions),'horizontal' if pair else layout)
    if pair:ratio=1.5
    if len(dimensions)==1:ratio=dimensions[0][0]/dimensions[0][1]
    required=1.
    for (w,h),(_,_,cw,ch) in zip(dimensions,bounds):
        # Cover-cropping can only discard the non-fitting dimension.
        natural_w=min(w,h*ratio*cw/ch)
        required=max(required,natural_w/cw)
    content_w=max(1,math.ceil(required));content_h=max(1,round(content_w/ratio))
    margin=round(min(content_w,content_h)*max(0.,border)) if style!='plain' else 0
    gap_px=round(min(content_w,content_h)*max(0.,gap)) if len(dimensions)>1 else 0
    footer=round(margin*2.2) if style=='instant' else round(margin*.8) if style=='contact' else 0
    width,height=content_w+margin*2,content_h+margin*2+footer
    scale=min(1.,edge/max(width,height)) if edge else 1.
    rects=[]
    for x,y,w,h in bounds:
        x0=round((margin+x*content_w+(gap_px/2 if x>0 else 0))*scale)
        y0=round((margin+y*content_h+(gap_px/2 if y>0 else 0))*scale)
        x1=round((margin+(x+w)*content_w-(gap_px/2 if x+w<.999 else 0))*scale)
        y1=round((margin+(y+h)*content_h-(gap_px/2 if y+h<.999 else 0))*scale)
        rects.append((x0,y0,max(x0+1,x1),max(y0+1,y1)))
    return max(1,round(width*scale)),max(1,round(height*scale)),rects,round(margin*scale)


def composition_plan(dimensions,layout='grid',ratio=1.5,gap=.015,border=.035,style='paper',edge=0,
                     frame_format='135',edge_view='strip',pair_axis='horizontal',group_turn=0,pair_on_strip=True,pair_spacing_mm=1.,**unused):
    dimensions=list(dimensions)
    if style in ('film','half_frame'):
        physical=physical_plan(dimensions,layout,gap,frame_format,edge_view,style=='half_frame',pair_axis,group_turn,pair_on_strip,pair_spacing_mm)
        # Preserve the pixel density of the largest selected source crop.
        oriented=[(h,w) if physical['photo_turn']%180 else (w,h) for w,h in dimensions]
        density=max(min(w/max(1e-6,box[2]),h/max(1e-6,box[3])) for (w,h),box in zip(oriented,physical['gates']))
        width,height=physical['width']*density,physical['height']*density
        scale=min(1.,float(edge)/max(width,height)) if edge else 1.;density*=scale
        width,height=max(1,round(width*scale)),max(1,round(height*scale))
        rects=[]
        for x,y,w,h in physical['gates']:
            left,top=round(x*density),round(y*density)
            rects.append((left,top,min(width,left+max(1,round(w*density))),min(height,top+max(1,round(h*density)))))
        return dict(width=width,height=height,rects=rects,margin=max(1,round(density*2.5)),
                    physical=physical,density=density,photo_turn=physical['photo_turn'])
    width,height,rects,margin=geometry(dimensions,layout,ratio,gap,border,style,edge)
    turn=int(group_turn)%4
    if turn:
        rects=[rotate_rect([x,y,r-x,b-y],width,height,(-turn)%4) for x,y,r,b in rects]
        rects=[(round(x),round(y),round(x+w),round(y+h)) for x,y,w,h in rects]
        if turn%2:width,height=height,width
    return dict(width=width,height=height,rects=rects,margin=margin,photo_turn=turn*90)


def composition_decorations(plan,style,photos=(),frame_number=12,holes='light',edge_print=True):
    if 'physical' in plan:
        return dict(holes=[],bands=[],rules=[],labels=[],primitives=film_marks(plan['physical'],plan['density'],photos,frame_number,holes,edge_print))
    result=decoration_spec(plan['width'],plan['height'],plan['margin'],style,photos)
    result['primitives']=[]
    return result


def decoration_spec(width,height,margin,style,photos=()):
    """Return vector decorations shared by the QML preview and final export.

    Coordinates are output pixels; no camera or film-stock claims are encoded.
    Missing metadata simply produces no corresponding label.
    """
    width,height,margin=int(width),int(height),int(margin)
    result={'holes':[],'labels':[],'bands':[],'rules':[]}
    if style in ('film','half_frame') and margin>3:
        hole_w=max(2,round(margin*.35));hole_h=max(2,round(margin*.52));pitch=max(hole_w*2,round(margin*.8))
        for y in (round(margin*.2),height-round(margin*.2)-hole_h):
            for x in range(margin,max(margin+1,width-margin),pitch):
                result['holes'].append([x,y,hole_w,hole_h])
    # These are restrained structural cues shared by the preview and export.
    # They make the selected frame treatment legible without adding text.
    if style in ('instant','contact') and margin>3:
        footer=max(1,round(margin*(2.2 if style=='instant' else .8)))
        result['bands'].append([margin,max(0,height-margin-footer),max(1,width-2*margin),footer])
    if style=='contact' and margin>3:
        # One outer sheet edge establishes the contact-print boundary; avoid
        # internal rules that would compete with the photographs.
        result['rules'].append([margin,margin,width-margin,height-margin])
    photo_list=list(photos or ())
    # Metadata is placed in separate footer columns; adding more photographs
    # must not stack text through the picture or beyond the canvas.
    label_width=max(1,(width-2*margin)//max(1,len(photo_list)))
    for index,photo in enumerate(photo_list):
        if not isinstance(photo,dict):continue
        metadata=photo.get('metadata') or {}
        parts=[]
        if metadata.get('camera'):parts.append(str(metadata['camera']))
        if metadata.get('lens'):parts.append(str(metadata['lens']))
        if metadata.get('exposure'):parts.append(str(metadata['exposure']))
        if metadata.get('date'):parts.append(str(metadata['date']))
        if photo.get('caption'):parts.append(str(photo['caption']))
        if photo.get('date') and str(photo['date']) not in parts:parts.append(str(photo['date']))
        if parts and margin>=4:
            result['labels'].append({'x':margin+index*label_width,'y':max(0,height-margin*.78),
                                     'width':max(1,label_width-round(margin*.25)),
                                     'text':' · '.join(parts),'photo':index})
    return result


def normalized_decorations(spec,width,height):
    width=max(1,float(width));height=max(1,float(height))
    return dict(holes=[[x/width,y/height,w/width,h/height] for x,y,w,h in spec.get('holes',[])],
                bands=[[x/width,y/height,w/width,h/height] for x,y,w,h in spec.get('bands',[])],
                rules=[[x0/width,y0/height,x1/width,y1/height] for x0,y0,x1,y1 in spec.get('rules',[])],
                labels=[dict(item,x=item['x']/width,y=item['y']/height,width=item.get('width',width)/width) for item in spec.get('labels',[])])
