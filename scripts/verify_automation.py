"""One offline automation milestone: real CLI/stdio MCP, sidecars and PNG16."""
from pathlib import Path
import json,subprocess,sys,tempfile,time
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
from PIL import Image
import numpy as np
import tifffile
from desktop.automation import AutomationSession
from desktop import native_spectral
from shared.geometry import Geometry
from shared.settings_sync import make_clip,apply_clip
from desktop.imaging import Settings
from dataclasses import asdict,replace

OUT=ROOT/'output/automation';OUT.mkdir(parents=True,exist_ok=True)
report={};started=time.perf_counter()
with tempfile.TemporaryDirectory(prefix='spektrafilm-automation-') as folder:
    folder=Path(folder);source=folder/'原片1.tif';second=folder/'原片2.tif';session=folder/'session.json'
    values=np.linspace(.04,.85,64*48*3,dtype=np.float32).reshape(48,64,3)
    samples=np.rint(values*65535).astype(np.uint16)
    tifffile.imwrite(source,samples,photometric='rgb');tifffile.imwrite(second,samples[::-1],photometric='rgb')
    before=source.read_bytes()
    cli=[sys.executable,'-X','utf8',str(ROOT/'scripts/spektrafilm.py'),'--session',str(session)]
    result=subprocess.run([*cli,'open',str(source),str(second)],capture_output=True,text=True,encoding='utf-8',timeout=20)
    assert result.returncode==0,result.stderr+result.stdout
    opened=json.loads(result.stdout)['result'];assert opened['added']==2
    first_id,second_id=(photo['id'] for photo in opened['photos'])
    service=AutomationSession(session)
    service.call('set',dict(photo=first_id,settings=dict(exposure=.37,temperature=5100)))
    service.call('set',dict(photo=second_id,settings=dict(geometry=asdict(Geometry(crop=(.1,.15,.9,.85))))))
    service.call('copy',dict(photo=first_id,categories=['exposure','WB']))
    service.call('paste',dict(photos=[second_id]))
    target=service.call('get',dict(photo=second_id))
    assert target['settings']['exposure']==.37 and target['settings']['temperature']==5100
    assert target['settings']['geometry']['crop']==(.1,.15,.9,.85)
    service.call('undo',dict(photo=second_id));assert service.call('get',dict(photo=second_id))['settings']['exposure']==0
    service.call('redo',dict(photo=second_id));assert service.call('get',dict(photo=second_id))['settings']['exposure']==.37
    clip=folder/'clip.json';service.call('export_clip',dict(path=str(clip)))
    assert json.loads(clip.read_text(encoding='utf-8'))['source_name']=='原片1.tif'
    service.call('import_clip',dict(path=str(clip)))
    report['cli_open_sidecar_clipboard_preserves_crop_undo_redo']=True
    invalid=folder/'unrelated.json';invalid.write_text('{"original":true}',encoding='utf-8')
    try:AutomationSession(invalid).call('open',dict(paths=[str(source)]));raise AssertionError('unrelated JSON replaced')
    except ValueError:pass
    assert invalid.read_text(encoding='utf-8')=='{"original":true}'
    try:service.call('set',dict(photo=first_id,settings=dict(nonexistent=1)));raise AssertionError('unknown parameter accepted')
    except ValueError:pass
    report['unknown_fields_and_foreign_json_rejected']=True
    request=lambda ident,method,params={}:dict(jsonrpc='2.0',id=ident,method=method,params=params)
    requests=[request(1,'initialize',dict(protocolVersion='2025-06-18',capabilities={},clientInfo=dict(name='verification',version='1'))),
        dict(jsonrpc='2.0',method='notifications/initialized'),request(2,'tools/list'),
        request(3,'tools/call',dict(name='spektra_get',arguments=dict(photo=first_id))),
        request(4,'tools/call',dict(name='spektra_set',arguments=dict(photo=first_id,settings=dict(exposure=0,temperature=6500,lens_correction=False,defringe=False)))),
        request(5,'tools/call',dict(name='spektra_export',arguments=dict(photos=[first_id],recipe=dict(id='png',format='png',bit_depth=16,subfolder='export'),destination=str(folder/'out')))),
        request(6,'tools/call',dict(name='spektra_status',arguments={})),request(7,'tools/call',dict(name='unknown',arguments={}))]
    stdio=''.join(json.dumps(value,ensure_ascii=False)+'\n' for value in requests)
    result=subprocess.run([*cli,'mcp','--enable-local'],input=stdio,capture_output=True,text=True,encoding='utf-8',timeout=40)
    assert result.returncode==0,result.stderr
    responses=[json.loads(line) for line in result.stdout.splitlines()]
    assert len(responses)==7,(responses,result.stderr)
    by_id={row['id']:row for row in responses}
    assert by_id[1]['result']['protocolVersion']=='2025-06-18'
    assert len(by_id[2]['result']['tools'])==12
    assert not by_id[5]['result']['isError'],by_id[5]
    exported=json.loads(by_id[5]['result']['content'][0]['text']);path=Path(exported['outputs'][0]['path'])
    assert (exported['outputs'][0]['width'],exported['outputs'][0]['height'])==(64,48)
    assert exported['source_resolution'] and path.read_bytes()[24]==16
    assert by_id[7]['result']['isError']
    from desktop.raw_source import read_high_precision_raster
    pixels=read_high_precision_raster(str(path));assert pixels.shape==(48,64,3)
    assert len(np.unique(pixels[...,0]))>256
    assert source.read_bytes()==before
    Image.open(path).convert('RGB').resize((512,384)).save(OUT/'automation-output-preview.png')
    report.update(stdio_initialize_tools_call_export=True,mcp_tools=12,source_unchanged=True,
        export_size=[64,48],export_bit_depth=16,unique_red_samples=int(np.unique(pixels[...,0]).size),native_engine_available=native_spectral.available())
    denied=subprocess.run([*cli,'mcp'],capture_output=True,text=True,encoding='utf-8',timeout=10)
    assert denied.returncode!=0 and 'disabled by default' in denied.stderr
    report['mcp_requires_explicit_start']=True
report['elapsed_ms']=round((time.perf_counter()-started)*1000)
(OUT/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(report)
