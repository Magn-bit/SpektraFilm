"""Measure real preview latency including event dispatch; never infer animation FPS."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import sys,time,json,tempfile,statistics
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image
from PySide6.QtWidgets import QApplication
from desktop.imaging import Settings,render,render_interactive
from desktop.controller import Controller,PhotoProvider

app=QApplication.instance() or QApplication([])
image=Image.fromarray(np.random.default_rng(17).integers(0,256,(960,1440,3),dtype=np.uint8))
small=image.copy();small.thumbnail((640,640))
def timing(fn):
    values=[]
    for _ in range(8):
        start=time.perf_counter();fn();values.append((time.perf_counter()-start)*1000)
    return dict(first_ms=round(values[0],2),median_ms=round(statistics.median(values[1:]),2),worst_ms=round(max(values),2))
settings=Settings(exposure=.7)
report=dict(fine_1440=timing(lambda:render(image,settings)),interactive_640=timing(lambda:render_interactive(small,settings)),scope='CPU render and controller event-to-publication on this Windows machine; no display FPS claim')
image._spektrafilm_preview_cache={}
render(image,settings)
from dataclasses import replace
report['fine_cached_adjustment_1440']=timing(lambda:render(image,replace(settings,contrast=12,grain=37)))
def wait(predicate):
    deadline=time.monotonic()+20
    while not predicate() and time.monotonic()<deadline:app.processEvents();time.sleep(.001)
    assert predicate(),'preview timed out'
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)/'fixture.png';image.save(path)
    controller=Controller(PhotoProvider(),directory)
    try:
        controller.add_paths([str(path)]);wait(lambda:not controller.busy and bool(controller.frame))
        samples=[]
        for value in (.1,.4,.8,1.2,-.4,-.8):
            controller.beginEdit();start=time.perf_counter();controller.updateParameter('exposure',value)
            generation=controller._generation
            wait(lambda:controller._quality_generation==generation and controller._quality==1)
            samples.append((time.perf_counter()-start)*1000)
            controller.endEdit();wait(lambda:not controller.busy)
        report['event_to_interactive_ms']=dict(samples=[round(n,2) for n in samples],median=round(statistics.median(samples),2),worst=round(max(samples),2))
    finally:controller.close()
Path('output/preview-benchmark.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
