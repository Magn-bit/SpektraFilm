"""Explicit, offline CLI/MCP over a sidecar or an explicitly enabled GUI session.

No server is started by importing this module or opening the GUI. No network,
shell evaluation or model service is used. --gui connects to an already-enabled,
authenticated current-user local socket; the default sidecar remains independent.
The processing path is the application's decoder, renderer and output recipe.
"""
from __future__ import annotations

from contextlib import contextmanager,redirect_stdout
from dataclasses import asdict,fields
from pathlib import Path
import argparse
import json
import math
import os
import sys
import tempfile
import time
import uuid

ROOT=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
if (ROOT/'vendor').is_dir() and str(ROOT/'vendor') not in sys.path:sys.path.insert(0,str(ROOT/'vendor'))
SESSION_FORMAT='SpektraFilm.automation-session'
MAX_DOCUMENT_BYTES=32*1024**2
MAX_REQUEST_BYTES=8*1024**2
MAX_PHOTOS=4096
PROTOCOL_VERSIONS=('2025-11-25','2025-06-18','2025-03-26','2024-11-05')


def _json(value):
    return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'))


def _parse_json(value):
    def invalid(number):raise ValueError('JSON 不接受 NaN 或 Infinity')
    return json.loads(value,parse_constant=invalid)


def _read_json(path,limit=MAX_DOCUMENT_BYTES):
    path=Path(path)
    if path.stat().st_size>limit:raise ValueError('参数文档过大')
    return _parse_json(path.read_text(encoding='utf-8-sig'))


def _atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    content=_json(value)
    if len(content.encode('utf-8'))>MAX_DOCUMENT_BYTES:raise ValueError('会话超过 32 MiB，请拆分批次')
    descriptor,temporary=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(descriptor,'w',encoding='utf-8',newline='\n') as stream:
            stream.write(content+'\n');stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)


@contextmanager
def _locked(path):
    """Fail promptly if another explicit script is changing this sidecar."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.with_name(path.name+'.lock').open('a+b') as stream:
        stream.seek(0,2)
        if stream.tell()==0:stream.write(b'0');stream.flush()
        stream.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as error:raise ValueError('另一个脚本正在使用此会话') from error
        try:yield
        finally:
            stream.seek(0)
            if os.name=='nt':msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)


def _settings(value):
    """Reuse canonical validation, rejecting unknown/invalid simple fields."""
    from .imaging import Settings,film_settings,PARAMETER_LIMITS,GRAIN_TYPES,catalog
    from shared.darkroom import paper_choices
    if not isinstance(value,dict):raise ValueError('settings 应为 JSON 对象')
    known={field.name for field in fields(Settings)}
    unknown=set(value)-known
    if unknown:raise ValueError('未知设置字段：'+', '.join(sorted(unknown)))
    for key in PARAMETER_LIMITS:
        if key in value and not (key=='halation_scatter_amount' and value[key] is None) and (isinstance(value[key],bool) or not isinstance(value[key],(int,float)) or not math.isfinite(value[key])):
            raise ValueError('参数需要有限数值：'+key)
    if 'stock' in value and value['stock'] not in {item['id'] for item in catalog()}:
        raise ValueError('未知胶片：'+str(value['stock']))
    if 'grain_type' in value and value['grain_type'] not in GRAIN_TYPES:raise ValueError('未知颗粒类型')
    for key in ('spectral','film_enabled','lens_correction','defringe','antihalation_removed','scene_latitude_active','minilab_active',
                'scan_film','extended_dynamic_range','print_effects','grain_layered','grain_enabled','halation_enabled','hdr_enabled','digital_intermediate'):
        if key in value and not isinstance(value[key],bool):raise ValueError('参数需要布尔值：'+key)
    stock=value.get('stock',Settings.stock)
    if 'paper' in value and value['paper'] not in {'auto',*(item['id'] for item in paper_choices(stock))}:
        raise ValueError('相纸不适用于当前胶片')
    return film_settings(value)


def _source_path(value):
    from shared.photo_formats import PHOTO_EXTENSIONS
    if not isinstance(value,str) or not value.strip():raise ValueError('照片路径不能为空')
    path=Path(value).expanduser().resolve(strict=True)
    if not path.is_file() or path.suffix.lower() not in PHOTO_EXTENSIONS:raise ValueError('不支持的本地照片：'+str(path))
    return path


class AutomationSession:
    """Separate sidecar state; never edits the GUI's own hashed edit store."""
    def __init__(self,path):
        self.path=Path(path).expanduser().resolve()
        if self.path.suffix.lower()!='.json':raise ValueError('会话应使用显式 .json 文件')

    def _load(self):
        if not self.path.exists():return dict(format=SESSION_FORMAT,version=1,photos=[],clipboard=None)
        state=_read_json(self.path)
        if not isinstance(state,dict) or state.get('format')!=SESSION_FORMAT or state.get('version')!=1:
            raise ValueError('现有文件不是 SpektraFilm 自动化会话，拒绝覆盖')
        if not isinstance(state.get('photos'),list) or len(state['photos'])>MAX_PHOTOS:raise ValueError('会话照片列表无效')
        return state

    def call(self,method,arguments=None):
        arguments={} if arguments is None else arguments
        if not isinstance(arguments,dict):raise ValueError('arguments 应为 JSON 对象')
        allowed={'status','catalog','open','get','set','copy','paste','undo','redo','export','import_clip','export_clip'}
        if method not in allowed:raise ValueError('未知操作：'+str(method))
        with _locked(self.path):
            state=self._load();result,changed=getattr(self,'_'+method)(state,**arguments)
            if changed:_atomic_json(self.path,state)
        return result

    def _status(self,state):
        return dict(session=str(self.path),scope='independent-sidecar',offline=True,network=False,
                    photos=[self._summary(photo) for photo in state['photos']],
                    clipboard=None if not state.get('clipboard') else {key:state['clipboard'][key] for key in ('source_name','categories')},
                    methods=['status','catalog','open','get','set','copy','paste','undo','redo','export','import_clip','export_clip']),False

    @staticmethod
    def _summary(photo):
        return {key:photo[key] for key in ('id','path','width','height')}

    def _catalog(self,state,stock=None):
        from .imaging import catalog,PARAMETER_LIMITS
        from shared.darkroom import paper_choices
        from shared.output_recipes import DEFAULT_RECIPES
        from shared.settings_sync import CATEGORIES,CATEGORY_TITLES,DEFAULT_CATEGORIES
        result=dict(stocks=catalog(),recipes=[asdict(recipe) for recipe in DEFAULT_RECIPES],
            categories=[dict(id=key,name=CATEGORY_TITLES[key],fields=list(value),default=key in DEFAULT_CATEGORIES) for key,value in CATEGORIES.items()],
            numeric_limits={key:list(value) for key,value in PARAMETER_LIMITS.items()})
        if stock is not None:
            if stock not in {item['id'] for item in catalog()}:raise ValueError('未知胶片')
            result['papers']=paper_choices(stock)
        return result,False

    def _open(self,state,paths):
        from .imaging import Settings,photo_dimensions
        if not isinstance(paths,list) or not paths:raise ValueError('paths 应为非空本地照片路径列表')
        if len(paths)+len(state['photos'])>MAX_PHOTOS:raise ValueError('每个自动化会话最多 4096 张照片')
        candidates=[_source_path(value) for value in paths]
        if self.path in candidates:raise ValueError('照片路径不能是会话文件')
        existing={os.path.normcase(photo['path']):photo for photo in state['photos']};added=[];result=[]
        for path in candidates:
            key=os.path.normcase(str(path))
            if key not in existing:
                width,height=photo_dimensions(str(path))
                photo=dict(id=uuid.uuid4().hex,path=str(path),width=int(width),height=int(height),settings=asdict(Settings()),undo=[],redo=[])
                added.append(photo);existing[key]=photo
            result.append(self._summary(existing[key]))
        state['photos'].extend(added)
        return dict(photos=result,added=len(added)),bool(added)

    @staticmethod
    def _photo(state,photo):
        if not isinstance(photo,str):raise ValueError('photo 应为照片 id 或绝对路径')
        for candidate in state['photos']:
            if candidate['id']==photo or os.path.normcase(candidate['path'])==os.path.normcase(photo):return candidate
        raise ValueError('照片不在此自动化会话中：'+photo)

    @classmethod
    def _photos(cls,state,photos=None):
        if photos is None:return state['photos']
        if not isinstance(photos,list) or not photos:raise ValueError('photos 应为非空照片 id 列表')
        selected=[]
        for ident in photos:
            photo=cls._photo(state,ident)
            if photo not in selected:selected.append(photo)
        return selected

    @staticmethod
    def _replace(photo,settings):
        settings=asdict(settings)
        if photo['settings']==settings:return False
        photo.setdefault('undo',[]).append(photo['settings']);photo['undo']=photo['undo'][-32:]
        photo['redo']=[];photo['settings']=settings;return True

    def _get(self,state,photo):
        selected=self._photo(state,photo)
        return dict(self._summary(selected),settings=asdict(_settings(selected['settings'])),can_undo=bool(selected.get('undo')),can_redo=bool(selected.get('redo'))),False

    def _set(self,state,photo,settings):
        selected=self._photo(state,photo)
        if not isinstance(settings,dict):raise ValueError('settings 应为 JSON 对象')
        values=dict(selected['settings']);values.update(settings)
        # A film change keeps current adjustments but incompatible paper must
        # return to auto, exactly as the GUI's category synchronization does.
        if 'stock' in settings and 'paper' not in settings:
            from .imaging import catalog
            from shared.darkroom import paper_choices
            if values['stock'] not in {item['id'] for item in catalog()}:raise ValueError('未知胶片')
            if values.get('paper') not in {'auto',*(item['id'] for item in paper_choices(values['stock']))}:values['paper']='auto'
        updated=_settings(values);changed=self._replace(selected,updated)
        return dict(photo=selected['id'],settings=asdict(updated),changed=changed),changed

    def _copy(self,state,photo,categories=None):
        from shared.settings_sync import make_clip,DEFAULT_CATEGORIES
        selected=self._photo(state,photo)
        state['clipboard']=make_clip(_settings(selected['settings']),DEFAULT_CATEGORIES if categories is None else categories,Path(selected['path']).name)
        return state['clipboard'],True

    def _paste(self,state,photos=None,categories=None):
        from shared.settings_sync import apply_clip
        if not state.get('clipboard'):raise ValueError('此会话的参数剪贴板为空')
        targets=self._photos(state,photos);updates=[]
        for photo in targets:
            values=apply_clip(photo['settings'],state['clipboard'],categories)
            from shared.darkroom import paper_choices
            if values.get('paper') not in {'auto',*(item['id'] for item in paper_choices(values['stock']))}:values['paper']='auto'
            updates.append((photo,_settings(values)))
        changed=[photo['id'] for photo,settings in updates if self._replace(photo,settings)]
        return dict(changed=changed,count=len(changed)),bool(changed)

    def _undo(self,state,photo):return self._history(state,photo,'undo','redo')
    def _redo(self,state,photo):return self._history(state,photo,'redo','undo')
    def _history(self,state,photo,source,target):
        selected=self._photo(state,photo);history=selected.setdefault(source,[])
        if not history:return dict(photo=selected['id'],changed=False),False
        selected.setdefault(target,[]).append(selected['settings']);selected[target]=selected[target][-32:]
        selected['settings']=asdict(_settings(history.pop()))
        return dict(photo=selected['id'],changed=True,settings=selected['settings']),True

    def _import_clip(self,state,path):
        from shared.settings_sync import normalize_clip
        clip=normalize_clip(_read_json(path,MAX_REQUEST_BYTES))
        # Canonical type normalization before any later paste.
        normalized=asdict(_settings(clip['settings']))
        clip['settings']={key:normalized[key] for key in clip['settings']}
        state['clipboard']=clip
        return dict(source_name=clip['source_name'],categories=clip['categories']),True

    def _export_clip(self,state,path):
        if not state.get('clipboard'):raise ValueError('此会话的参数剪贴板为空')
        target=Path(path).expanduser().resolve()
        if target==self.path or target in (Path(photo['path']) for photo in state['photos']):raise ValueError('剪贴板不能覆盖会话或原片')
        if target.exists():raise ValueError('剪贴板目标已存在；请选择新文件名')
        _atomic_json(target,state['clipboard']);return dict(path=str(target)),False

    def _export(self,state,photos=None,recipe=None,destination=None):
        from .batch import plan_recipe_exports
        from .output import export_recipe
        from shared.output_recipes import DEFAULT_RECIPES,normalize_recipe
        selected=self._photos(state,photos)
        if not selected:raise ValueError('会话中没有照片')
        if isinstance(recipe,str):
            matches=[item for item in DEFAULT_RECIPES if item.id==recipe]
            if not matches:raise ValueError('未知配方：'+recipe)
            recipe=matches[0]
        recipe=DEFAULT_RECIPES[0] if recipe is None else normalize_recipe(recipe)
        root=Path(destination).expanduser().resolve() if destination is not None else None
        prepared=[dict(path=photo['path'],settings=_settings(photo['settings'])) for photo in selected]
        for photo in prepared:_source_path(photo['path'])
        plans=plan_recipe_exports(prepared,range(len(prepared)),recipe,root)
        originals={Path(photo['path']).resolve() for photo in state['photos']}
        outputs=[];started=time.perf_counter()
        for source,target,settings in plans:
            if Path(target).resolve() in originals or Path(target).resolve()==self.path:raise ValueError('导出不能覆盖原片或会话')
            size=export_recipe(source,target,settings,recipe)
            if recipe.format=='raw':
                from .imaging import photo_dimensions
                size=photo_dimensions(source)
            outputs.append(dict(source=source,path=target,width=int(size[0]),height=int(size[1])))
        return dict(outputs=outputs,count=len(outputs),elapsed_ms=round((time.perf_counter()-started)*1000),
                    source_resolution=recipe.long_edge==0,recipe=asdict(recipe)),False


def _schema(properties=None,required=()):
    return dict(type='object',properties=properties or {},required=list(required),additionalProperties=False)
STRING=dict(type='string')
PHOTOS=dict(type='array',items=STRING,minItems=1)
from shared.settings_sync import CATEGORIES as SETTINGS_CATEGORIES
CATEGORIES=dict(type='array',items=dict(type='string',enum=list(SETTINGS_CATEGORIES)))
TOOL_SCHEMAS={
    'status':('Read this independent offline session.',_schema()),
    'catalog':('List film/paper materials, recipes and category fields.',_schema({'stock':STRING})),
    'open':('Add local photo paths non-destructively; no decode or edit to originals.',_schema({'paths':PHOTOS},['paths'])),
    'get':('Read canonical settings for one photo id or absolute path.',_schema({'photo':STRING},['photo'])),
    'set':('Update canonical application settings; the original photo is unchanged.',_schema({'photo':STRING,'settings':dict(type='object')},['photo','settings'])),
    'copy':('Copy selected setting categories into this sidecar clipboard.',_schema({'photo':STRING,'categories':CATEGORIES},['photo'])),
    'paste':('Paste captured categories to specified photos (all if omitted); each is undoable.',_schema({'photos':PHOTOS,'categories':CATEGORIES})),
    'undo':('Undo the latest sidecar edit for one photo.',_schema({'photo':STRING},['photo'])),
    'redo':('Redo the latest undone sidecar edit for one photo.',_schema({'photo':STRING},['photo'])),
    'export':('Render sequentially using the application source decoder and output recipe. Default keeps source resolution.',_schema({'photos':PHOTOS,'recipe':dict(oneOf=[STRING,dict(type='object')]),'destination':STRING})),
    'import_clip':('Import a portable category clipboard JSON file.',_schema({'path':STRING},['path'])),
    'export_clip':('Write the portable category clipboard to a new JSON file.',_schema({'path':STRING},['path'])),
}


def _tool_content(value):
    """MCP images are actual content blocks, never JSON pretending to be media."""
    media = value.get('image') if isinstance(value,dict) else None
    if isinstance(media,dict) and media.get('mimeType') in ('image/jpeg','image/png') and isinstance(media.get('data'),str):
        metadata = {key:item for key,item in value.items() if key != 'image'}
        return [dict(type='text',text=_json(metadata)),dict(type='image',mimeType=media['mimeType'],data=media['data'])]
    return [dict(type='text',text=_json(value))]


def serve_stdio(session,input_stream=None,output_stream=None):
    """MCP newline-delimited JSON-RPC; transport is process pipes only."""
    input_stream=input_stream or sys.stdin.buffer;output_stream=output_stream or sys.stdout
    initialized=False
    schemas=getattr(session,'tool_schemas',TOOL_SCHEMAS)
    live_gui=getattr(session,'scope','')=='live-gui-session'
    for line in iter(lambda:input_stream.readline(MAX_REQUEST_BYTES+1),b''):
        if not line.strip():continue
        ident=None
        try:
            if len(line)>MAX_REQUEST_BYTES:raise ValueError('MCP request exceeds 8 MiB')
            request=_parse_json(line)
            if not isinstance(request,dict) or request.get('jsonrpc')!='2.0':raise ValueError('Expected JSON-RPC 2.0 object')
            ident=request.get('id');method=request.get('method');params=request.get('params',{})
            if not isinstance(params,dict):raise ValueError('params must be an object')
            if method=='initialize':
                version=params.get('protocolVersion');version=version if version in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
                result=dict(protocolVersion=version,capabilities=dict(tools=dict(listChanged=False)),
                    serverInfo=dict(name='SpektraFilm Local',version='1.0.0'),
                    instructions=('Offline, live GUI session through the explicitly enabled local interface. Open/export return job IDs; use spektra_job to read progress. Source images are not changed. Explicit export recipes control output sizing.'
                        if live_gui else 'Offline, independent JSON sidecar session; never the live GUI session. Source images are not changed. Explicit export recipes control output sizing.'))
                initialized=True
            elif method in ('notifications/initialized','notifications/cancelled'):
                continue
            elif method=='ping':result={}
            elif not initialized:raise ValueError('initialize must be called first')
            elif method=='tools/list':
                result=dict(tools=[dict(name='spektra_'+key,description=description,inputSchema=schema,
                    annotations=dict(readOnlyHint=key in ('status','catalog','get','job','describe','preview_image','latitude'),destructiveHint=False,openWorldHint=False))
                    for key,(description,schema) in schemas.items()])
            elif method=='tools/call':
                name=params.get('name','')
                try:
                    if not isinstance(name,str) or not name.startswith('spektra_') or name[8:] not in schemas:raise ValueError('Unknown tool')
                    # Engine diagnostics must not corrupt the stdio transport.
                    with redirect_stdout(sys.stderr):value=session.call(name[8:],params.get('arguments',{}))
                    result=dict(content=_tool_content(value),isError=False)
                except Exception as error:result=dict(content=[dict(type='text',text=str(error))],isError=True)
            else:
                if ident is not None:
                    output_stream.write(_json(dict(jsonrpc='2.0',id=ident,error=dict(code=-32601,message='Method not found')))+'\n');output_stream.flush()
                continue
            if ident is None:continue
            response=dict(jsonrpc='2.0',id=ident,result=result)
        except Exception as error:response=dict(jsonrpc='2.0',id=ident,error=dict(code=-32600,message=str(error)))
        output_stream.write(_json(response)+'\n');output_stream.flush()


def main(argv=None):
    # Console pipes and MCP JSON are UTF-8 even under a legacy Windows code page.
    for stream in (sys.stdin,sys.stdout,sys.stderr):
        if stream is not None and hasattr(stream,'reconfigure'):
            stream.reconfigure(encoding='utf-8',errors='replace')
    parser=argparse.ArgumentParser(description='SpektraFilm offline automation: explicit independent sidecar or explicitly enabled live GUI session.')
    scope=parser.add_mutually_exclusive_group(required=True)
    scope.add_argument('--session',help='Explicit independent automation sidecar .json path')
    scope.add_argument('--gui',action='store_true',help='Connect to the live GUI window; enable its local interface in settings first')
    parser.add_argument('--gui-session',help='Choose a GUI session ID when multiple windows are enabled')
    parser.add_argument('--gui-directory',help='Explicit local endpoint directory (portable/custom data store)')
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('status');catalog=commands.add_parser('catalog');catalog.add_argument('--stock')
    opened=commands.add_parser('open');opened.add_argument('paths',nargs='+')
    for method in ('get','undo','redo'):
        action=commands.add_parser(method);action.add_argument('photo')
    update=commands.add_parser('set');update.add_argument('photo');update.add_argument('--settings',required=True,help='JSON object or @path.json')
    copy=commands.add_parser('copy');copy.add_argument('photo');copy.add_argument('--categories',nargs='+')
    paste=commands.add_parser('paste');paste.add_argument('--photos',nargs='+');paste.add_argument('--categories',nargs='+')
    export=commands.add_parser('export');export.add_argument('--photos',nargs='+');export.add_argument('--recipe',default='jpg-high',help='Built-in recipe id or @recipe.json');export.add_argument('--destination')
    for method in ('job','cancel-export'):
        action=commands.add_parser(method);action.add_argument('job')
    for method in ('describe','latitude','place'):
        action=commands.add_parser(method);action.add_argument('photo',nargs='?',default='current')
    preview=commands.add_parser('preview-image');preview.add_argument('photo',nargs='?',default='current');preview.add_argument('--long-edge',type=int,default=1280)
    meter=commands.add_parser('auto-meter');meter.add_argument('photo',nargs='?',default='current')
    meter.add_argument('--target',choices=('exposure','filter_pack','both'),default='both')
    meter.add_argument('--method',choices=('balanced','center','protect_highlights','protect_shadows'),default='balanced')
    for method in ('import-clip','export-clip'):
        action=commands.add_parser(method);action.add_argument('path')
    server=commands.add_parser('mcp');server.add_argument('--enable-local',action='store_true',help='Explicitly start this local stdio session; no listener or background service')
    args=parser.parse_args(argv)
    if (args.gui_session or args.gui_directory) and not args.gui:parser.error('--gui-session and --gui-directory require --gui')
    if args.command in ('job','cancel-export','describe','preview-image','auto-meter','latitude','place') and not args.gui:
        parser.error(args.command+' is available with --gui only')
    if args.command=='mcp' and not args.enable_local:parser.error('MCP is disabled by default; use mcp --enable-local to start explicitly')
    try:
        if args.gui:
            from .gui_automation import GuiAutomationClient
            session=GuiAutomationClient(directory=args.gui_directory,session=args.gui_session)
        else:session=AutomationSession(args.session)
        if args.command=='mcp':serve_stdio(session);return 0
        values=vars(args);method=values.pop('command').replace('-','_')
        for key in ('session','gui','gui_session','gui_directory'):values.pop(key,None)
        for key in ('settings','recipe'):
            if key in values and isinstance(values[key],str):
                if values[key].startswith('@'):values[key]=_read_json(values[key][1:],MAX_REQUEST_BYTES)
                elif key=='settings':values[key]=_parse_json(values[key])
        values={key:value for key,value in values.items() if value is not None}
        with redirect_stdout(sys.stderr):result=session.call(method,values)
        print(_json(dict(ok=True,result=result)),flush=True);return 0
    except KeyboardInterrupt:
        print(_json(dict(ok=False,error='Cancelled')),flush=True);return 130
    except Exception as error:
        print(_json(dict(ok=False,error=str(error))),flush=True);return 1


if __name__=='__main__':raise SystemExit(main())
