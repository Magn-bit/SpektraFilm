"""A bounded real-window theme/tint node; no export or full-detail rebench."""
from pathlib import Path
import json,sys,tempfile,time
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
from PySide6.QtCore import QObject,QPointF,QSize,Qt,QUrl,qInstallMessageHandler
from PySide6.QtGui import QColor
from PySide6.QtQml import QQmlApplicationEngine,QQmlComponent,QQmlEngine,QQmlExpression
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from desktop.controller import Controller,PhotoProvider
from desktop.typography import load_mincho
from desktop.icon_provider import theme_icon

messages=[];qInstallMessageHandler(lambda kind,context,message:messages.append(str(message)))
app=QApplication([]);app.setApplicationName('SpektraFilmTheme');app.setOrganizationName('SpektraFilmVerification')
QQuickStyle.setStyle('Basic');family=load_mincho(app,ROOT)
store=tempfile.TemporaryDirectory();provider=PhotoProvider();ctrl=Controller(provider,store.name)
engine=QQmlApplicationEngine();engine.addImageProvider('photos',provider)
for name,value in [('ctrl',ctrl),('minchoFamily',family),('interfaceDisplayFamily',app._interface_font_selection['display']),
    ('interfaceEditorialFamily',app._interface_font_selection['editorial']),('interfaceFontDescription',''),
    ('assetsUrl',QUrl.fromLocalFile(str(ROOT/'assets')+'/').toString()),('systemReduceMotion',True)]:engine.rootContext().setContextProperty(name,value)
engine.load(QUrl.fromLocalFile(str(ROOT/'desktop/qml/Studio.qml')))
assert engine.rootObjects(),messages
window=engine.rootObjects()[0];window.resize(1366,768);window.show()
output=ROOT/'output/dark-theme-review';output.mkdir(parents=True,exist_ok=True)

def wait(predicate):
    deadline=time.monotonic()+25
    while not predicate() and time.monotonic()<deadline:app.processEvents();time.sleep(.005)
    assert predicate(),ctrl.status
def items(parent):
    for child in parent.childItems():yield child;yield from items(child)
def find(name):
    return next((child for child in items(window.contentItem()) if child.objectName()==name),None) or window.findChild(QObject,name)
def js(obj,source):
    expression=QQmlExpression(QQmlEngine.contextForObject(obj),obj,source);value=expression.evaluate()
    assert not expression.hasError(),expression.error().toString()
    return value[0] if isinstance(value,tuple) else value
def luminance(color):
    c=QColor(color);parts=[c.redF(),c.greenF(),c.blueF()]
    values=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in parts]
    return .2126*values[0]+.7152*values[1]+.0722*values[2]
def contrast(a,b):
    values=sorted([luminance(a),luminance(b)])
    return (values[1]+.05)/(values[0]+.05)
def crop(image,obj):
    ratio=image.width()/window.width();at=obj.mapToScene(QPointF(0,0))
    return image.copy(round(at.x()*ratio),round(at.y()*ratio),round(obj.width()*ratio),round(obj.height()*ratio))
try:
    ctrl.add_paths([str(ROOT/'output/current-ui/source-preview.jpg')]);wait(lambda:bool(ctrl.frame) and not ctrl.busy)
    window.setProperty('activeTask','basic');window.setProperty('toolsVisible',True)
    export=find('exportActionButton');task=find('task_basic');glyph=find('settingsGlyph');plot=find('globalHistogramPlot')
    assert export and task and glyph and plot
    sections=[obj for obj in items(window.contentItem()) if obj.property('title')=='影调' and obj.property('expanded') is not None]
    assert sections;header=sections[0].childItems()[0]
    report={'checks':[],'logical_size':[1366,768],'contrasts':{}}
    glyphs={}
    for appearance in ('light','dark','light','dark'):
        ctrl.updatePreference('appearance',appearance);QTest.qWait(100)
        at=header.mapToScene(QPointF(header.width()/2,header.height()/2)).toPoint()
        QTest.mouseMove(window,at);QTest.qWait(50)
        image=window.grabWindow();assert not image.isNull()
        suffix='dark' if appearance=='dark' else 'light'
        assert image.save(str(output/(suffix+'-editor-1366.png')))
        glyphs[suffix]=crop(image,glyph);glyphs[suffix].save(str(output/(suffix+'-settings-glyph.png')))
        glyph_values=[glyphs[suffix].pixelColor(x,y).lightnessF() for y in range(glyphs[suffix].height()) for x in range(glyphs[suffix].width())]
        assert (max(glyph_values)>.7 if appearance=='dark' else min(glyph_values)<.3),'settings strokes must use current theme ink'
        export_ratio=contrast(export.property('contentItem').property('color'),export.property('background').property('color'))
        selected_ratio=contrast(task.property('contentItem').property('color'),task.property('background').property('color'))
        title=header.property('contentItem').childItems()[0]
        hover_ratio=contrast(title.property('color'),header.property('background').property('color'))
        assert min(export_ratio,selected_ratio,hover_ratio)>=4.5,(appearance,export_ratio,selected_ratio,hover_ratio)
        report['contrasts'][appearance]=dict(export=round(export_ratio,2),selected_task=round(selected_ratio,2),section_hover=round(hover_ratio,2))
        if appearance=='dark':
            assert luminance(plot.parentItem().childItems()[0].property('color'))<.1
            for name in ('crop','plus','trash','chevron'):
                image=theme_icon('ui-icon/'+name+'/%23E9EAE2',QSize(32,32));assert not image.isNull()
                opaque=[image.pixelColor(x,y) for y in range(image.height()) for x in range(image.width()) if image.pixelColor(x,y).alpha()>240]
                assert opaque and all(abs(c.red()-233)<=1 and abs(c.green()-234)<=1 and abs(c.blue()-226)<=1 for c in opaque)
    assert glyphs['light']!=glyphs['dark'],'Canvas icon must repaint when appearance switches in the same window'
    # Instantiate the existing components in one bounded overlay so offscreen
    # controls can be checked without repeating export/RAW workflows.
    component=QQmlComponent(engine)
    component.setData(b'''import QtQuick
import "../../desktop/qml/components"
Rectangle {
    width:820;height:690;z:1000;color:Theme.surface
    SettingsIcon {objectName:'themeSettings';x:32;y:28}
    OrientationIcon {objectName:'themeOrientation';x:82;y:28}
    MaterialSelector {objectName:'themeMaterial';x:32;y:72;width:330;label:'test';choices:[{id:'one',name:'one'},{id:'two',name:'two'}];value:'one'}
    GrainSelector {objectName:'themeGrain';x:32;y:120;width:330}
    LevelsEditor {objectName:'themeLevels';x:32;y:184;width:330;channel:'red'}
    CurveEditor {objectName:'themeCurve';x:410;y:28;width:360;channel:'blue'}
    LatitudePanel {objectName:'themeLatitude';x:410;y:480;width:360}
}''',QUrl.fromLocalFile(str(output/'theme-components.qml')))
    overlay=component.create();assert overlay,component.errors()
    overlay.setParentItem(window.contentItem());overlay.setParent(window.contentItem())
    snapshots={}
    for appearance in ('light','dark','light','dark'):
        ctrl.updatePreference('appearance',appearance);QTest.qWait(100)
        image=window.grabWindow();assert image.save(str(output/(appearance+'-components.png')))
        for name in ('themeSettings','themeOrientation','themeMaterial','themeGrain','themeCurve','themeLevels','themeLatitude'):
            obj=find(name);assert obj
            sample=crop(image,obj)
            if appearance=='dark' and name in ('themeSettings','themeOrientation'):
                values=[sample.pixelColor(x,y).lightnessF() for y in range(sample.height()) for x in range(sample.width())]
                assert max(values)>.7,(appearance,name,'unrepainted Canvas')
            snapshots[(appearance,name)]=sample
        for name in ('themeMaterial','themeGrain'):
            canvas=next(obj for obj in items(find(name)) if 'Canvas' in obj.metaObject().className())
            sample=crop(image,canvas)
            values=[sample.pixelColor(x,y).lightnessF() for y in range(sample.height()) for x in range(sample.width())]
            assert (max(values)>.55 if appearance=='dark' else min(values)<.5),(name,appearance)
        if appearance=='dark':
            assert contrast(find('themeCurve').property('channelColor'),'#373B34')>=3
            assert contrast(find('themeLevels').property('channelColor'),'#373B34')>=3
    for name in ('themeSettings','themeOrientation','themeMaterial','themeGrain','themeCurve','themeLevels','themeLatitude'):
        assert snapshots[('light',name)]!=snapshots[('dark',name)],name
    overlay.setVisible(False);overlay.deleteLater();app.processEvents()
    errors=[text for text in messages if 'Error:' in text or 'Unable to' in text or 'Cannot ' in text or 'QML Image:' in text]
    assert not errors,errors
    report.update(qml_errors=errors,checks=['light-dark-light-dark in one running window','primary/selected/hover text contrast >= 4.5:1','dark histogram surface','pure-black SVG strokes tint to exact requested RGB','settings/orientation/dropdown Canvas repaints with theme','RGB curve/levels strokes contrast >=3:1 on dark surface','latitude Canvas updates on theme change'],status='passed')
    (output/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
finally:
    ctrl.close();window.hide();del engine;store.cleanup()
