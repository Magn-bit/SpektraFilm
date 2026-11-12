"""One real-RAW HDR milestone: cache reuse, continuous frames and final value.

Measures worker publication, not display FPS. No full-resolution export, source
mutation, hash check or repeated broad suite is part of this small probe.
"""
from pathlib import Path
import argparse
from dataclasses import replace
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PySide6.QtWidgets import QApplication
from desktop.controller import Controller,PhotoProvider
from desktop.imaging import render_pixels
from shared.color_management import convert_pixels
import numpy as np


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--photo',default='D:/Download/DSC09118.ARW')
    args=parser.parse_args()
    app=QApplication.instance() or QApplication([])
    samples=[]
    frames=[]
    changed={}
    active=False
    report=dict(source=Path(args.photo).name,proxy_edge=640,
                scope='Real RAW, full spectral film; Qt event -> worker publication, not display FPS')
    def gpu_snapshot():
        try:
            result=subprocess.run(['nvidia-smi','--query-gpu=utilization.gpu,clocks.sm,power.draw,temperature.gpu',
                '--format=csv,noheader'],capture_output=True,text=True,timeout=5,check=True,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            return result.stdout.strip()
        except (OSError,subprocess.SubprocessError):return 'unavailable'
    report['gpu_before']=gpu_snapshot()
    def wait(predicate,seconds=45):
        deadline=time.perf_counter()+seconds
        while not predicate() and time.perf_counter()<deadline:
            app.processEvents();time.sleep(.001)
        assert predicate(),'Timed out waiting for preview'
    with tempfile.TemporaryDirectory() as directory:
        ctrl=Controller(PhotoProvider(),directory)
        def published():
            generation=ctrl._quality_generation
            if active and generation in changed:
                frames.append(dict(generation=generation,quality=ctrl._quality,
                    lag_ms=round((time.perf_counter()-changed[generation])*1000,3),
                    render_ms=ctrl._render_ms))
        ctrl.frameChanged.connect(published)
        try:
            ctrl.add_paths([str(Path(args.photo).resolve())])
            wait(lambda:bool(ctrl.frame) and not ctrl.busy)
            ctrl.setFilmEnabled(True)
            wait(lambda:not ctrl.busy and not ctrl._pending and not ctrl._fast_busy)
            # Build the small film stage once. All subsequent HDR values reuse
            # this full-spectral result, never a film LUT approximation.
            path=ctrl.currentPath
            ctrl._preview_images(path,ctrl._settings,640,True)
            original,_=ctrl._prepared_source(path,ctrl._settings,640)
            stage=next(iter(original._spektrafilm_preview_cache.values()))
            prepared=original._spektrafilm_prepared_editor[1]
            for value in (18,-38,57,-64,27):
                started=time.perf_counter()
                ctrl._preview_images(path,replace(ctrl._settings,highlights=value),640,True)
                samples.append(round((time.perf_counter()-started)*1000,3))
                assert next(iter(original._spektrafilm_preview_cache.values())) is stage
                assert original._spektrafilm_prepared_editor[1] is prepared
                if len(samples)==1:base=original._spektrafilm_hdr_base[1]
                else:assert original._spektrafilm_hdr_base[1] is base
            report['cached_hdr_ms']=samples
            report['cached_hdr_median_ms']=round(statistics.median(samples),3)
            report['film_and_preparation_reused']=True
            report['hdr_detail_base_reused']=True
            # Standard-display shortcut must preserve the existing wide path,
            # including values outside the display range before quantisation.
            settings=replace(ctrl._settings,highlights=-42,shadows=31)
            direct=render_pixels(original,settings,preview=True,preserve_headroom=True)
            wide=render_pixels(original,settings,preview=True,output_color_space='ProPhoto RGB')
            error=float(np.max(np.abs(direct-convert_pixels(wide,'ProPhoto RGB','sRGB'))))
            assert error<.0001,error
            report['standard_display_max_error_vs_wide']=error
            ctrl.beginEdit();active=True
            start=time.perf_counter()
            for index in range(40):
                ctrl.updateParameter('highlights',-78+index*3)
                changed[ctrl._generation]=time.perf_counter()
                tick=start+(index+1)*.025
                while time.perf_counter()<tick:
                    app.processEvents();time.sleep(.001)
            target=ctrl._generation
            wait(lambda:ctrl._quality_generation==target and ctrl._quality>=1)
            ctrl.endEdit()
            wait(lambda:not ctrl.busy and not ctrl._pending and not ctrl._fast_busy)
            report['continuous_published_frames']=frames
            report['final_value']=ctrl.settings['highlights']
            report['final_generation']=target
            report['final_generation_published']=ctrl._quality_generation==target
            assert report['final_generation_published']
            assert all(a['generation']<=b['generation'] for a,b in zip(frames,frames[1:]))
            assert len({frame['generation'] for frame in frames})>1,'No intermediate frames'
            assert ctrl.settings['highlights']==39
            report['ok']=True
        finally:
            active=False;ctrl.close()
    report['gpu_after']=gpu_snapshot()
    out=ROOT/'output/hdr-interaction-review'
    out.mkdir(parents=True,exist_ok=True)
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
