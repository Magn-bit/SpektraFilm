"""Exercise real Qt layouts across window sizes and DPI factors without desktop input."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--scale')
args=parser.parse_args()
out=root/'output/scrollbar-verification'
out.mkdir(parents=True,exist_ok=True)
if not args.scale:
    for scale in ['1','1.25','1.5','2']:
        env=os.environ.copy();env['QT_SCALE_FACTOR']=scale;env['QT_QPA_PLATFORM']='offscreen'
        result=subprocess.run([sys.executable,'-X','utf8',__file__,'--scale',scale],cwd=root,env=env,capture_output=True,text=True,encoding='utf-8',timeout=40)
        (out/('scale-'+scale+'.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
        print(result.stdout+result.stderr,flush=True)
        if result.returncode:raise SystemExit(result.returncode)
    env=os.environ.copy();env['QT_QPA_PLATFORM']='windows';env.pop('QT_SCALE_FACTOR',None)
    result=subprocess.run([sys.executable,'-X','utf8',__file__,'--scale','native'],cwd=root,env=env,capture_output=True,text=True,encoding='utf-8',timeout=40)
    (out/'native.log').write_text(result.stdout+result.stderr,encoding='utf-8')
    print(result.stdout+result.stderr,flush=True)
    if result.returncode:raise SystemExit(result.returncode)
    print('SCROLLBAR_OK: four DPI factors, six window sizes, two tabs, bottom-scroll tracking, native Windows captures',flush=True)
    raise SystemExit(0)

sys.path.insert(0,str(root))
from PySide6.QtCore import QObject,QPointF,QUrl,Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication
from desktop.controller import Controller,PhotoProvider
from desktop.typography import load_mincho

app=QApplication([])
family=load_mincho(app,root)
store=tempfile.TemporaryDirectory()
provider=PhotoProvider();ctrl=Controller(provider,store.name)
engine=QQmlApplicationEngine();engine.addImageProvider('photos',provider)
context=engine.rootContext()
context.setContextProperty('ctrl',ctrl)
context.setContextProperty('assetsUrl',QUrl.fromLocalFile(str(root/'assets')+'/').toString())
context.setContextProperty('minchoFamily',family)
context.setContextProperty('systemReduceMotion',True)
engine.load(QUrl.fromLocalFile(str(root/'desktop/qml/Studio.qml')))
assert engine.rootObjects(),'QML failed to load'
window=engine.rootObjects()[0]
if args.scale=='native':window.setFlag(Qt.WindowDoesNotAcceptFocus,True)
window.show()
scroll=window.findChild(QObject,'parameterScroll')
bar=window.findChild(QObject,'parameterScrollBar')
assert scroll and bar

def settle():
    until=time.monotonic()+.25
    while time.monotonic()<until:app.processEvents();time.sleep(.005)

checks=[]
try:
    cases=[('normal',1480,960),('minimum',1120,760)] if args.scale=='native' else [('normal',1480,960),('minimum',1120,760),('tall',1120,1000),('short',1480,760),('large',1920,1080),('restored',1480,960)]
    for name,width,height in cases:
        window.resize(width,height);settle()
        for action in ['minimize','maximize','close']:
            dot=window.findChild(QObject,'windowDot_'+action)
            face=dot.findChild(QObject,'dotFace');ring=dot.findChild(QObject,'dotFocus')
            center=face.mapToItem(dot,QPointF(face.width()/2,face.height()/2))
            assert abs(center.x()-dot.width()/2)<.01 and abs(center.y()-dot.height()/2)<.01,(args.scale,action,center)
            ring_center=ring.mapToItem(face,QPointF(ring.width()/2,ring.height()/2))
            assert abs(ring_center.x()-6)<.01 and abs(ring_center.y()-6)<.01
            glyph=dot.findChild(QObject,'maximizeGlyph')
            glyph_center=glyph.mapToItem(face,QPointF(glyph.width()/2,glyph.height()/2))
            assert abs(glyph_center.x()-6)<.01 and abs(glyph_center.y()-6)<.01
        for tab in [0,1]:
            window.setProperty('editTab',tab);settle()
            keys=['exposure','contrast','warmth','saturation'] if tab==0 else ['grain','halation','vignette']
            gutter=float(scroll.property('rightPadding'))
            assert gutter>=20
            bar_left=bar.mapToItem(scroll,QPointF(0,0)).x()
            gaps=[]
            for key in keys+['strength']:
                value=window.findChild(QObject,'parameterValue_'+key)
                assert value,key
                right=value.mapToItem(scroll,QPointF(value.width(),0)).x()
                gaps.append(bar_left-right)
                assert right<=bar_left-7.5,(args.scale,name,key,right,bar_left)
            assert float(scroll.property('contentWidth'))<=float(scroll.property('availableWidth'))+.5
            flick=scroll.property('contentItem')
            content_height=float(flick.property('contentHeight'))
            max_y=max(0,content_height-float(flick.property('height')))
            flick.setProperty('contentY',max_y);settle()
            actual_y=float(flick.property('contentY'))
            assert -.5<=actual_y<=max_y+.5,(name,actual_y,max_y)
            expected=actual_y/content_height if content_height else 0
            assert abs(float(bar.property('position'))-expected)<.003,(name,bar.property('position'),expected)
            checks.append(dict(window=name,size=[width,height],tab=tab,min_gap=round(min(gaps),2),bar_visible=bar.isVisible()))
            flick.setProperty('contentY',0);settle()
            if args.scale=='native' and tab==0:
                image=window.grabWindow();assert not image.isNull()
                assert image.save(str(out/('scale-'+args.scale+'-'+name+'.png')))
    report=dict(ok=True,scale=args.scale,checks=checks,scope='Actual QML geometry, scroll position and native Windows captures when scale=native. Other scale factors test offscreen geometry only; no physical monitor DPI switch.')
    (out/('scale-'+args.scale+'.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)
finally:
    ctrl.close();window.close();app.processEvents();del engine;store.cleanup()
