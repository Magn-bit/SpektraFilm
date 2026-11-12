"""One new-tools-only node: actual controller, native jobs and MCP images."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

CLIENT=r'''
import base64,io,json,subprocess,sys,time
from pathlib import Path
from PIL import Image
from desktop.gui_automation import GuiAutomationClient
from shared.settings_sync import make_clip
directory,folder=map(Path,sys.argv[1:])
client=GuiAutomationClient(directory=directory)
cli=[sys.executable,'-X','utf8','scripts/spektrafilm.py','--gui','--gui-directory',str(directory)]
def command(*args):
 result=subprocess.run(cli+list(args),capture_output=True,text=True,encoding='utf-8',timeout=15)
 assert result.returncode==0,result.stdout+'\n'+result.stderr
 answer=json.loads(result.stdout);assert answer['ok'];return answer['result']
def wait_job(ident):
 deadline=time.monotonic()+20
 while time.monotonic()<deadline:
  result=client.call('job',{'job':ident})
  if result['state'] not in ('queued','running'):
   assert result['state']=='completed',result
   return result['result']
  time.sleep(.01)
 raise AssertionError('analysis job timeout')
deadline=time.monotonic()+20
while not client.call('describe',{})['processing']['preview_ready']:
 assert time.monotonic()<deadline
 time.sleep(.01)
description=command('describe')
assert description['scope']=='live-gui-session' and description['film']['compatible_papers']
report={'describe_material_and_state':True}
for kind,args in [('auto_meter',['auto-meter','--target','both','--method','protect_highlights']),('latitude',['latitude']),('place',['place'])]:
 accepted=command(*args);assert accepted['accepted']
 result=wait_job(accepted['job'])
 if kind=='auto_meter':assert result['applied'] and 'solved_params' in result['analysis']
 if kind=='latitude':assert not result['applied'] and 'scene' in result['analysis'] and 'medium' in result['analysis']
 if kind=='place':assert result['applied']==bool(result['analysis'].get('fit',{}).get('valid'))
 report[kind]={'real_engine_job':True,'applied':result['applied']}
clip=make_clip({'exposure':.37},['exposure'],'Source Camera.RAW')
(folder/'input-clip.json').write_text(json.dumps(clip),encoding='utf-8')
client.call('import_clip',{'path':str(folder/'input-clip.json')})
client.call('export_clip',{'path':str(folder/'output-clip.json')})
exported=json.loads((folder/'output-clip.json').read_text(encoding='utf-8'))
assert exported['source_name']==clip['source_name'] and exported['categories']==clip['categories']
assert exported['settings']==clip['settings']
report['clipboard_preserves_canonical_subset_origin_and_categories']=True
deadline=time.monotonic()+20
while not client.call('describe',{})['processing']['preview_ready']:
 assert time.monotonic()<deadline
 time.sleep(.01)
requests=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25'}},
 {'jsonrpc':'2.0','id':2,'method':'tools/list'},
 {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'spektra_preview_image','arguments':{'long_edge':64}}}]
mcp=subprocess.run(cli+['mcp','--enable-local'],input=''.join(json.dumps(r)+'\n' for r in requests),capture_output=True,text=True,encoding='utf-8',timeout=15)
assert mcp.returncode==0,mcp.stderr
answers=[json.loads(line) for line in mcp.stdout.splitlines()]
names={item['name'] for item in answers[1]['result']['tools']}
assert {'spektra_describe','spektra_preview_image','spektra_auto_meter','spektra_latitude','spektra_place'}<=names
assert not answers[2]['result']['isError'],answers[2]
content=answers[2]['result']['content'];media=next(row for row in content if row['type']=='image')
metadata=json.loads(next(row['text'] for row in content if row['type']=='text'))
encoded=base64.b64decode(media['data'],validate=True)
with Image.open(io.BytesIO(encoded)) as image:
 assert image.format=='JPEG' and max(image.size)<=64
 assert tuple(image.size)==(metadata['width'],metadata['height'])
 report['mcp_actual_image']={'mimeType':media['mimeType'],'size':list(image.size),'bytes':len(encoded),'color_domain':metadata['color_domain']}
(folder/'preview.jpg').write_bytes(encoded)
print(json.dumps(report,ensure_ascii=False))
'''


def main():
    import numpy as np
    from PIL import Image
    from PySide6.QtCore import QEventLoop,QTimer
    from PySide6.QtWidgets import QApplication
    from desktop.controller import Controller,PhotoProvider
    from desktop.imaging import Settings
    from dataclasses import asdict
    app=QApplication([]);app.setApplicationName('SpektraFilm');app.setOrganizationName('SpektraFilm')
    output=ROOT/'output/gui-analysis-tools';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='new-tools-',dir=output) as folder:
        temporary=Path(folder);source=temporary/'source.png'
        y,x=np.mgrid[0:79,0:127]
        samples=np.stack((x/126,y/78,(x+y)/204),axis=-1)
        Image.fromarray(np.rint(samples*255).astype(np.uint8)).save(source)
        controller=Controller(PhotoProvider(),str(temporary/'store'))
        settings=Settings(film_enabled=True,lens_correction=False,defringe=False,grain=0,halation=0)
        controller._photos.append(dict(path=str(source),name=source.name,width=127,height=79,
            dimensions='127 × 79',settings=asdict(settings)))
        controller._current=0;controller._settings=settings;controller._sync_editor_bindings();controller._changed()
        interface=controller.guiAutomation;interface.setEnabled(True);assert interface.enabled
        heartbeat=[];timer=QTimer();timer.setInterval(5);timer.timeout.connect(lambda:heartbeat.append(1));timer.start()
        child=subprocess.Popen([sys.executable,'-X','utf8','-c',CLIENT,str(interface._directory),str(temporary)],
            cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
        loop=QEventLoop();poll=QTimer();poll.setInterval(20);deadline=time.monotonic()+75
        def tick():
            if child.poll() is not None:loop.quit()
            elif time.monotonic()>deadline:child.kill();loop.quit()
        poll.timeout.connect(tick);poll.start();loop.exec();poll.stop();timer.stop()
        stdout,stderr=child.communicate(timeout=3)
        try:
            assert child.returncode==0,stdout+'\n'+stderr
            report=json.loads(stdout);report.update(status='passed',fixture=[127,79],ui_heartbeat_ticks=len(heartbeat),
                scope='actual Controller and authenticated QLocalServer; no sidecar or export recheck')
            (output/'mcp-preview.jpg').write_bytes((temporary/'preview.jpg').read_bytes())
        finally:controller.close()
    (output/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
