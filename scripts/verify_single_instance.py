"""One two-process handoff node, two tiny original photos, no RAW benchmark."""
import argparse,json,os
from pathlib import Path
import queue,subprocess,sys,tempfile,threading,time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def worker(args):
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QWindow,QFileOpenEvent
    from PySide6.QtWidgets import QApplication
    from desktop.single_instance import SingleInstance
    app=QApplication([]);app.setApplicationName('SingleInstanceVerification');app.setOrganizationName('SpektraFilmVerification')
    broker=SingleInstance(app,directory=Path(args.folder)/'instance',name=args.name)
    forwarded=broker.claim_or_forward(args.paths)
    if args.mode=='client':
        assert forwarded,'second process must hand off, not become another window'
        print('FORWARDED',flush=True);broker.close();return 0
    assert not forwarded
    from desktop.controller import Controller,PhotoProvider
    ctrl=Controller(PhotoProvider(),Path(args.folder)/'state')
    window=QWindow();window.resize(640,480);window.show();window.showMinimized()
    ctrl._exporting=True
    broker.bind(window,ctrl)
    report={'primary_pid':os.getpid(),'export_busy_defers_paths':False,'file_open_event':False}
    def finish_export():
        report['export_busy_defers_paths']=len(ctrl.photos)==0 and len(broker._pending)==2
        ctrl._exporting=False;ctrl.stateChanged.emit()
    def opened_event():
        # The duplicate is coalesced by the same controller import boundary.
        app.sendEvent(app,QFileOpenEvent(args.paths[0]));report['file_open_event']=True
    QTimer.singleShot(1400,finish_export);QTimer.singleShot(2000,opened_event)
    started=time.monotonic()
    def check():
        if time.monotonic()-started<2.1:return
        if len(ctrl.photos)==2 and not ctrl.busy:
            report.update(paths=[row['path'] for row in ctrl.photos],controller_count=len(ctrl.photos),
                          window_restored=window.visibility()!=QWindow.Minimized,same_primary=True,
                          automation_disabled=not ctrl.guiAutomation.enabled)
            (Path(args.folder)/'host-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            app.quit()
        elif time.monotonic()-started>15:
            print('HOST_TIMEOUT',ctrl.status,len(ctrl.photos),flush=True);app.exit(4)
    timer=QTimer();timer.timeout.connect(check);timer.start(50)
    print('HOST_READY',flush=True);app.aboutToQuit.connect(ctrl.close)
    return app.exec()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['host','client'])
    parser.add_argument('--folder');parser.add_argument('--name');parser.add_argument('paths',nargs='*');args=parser.parse_args()
    if args.mode:return worker(args)
    from PIL import Image
    out=ROOT/'output/single-instance';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='open-',dir=out,ignore_cleanup_errors=True) as directory:
        folder=Path(directory);first=folder/'第一张.png';second=folder/'第二张.png'
        Image.new('RGB',(96,64),(120,140,90)).save(first);Image.new('RGB',(96,64),(170,100,90)).save(second)
        name='SpektraFilm.SingleInstanceVerification.'+str(os.getpid())
        command=[sys.executable,'-X','utf8',str(Path(__file__).resolve())]
        host=subprocess.Popen(command+['--mode','host','--folder',directory,'--name',name,str(first)],
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',cwd=ROOT)
        lines=queue.Queue();threading.Thread(target=lambda:[lines.put(line) for line in host.stdout],daemon=True).start()
        try:
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                try:line=lines.get(timeout=.2)
                except queue.Empty:
                    if host.poll() is not None:raise AssertionError(host.stderr.read())
                    continue
                if 'HOST_READY' in line:break
            else:raise AssertionError('primary did not become ready')
            client=subprocess.run(command+['--mode','client','--folder',directory,'--name',name,str(second)],
                                  capture_output=True,text=True,encoding='utf-8',timeout=15,cwd=ROOT)
            assert client.returncode==0 and 'FORWARDED' in client.stdout,(client.stdout,client.stderr)
            host.wait(timeout=20);assert host.returncode==0,host.stderr.read()
            report=json.loads((folder/'host-result.json').read_text(encoding='utf-8'))
            assert report['export_busy_defers_paths'] and report['window_restored'] and report['automation_disabled'],report
            assert report['controller_count']==2 and set(report['paths'])=={str(first),str(second)},report
            report.update(status='passed',sources=[[96,64],[96,64]],client_exited_after_ack=True)
            (out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(report,ensure_ascii=False,indent=2))
        finally:
            if host.poll() is None:host.terminate();host.wait(timeout=5)
    return 0


if __name__=='__main__':raise SystemExit(main())
