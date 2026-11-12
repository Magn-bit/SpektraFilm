from __future__ import annotations

from dataclasses import asdict
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import zipfile
from copy import deepcopy

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from desktop.ai_contract import parse_suggestion
from desktop.ai_editor import AiEditor, _payload
from desktop.ai_providers import Provider, ProviderStore, endpoint_url
from desktop.imaging import Settings
import publish_local_release


def test_provider_endpoints_require_tls_except_loopback():
    assert endpoint_url('https://api.openai.com/v1', 'responses') == 'https://api.openai.com/v1/responses'
    assert endpoint_url('https://api.anthropic.com/v1/messages', 'anthropic') == 'https://api.anthropic.com/v1/messages'
    assert endpoint_url('http://localhost:1234/v1', 'chat') == 'http://localhost:1234/v1/chat/completions'
    with pytest.raises(ValueError): endpoint_url('http://192.168.1.5/v1', 'chat')
    with pytest.raises(ValueError): endpoint_url('https://example.com/v1/messages', 'responses')


def test_protocol_adapters_attach_image_and_strict_proposal_tool():
    image='data:image/jpeg;base64,AA=='
    for protocol in ('responses', 'chat', 'anthropic'):
        provider=Provider('id','model',protocol,'https://example.com/v1','vision-model')
        url,body=_payload(provider,'system','intent',image)
        assert url.startswith('https://example.com/')
        assert body['model']=='vision-model'
        assert body['tool_choice']
        expected='data:image/jpeg;base64,AA==' if protocol!='anthropic' else 'AA=='
        assert expected in json.dumps(body)
        assert 'additionalProperties' in json.dumps(body)


def test_suggestion_uses_absolute_allowlisted_values_and_rejects_bad_ranges():
    current=asdict(Settings())
    summary,changes,patch=parse_suggestion(json.dumps({'summary':'自然调整','adjustments':[
        {'parameter':'exposure','value':-0.35},
        {'parameter':'hsl.orange.hue','value':-4.25}]}),current)
    assert summary=='自然调整'
    assert [item['parameter'] for item in changes]==['exposure','hsl.orange.hue']
    assert patch['exposure']==-0.35
    assert patch['hsl'].orange.hue==-4.25
    for value in (True, 8.01, float('inf')):
        with pytest.raises(ValueError):
            parse_suggestion(json.dumps({'summary':'x','adjustments':[{'parameter':'exposure','value':value}]}),current)
    with pytest.raises(ValueError):
        parse_suggestion('{"summary":"x","summary":"y","adjustments":[]}',current)
    with pytest.raises(ValueError):
        parse_suggestion(json.dumps({'summary':'x','adjustments':[{'parameter':'geometry','value':{}}]}),current)


from PySide6.QtCore import QObject,Signal


class _Controller(QObject):
    stateChanged=Signal()
    photosChanged=Signal()
    def __init__(self):
        super().__init__()
        self._store=Path('C:/test')/'edits'
        self.provider=type('Images',(),{'lock':threading.RLock(),'images':{}})()
        self.currentIndex=0;self.currentPath='current-photo';self._settings=asdict(Settings())
        self.frame='frame';self.busy=False;self.exporting=False;self.history=[]
    def _render_photo(self,path,settings,edge,color_config=None):
        from PIL import Image
        return None,Image.new('RGB',(64,48),(90,120,150)),None,None
    @property
    def settings(self):
        return deepcopy(self._settings)
    def _replace_tools(self,**patch):
        self.history.append(dict(self.settings))
        self._settings.update(patch)
        self.stateChanged.emit()


def _recommendations():
    return {'summary':'晚霞与水面反光是照片的主要色彩。','observations':[
        '天空有粉橙与蓝灰相接的霞光层次。','水面保留天空的暖色倒影。','前景树木形成清晰的低调剪影。'],
        'styles':[
            {'id':'natural','name':'保留霞光','reason':'保留天空渐层与水面倒影，只平衡亮部。','changes':[{'parameter':'highlights','value':-8}]},
            {'id':'print','name':'温润相纸','reason':'柔和高光，保留画面整体的暖色氛围。','changes':[{'parameter':'contrast','value':-4}]},
            {'id':'deep','name':'深调晚霞','reason':'保持剪影深度，让水面纹理更清楚。','changes':[{'parameter':'shadows','value':8}]}]}


def test_analysis_requires_user_style_selection_before_changes(tmp_path):
    from PySide6.QtCore import QCoreApplication
    app=QCoreApplication.instance() or QCoreApplication([])
    ctrl=_Controller()
    editor=AiEditor(ctrl,object(),directory=tmp_path)
    editor._phase='analyze';editor._request_identity=editor._identity()
    editor._accept_output(_recommendations())
    assert editor.state=='recommended'
    assert len(editor.styles)==3
    assert editor.selectedStyle==''
    assert ctrl.settings['highlights']==0
    editor.chooseStyle('natural')
    editor.apply()
    assert ctrl.settings['highlights']==-8
    assert len(ctrl.history)==1
    assert editor.state=='applied'
    assert editor.selectedStyle=='natural'
    assert len(editor.styles)==3
    editor.close()


def test_draft_is_invalidated_after_manual_edit(tmp_path):
    from PySide6.QtCore import QCoreApplication
    app=QCoreApplication.instance() or QCoreApplication([])
    ctrl=_Controller();editor=AiEditor(ctrl,object(),directory=tmp_path)
    editor._phase='analyze';editor._request_identity=editor._identity()
    editor._accept_output(_recommendations())
    ctrl._settings['exposure']=-1
    ctrl.stateChanged.emit()
    assert editor.styles==[]
    assert editor.selectedStyle==''
    editor.close()


def test_analysis_sends_only_preview_and_controls_to_configured_local_service(tmp_path,monkeypatch):
    from PySide6.QtCore import QCoreApplication,QEventLoop,QTimer
    import desktop.ai_providers as providers
    received={}
    proposal=_recommendations()
    response={'output':[{'type':'function_call','name':'propose_photo_edit',
        'arguments':json.dumps(proposal,ensure_ascii=False)}]}
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received['path']=self.path
            received['headers']=dict(self.headers)
            received['body']=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            payload=json.dumps(response,ensure_ascii=False).encode('utf-8')
            self.send_response(200);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
        def log_message(self,*_args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    def protect(value,*,decrypt=False):
        return value.removeprefix(b'protected:') if decrypt else b'protected:'+value
    monkeypatch.setattr(providers,'_dpapi',protect)
    app=QCoreApplication.instance() or QCoreApplication([])
    ctrl=_Controller();editor=AiEditor(ctrl,object(),directory=tmp_path)
    try:
        editor._store.save(dict(id='',name='Local',protocol='responses',
            address=f'http://127.0.0.1:{server.server_port}/v1',model='vision'),'test-only-key')
        editor.analyze('保留朝霞的自然渐层，不要提亮剪影。')
        loop=QEventLoop();poll=QTimer();poll.setInterval(10)
        poll.timeout.connect(lambda:loop.quit() if editor.state in ('recommended','error') else None)
        timeout=QTimer();timeout.setSingleShot(True);timeout.timeout.connect(loop.quit)
        poll.start();timeout.start(15000);loop.exec();poll.stop();timeout.stop()
        assert editor.state=='recommended',editor.message
        assert received['path']=='/v1/responses'
        assert received['headers']['Authorization']=='Bearer test-only-key'
        body=received['body']
        assert body['store'] is False
        encoded=json.dumps(body,ensure_ascii=False)
        assert 'data:image/jpeg;base64,' in encoded
        assert 'current-photo' not in encoded and 'D:/Download' not in encoded
        assert 'exposure' in encoded and '保留朝霞的自然渐层' in encoded
        assert ctrl.settings['highlights']==0
        assert editor.selectedStyle==''
    finally:
        editor.close();server.shutdown();server.server_close();thread.join(timeout=2)


def test_public_source_archive_refuses_embedded_provider_keys(tmp_path):
    fake_key='sk-'+'A'*48
    safe=tmp_path/'safe.py';safe.write_text("TOKEN_PREFIX = 'sk-' + 'A' * 48\n",encoding='utf-8')
    publish_local_release.reject_embedded_credentials([safe])
    unsafe=tmp_path/'unsafe.txt';unsafe.write_text('credential='+fake_key,encoding='utf-8')
    with pytest.raises(ValueError,match='API credential'):
        publish_local_release.reject_embedded_credentials([unsafe])


def test_public_release_audit_scans_binaries_and_archive_contents(tmp_path):
    fake_key=('sk-'+'B'*48).encode('ascii')
    binary=tmp_path/'SpektraFilm.exe';binary.write_bytes(b'MZ\x00'+fake_key+b'\x00')
    with pytest.raises(ValueError,match='API credential'):
        publish_local_release.audit_public_artifacts([binary])
    package=tmp_path/'release.apk'
    with zipfile.ZipFile(package,'w') as archive:
        archive.writestr('classes.dex',b'dex\n035\x00'+fake_key)
    with pytest.raises(ValueError,match='API credential'):
        publish_local_release.audit_public_artifacts([package])


def test_provider_store_keeps_secret_ciphertext_only(tmp_path,monkeypatch):
    import desktop.ai_providers as providers
    monkeypatch.setattr(providers,'_dpapi',lambda value,**kwargs:b'protected:'+value)
    store=ProviderStore(tmp_path/'providers.json')
    provider=store.save(dict(id='',name='Local',protocol='responses',address='http://localhost:9000/v1',model='vision'),
                        'local-test-secret')
    saved=(tmp_path/'providers.json').read_text(encoding='utf-8')
    assert provider.secret
    assert 'local-test-secret' not in saved
    encoded=__import__('base64').b64encode(b'protected:local-test-secret').decode('ascii')
    assert encoded in saved
    assert store.get().public()['hasKey'] is True
