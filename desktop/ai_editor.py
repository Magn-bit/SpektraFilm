"""Explicit external photo analysis, style recommendations and image trials."""
from __future__ import annotations

import json
import re
import uuid

from PySide6.QtCore import QObject, Property, QBuffer, QIODevice, QRunnable, QThreadPool, QTimer, QUrl, Signal, Slot, Qt
from PySide6.QtGui import QColorSpace, QImage
from PIL.ImageQt import ImageQt
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest

from .ai_contract import RESPONSE_SCHEMA, context, parse_suggestion
from .ai_prompts import PROMPT_VERSION, SYSTEM_PROMPT, IMAGE_EDIT_PROMPT, request_text
from .ai_providers import ProviderStore, endpoint_url

MAX_REPLY = 1536 * 1024
MAX_PREVIEW = 3 * 1024 * 1024
AI_PREVIEW_EDGE = 1280


class _PreviewSignals(QObject):
    ready=Signal(int,object)


class _PreviewTask(QRunnable):
    def __init__(self,ctrl,identity,sequence,signals):
        super().__init__();self.ctrl=ctrl;self.identity=identity;self.sequence=sequence;self.signals=signals
    def run(self):
        try:
            path,_,settings=self.identity
            _,image,_,_=self.ctrl._render_photo(path,settings,AI_PREVIEW_EDGE,color_config=None)
            image=image.convert('RGB')
            qimage=QImage(ImageQt(image)).copy()
            qimage.setColorSpace(QColorSpace(QColorSpace.NamedColorSpace.SRgb))
            buffer=QBuffer();buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            if not qimage.save(buffer,'JPEG',90):raise ValueError('照片预览编码失败。')
            data=bytes(buffer.data());buffer.close()
            if len(data)>MAX_PREVIEW:raise ValueError('照片预览超过安全上限。')
            self.signals.ready.emit(self.sequence,dict(data=data,width=qimage.width(),height=qimage.height()))
        except Exception:
            self.signals.ready.emit(self.sequence,dict(error='无法准备当前照片预览。'))


def _schema():
    adjustment = dict(type='object', additionalProperties=False,
        required=['parameter', 'value'], properties={
            'parameter': dict(type='string', enum=list(RESPONSE_SCHEMA['properties']['adjustments']['items']['properties']['parameter']['enum'])),
            'value': dict(anyOf=[dict(type='number'), dict(type='string'), dict(type='boolean')])})
    styles = dict(type='array', items=dict(type='object', additionalProperties=False,
        required=['id', 'name', 'reason', 'changes'], properties={
            'id':dict(type='string'), 'name':dict(type='string'), 'reason':dict(type='string'),
            'changes':dict(type='array', items=adjustment)}))
    return dict(type='object', additionalProperties=False,
        required=['summary', 'observations', 'styles'], properties={
            'summary':dict(type='string'),
            'observations':dict(type='array', items=dict(type='string')),
            'styles':styles})


def _tool():
    return dict(name='propose_photo_edit', description='Return evidence-based photo observations and reviewable editor parameter proposals.', input_schema=_schema())


def _payload(provider, system, user, image_url):
    model = provider.model
    if provider.protocol == 'responses':
        return endpoint_url(provider.address, provider.protocol), {
            'model':model, 'store':False,
            'instructions':system,
            'input':[{'role':'user','content':[
                {'type':'input_text','text':user},
                {'type':'input_image','image_url':image_url,'detail':'high'}]}],
            'tools':[dict(type='function',name=_tool()['name'],description=_tool()['description'],parameters=_schema(),strict=True)],
            'tool_choice':{'type':'function','name':'propose_photo_edit'}}
    if provider.protocol == 'chat':
        function=dict(name=_tool()['name'],description=_tool()['description'],parameters=_schema(),strict=True)
        return endpoint_url(provider.address, provider.protocol), {
            'model':model,'stream':False,
            'messages':[{'role':'system','content':system},
                {'role':'user','content':[{'type':'text','text':user},
                    {'type':'image_url','image_url':{'url':image_url,'detail':'high'}}]}],
            'tools':[{'type':'function','function':function}],
            'tool_choice':{'type':'function','function':{'name':'propose_photo_edit'}}}
    if provider.protocol == 'anthropic':
        return endpoint_url(provider.address, provider.protocol), {
            'model':model,'max_tokens':6000,'stream':False,'system':system,
            'messages':[{'role':'user','content':[
                {'type':'text','text':user},
                {'type':'image','source':{'type':'base64','media_type':'image/jpeg','data':image_url.split(',',1)[1]}}]}],
            'tools':[_tool()],'tool_choice':{'type':'tool','name':'propose_photo_edit'}}
    raise ValueError('不支持的 AI 协议。')


def _response_arguments(protocol, raw):
    if protocol == 'responses':
        for item in raw.get('output',[]):
            if item.get('type') == 'function_call' and item.get('name') == 'propose_photo_edit':
                return item.get('arguments')
    elif protocol == 'chat':
        calls = raw.get('choices',[{}])[0].get('message',{}).get('tool_calls',[])
        for call in calls:
            function = call.get('function',{})
            if function.get('name') == 'propose_photo_edit': return function.get('arguments')
    elif protocol == 'anthropic':
        for item in raw.get('content',[]):
            if item.get('type') == 'tool_use' and item.get('name') == 'propose_photo_edit':
                return item.get('input')
    raise ValueError('模型没有返回照片调整方案，请检查模型是否支持图像输入和工具调用。')


class AiEditor(QObject):
    changed = Signal()
    error = Signal(str)
    notice = Signal(str)

    def __init__(self, controller, preview_provider, parent=None, *, directory=None):
        super().__init__(parent or controller)
        self.ctrl, self.preview_provider = controller, preview_provider
        root = directory or controller._store.parent
        self._store = ProviderStore(f'{root}/ai-providers.json')
        self._manager = QNetworkAccessManager(self)
        self._preview_pool=QThreadPool(self);self._preview_pool.setMaxThreadCount(1)
        self._preview_signals=_PreviewSignals(self)
        self._preview_signals.ready.connect(self._preview_ready,Qt.QueuedConnection)
        self._preview_pending=False
        self._pending_intent=''
        self._pending_provider=None
        self._reply = None
        self._deadline = QTimer(self); self._deadline.setSingleShot(True); self._deadline.setInterval(120000)
        self._deadline.timeout.connect(self._timeout)
        self._state = 'idle'
        self._message = ''
        self._summary = ''
        self._observations = []
        self._styles = []
        self._internal = {}
        self._selected_style = ''
        self._phase = ''
        self._request_identity = None
        self._request_image = QImage()
        self._request_sequence = 0
        self._applying = False
        self._visual_image = QImage()
        self._visual_url = ''
        self._configured = {}
        self.ctrl.stateChanged.connect(self._check_identity)
        self.ctrl.photosChanged.connect(self._check_identity)

    @Property(str, notify=changed)
    def state(self): return self._state
    @Property(str, notify=changed)
    def message(self): return self._message
    @Property(str, notify=changed)
    def summary(self): return self._summary
    @Property('QVariantList', notify=changed)
    def observations(self): return list(self._observations)
    @Property('QVariantList', notify=changed)
    def styles(self): return list(self._styles)
    @Property(str, notify=changed)
    def selectedStyle(self): return self._selected_style
    @Property(str, notify=changed)
    def visualUrl(self): return self._visual_url
    @Property('QVariantList', notify=changed)
    def providers(self): return [provider.public() for provider in self._store.profiles]
    @Property('QVariantMap', notify=changed)
    def activeProvider(self):
        provider = self._store.get()
        return provider.public() if provider else {}
    @Property(bool, notify=changed)
    def busy(self): return bool(self._reply or self._preview_pending)
    @Property(bool, notify=changed)
    def hasStyle(self): return self._selected_style in self._internal

    def _identity(self):
        if self.ctrl.currentIndex < 0: return None
        return self.ctrl.currentPath, self.ctrl.currentIndex, self.ctrl.settings

    def _check_identity(self, *_):
        if self._applying:return
        if self.busy and self._request_identity != self._identity():
            self.cancel()
            self._state = 'idle'; self._message = '照片或参数已变化；旧建议已取消。'
            self._summary = ''; self._observations = []; self._styles = []; self._internal = {}; self._selected_style = ''
            self._visual_image = QImage(); self._visual_url = ''
            self.changed.emit()
            return
        if self._styles and self._request_identity != self._identity():
            self.clear()

    def _invalidate(self):
        self._request_sequence+=1
        self._preview_pending=False;self._pending_intent='';self._pending_provider=None
        if self._reply:
            reply,self._reply=self._reply,None
            self._deadline.stop();reply.abort();reply.deleteLater()

    def _start(self, phase, intent, selected_style=''):
        if self.busy: raise ValueError('请等待当前分析结束，或先取消。')
        provider=self._store.get()
        if provider is None: raise ValueError('请先配置 AI 服务商。')
        if not provider.secret:raise ValueError('此服务商尚未配置 API 密钥。')
        key=self._store.key(provider)
        if not key:raise ValueError('此服务商尚未配置 API 密钥。')
        del key
        identity=self._identity()
        if self.ctrl.currentIndex<0 or not self.ctrl.frame or self.ctrl.busy:
            raise ValueError('请先等待当前照片预览完成。')
        if identity is None: raise ValueError('请先导入并选择照片。')
        self._request_sequence+=1;sequence=self._request_sequence
        self._phase=phase;self._request_identity=identity;self._pending_intent=request_text(phase,intent,context(self.ctrl.settings),selected_style)
        self._pending_provider=provider;self._preview_pending=True
        self._state=phase;self._message='正在准备照片预览…';self._deadline.start(120000)
        self._preview_pool.start(_PreviewTask(self.ctrl,identity,sequence,self._preview_signals))
        self.changed.emit()

    @Slot(int,object)
    def _preview_ready(self,sequence,result):
        if sequence!=self._request_sequence or not self._preview_pending:return
        self._preview_pending=False
        if self._request_identity!=self._identity():
            self._deadline.stop();self._fail('照片或参数已变化；该分析请求已作废。');return
        if 'error' in result:
            self._deadline.stop();self._fail(result['error']);return
        try:self._send_preview(result,sequence)
        except (ValueError,OSError,TypeError,RuntimeError) as error:
            self._deadline.stop();self._fail(str(error)[:300])
        except Exception:
            self._deadline.stop();self._fail('无法准备 AI 请求，请检查服务商设置。')

    def _send_preview(self,result,sequence):
        import base64
        import json as _json
        provider=self._pending_provider
        image_url='data:image/jpeg;base64,'+base64.b64encode(result['data']).decode('ascii')
        url,payload=_payload(provider,SYSTEM_PROMPT,self._pending_intent,image_url)
        request=QNetworkRequest(QUrl(url))
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader,'application/json')
        request.setRawHeader(b'Accept',b'application/json')
        request.setRawHeader(b'Cache-Control',b'no-store')
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        request.setTransferTimeout(30000)
        request.setRawHeader(b'x-spektrafilm-prompt-version',str(PROMPT_VERSION).encode('ascii'))
        key=self._store.key(provider)
        if not key:raise ValueError('此服务商尚未配置 API 密钥。')
        if provider.protocol == 'anthropic':
            request.setRawHeader(b'x-api-key',key.encode('utf-8'))
            request.setRawHeader(b'anthropic-version',b'2023-06-01')
        else:
            request.setRawHeader(b'Authorization',('Bearer '+key).encode('utf-8'))
        if provider.protocol=='responses':request.setRawHeader(b'OpenAI-Store',b'false')
        self._configured=dict(provider=provider.protocol,model=provider.model,endpoint=endpoint_url(provider.address,provider.protocol))
        body=_json.dumps(payload,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')
        if len(body)>MAX_PREVIEW*2:raise ValueError('模型请求超过安全上限。')
        self._reply=self._manager.post(request,body)
        self._reply.downloadProgress.connect(lambda received,total,r=self._reply: r.abort() if received>MAX_REPLY else None)
        self._reply.finished.connect(lambda r=self._reply,seq=sequence:self._finished(r,seq,provider))
        self._pending_intent='';self._pending_provider=None
        self._message='正在分析照片…' if self._phase=='analyze' else '正在生成微调建议…'
        self.changed.emit()

    @Slot(str)
    def analyze(self,intent):
        try:
            self.clear();self._start('analyze',intent)
        except (ValueError,OSError) as error:self._fail(str(error))

    @Slot(str)
    def refine(self,intent):
        if not self._selected_style:
            self._fail('请先选择一种风格。');return
        try:
            self._invalidate();self._state='idle'
            selected=next((item for item in self._styles if item['id']==self._selected_style),None)
            label=selected['name']+'：'+selected['reason'] if selected else self._selected_style
            self._start('refine',intent,label)
        except (ValueError,OSError) as error:self._fail(str(error))

    @Slot(str)
    def chooseStyle(self,ident):
        if ident not in self._internal:return
        self._selected_style=ident;self.changed.emit()

    @Slot()
    def apply(self):
        patch=self._internal.get(self._selected_style)
        if not patch or self._request_identity!=self._identity():
            self._fail('照片或参数已变化，请重新分析后再应用。');return
        if self.ctrl.exporting or self.ctrl.currentIndex<0:
            self._fail('当前状态不能应用 AI 建议。');return
        try:
            before=self._request_identity[2]
            self._applying=True
            self.ctrl._replace_tools(**patch)
            if self.ctrl.settings==before:
                self._fail('建议没有实际变化。');return
            self._applying=False
            self._request_identity=self._identity()
            self._internal={}
            self._state='applied';self._message='建议已应用；可以继续微调，Ctrl+Z 可撤销。'
            self.changed.emit()
            self.notice.emit('AI 建议已应用；Ctrl+Z 可撤销。')
        except (ValueError,TypeError) as error:self._fail(str(error))
        finally:self._applying=False

    @Slot()
    def cancel(self):
        if self._reply:
            reply,self._reply=self._reply,None
            self._deadline.stop();reply.abort();reply.deleteLater()
        self._request_sequence+=1
        self._preview_pending=False;self._pending_intent='';self._pending_provider=None
        if self._state in ('analyze','refine','image'):
            self._state='idle';self._message='已取消。';self.changed.emit()

    @Slot()
    def clear(self):
        self._invalidate()
        self._state='idle';self._message='';self._summary='';self._observations=[]
        self._styles=[];self._internal={};self._selected_style=''
        self._visual_image=QImage();self._visual_url=''
        self.changed.emit()

    def _timeout(self):
        if self._reply:
            reply,self._reply=self._reply,None
            self._request_sequence+=1;reply.abort();reply.deleteLater()
        self._preview_pending=False;self._pending_intent='';self._pending_provider=None
        self._fail('AI 请求超时，请检查网络并重试。')

    def _fail(self,message):
        self._state='error';self._message=str(message)[:360];self.error.emit(self._message);self.changed.emit()

    def _finished(self,reply,sequence,provider):
        if sequence!=self._request_sequence or reply is not self._reply:return
        self._deadline.stop();self._reply=None
        try:
            if self._request_identity!=self._identity():raise ValueError('照片或参数已变化；该 AI 结果已作废。')
            data=bytes(reply.readAll())
            if len(data)>MAX_REPLY:raise ValueError('AI 服务返回内容过大。')
            if reply.attribute(QNetworkRequest.Attribute.RedirectionTargetAttribute):raise ValueError('AI 服务返回重定向，已拒绝发送授权信息。请使用正确的 HTTPS 地址。')
            status=int(reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) or 0)
            if status<200 or status>=300:
                if status in (401,403):raise ValueError('AI 服务认证失败，请检查 API 密钥和服务地址。')
                if status==429:raise ValueError('AI 服务请求过于频繁，请稍后再试。')
                if status:raise ValueError(f'AI 服务返回 HTTP {status}，请检查模型、协议和地址。')
                raise ValueError('AI 网络请求失败，请检查连接和服务商设置。')
            try:raw=json.loads(data)
            except (ValueError,UnicodeError) as error:raise ValueError('AI 服务没有返回有效 JSON。') from error
            arguments=_response_arguments(provider.protocol,raw)
            output=arguments if isinstance(arguments,dict) else json.loads(arguments)
            self._accept_output(output)
        except (ValueError,KeyError,TypeError,IndexError,json.JSONDecodeError) as error:self._fail(str(error))
        except Exception:self._fail('无法完成 AI 响应，请检查服务商配置后重试。')
        finally:reply.deleteLater()

    def close(self):
        self.cancel()
        self._deadline.stop()
        self._preview_pool.waitForDone()

    def _accept_output(self,raw):
        if not isinstance(raw,dict) or set(raw)!={'summary','observations','styles'}:
            raise ValueError('AI 结果格式与默认提示词不一致。')
        summary, observations, styles=raw['summary'],raw['observations'],raw['styles']
        observation_count=(3<=len(observations)<=5) if isinstance(observations,list) and self._phase=='analyze' else (1<=len(observations)<=3) if isinstance(observations,list) else False
        if not isinstance(summary,str) or len(summary)>480 or not observation_count or any(not isinstance(v,str) or not v.strip() or len(v)>260 for v in observations):
            raise ValueError('AI 照片分析内容无效。')
        expected=3 if self._phase=='analyze' else 1
        if not isinstance(styles,list) or len(styles)!=expected:raise ValueError('AI 推荐方案数量不正确，请重新分析。')
        current=dict(self.ctrl.settings)
        public=[];internal={};ids=set()
        for raw_style in styles:
            if not isinstance(raw_style,dict) or set(raw_style)!={'id','name','reason','changes'}:
                raise ValueError('AI 风格方案格式无效。')
            ident,name,reason=raw_style['id'],raw_style['name'],raw_style['reason']
            if (not isinstance(ident,str) or not re.fullmatch(r'[a-z0-9_-]{1,48}',ident) or ident in ids
                    or not isinstance(name,str) or not name.strip() or len(name)>48
                    or not isinstance(reason,str) or not reason.strip() or len(reason)>260):
                raise ValueError('AI 风格名称或说明无效。')
            ids.add(ident)
            obj=dict(summary=summary,adjustments=raw_style['changes'])
            _,changes,patch=parse_suggestion(json.dumps(obj,ensure_ascii=False,allow_nan=False),current)
            # Replace incompatible paper only when the selected film actually changes.
            if 'stock' in patch and 'paper' not in patch:
                allowed={item['id'] for item in context(dict(current,stock=patch['stock']))['papers']}
                if current['paper'] not in allowed:raise ValueError('建议胶片与当前相纸不兼容，请同时提出适用相纸。')
            card=dict(id=ident,name=name.strip(),reason=reason.strip(),changes=changes)
            public.append(card);internal[ident]=patch
        self._summary=summary.strip();self._observations=[v.strip() for v in observations if v.strip()]
        self._styles=public;self._internal=internal
        if self._phase=='analyze':self._selected_style=''
        elif public:self._selected_style=public[0]['id']
        self._state='recommended' if self._phase=='analyze' else 'refined'
        self._message='请选择一种风格。' if self._phase=='analyze' else '微调建议已准备好，请确认。'
        self.changed.emit()

    @Slot(str,str,str,str,str,str)
    def saveProvider(self,name,address,protocol,model,key,provider_id=''):
        try:
            provider=self._store.save(dict(id=provider_id,name=name,protocol=protocol,address=address,model=model),key)
            self._message='服务商已保存。';self._state='idle';self.changed.emit()
        except (ValueError,OSError) as error:self._fail(str(error))

    @Slot(str)
    def selectProvider(self,ident):
        try:self._store.select(ident);self._message='';self._state='idle';self.changed.emit()
        except ValueError as error:self._fail(str(error))

    @Slot(str)
    def removeProvider(self,ident):
        try:self._store.remove(ident);self._state='idle';self._message='服务商已移除。';self.changed.emit()
        except (ValueError,OSError) as error:self._fail(str(error))

    @Slot()
    def requestImageTrial(self):
        self._fail('生图试用使用独立配置；请在“设置 → AI”单独保存生图服务商。它不会改动本地照片或参数。')
