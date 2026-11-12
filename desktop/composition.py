"""Optional print/layout workspace, separate from source editing and its history."""
from dataclasses import asdict,replace
from pathlib import Path
import math
import shutil
import tempfile
import threading
import zlib
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from PySide6.QtCore import QObject,Property,Signal,Slot,QThreadPool,QRunnable,QUrl,QAbstractListModel,QModelIndex,Qt,QTimer
from PySide6.QtGui import QDesktopServices,QImage
from PIL.ImageQt import ImageQt
from shared.composition import geometry,crop_box,LAYOUTS,STYLES,STYLE_COLORS,decoration_spec,normalized_decorations,composition_plan,composition_decorations
from shared.composition_edge import FORMATS,stock_format_choices
from shared.geometry import output_size
from shared.output_recipes import OutputRecipe,safe_filename
from shared.date_back import date_capabilities,exposure_text
from shared.film_pair import read_pair,pair_document,write_pair,hole_settings,number
from .dialogs import StudioFileDialog


# These are real film configurations, not six names for the same painted rim.
# The thumbnails are developed by the same native path as the large canvas.
_FRAME_PRESETS=(
    dict(id='film_135',name='135 片条',style='film',frame_format='135',edge_view='strip'),
    dict(id='film_120_square',name='120 · 6×6',style='film',frame_format='120_6x6',edge_view='strip'),
    dict(id='film_filed',name='片夹开窗',style='film',frame_format='135',edge_view='filed'),
    dict(id='film_xpan',name='XPan',style='film',frame_format='135_xpan',edge_view='strip'),
    dict(id='film_120_67',name='120 · 6×7',style='film',frame_format='120_6x7',edge_view='strip'),
    dict(id='film_half',name='半格双图',style='half_frame',frame_format='135_half',edge_view='strip'),
)


class _Work(QRunnable):
    def __init__(self,owner,fn,kind):super().__init__();self.owner=owner;self.fn=fn;self.kind=kind
    def run(self):
        try:self.owner.completed.emit((self.kind,True,self.fn()))
        except Exception as error:self.owner.completed.emit((self.kind,False,str(error)))


class _PhotoCells(QAbstractListModel):
    def __init__(self,parent):super().__init__(parent);self.rows=[]
    def roleNames(self):return {Qt.UserRole+1:b'entry'}
    def rowCount(self,parent=QModelIndex()):return 0 if parent.isValid() else len(self.rows)
    def data(self,index,role):
        return self.rows[index.row()] if index.isValid() and role==Qt.UserRole+1 else None
    def update(self,rows):
        if len(rows)!=len(self.rows):
            self.beginResetModel();self.rows=rows;self.endResetModel();return
        for index,row in enumerate(rows):
            if row!=self.rows[index]:
                self.rows[index]=row;model_index=self.index(index,0);self.dataChanged.emit(model_index,model_index,[Qt.UserRole+1])


def _photo_metadata(path):
    """Read available EXIF once for layout labels; never invent missing values."""
    result={}
    try:
        with Image.open(path) as image:
            entries=dict(image.getexif())
            try: entries.update(image.getexif().get_ifd(34665))
            except (KeyError,TypeError,ValueError,SyntaxError): pass
            def text(tag):
                value=entries.get(tag)
                return str(value).strip() if value not in (None,'') else ''
            make,model=text(271),text(272)
            result['camera']=' '.join(part for part in (make,model) if part)
            result['lens']=text(42036)
            focal=text(37386);aperture=text(33437);shutter=text(33434);iso=text(34855)
            values=[]
            if focal:values.append(f'{focal}mm')
            if aperture:values.append(f'f/{aperture}')
            if shutter:values.append(shutter)
            if iso:values.append(f'ISO {iso}')
            result['exposure']=' · '.join(values)
            result['date']=text(36867) or text(306)
            result['data_text']=exposure_text(entries.get(33434),entries.get(33437))
            if aperture:result['f_number']=float(entries[33437])
    except (OSError,ValueError,TypeError):pass
    if not result.get('date'):
        # RAW EXIF is metadata, not a reason to demosaic the sensor again.
        # The worker uses the already-installed metadata reader when Pillow
        # cannot expose these TIFF/EXIF fields.
        from .lens import _exiftool
        tool=_exiftool()
        if tool:
            import json,subprocess
            try:
                run=subprocess.run([tool,'-json','-Make','-Model','-LensModel','-FocalLength',
                    '-FNumber','-ExposureTime','-ISO','-DateTimeOriginal',str(path)],
                    capture_output=True,text=True,encoding='utf-8',timeout=8,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                data=json.loads(run.stdout)[0] if run.returncode==0 else {}
                result['camera']=' '.join(str(data.get(key) or '') for key in ('Make','Model')).strip() or result.get('camera','')
                result['lens']=str(data.get('LensModel') or result.get('lens',''))
                result['date']=str(data.get('DateTimeOriginal') or result.get('date',''))
                result['data_text']=exposure_text(data.get('ExposureTime'),data.get('FNumber')) or result.get('data_text','')
                if data.get('FNumber'):
                    result['f_number']=float(data['FNumber'])
                values=[str(data['FocalLength']) if data.get('FocalLength') else '',
                    'f/'+str(data['FNumber']) if data.get('FNumber') else '',
                    str(data.get('ExposureTime') or ''),'ISO '+str(data['ISO']) if data.get('ISO') else '']
                result['exposure']=' · '.join(value for value in values if value) or result.get('exposure','')
            except (OSError,ValueError,TypeError,IndexError,subprocess.TimeoutExpired):pass
    return {key:value for key,value in result.items() if value}


class Composition(QObject):
    changed=Signal()
    completed=Signal(object)
    message=Signal(str)
    def __init__(self,controller):
        super().__init__(controller);self.ctrl=controller;self.pool=QThreadPool(self);self.pool.setMaxThreadCount(1)
        self.rows=[];self.layout='grid';self.style='paper';self.ratio=1.5;self.gap=.015;self.border=.035
        self.color='#FCF9F2';self.caption='';self.date='';self.show_info=True;self.edge=0;self.format='tiff';self.active=0
        self.frame_format='135';self.edge_view='strip';self.pair_axis='horizontal';self.group_turn=0
        self.pair_on_strip=True;self.pair_spacing_mm=1.;self._pair_raw={};self._pair_path=''
        self.frame_number=12;self.holes='light';self.edge_print=True
        self.gate='auto';self.carrier='none';self.fog=1.;self.leaks=0.;self.frame_seed=1
        self.date_imprint_active=False;self.date_style='lcd';self.date_placement='frame';self.date_corner='br';self.date_exposure=3.5;self.date_size=1.
        self.date_also_data=False;self.date_order='japan';self.date_inset_x=3.;self.date_inset_y=2.4
        self.group_zoom=1.;self.group_pan_x=.5;self.group_pan_y=.5
        self._film_url='';self._film_geometry=None;self._film_revision=0;self._film_rendered=-1
        self._film_timer=QTimer(self);self._film_timer.setSingleShot(True);self._film_timer.setInterval(55);self._film_timer.timeout.connect(self._start_film_preview)
        self._frame_templates={};self._template_pending=[];self._template_in_flight=False;self._templates_requested=False;self._template_active='';self._film_error=''
        self._template_timer=QTimer(self);self._template_timer.setSingleShot(True);self._template_timer.setInterval(100);self._template_timer.timeout.connect(self._start_frame_template)
        self._busy=False;self._operation='';self._status='';self._progress=0.;self._cancel=threading.Event();self.generation=0;self.closed=False
        self.completed.connect(self._done)
        self._cells=_PhotoCells(self);self.changed.connect(lambda:self._cells.update(self.state['photos']))
    @Property(QObject,constant=True)
    def photoCells(self):return self._cells
    @Property('QVariantMap',notify=changed)
    def state(self):
        plan=self._plan();w,h,rects,margin=plan['width'],plan['height'],plan['rects'],plan['margin']
        photos=[]
        for row,rect in zip(self.rows,rects):
            item={k:v for k,v in row.items() if k not in ('settings','path','_prepared')}
            item['sourceWidth'],item['sourceHeight']=row['width'],row['height']
            item['width'],item['height']=self._dimensions(row,plan['photo_turn'])
            item['rotation']=(int(row.get('rotation',0))+plan['photo_turn'])%360
            item['stock']=getattr(row.get('settings'),'stock','kodak_portra_400')
            item['metadata']=dict(row.get('metadata') or {})
            item['caption']=self.caption if len(photos)==0 else ''
            item['date']=self.date if len(photos)==0 else ''
            item['rect']=[rect[0]/w,rect[1]/h,(rect[2]-rect[0])/w,(rect[3]-rect[1])/h]
            photos.append(item)
        native=self.style in ('film','half_frame') and self._film_geometry is not None
        spec=composition_decorations(plan,self.style,photos,self.frame_number,self.holes,self.edge_print) if self.style not in ('film','half_frame') else dict(holes=[],bands=[],rules=[],labels=[])
        decorations=normalized_decorations(spec,w,h)
        overlay=''
        style_names={'plain':'无边框','paper':'留白纸张','instant':'即影纸边','film':'胶片片边','contact':'接触印样','half_frame':'半格双图'}
        return dict(layout=self.layout,style=self.style,styleName=style_names.get(self.style,self.style),ratio=self.ratio,gap=self.gap,border=self.border,color=self.color,
            caption=self.caption,date=self.date,show_info=self.show_info,edge=self.edge,format=self.format,active=self.active,busy=self._busy,exporting=self._busy and self._operation=='export',status=self._status,
            progress=self._progress,width=w,height=h,margin=margin,decorations=decorations,overlay=overlay,photos=photos,canPair=len(photos)==2,
            frame_format=self.frame_format,edge_view=self.edge_view,pair_axis=self.pair_axis,group_turn=self.group_turn,
            pair_on_strip=self.pair_on_strip,pair_spacing_mm=self.pair_spacing_mm,pair_effective_spacing=1. if self.pair_on_strip else self.pair_spacing_mm,
            pair_path=self._pair_path,filled_count=sum(not row.get('_empty') for row in self.rows),
            frame_formats=stock_format_choices(getattr(self.rows[0].get('settings'),'stock','') if self.rows else ''),
            frame_presets=self._frame_preset_rows(),
            frame_preset_name=next((item['name'] for item in self._frame_preset_rows() if item['selected']),'自定义'),
            preview_error=self._film_error,
            frame_number=self.frame_number,holes=self.holes,edge_print=self.edge_print,
            gate=self.gate,carrier=self.carrier,fog=self.fog,leaks=self.leaks,frame_seed=self.frame_seed,
            native_canvas=self._film_url if native else '',native_geometry=self._film_geometry if native else {},
            native_pending=self.style in ('film','half_frame') and self._film_rendered!=self._film_revision,
            date_imprint_active=self.date_imprint_active,date_style=self.date_style,date_placement=self.date_placement,
            date_corner=self.date_corner,date_exposure=self.date_exposure,date_size=self.date_size,
            date_also_data=self.date_also_data,date_order=self.date_order,date_inset_x=self.date_inset_x,date_inset_y=self.date_inset_y,
            date_capabilities=date_capabilities(dict(style=self.style,pair_on_strip=self.pair_on_strip,frame_format=self.frame_format,
                date_style=self.date_style,date_placement=self.date_placement,date_imprint_active=self.date_imprint_active,date_also_data=self.date_also_data)),
            group_zoom=self.group_zoom,group_pan_x=self.group_pan_x,group_pan_y=self.group_pan_y)
    @staticmethod
    def _dimensions(row,extra=0):
        return (row['height'],row['width']) if ((int(row.get('rotation',0))+extra)//90)%2 else (row['width'],row['height'])
    def _plan(self):
        if self.style in ('film','half_frame') and self._film_geometry:
            native=self._film_geometry;w,h=native.get('source_canvas_w',native['canvas_w']),native.get('source_canvas_h',native['canvas_h']);rects=[]
            for quad in native['gates']:
                points=np.asarray(quad).reshape(4,2)
                rects.append((round(points[:,0].min()*w),round(points[:,1].min()*h),round(points[:,0].max()*w),round(points[:,1].max()*h)))
            return dict(width=w,height=h,rects=rects,margin=max(1,round(2.5/max(1e-6,native.get('mm_per_px',1)))),photo_turn=((self.group_turn+(3 if self.style=='half_frame' and self.pair_axis=='vertical' else 0))%4)*90)
        return composition_plan([self._dimensions(r) for r in self.rows] or [(1500,1000)],self.layout,self.ratio,self.gap,self.border,self.style,self.edge,
            frame_format=self.frame_format,edge_view=self.edge_view,pair_axis=self.pair_axis,group_turn=self.group_turn,
            pair_on_strip=self.pair_on_strip,pair_spacing_mm=self.pair_spacing_mm)
    def _geometry(self):
        plan=self._plan();return plan['width'],plan['height'],plan['rects'],plan['margin']
    def _frame_preset_rows(self):
        stock=self.rows[0]['settings'].stock if self.rows else ''
        formats={choice['id'] for choice in stock_format_choices(stock)}
        return [dict(preset,enabled=bool(self.rows) and preset['frame_format'] in formats and
                     (preset['style']!='half_frame' or len(self.rows)==2),
                     selected=self.style==preset['style'] and self.edge_view==preset['edge_view'] and
                     (self.style=='half_frame' or self.frame_format==preset['frame_format']),
                     loading=self._template_active==preset['id'],
                     source=self._frame_templates.get(preset['id'],'')) for preset in _FRAME_PRESETS]
    @Slot(bool)
    def requestFrameTemplates(self,visible):
        self._templates_requested=bool(visible)
        if visible:
            self._template_pending=[item for item in self._frame_preset_rows() if item['enabled'] and item['id'] not in self._frame_templates and item['id']!=self._template_active]
            self._template_timer.start()
        else:self._template_pending=[];self._template_timer.stop()
    @Slot()
    def retryPreview(self):
        if not self._busy and self.rows:
            if any(row.get('_prepared') is None for row in self.rows):
                self.open_selection([dict(row) for row in self.rows])
            else:self._film_error='';self._invalidate_film();self.changed.emit()
    @Slot(str)
    def applyFramePreset(self,preset_id):
        if self._busy and self._operation=='export':return
        preset=next((item for item in self._frame_preset_rows() if item['id']==preset_id and item['enabled']),None)
        if preset is None:return
        old=self.style
        self.style=preset['style'];self.frame_format=preset['frame_format'];self.edge_view=preset['edge_view']
        self.carrier='none'
        if self.color==STYLE_COLORS.get(old):self.color=STYLE_COLORS[self.style]
        self._invalidate_film();self.changed.emit()
    def open_selection(self,photos):
        if self._busy:return False
        self.generation+=1;token=self.generation;self.rows=[];self.active=0;self._status='';self._progress=0.
        self._pair_raw={};self._pair_path=''
        self._film_timer.stop();self._film_url='';self._film_geometry=None;self._film_rendered=-1;self._film_revision+=1
        self._template_timer.stop();self._frame_templates={};self._template_pending=[];self._templates_requested=False;self._film_error=''
        self.group_zoom=1.;self.group_pan_x=.5;self.group_pan_y=.5
        self.frame_seed=int(self.ctrl.preferences.get('frame_body_seed',0)) or (zlib.crc32('|'.join(sorted(photo['path'] for photo in photos[:9])).encode('utf-8'))&0x7fffffff)
        for photo in photos[:9]:
            from .imaging import film_settings
            settings=film_settings(photo['settings']);w,h=output_size(photo['width'],photo['height'],settings.geometry)
            self.rows.append(dict(path=photo['path'],name=photo['name'],settings=settings,width=w,height=h,
                metadata={},
                source=self.ctrl.frame if photo['path']==self.ctrl.currentPath and self.ctrl.frame else photo.get('thumbnail',''),zoom=1.,pan_x=.5,pan_y=.5,rotation=0))
        if self.style=='half_frame' and len(self.rows)!=2:self.style='film'
        if self.rows and self.frame_format not in {choice['id'] for choice in stock_format_choices(self.rows[0]['settings'].stock)}:self.frame_format='135'
        self.changed.emit()
        self._load_previews(list(enumerate(self.rows)));return True
    def _load_previews(self,indexed):
        token=self.generation;snapshots=[(index,dict(row)) for index,row in indexed]
        self._operation='preview';self._busy=True;self.changed.emit()
        self._cancel.clear()
        def load():
            from .imaging import read_photo,prepare_photo_source,render
            images=[]
            for i,row in snapshots:
                if self.closed or token!=self.generation or self._cancel.is_set():break
                if row.get('_empty'):
                    prepared=Image.new('RGB',(180,240))
                    images.append((i,QImage(),prepared,{}));continue
                original=read_photo(row['path'],1000)
                metadata=_photo_metadata(row['path'])
                prepared,_=prepare_photo_source(original,row['path'],row['settings'])
                if prepared is not original:original.close()
                image=render(prepared,row['settings'],preview=True)
                images.append((i,QImage(ImageQt(image)).copy(),prepared,metadata))
            return token,images
        self.pool.start(_Work(self,load,'preview'))
    @Slot(str,'QVariant')
    def setOption(self,key,value):
        # Preview decoding does not depend on framing. Accept those edits
        # immediately, but keep the canvas stable while an export owns it.
        if self._busy and self._operation=='export':return
        if key=='layout' and value in LAYOUTS:self.layout=value
        elif key=='style' and value in STYLES:
            # A pair has two independent scene exposures on one common film.
            if value=='half_frame' and len(self.rows)!=2:return
            if self.color==STYLE_COLORS.get(self.style):self.color=STYLE_COLORS[value]
            self.style=value
        elif key=='format' and value in ('jpeg','png','tiff'):self.format=value
        elif key=='frame_format' and value in FORMATS:
            if self.rows and value not in {choice['id'] for choice in stock_format_choices(self.rows[0]['settings'].stock)}:return
            self.frame_format=value
        elif key=='edge_view' and value in ('strip','filed'):self.edge_view=value
        elif key=='pair_axis' and value in ('horizontal','vertical'):self.pair_axis=value
        elif key=='pair_on_strip':self.pair_on_strip=bool(value)
        elif key=='pair_spacing_mm':self.pair_spacing_mm=number(value,1.,.5,2.)
        elif key=='holes' and value in ('light','black'):self.holes=value
        elif key=='edge_print':self.edge_print=bool(value)
        elif key=='gate' and value in ('auto','square','rounded','eared','shouldered','kicked'):self.gate=value
        elif key=='carrier' and value in ('none','black','open'):self.carrier=value
        elif key in ('fog','leaks'):
            try:v=float(value)
            except (TypeError,ValueError):return
            if not math.isfinite(v):return
            setattr(self,key,max(0.,min(4.,v)))
        elif key=='date_imprint_active':self.date_imprint_active=bool(value)
        elif key=='date_also_data':self.date_also_data=bool(value)
        elif key=='date_order' and value in ('japan','us'):self.date_order=value
        elif key=='date_style' and value in ('lcd','dots','data'):self.date_style=value
        elif key=='date_placement' and value in ('frame','rebate'):self.date_placement=value
        elif key=='date_corner' and value in ('br','bl','tr','tl'):self.date_corner=value
        elif key in ('date_exposure','date_size','date_inset_x','date_inset_y'):
            try:v=float(value)
            except (TypeError,ValueError):return
            if not math.isfinite(v):return
            limits=(-2.,8.) if key=='date_exposure' else (.4,3.) if key=='date_size' else (0.,30.)
            setattr(self,key,max(limits[0],min(limits[1],v)))
        elif key=='frame_number':self.frame_number=max(0,min(99,int(value)))
        elif key in ('caption','date'):setattr(self,key,str(value)[:160])
        elif key=='show_info':self.show_info=bool(value)
        elif key=='color' and isinstance(value,str) and len(value)==7:
            try:int(value[1:],16)
            except ValueError:return
            self.color=value
        elif key in ('ratio','gap','border','edge'):
            try:v=float(value)
            except (TypeError,ValueError):return
            if not math.isfinite(v):return
            limits={'ratio':(.5,3.),'gap':(0,.12),'border':(0,.2),'edge':(0,32000)}
            setattr(self,key,max(limits[key][0],min(limits[key][1],v)))
        else:return
        if key!='format':self._invalidate_film()
        self.changed.emit()
    @Slot(int)
    def select(self,index):
        if 0<=index<len(self.rows):self.active=index;self.changed.emit()
    @Slot()
    def savePair(self):
        if self._busy or self.style!='half_frame' or len(self.rows)!=2:return
        source=next((row['path'] for row in self.rows if row.get('path')),'')
        target,_=StudioFileDialog.getSaveFileName(None,'保存半格组合',self._pair_path or str(Path(source).with_suffix('.spektrapair')),'半格组合 (*.spektrapair)')
        if target:self.savePairPath(target)
    @Slot(str,result=bool)
    def savePairPath(self,path):
        if self._busy or self.style!='half_frame' or len(self.rows)!=2:return False
        try:
            value=pair_document(self.rows,self.state,self._pair_raw)
            target=write_pair(path,value);self._pair_raw=value;self._pair_path=str(target)
            self._status='已保存 '+target.name;self.changed.emit();return True
        except (OSError,ValueError,TypeError) as error:self.message.emit(str(error));return False
    @Slot()
    def openPair(self):
        if self._busy:return
        paths,_=StudioFileDialog.getOpenFileNames(None,'打开半格组合',str(Path(self._pair_path).parent) if self._pair_path else '', '半格组合 (*.spektrapair)')
        if paths:self.openPairPath(paths[0])
    @Slot(str,result=bool)
    def openPairPath(self,path):
        if self._busy:return False
        from .imaging import Settings,photo_dimensions
        try:
            value=read_pair(path);directory=Path(path).resolve().parent;rows=[];defaults=asdict(self.ctrl._settings)
            missing=[]
            for key in ('left','right'):
                hole=value.get(key)
                if hole is None:
                    rows.append(dict(path='',name='空位',settings=Settings.from_mapping(defaults),width=180,height=240,
                        metadata={},source='',zoom=1.,pan_x=.5,pan_y=.5,rotation=0,_empty=True,dated=True));continue
                source=Path(hole['path'])
                if not source.is_absolute():
                    folder=Path(value.get('folder') or '')
                    candidate=(folder/source) if folder.is_absolute() else directory/folder/source
                    source=candidate if candidate.is_file() else directory/source
                settings=Settings.from_mapping(hole_settings(hole,defaults));placement=hole.get('placement') or {}
                exists=source.is_file()
                width,height=photo_dimensions(str(source)) if exists else (180,240)
                if not exists:missing.append(source.name)
                rows.append(dict(path=str(source) if exists else '',missing_path=str(source) if not exists else '',name=source.name,
                    settings=settings,width=width,height=height,metadata={},source='',
                    zoom=number(placement.get('scale'),1,1,5),pan_x=(number(placement.get('x'),0,-1,1)+1)/2,
                    pan_y=(number(placement.get('y'),0,-1,1)+1)/2,rotation=int(number(placement.get('quarterTurns'),0,0,3))*90,
                    dated=bool(hole.get('dated',True)),_empty=not exists))
            self.generation+=1;self._film_timer.stop();self._template_timer.stop()
            self.rows=rows;self.active=0;self._pair_raw=value;self._pair_path=str(Path(path).resolve())
            self.style='half_frame';self.frame_format='135_half';self._film_url='';self._film_geometry=None;self._film_rendered=-1
            self._film_error=''
            self._frame_templates={};self._template_pending=[]
            extension=value.get('spektrafilm') or {};saved=extension.get('options',{}) if isinstance(extension,dict) else {}
            for key in ('edge_view','frame_number','holes','edge_print','gate','carrier','fog','leaks','date_imprint_active',
                        'date_style','date_placement','date_corner','date_exposure','date_size','date_also_data','date_order','date_inset_x','date_inset_y','date','caption'):
                if key in saved:self.setOption(key,saved[key])
            self.pair_on_strip=bool(value.get('onStrip',False));self.pair_spacing_mm=number(value.get('spacingMM'),1,.5,2)
            self.pair_axis='vertical' if value.get('turned') else 'horizontal'
            self.group_turn=int(number(saved.get('group_turn'),0,0,3))
            self.frame_seed=int(number(saved.get('frame_seed'),zlib.crc32('|'.join(row['path'] for row in rows).encode('utf-8'))&0x7fffffff,0,2147483647))
            self._film_revision+=1
            self._load_previews(list(enumerate(self.rows)))
            if missing:self.message.emit('找不到照片：'+ '、'.join(missing)+'；可替换对应片位')
            return True
        except (OSError,ValueError,TypeError,KeyError) as error:self.message.emit(str(error));return False
    @Slot(int)
    def replaceHole(self,index):
        if self._busy or self.style!='half_frame' or index not in (0,1):return
        from shared.photo_formats import PHOTO_DIALOG_FILTER
        paths,_=StudioFileDialog.getOpenFileNames(None,'替换半格照片',str(Path(self.rows[index]['path']).parent),PHOTO_DIALOG_FILTER)
        if paths:self.replaceHolePath(index,paths[0])
    @Slot(int,str,result=bool)
    def replaceHolePath(self,index,path):
        if self._busy or self.style!='half_frame' or index not in (0,1):return False
        from .imaging import Settings
        from shared.settings_sync import category_fields
        try:
            photos,errors=self.ctrl._read_imports([str(Path(path).resolve())])
            if errors or not photos:raise ValueError(errors[0] if errors else '无法读取照片')
            photo=photos[0];settings=Settings.from_mapping(photo['settings']);common=self.rows[0]['settings']
            if index==0:
                settings=replace(settings,**{field:getattr(common,field) for field in category_fields(('materials','film_effects','print_effects'))})
            self.rows[index]=dict(path=photo['path'],name=photo['name'],settings=settings,width=photo['width'],height=photo['height'],
                metadata={},source='',zoom=1.,pan_x=.5,pan_y=.5,rotation=0,dated=True,_empty=False)
            self.generation+=1;self._film_revision+=1;self.active=index;self._film_error=''
            self._load_previews([(index,self.rows[index])]);return True
        except (OSError,ValueError,TypeError) as error:self.message.emit(str(error));return False
    @Slot(int)
    def removeHole(self,index):
        if self._busy or self.style!='half_frame' or index not in (0,1):return
        if self.rows[index].get('_empty'):return
        row=self.rows[index]
        self.rows[index]=dict(path='',name='空位',settings=row['settings'],width=180,height=240,metadata={},source='',
            zoom=1.,pan_x=.5,pan_y=.5,rotation=0,dated=True,_empty=True)
        self.generation+=1;self._film_revision+=1;self.active=index
        self._load_previews([(index,self.rows[index])])
    @Slot(int,bool)
    def setHoleDated(self,index,dated):
        if self._operation=='export' or index not in (0,1) or index>=len(self.rows):return
        self.rows[index]['dated']=bool(dated);self._invalidate_film();self.changed.emit()
    @Slot(int,float,float,float)
    def position(self,index,x,y,zoom):
        if self._operation=='export' or not 0<=index<len(self.rows) or not all(math.isfinite(v) for v in (x,y,zoom)):return
        self.rows[index].update(pan_x=max(0.,min(1.,x)),pan_y=max(0.,min(1.,y)),zoom=max(1.,min(5.,zoom)));self._invalidate_film();self.changed.emit()
    @Slot(int,int)
    def swap(self,first,second):
        if self._operation=='export' or not all(0<=i<len(self.rows) for i in (first,second)):return
        self.rows[first],self.rows[second]=self.rows[second],self.rows[first];self.active=second;self._invalidate_film();self.changed.emit()
    @Slot()
    def resetPosition(self):self.position(self.active,.5,.5,1.)
    @Slot(int,int)
    def rotate(self,index,degrees=90):
        if self._operation=='export' or not 0<=index<len(self.rows):return
        self.rows[index]['rotation']=(int(self.rows[index].get('rotation',0))+int(degrees))%360
        self._invalidate_film();self.changed.emit()
    @Slot(int)
    def rotateGroup(self,degrees):
        if self._operation=='export':return
        self.group_turn=(self.group_turn+int(degrees)//90)%4;self._invalidate_film();self.changed.emit()
    @Slot(float,float,float)
    def positionGroup(self,x,y,zoom):
        if self._operation=='export' or not all(math.isfinite(v) for v in (x,y,zoom)):return
        x,y,zoom=max(0.,min(1.,x)),max(0.,min(1.,y)),max(1.,min(5.,zoom))
        ratio=zoom/self.group_zoom;dx,dy=x-self.group_pan_x,y-self.group_pan_y
        for row in self.rows:
            row.update(zoom=max(1.,min(5.,row['zoom']*ratio)),pan_x=max(0.,min(1.,row['pan_x']+dx)),pan_y=max(0.,min(1.,row['pan_y']+dy)))
        self.group_pan_x,self.group_pan_y,self.group_zoom=x,y,zoom;self._invalidate_film();self.changed.emit()
    @Slot()
    def resetGroupPosition(self):
        if self._operation=='export':return
        for row in self.rows:row.update(zoom=1.,pan_x=.5,pan_y=.5)
        self.group_pan_x,self.group_pan_y,self.group_zoom=.5,.5,1.;self._invalidate_film();self.changed.emit()
    def _invalidate_film(self):
        self._film_revision+=1
        self._film_error=''
        if self._operation!='export':self._cancel.clear()
        if self.style in ('film','half_frame') and self.rows and not self.closed:self._film_timer.start()
    def _start_film_preview(self):
        if self.closed or self.style not in ('film','half_frame') or not self.rows:return
        if self._busy or self._template_in_flight:
            # One worker owns native work; replace pending state, never queue
            # every slider event behind a long source decode or render.
            return
        if not all(row.get('_prepared') is not None for row in self.rows):return
        token,revision=self.generation,self._film_revision
        if revision==self._film_rendered:return
        rows=[dict(row) for row in self.rows];options=self.state
        self._operation='film_preview';self._busy=True;self._status='正在显影片边';self.changed.emit()
        def work():
            from .raw_source import quantize_display
            pixels,geometry=self._render_film_rows(rows,options,preview=True)
            return token,revision,QImage(ImageQt(Image.fromarray(quantize_display(pixels)))).copy(),geometry
        self.pool.start(_Work(self,work,'film_preview'))
    def _start_frame_template(self):
        """One small native thumbnail at a time; live canvas always goes first."""
        if self.closed or not self._templates_requested or not self._template_pending:return
        if self._busy or self._template_in_flight:return
        if self.style in ('film','half_frame') and self._film_rendered!=self._film_revision:
            self._start_film_preview();return
        if not self.rows or not all(row.get('_prepared') is not None for row in self.rows):return
        preset=self._template_pending.pop(0);token=self.generation
        rows=[dict(row) for row in self.rows[:2 if preset['style']=='half_frame' else 1]]
        options=dict(self.state,**{key:preset[key] for key in ('style','frame_format','edge_view')},
                     carrier='none',group_turn=0,edge=0,date_imprint_active=False)
        self._template_in_flight=True;self._template_active=preset['id'];self.changed.emit()
        def work():
            from .raw_source import source_pixels,resize_pixels,display_image,source_metadata,quantize_display
            small=[]
            try:
                for row in rows:
                    source=row['_prepared'];scale=min(1.,240/max(source.size))
                    size=(max(1,round(source.width*scale)),max(1,round(source.height*scale)))
                    image=display_image(resize_pixels(source_pixels(source),size),full_size=source.info.get('source_size',source.size),metadata=source_metadata(source))
                    small.append(image);row['_prepared']=image
                    row.update(zoom=1.,pan_x=.5,pan_y=.5,rotation=0)
                pixels,_=self._render_film_rows(rows,options,preview=True)
                return token,preset['id'],QImage(ImageQt(Image.fromarray(quantize_display(pixels)))).copy()
            finally:
                for image in small:image.close()
        self.pool.start(_Work(self,work,'frame_template'))
    def _render_film_rows(self,rows,options,preview=False):
        """A physical pair is one exposure source; other strips remain separate."""
        from .film_canvas import render_film_edge,rotate_canvas
        from .imaging import read_photo,prepare_photo_source
        from .raw_source import resize_pixels
        from .output import ExportCancelled
        from .native_spectral import _mapped_result
        def prepared(row):
            if row.get('_empty'):
                if preview and row.get('_prepared') is not None:return row['_prepared'],False
                return Image.new('RGB',(180,240)),True
            if preview:return row['_prepared'],False
            if self._cancel.is_set():raise ExportCancelled('排版导出已取消')
            original=read_photo(row['path']);value,_=prepare_photo_source(original,row['path'],row['settings'])
            if value is not original:original.close()
            return value,True
        pair=options['style']=='half_frame';groups=[rows] if pair else [[row] for row in rows]
        frames=[];geometries=[]
        for index,group in enumerate(groups):
            sources=[];owned=[]
            try:
                for row in group:
                    source,own=prepared(row);sources.append(source)
                    if own:owned.append(source)
                current=dict(options,placements=[{key:row[key] for key in ('path','rotation','zoom','pan_x','pan_y','metadata','dated') if key in row} for row in group],
                    group_turn=0,edge=0,frame_number=int(options.get('frame_number',12))+index,frame_seed=(int(options.get('frame_seed',1))+index)&0x7fffffff)
                pixels,geometry=render_film_edge(sources if pair else sources[0],
                    [row['settings'] for row in group] if pair else group[0]['settings'],current,preview=preview,
                    progress=None if preview else lambda fraction:self.completed.emit(('progress',True,((index+fraction)/(len(groups)+1),'显影 '+str(index+1)+' / '+str(len(groups))))))
                frames.append(pixels);geometries.append(geometry)
            finally:
                for source in owned:source.close()
            if not preview:self.completed.emit(('progress',True,((index+1)/(len(groups)+1),'显影 '+str(index+1)+' / '+str(len(groups)))))
            if self._cancel.is_set():raise ExportCancelled('排版导出已取消')
        if len(frames)==1:canvas,geometry=frames[0],geometries[0]
        else:
            count=len(frames);columns=count if options['layout']=='horizontal' else 1 if options['layout']=='vertical' else math.ceil(math.sqrt(count))
            cell_w=max(native.get('source_canvas_w',frame.shape[1]) for frame,native in zip(frames,geometries))
            cell_h=max(native.get('source_canvas_h',frame.shape[0]) for frame,native in zip(frames,geometries))
            gap=round(min(cell_w,cell_h)*options['gap']);lines=math.ceil(count/columns)
            source_w=columns*cell_w+(columns-1)*gap;source_h=lines*cell_h+(lines-1)*gap
            scale=min(1.,1800/max(source_w,source_h)) if preview else 1.
            width,height=max(1,round(source_w*scale)),max(1,round(source_h*scale))
            if not preview and (width>65535 or height>65535):raise ValueError('原像素排版超出文件尺寸限制，请选择导出长边')
            canvas=_mapped_result((height,width,3)) if width*height>16_000_000 else np.empty((height,width,3),np.float32)
            rgb=np.array([int(options['color'][i:i+2],16) for i in (1,3,5)],np.float32)/255
            for top in range(0,height,64):canvas[top:top+64]=rgb
            gates=[]
            for i,(frame,native) in enumerate(zip(frames,geometries)):
                source_fw=native.get('source_canvas_w',frame.shape[1]);source_fh=native.get('source_canvas_h',frame.shape[0])
                w,h=max(1,round(source_fw*scale)),max(1,round(source_fh*scale))
                x=round(((i%columns)*(cell_w+gap)+(cell_w-source_fw)/2)*scale);y=round(((i//columns)*(cell_h+gap)+(cell_h-source_fh)/2)*scale)
                w,h=min(w,width-x),min(h,height-y)
                canvas[y:y+h,x:x+w]=frame if frame.shape[:2]==(h,w) else resize_pixels(frame,(w,h))
                for quad in native['gates']:
                    points=np.asarray(quad,np.float64).reshape(4,2);points=(points*[w,h]+[x,y])/[width,height];gates.append(points.reshape(-1).tolist())
            geometry=dict(valid=True,canvas_w=width,canvas_h=height,gates=gates,vertical=False,
                source_canvas_w=source_w,source_canvas_h=source_h,
                mm_per_px=geometries[0].get('mm_per_px',1),frames=geometries)
        canvas,geometry=rotate_canvas(canvas,geometry,int(options.get('group_turn',0)))
        edge=int(options.get('edge') or 0)
        natural=max(geometry.get('source_canvas_w',canvas.shape[1]),geometry.get('source_canvas_h',canvas.shape[0]))
        if edge and natural>edge:
            factor=edge/natural;geometry=dict(geometry,source_canvas_w=round(geometry.get('source_canvas_w',canvas.shape[1])*factor),source_canvas_h=round(geometry.get('source_canvas_h',canvas.shape[0])*factor))
        if edge and max(canvas.shape[:2])>edge:
            scale=edge/max(canvas.shape[:2]);size=(max(1,round(canvas.shape[1]*scale)),max(1,round(canvas.shape[0]*scale)))
            canvas=resize_pixels(canvas,size);geometry=dict(geometry,canvas_w=size[0],canvas_h=size[1],mm_per_px=geometry.get('mm_per_px',1)/scale)
        if max(canvas.shape[:2])>65535:raise ValueError('原像素排版超出文件尺寸限制，请选择导出长边')
        return canvas,geometry
    @Slot()
    def cancel(self):
        self._cancel.set()
        if self._busy and self.style in ('film','half_frame'):
            from .native_spectral import cancel_active
            cancel_active()
        if self._busy:self._status='正在停止';self.changed.emit()
    @Slot()
    def export(self):
        if self._busy or not self.rows:return
        directory=StudioFileDialog.getExistingDirectory(None,'选择排版导出位置',str(Path(self.rows[0]['path']).parent))
        if not directory:return
        suffix={'jpeg':'.jpg','png':'.png','tiff':'.tif'}[self.format]
        folder=Path(directory)/'排版';folder.mkdir(parents=True,exist_ok=True)
        base=safe_filename(Path(self.rows[0]['path']).stem+'_排版');path=folder/(base+suffix);counter=2
        while path.exists():path=folder/f'{base}_{counter}{suffix}';counter+=1
        self.start_export(path)
    def start_export(self,path):
        if self._busy or not self.rows or not any(not row.get('_empty') for row in self.rows):return False
        self._operation='export';self._busy=True;self._cancel.clear();self._status='准备画布';self._progress=0.;self.changed.emit()
        snapshot=[dict(row) for row in self.rows];options=self.state
        def work():return self._export(snapshot,options,Path(path))
        self.pool.start(_Work(self,work,'export'));return True
    def _export(self,rows,options,path):
        from .output import export_pixels,ExportCancelled
        from .imaging import read_photo,prepare_photo_source,render_pixels
        from .raw_source import resize_pixels
        if any(row['settings'].hdr_enabled for row in rows):
            raise ValueError('HDR 增益图请使用照片输出配方；排版导出暂不支持增益图')
        if options['style'] in ('film','half_frame'):
            # Final physical output always reopens original sources and uses
            # the actual native film canvas. Proxy/painted borders never enter.
            pixels,_=self._render_film_rows(rows,options,preview=False)
            if self._cancel.is_set():raise ExportCancelled('排版导出已取消')
            recipe=OutputRecipe(format=options['format'],bit_depth=8 if options['format']=='jpeg' else 16,quality=100)
            return str(path),export_pixels(pixels,path,recipe,cancel=self._cancel)
        plan=composition_plan([self._dimensions(r) for r in rows],options['layout'],options['ratio'],options['gap'],options['border'],options['style'],options['edge'],
            frame_format=options.get('frame_format','135'),edge_view=options.get('edge_view','strip'),pair_axis=options.get('pair_axis','horizontal'),group_turn=options.get('group_turn',0))
        width,height,rects,margin=plan['width'],plan['height'],plan['rects'],plan['margin']
        if width>65535 or height>65535:raise ValueError('原像素排版超出文件尺寸限制，请明确选择导出长边')
        required=width*height*12
        if shutil.disk_usage(tempfile.gettempdir()).free<required+128*1024**2:raise ValueError('临时磁盘空间不足，请选择较小的排版输出尺寸')
        rgb=np.array([int(options['color'][i:i+2],16) for i in (1,3,5)],np.float32)/255
        with tempfile.TemporaryDirectory(prefix='spektra-layout-') as directory:
            canvas=np.memmap(Path(directory)/'canvas.f32',dtype=np.float32,mode='w+',shape=(height,width,3))
            try:
                for top in range(0,height,64):canvas[top:top+64]=rgb
                for i,(row,rect) in enumerate(zip(rows,rects)):
                    if self._cancel.is_set():raise ExportCancelled('排版导出已取消')
                    original=read_photo(row['path']);prepared=None
                    try:
                        prepared,_=prepare_photo_source(original,row['path'],row['settings'])
                        if prepared is not original:original.close();original=None
                        pixels=render_pixels(prepared,row['settings'])
                    finally:
                        if original is not None:original.close()
                        if prepared is not None and prepared is not original:prepared.close()
                    turns=((int(row.get('rotation',0))+plan['photo_turn'])//90)%4
                    if turns:pixels=np.rot90(pixels,turns)
                    left,top,right,bottom=rect;cw,ch=right-left,bottom-top
                    x0,y0,x1,y1=crop_box(pixels.shape[1],pixels.shape[0],cw/ch,row['zoom'],row['pan_x'],row['pan_y'])
                    crop=pixels[y0:y1,x0:x1]
                    canvas[top:bottom,left:right]=crop if crop.shape[:2]==(ch,cw) else resize_pixels(crop,(cw,ch))
                    del crop,pixels
                    self.completed.emit(('progress',True,((i+1)/(len(rows)+1),'显影 '+str(i+1)+' / '+str(len(rows)))))
                self._decorate(canvas,options,margin,rows)
                recipe=OutputRecipe(format=options['format'],bit_depth=8 if options['format']=='jpeg' else 16,quality=100)
                size=export_pixels(canvas,path,recipe,cancel=self._cancel)
            finally:
                canvas.flush();canvas._mmap.close();del canvas
        return str(path),size
    def _decorate(self,canvas,options,margin,rows=()):
        height,width=canvas.shape[:2]
        photos=[dict(stock=getattr(row.get('settings'),'stock','kodak_portra_400'),metadata=row.get('metadata') or {},caption=options.get('caption','') if i==0 else '',date=options.get('date','') if i==0 else '') for i,row in enumerate(rows)]
        plan=composition_plan([self._dimensions(r) for r in rows] or [(width,height)],options['layout'],options['ratio'],options['gap'],options['border'],options['style'],options['edge'],
            frame_format=options.get('frame_format','135'),edge_view=options.get('edge_view','strip'),pair_axis=options.get('pair_axis','horizontal'),group_turn=options.get('group_turn',0))
        spec=composition_decorations(plan,options['style'],photos,options.get('frame_number',12),options.get('holes','light'),options.get('edge_print',True))
        for x,y,w,h in spec['holes']:canvas[y:y+h,x:x+w]=(.86,.83,.73)
        for x,y,w,h in spec.get('bands',[]):
            color=(.96,.94,.89) if options['style']=='instant' else (.15,.18,.14) if options['style']=='contact' else (.13,.14,.12)
            canvas[y:y+h,x:x+w]=color
        for x0,y0,x1,y1 in spec.get('rules',[]):
            if x0==x1:
                x=max(0,min(width-1,int(x0)));canvas[int(y0):int(y1)+1,max(0,x-1):min(width,x+1)]=(.44,.47,.43)
            elif y0!=y1:
                # Contact sheet uses one quiet outer keyline. Keep the same
                # four edges as the QML preview instead of exporting only its
                # top edge.
                left,right=max(0,int(x0)),min(width,int(x1));top,bottom=max(0,int(y0)),min(height,int(y1))
                ink=(.44,.47,.43)
                canvas[max(0,top-1):min(height,top+1),left:right+1]=ink
                canvas[max(0,bottom-1):min(height,bottom+1),left:right+1]=ink
                canvas[top:bottom+1,max(0,left-1):min(width,left+1)]=ink
                canvas[top:bottom+1,max(0,right-1):min(width,right+1)]=ink
            else:
                y=max(0,min(height-1,int(y0)));canvas[max(0,y-1):min(height,y+1),int(x0):int(x1)+1]=(.44,.47,.43)
        if not options.get('show_info',True) or margin<4:return
        from .imaging import ROOT
        font_path=ROOT/'assets/fonts/SpektraBilingualSerif-Regular.ttf'
        font=ImageFont.truetype(str(font_path),max(8,round(margin*.32)))
        fill=(218,181,121,255) if options['style'] in ('film','half_frame') else (203,211,195,255) if options['style']=='contact' else (64,67,57,255)
        for label in spec['labels']:
            text=str(label.get('text') or '')
            if not text:continue
            text_image=Image.new('RGBA',(max(1,int(label.get('width',width-2*margin))),max(1,round(margin*.55))))
            draw=ImageDraw.Draw(text_image);draw.text((0,0),text,font=font,fill=fill)
            rgba=np.asarray(text_image);alpha=rgba[...,3:4].astype(np.float32)/255
            y=min(height-len(rgba),max(0,int(label['y'])));x=max(0,min(width-rgba.shape[1],int(label['x'])))
            area=canvas[y:y+len(rgba),x:x+rgba.shape[1]]
            area[:]=area*(1-alpha)+rgba[...,:3].astype(np.float32)/255*alpha
    @Slot(object)
    def _done(self,result):
        if self.closed:return
        kind,ok,value=result
        if kind=='progress':self._progress,self._status=value;self.changed.emit();return
        if kind=='frame_template':
            self._template_in_flight=False;self._template_active=''
            if ok:
                token,preset_id,image=value
                if token==self.generation:
                    key='composition-template-'+preset_id;self.ctrl.provider.publish(key,image)
                    self._frame_templates[preset_id]=f'image://photos/{key}?v={token}'
            self.changed.emit()
            if self.style in ('film','half_frame') and self._film_rendered!=self._film_revision:self._film_timer.start()
            elif self._template_pending:self._template_timer.start()
            return
        self._busy=False;self._operation=''
        if not ok:
            self._status=value;self.message.emit(value)
            if kind=='preview':self._film_error=value
            if kind=='film_preview':self._film_timer.stop();self._film_error=value
        elif kind=='preview':
            token,images=value
            if token==self.generation:
                for index,image,prepared,metadata in images:
                    key=f'composition-{index}'
                    if not image.isNull():self.ctrl.provider.publish(key,image)
                    self.rows[index]['source']=f'image://photos/{key}?v={token}' if not image.isNull() else ''
                    self.rows[index]['_prepared']=prepared
                    self.rows[index]['metadata']=metadata
                self._status='预览已停止' if self._cancel.is_set() else ''
                if self._templates_requested:self._template_pending=[preset for preset in self._frame_preset_rows() if preset['enabled']]
                if not self._cancel.is_set():self._film_timer.start();self._template_timer.start()
        elif kind=='film_preview':
            token,revision,image,geometry=value
            if token==self.generation and revision==self._film_revision and self.style in ('film','half_frame'):
                self.ctrl.provider.publish('composition-native',image)
                self._film_url=f'image://photos/composition-native?v={token}-{revision}'
                self._film_geometry=geometry;self._film_rendered=revision;self._status=''
            elif self.style in ('film','half_frame') and not self._cancel.is_set():self._film_timer.start()
        elif kind=='export':
            self._status='已导出 '+Path(value[0]).name;self._progress=1.;self.message.emit(self._status)
            if self.style in ('film','half_frame') and self._film_rendered!=self._film_revision:self._film_timer.start()
        if not self._busy and self._template_pending:self._template_timer.start()
        self.changed.emit()
    def close(self):
        self.closed=True;self._film_timer.stop();self._template_timer.stop();self._cancel.set();self.pool.waitForDone()
