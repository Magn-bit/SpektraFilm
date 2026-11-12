"""Capture the actual typography component at three physical DPI scales."""
from pathlib import Path
import json
import os
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'output/desktop-ui-refinement'


def capture(label):
    from PySide6.QtCore import QTimer,QUrl
    from PySide6.QtWidgets import QApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickWindow
    sys.path.insert(0,str(ROOT))
    from desktop.typography import load_mincho
    app=QApplication([]);family=load_mincho(app,ROOT)
    engine=QQmlApplicationEngine();ctx=engine.rootContext()
    for name,value in [('minchoFamily',family),('interfaceDisplayFamily',family),
                       ('interfaceEditorialFamily',family),('systemReduceMotion',True)]:
        ctx.setContextProperty(name,value)
    qml='''import QtQuick
import QtQuick.Window
import "components"
Window {
    width:460;height:225;visible:true;color:Theme.surface
    Column {
        anchors.fill:parent;anchors.margins:24;spacing:16
        MinchoText { text:"光影暗房 · Portra 400";font.pixelSize:Theme.heading }
        MinchoText { text:"曝光补偿     颗粒强度     胶片档案" }
        MinchoText { text:"+0.16 EV     60%     0.85×" }
        MinchoText { text:"原图对比   9,564 × 6,376";font.pixelSize:Theme.caption;color:Theme.secondary }
        MinchoText { text:"裁切   导出照片   恢复默认" }
    }
}'''
    engine.loadData(qml.encode(),QUrl.fromLocalFile(str(ROOT/'desktop/qml/FontCheck.qml')))
    if not engine.rootObjects():raise RuntimeError('Font QML failed')
    window=engine.rootObjects()[0]
    def save():
        frame=window.grabWindow()
        if not frame.save(str(OUTPUT/f'font-final-{label}.png')):raise RuntimeError('Capture failed')
        (OUTPUT/f'font-final-{label}.json').write_text(json.dumps(dict(
            target_percent=int(label),actual_dpr=window.devicePixelRatio(),
            logical_size=[window.width(),window.height()],pixels=[frame.width(),frame.height()],
            family=family,rendering='Product MinchoText / QtRendering / vertical hinting',
            body=15,caption=14),ensure_ascii=False,indent=2),encoding='utf-8')
        window.close();app.quit()
    QTimer.singleShot(350,save)
    return app.exec()


if __name__=='__main__':
    OUTPUT.mkdir(parents=True,exist_ok=True)
    if len(sys.argv)>1:sys.exit(capture(sys.argv[1]))
    else:
        # The physical host uses 150%; explicit factors exercise 100/125/150.
        for label,factor in [('100',2/3),('125',5/6),('150',1)]:
            env=dict(os.environ,QT_SCALE_FACTOR=str(factor))
            env.pop('QT_SCREEN_SCALE_FACTORS',None)
            subprocess.run([sys.executable,__file__,label],env=env,check=True)
        from PIL import Image,ImageDraw
        shots=[(label,Image.open(OUTPUT/f'font-final-{label}.png')) for label in ('100','125','150')]
        board=Image.new('RGB',(max(im.width for _,im in shots)+32,sum(im.height+40 for _,im in shots)+16),'#FCFCFB')
        draw=ImageDraw.Draw(board);top=8
        for label,frame in shots:
            draw.text((16,top),label+'% - original pixels',fill='#252725')
            board.paste(frame,(16,top+24));top+=frame.height+40
        board.save(OUTPUT/'font-final-scales.png')
        print('Captured product typography at 100%, 125%, 150%; review native pixels.')
