"""Single small-photo, actual-controller/QLocalServer/CLI/MCP milestone."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CLIENT = r'''
import json,sys,time,subprocess
from pathlib import Path
from desktop.gui_automation import GuiAutomationClient
from PySide6.QtNetwork import QLocalSocket
directory,photo,destination=map(Path,sys.argv[1:])
client=GuiAutomationClient(directory=directory)
def wait_job(job):
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        result=client.call('job',{'job':job})
        if result['state'] not in ('queued','running'):return result
        time.sleep(.025)
    raise AssertionError('job timeout')
record=client._record
def raw(method,token):
    sock=QLocalSocket();sock.connectToServer(record['server']);assert sock.waitForConnected(2000)
    sock.write((json.dumps({'id':'probe','token':token,'method':method,'arguments':{}})+'\n').encode());sock.flush()
    data=bytearray()
    deadline=time.monotonic()+3
    while b'\n' not in data and time.monotonic()<deadline:
        if sock.bytesAvailable():data.extend(bytes(sock.readAll()))
        else:sock.waitForReadyRead(250)
    sock.abort();return json.loads(data.split(b'\n',1)[0])
assert raw('status','wrong-token')['error']['code']=='unauthorized'
assert raw('__dict__',record['token'])['error']['code']=='invalid_request'
opened=client.call('open',{'paths':[str(photo)]});assert opened['accepted']
assert wait_job(opened['job'])['state']=='completed'
value=client.call('set',{'photo':'current','settings':{'film_enabled':True,'exposure':.25,'grain':0.0}})
assert value['settings']['exposure']==.25
assert client.call('get',{'photo':'current'})['settings']['exposure']==.25
client.call('copy',{'photo':'current','categories':['exposure']})
client.call('set',{'photo':'current','settings':{'exposure':.5}})
client.call('undo',{'photo':'current'})
assert client.call('get',{'photo':'current'})['settings']['exposure']==.25
client.call('redo',{'photo':'current'})
assert client.call('get',{'photo':'current'})['settings']['exposure']==.5
client.call('paste',{'photos':[str(photo)],'categories':['exposure']})
assert client.call('get',{'photo':'current'})['settings']['exposure']==.25
exported=client.call('export',{'photos':[str(photo)],'recipe':'png','destination':str(destination)})
assert exported['accepted'] and exported['source_resolution']
finished=wait_job(exported['job']);assert finished['state']=='completed',finished
paths=finished['result']['completed'];assert len(paths)==1
from PIL import Image
with Image.open(paths[0]) as result:assert result.size==(64,48)
cli=subprocess.run([sys.executable,'scripts/spektrafilm.py','--gui','--gui-directory',str(directory),'status'],capture_output=True,text=True,encoding='utf-8')
assert cli.returncode==0,cli.stderr
assert json.loads(cli.stdout)['result']['scope']=='live-gui-session'
requests=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25'}},
          {'jsonrpc':'2.0','id':2,'method':'tools/list'},
          {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'spektra_status','arguments':{}}}]
mcp=subprocess.run([sys.executable,'scripts/spektrafilm.py','--gui','--gui-directory',str(directory),'mcp','--enable-local'],input=''.join(json.dumps(r)+'\n' for r in requests),capture_output=True,text=True,encoding='utf-8')
assert mcp.returncode==0,mcp.stderr
replies=[json.loads(line) for line in mcp.stdout.splitlines()]
assert 'live GUI' in replies[0]['result']['instructions']
names=[t['name'] for t in replies[1]['result']['tools']]
assert 'spektra_job' in names and not replies[2]['result']['isError']
print(json.dumps({'authentication_rejected':True,'method_allowlist':True,'same_gui_settings':True,'gui_clipboard':True,'undo_redo':True,'asynchronous_import':True,'asynchronous_native_export':True,'dimensions':[64,48],'cli_gui_route':True,'mcp_live_gui_tools':len(names),'export_path':paths[0]},ensure_ascii=False))
'''


def main():
    from PIL import Image
    import numpy as np
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtNetwork import QLocalServer
    from PySide6.QtWidgets import QApplication
    from desktop.controller import Controller, PhotoProvider
    from desktop.gui_automation import GuiAutomation
    app = QApplication([])
    app.setApplicationName('SpektraFilm')
    app.setOrganizationName('SpektraFilm')
    output = ROOT / 'output/gui-automation'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='small-', dir=output) as folder:
        temporary = Path(folder)
        photo = temporary / '小图.jpg'
        ramp = np.linspace(20, 230, 64, dtype=np.uint8)
        pixels = np.repeat(ramp[None, :, None], 48, axis=0)
        Image.fromarray(np.repeat(pixels, 3, axis=2)).save(photo, quality=100)
        original = photo.read_bytes()
        controller = Controller(PhotoProvider(), str(temporary / 'store'))
        directory = temporary / 'store/automation-probe'
        interface = GuiAutomation(controller, directory=directory)
        assert not interface.enabled and not directory.exists()
        errors = []
        interface.error.connect(errors.append)
        interface.setEnabled(True)
        assert interface.enabled, errors
        assert interface._server.socketOptions() == QLocalServer.UserAccessOption
        credentials = list(directory.glob('gui-*.json'))
        assert len(credentials) == 1
        heartbeat = []
        timer = QTimer()
        timer.setInterval(5)
        timer.timeout.connect(lambda: heartbeat.append(time.perf_counter()))
        timer.start()
        child = subprocess.Popen([sys.executable, '-X', 'utf8', '-c', CLIENT, str(directory), str(photo), str(temporary / 'exports')],
                                 cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
        loop = QEventLoop()
        poll = QTimer()
        poll.setInterval(20)
        deadline = time.monotonic() + 45
        def tick():
            if child.poll() is not None: loop.quit()
            elif time.monotonic() > deadline:
                child.kill(); loop.quit()
        poll.timeout.connect(tick)
        poll.start()
        loop.exec()
        poll.stop()
        timer.stop()
        stdout, stderr = child.communicate(timeout=3)
        try:
            assert child.returncode == 0, stdout + '\n' + stderr
            report = json.loads(stdout)
            assert photo.read_bytes() == original
            # Retain only the tiny exported artifact and report, not credentials.
            export = Path(report.pop('export_path'))
            target = output / 'same-gui-native-export.png'
            target.write_bytes(export.read_bytes())
            report.update(default_disabled=True, protected_directory=True, user_access_socket=True,
                          ui_heartbeat_ticks=len(heartbeat), source_bytes_unchanged=True,
                          engine='same GUI controller export_recipe_batch',
                          sidecar_created=False, status='passed')
        finally:
            interface.close()
            assert not list(directory.glob('gui-*.json'))
            controller.close()
        report['disable_removes_credentials'] = True
    (output / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
