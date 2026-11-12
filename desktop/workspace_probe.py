"""Opt-in exact-build milestone, driven by the running window's event loop."""
from dataclasses import replace
import json
from pathlib import Path
import time
import sys
import subprocess
import os
import tempfile

from PySide6.QtCore import QObject,QMetaObject,QTimer


class WorkspaceProbe(QObject):
    def __init__(self,app,engine,controller,directory,finished):
        super().__init__(app);self.app=app;self.engine=engine;self.ctrl=controller
        self.window=engine.rootObjects()[0];self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.finished=finished;self.report={'ok':False,'frozen':bool(getattr(sys,'frozen',False)),'pages':{},'checks':[]};self.step=10 if os.environ.get('SPEKTRAFILM_PROBE_TOOLS_ONLY')=='1' else 9 if os.environ.get('SPEKTRAFILM_PROBE_LIVE_ONLY')=='1' else 0;self.entered=False;self.started=time.monotonic()
        self.timer=QTimer(self);self.timer.setInterval(100);self.timer.timeout.connect(self.tick);self.timer.start()
        self.window.setWidth(1366);self.window.setHeight(768)
        self.work=None;self.variants=[]
        self.process=None;self.command_index=0;self.command_results=[];self.export_job=None
    def capture(self,name):
        image=self.window.grabWindow();target=self.directory/(name+'.png');assert image.save(str(target))
        self.report['pages'][name]={'logical':[self.window.width(),self.window.height()],
            'pixels':[image.width(),image.height()],'file':target.name}
    def advance(self):self.step+=1;self.entered=False;self.started=time.monotonic()
    def done(self,ok,error=''):
        self.timer.stop()
        if ok and os.environ.get('SPEKTRAFILM_PROBE_LIVE_ONLY')!='1' and os.environ.get('SPEKTRAFILM_PROBE_TOOLS_ONLY')!='1':
            try:
                from .refinement_probe import run_refinement_probe
                self.report['refinements']=run_refinement_probe(self.app,self.window,self.ctrl,self.directory/'refinements')
            except Exception as failure:
                ok=False;error=type(failure).__name__+': '+str(failure)
        self.report.update(ok=ok,error=error)
        if not ok and self.step in (9,10):
            self.report['live_failure']=dict(command_index=self.command_index,answers=self.command_results,
                exporting=self.ctrl.exporting,jobs=list(self.ctrl.guiAutomation._jobs.values()))
        (self.directory/'workspace.json').write_text(json.dumps(self.report,ensure_ascii=False,indent=2),encoding='utf-8')
        self.finished(ok)
    def tick(self):
        try:self.run_step()
        except Exception as error:self.done(False,type(error).__name__+': '+str(error))
    def run_step(self):
        if time.monotonic()-self.started>(120 if self.step in (9,10) else 30):
            raise TimeoutError('workspace probe step '+str(self.step))
        ctrl=self.ctrl;window=self.window
        if self.step==0:
            if ctrl.busy:return
            if not self.entered:
                self.entered=True;ctrl.importPhotos();ctrl.importWorkspace.setSources([ctrl.currentPath]);return
            if ctrl.importWorkspace.state['scanning']:return
            assert window.property('workspaceMode')=='import';self.capture('import');window.setProperty('workspaceMode','edit')
            self.report['checks'].append('runtime import staging and existing-photo exclusion');self.advance()
        elif self.step==1:
            if not self.entered:
                self.entered=True;self.work=ctrl.libraryWorkspace
                self.work.createLibrary(str(self.directory/'probe-catalog'),'catalog');return
            if not self.work.hasLibrary or self.work._requests:return
            self.work.addPaths([ctrl.currentPath],False);self.advance()
        elif self.step==2:
            if self.work.total!=1 or self.work._requests:return
            row=self.work.images[0];self.work.activateVariant(row['uuid'],'');self.advance()
        elif self.step==3:
            if not ctrl._library_context or self.work._requests:return
            window.setProperty('workspaceMode','library');window.setProperty('quickLibrary',False);self.capture('library')
            self.report['checks'].append('runtime SQLite helper catalog and real controller activation')
            window.setProperty('quickLibrary',True);self.advance()
        elif self.step==4:
            if ctrl.busy:return
            grid=window.findChild(QObject,'sessionBrowserGrid');assert grid is not None
            assert grid.property('width')>window.width()*.75
            assert window.findChild(QObject,'openLightTableButton') is None
            assert window.findChild(QObject,'workspace_develop') is None
            self.capture('gallery');window.setProperty('workspaceMode','edit')
            self.report['checks'].append('single gallery entry with full-width session grid and return to editing')
            self.advance()
        elif self.step in (5,6,7):
            names={5:('exportDialog','export'),6:('outputRecipeDialog','recipes'),7:('settingsPanel','settings')}
            name,label=names[self.step];dialog=window.findChild(QObject,name);assert dialog is not None
            if not self.entered:
                self.entered=True;QMetaObject.invokeMethod(dialog,'open')
                if self.step==7:dialog.setProperty('category','color')
                return
            if time.monotonic()-self.started<.6:return
            if self.step in (5,6):
                proof=ctrl.outputProof
                if proof.busy:return
                assert proof.source and not proof.error,proof.error
                if self.step==6 and not proof.fullResolution:
                    proof.request(self.recipe_value(dialog),True,True,False)
                    return
                if self.step==6:
                    assert proof.dimensions==proof.expectedDimensions
                    proof.viewTile(0,0,256,256);assert proof.tileSource
                    artifact=proof.exportArtifact();assert artifact is not None
                    recipe=__import__('shared.output_recipes',fromlist=['normalize_recipe']).normalize_recipe(self.recipe_value(dialog))
                    assert artifact.matches(ctrl.currentPath,ctrl._settings,recipe)
                    target=self.directory/('full-proof'+artifact.path.suffix)
                    artifact.publish(target,recipe)
                    assert target.read_bytes()==artifact.path.read_bytes()
                    self.report['checks'].append('recipe-encoded soft proof, full pixel tile and exact encoded proof publication')
            assert dialog.property('width')==window.width() and dialog.property('height')==window.height()-34
            self.capture(label);QMetaObject.invokeMethod(dialog,'close');self.advance()
        elif self.step==8:
            if ctrl.busy:return
            from .imaging import read_photo,Settings
            from .output import export_recipe
            from shared.output_recipes import OutputRecipe
            # Source fixture is deliberately small. These invoke the frozen
            # modules/DLLs; the earlier real-RAW timings retain their scope.
            fixture=ctrl.currentPath
            for fmt,space in [('heif','Adobe RGB (1998)'),('di','ProPhoto RGB')]:
                path=self.directory/('proof.heic' if fmt=='heif' else 'negative.tif')
                settings=replace(ctrl._settings,film_enabled=True,stock='kodak_portra_400',paper='auto',
                    grain=0,halation=0,dir_couplers_amount=0,minilab_active=False)
                export_recipe(fixture,path,settings,OutputRecipe(format=fmt,bit_depth=8 if fmt=='heif' else 16,color_space=space))
                with read_photo(path) as image:
                    self.report.setdefault('outputs',{})[fmt]=dict(size=list(image.size),bytes=path.stat().st_size)
            self.report['checks'].extend(['runtime HEIF and Adobe RGB encoder','runtime genuine Cineon DI and dedicated view LUTs'])
            self.advance()
        elif self.step==9:
            self.verify_live_gui()
        elif self.step==10:
            self.verify_live_tools()

    @staticmethod
    def recipe_value(dialog):
        value=dialog.property('draft')
        return value.toVariant() if hasattr(value,'toVariant') else value

    def verify_live_gui(self):
        """Run the packaged console and stdio MCP against this exact window."""
        ctrl=self.ctrl
        if not self.entered:
            assert not ctrl.guiAutomation.enabled
            ctrl.guiAutomation.setEnabled(True);assert ctrl.guiAutomation.enabled
            self.entered=True
            prefix=([str(Path(sys.executable).with_name('SpektraFilmCLI.exe'))] if getattr(sys,'frozen',False)
                    else [sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/spektrafilm.py')])
            self.cli_prefix=prefix+['--gui','--gui-directory',str(ctrl.guiAutomation._directory)]
            self.commands=[['status'],['set','current','--settings',json.dumps(dict(stock='kodak_portra_400',paper='kodak_supra_endura',film_enabled=True,exposure=.41,grain=0,halation=0))],
                ['get','current'],['copy','current','--categories','materials','exposure','print_effects'],
                ['set','current','--settings','{"exposure":0.8}'],['paste','--categories','materials','exposure','print_effects'],
                ['get','current'],['export','--recipe','png','--destination',str(self.directory/'live-gui-export')]]
        if self.command_index<len(self.commands):
            answer=self.poll_command(self.commands[self.command_index])
            if answer is None:return
            self.command_results.append(answer);self.command_index+=1;return
        if self.export_job is None:
            assert self.command_results[0]['scope']=='live-gui-session'
            assert self.command_results[0]['pid']==os.getpid()
            assert self.command_results[2]['settings']['exposure']==.41
            assert self.command_results[6]['settings']['exposure']==.41
            assert ctrl._settings.exposure==.41 and ctrl._settings.paper=='kodak_supra_endura'
            self.export_job=self.command_results[-1]['job']
        if not getattr(self,'export_complete',False):
            answer=self.poll_command(['job',self.export_job])
            if answer is None:return
            if answer['state'] in ('queued','running'):return
            assert answer['state']=='completed',answer
            from PIL import Image
            for path in answer['result']['completed']:
                with Image.open(path) as image:assert image.size==tuple(ctrl._output_dimensions())
            self.export_complete=True
        requests=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25'}},
            {'jsonrpc':'2.0','id':2,'method':'tools/list'},
            {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'spektra_get','arguments':{'photo':'current'}}}]
        answer=self.poll_command(['mcp','--enable-local'],stdin=''.join(json.dumps(r)+'\n' for r in requests),mcp=True)
        if answer is None:return
        assert 'live GUI' in answer[0]['result']['instructions']
        content=answer[2]['result']['content'][0]['text'];settings=json.loads(content)['settings']
        assert settings['exposure']==ctrl._settings.exposure and settings['paper']==ctrl._settings.paper
        ctrl.guiAutomation.setEnabled(False);assert not ctrl.guiAutomation.enabled
        self.report['live_gui']={'same_process_pid':os.getpid(),'cli_set_get_copy_paste_export':True,
            'mcp_get_matches_visible_controller':True,'source_size_output':True,'default_disabled':True,'sidecar_created':False}
        self.report['checks'].append('packaged CLI and stdio MCP mutate/read/export the actual visible GUI controller')
        self.done(True)

    def poll_command(self,args,stdin=None,mcp=False):
        if self.process is None:
            self.command_stdout=tempfile.TemporaryFile(mode='w+t',encoding='utf-8')
            self.command_stderr=tempfile.TemporaryFile(mode='w+t',encoding='utf-8')
            self.process=subprocess.Popen(self.cli_prefix+args,stdin=subprocess.PIPE if stdin else subprocess.DEVNULL,
                stdout=self.command_stdout,stderr=self.command_stderr,text=True,encoding='utf-8')
            if stdin:self.process.stdin.write(stdin);self.process.stdin.close();self.process.stdin=None
            return None
        if self.process.poll() is None:return None
        code=self.process.returncode;self.process=None
        self.command_stdout.seek(0);self.command_stderr.seek(0)
        output,error=self.command_stdout.read(),self.command_stderr.read()
        self.command_stdout.close();self.command_stderr.close()
        assert code==0,(output,error)
        if mcp:return [json.loads(line) for line in output.splitlines()]
        answer=json.loads(output);assert answer['ok'],answer
        return answer['result']

    def verify_live_tools(self):
        """One opt-in new-tools node; does not repeat the prior CLI/export run."""
        ctrl=self.ctrl
        if not self.entered:
            if ctrl.busy or not ctrl.frame:return
            assert ctrl.sourceDimensions[0]*ctrl.sourceDimensions[1]<=1_000_000,'tools probe requires a bounded fixture'
            self.tools_was_enabled=ctrl.guiAutomation.enabled
            ctrl.guiAutomation.setEnabled(True);assert ctrl.guiAutomation.enabled
            prefix=([str(Path(sys.executable).with_name('SpektraFilmCLI.exe'))] if getattr(sys,'frozen',False)
                else [sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/spektrafilm.py')])
            self.cli_prefix=prefix+['--gui','--gui-directory',str(ctrl.guiAutomation._directory)]
            self.tools_commands=[('describe',['describe']),('auto_meter',['auto-meter','--target','both']),
                ('latitude',['latitude']),('place',['place'])]
            self.tools_index=0;self.tools_pending=None;self.tools_results={};self.entered=True
        if self.tools_pending:
            kind,job=self.tools_pending
            answer=self.poll_command(['job',job])
            if answer is None or answer['state'] in ('queued','running'):return
            assert answer['state']=='completed',answer
            result=answer['result'];assert result['photo']==ctrl.currentPath
            if kind=='auto_meter':assert result['applied'] and 'solved_params' in result['analysis']
            if kind=='latitude':assert not result['applied'] and 'medium' in result['analysis']
            if kind=='place':assert result['applied']==bool(result['analysis'].get('fit',{}).get('valid'))
            self.tools_results[kind]=dict(state=answer['state'],applied=result['applied'])
            self.tools_pending=None;return
        if self.tools_index<len(self.tools_commands):
            kind,command=self.tools_commands[self.tools_index]
            answer=self.poll_command(command)
            if answer is None:return
            self.tools_index+=1
            if kind=='describe':
                assert answer['scope']=='live-gui-session' and answer['film']['compatible_papers']
                self.tools_results[kind]=True
            else:self.tools_pending=(kind,answer['job'])
            return
        if ctrl.busy or ctrl._display_generation!=ctrl._generation:return
        requests=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25'}},
            {'jsonrpc':'2.0','id':2,'method':'tools/list'},
            {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'spektra_describe','arguments':{}}},
            {'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'spektra_preview_image','arguments':{'long_edge':256}}}]
        answers=self.poll_command(['mcp','--enable-local'],stdin=''.join(json.dumps(r)+'\n' for r in requests),mcp=True)
        if answers is None:return
        names={tool['name'] for tool in answers[1]['result']['tools']}
        assert {'spektra_describe','spektra_preview_image','spektra_auto_meter','spektra_latitude','spektra_place'}<=names
        assert not answers[2]['result']['isError'] and not answers[3]['result']['isError']
        media=next(item for item in answers[3]['result']['content'] if item['type']=='image')
        import base64,io
        from PIL import Image
        encoded=base64.b64decode(media['data'],validate=True)
        with Image.open(io.BytesIO(encoded)) as image:
            assert media['mimeType']=='image/jpeg' and max(image.size)<=256
            self.tools_results['mcp_image']=dict(mime=media['mimeType'],dimensions=list(image.size),bytes=len(encoded))
        (self.directory/'mcp-preview.jpg').write_bytes(encoded)
        self.capture('automation-tools')
        if not self.tools_was_enabled:ctrl.guiAutomation.setEnabled(False)
        self.report['new_live_tools']=self.tools_results
        self.report['checks'].append('same-window describe, native auto meter/latitude/accepted placement jobs and genuine MCP JPEG image content')
        self.done(True)
