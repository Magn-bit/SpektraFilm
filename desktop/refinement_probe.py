"""One bounded UI integration node, reusable by the source and frozen app.

Uses the application's active test photo, real QML controls and controller.
It never opens user photographs for writing or runs a full-RAW benchmark.
"""
from dataclasses import fields
import json
from pathlib import Path
import time

from PySide6.QtCore import QObject,QPointF,Qt
from PySide6.QtQml import QQmlEngine,QQmlExpression
from PySide6.QtTest import QTest


def run_refinement_probe(app,window,ctrl,directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    report={'scope':'bounded real QML workflow on the active test source; no RAW benchmark','checks':[]}
    def wait(predicate,seconds=35):
        until=time.monotonic()+seconds
        while not predicate() and time.monotonic()<until:
            app.processEvents();time.sleep(.008)
        assert predicate(),(ctrl.status,ctrl.fullDetail.state)
    def item(name):
        def walk(parent):
            for child in parent.childItems():
                if child.objectName()==name:return child
                found=walk(child)
                if found:return found
        result=walk(window.contentItem())
        return result or window.findChild(QObject,name)
    def js(obj,script):
        expression=QQmlExpression(QQmlEngine.contextForObject(obj),obj,script)
        value=expression.evaluate()
        assert not expression.hasError(),expression.error().toString()
        value=value[0] if isinstance(value,tuple) else value
        return value.toVariant() if hasattr(value,'toVariant') else value
    def point(obj,x,y):return obj.mapToScene(QPointF(x,y)).toPoint()
    def capture(name):
        # Capture the settled page, not a translucent frame mid-transition.
        QTest.qWait(600)
        assert window.grabWindow().save(str(directory/(name+'.png')))
    def reveal(obj):
        flick=scroll.property('contentItem')
        top=obj.mapToScene(QPointF(0,0)).y()-scroll.mapToScene(QPointF(0,0)).y()
        target=float(flick.property('contentY'))+top-max(0,(scroll.height()-obj.height())/2)
        flick.setProperty('contentY',max(0,min(target,float(flick.property('contentHeight'))-float(flick.property('height')))))
        QTest.qWait(40)
    def check(name):report['checks'].append(name)
    view=item('photoViewport')
    original_settings=ctrl._settings
    original_selection=set(ctrl._selected)
    original_task=window.property('activeTask')
    original_size=(window.width(),window.height())
    original_preferences=dict(ctrl.preferences)
    clipboard=(dict(ctrl._settings_clipboard),list(ctrl._copied_categories),list(ctrl._clipboard_categories),ctrl._clipboard_source)
    try:
        wait(lambda:bool(ctrl.frame) and not ctrl.busy)
        window.resize(1366,768);window.setProperty('toolsVisible',True)
        window.setProperty('activeTask','color');window.setProperty('comparing',False)
        color=item('colorToolsPanel');color.setProperty('openGroup','curves')
        curve=item('curveEditor');graph=item('curveGraph')
        scroll=item('parameterScroll')
        if scroll:scroll.property('contentItem').setProperty('contentY',0)
        ctrl.setParametricCurve('master','shadows',24,False)
        ctrl.setCurvePoints('master',[[0,0],[.5,.57],[1,1]])
        wait(lambda:not ctrl.busy)
        app.processEvents()
        x=js(curve,'graphX(.5)')*graph.width();y=.43*graph.height()
        assert graph.isVisible() and graph.isEnabled()
        before=len(ctrl._history.get(ctrl.currentIndex,[]))
        start=point(graph,x,y);end=point(graph,x+18,y-10)
        QTest.mousePress(window,Qt.LeftButton,Qt.NoModifier,start)
        for i in range(1,9):QTest.mouseMove(window,start+(end-start)*i/8,3)
        QTest.mouseRelease(window,Qt.LeftButton,Qt.NoModifier,end);app.processEvents()
        assert not curve.property('dragging')
        assert len(ctrl._history.get(ctrl.currentIndex,[]))==before+1
        assert abs(ctrl._settings.curves.master[1][1]-.57)>.005
        moved=ctrl._settings.curves
        ctrl.undo();assert abs(ctrl._settings.curves.master[1][1]-.57)<1e-6
        ctrl.redo();assert ctrl._settings.curves==moved
        check('composed parametric/point curve real first-press drag, one history, undo/redo')
        curve.setProperty('parametricMode',True);capture('parametric-1366')
        ctrl.setChannelMixer('red','blue',21.5)
        assert ctrl._settings.channel_mixer.red.blue==21.5
        ctrl.undo();assert ctrl._settings.channel_mixer.red.blue==0
        ctrl.redo();assert ctrl._settings.channel_mixer.red.blue==21.5
        color.setProperty('openGroup','mixer');capture('channel-mixer-1366')
        check('channel mixer typed values and undo/redo')
        color.setProperty('openGroup','grading');color.setProperty('zone','master')
        QTest.qWait(60);wheel=item('gradingWheelCanvas');reveal(wheel)
        before=len(ctrl._history.get(ctrl.currentIndex,[]))
        at=point(wheel,wheel.width()*.67,wheel.height()*.43)
        QTest.mousePress(window,Qt.LeftButton,Qt.NoModifier,at)
        QTest.mouseMove(window,at+point_delta(14,-6),6)
        QTest.mouseRelease(window,Qt.LeftButton,Qt.NoModifier,at+point_delta(14,-6))
        app.processEvents()
        assert ctrl._settings.grading.master.saturation>0
        assert len(ctrl._history.get(ctrl.currentIndex,[]))==before+1
        saturation=ctrl._settings.grading.master.saturation
        QTest.keyClick(window,Qt.Key_Up,Qt.ShiftModifier);app.processEvents()
        assert abs(ctrl._settings.grading.master.saturation-saturation-.1)<1e-6
        capture('master-wheel-1366');check('master wheel pointer transaction and fine keyboard step')
        ctrl.setClipboardCategories(['exposure','WB'])
        ctrl.copySettings(['exposure','WB'])
        from .controller import Controller,PhotoProvider
        restored=Controller(PhotoProvider(),ctrl._store.parent)
        try:
            assert restored.clipboardInfo==ctrl.clipboardInfo
            assert restored._settings_clipboard==ctrl._settings_clipboard
        finally:restored.close()
        check('clipboard copied categories, source and canonical values persist across controller restart')
        ctrl._replace_tools(**{field.name:getattr(original_settings,field.name) for field in fields(original_settings)});wait(lambda:not ctrl.busy)
        window.setProperty('activeTask','basic');js(view,'setZoom(2,width/2,height/2)')
        wait(lambda:ctrl.fullDetail.ready)
        assert item('fullDetailTile').isVisible()
        assert all(0<=v<=1 for v in ctrl.fullDetail.rect)
        window.setProperty('comparing',True)
        wait(lambda:ctrl.fullDetail.ready and bool(ctrl.fullDetail.originalSource))
        assert item('comparisonDetailTile').isVisible()
        capture('detail-compare-1366');check('visible source-size detail tile and same-coordinate natural comparison')
        window.setProperty('comparing',False);js(view,'fit()')
        ctrl.updatePreference('working_cache_mb',1024)
        assert ctrl.fullDetail.storageUsage['working']['limit']==1024*1024**2
        settings=item('settingsPanel');js(settings,"category='resources';open()")
        capture('resources-1366');check('three bounded storage consumers and current occupancy shown')
        ctrl.updatePreference('appearance','dark');settings.setProperty('category','interface')
        capture('dark-settings-1366');js(settings,'close()')
        capture('dark-editor-1366');check('dark theme uses surface/foreground tokens with real active controls')
        ctrl.updatePreference('appearance','light');window.resize(1440,900)
        window.setProperty('activeTask','film')
        ctrl.setFilmEnabled(True);ctrl.setFilmOption('grain_enabled',False);ctrl.setFilmOption('halation_enabled',False)
        assert not ctrl._settings.grain_enabled and not ctrl._settings.halation_enabled
        kept=(ctrl._settings.grain,ctrl._settings.halation)
        ctrl.setFilmOption('grain_enabled',True);ctrl.setFilmOption('halation_enabled',True)
        assert kept==(ctrl._settings.grain,ctrl._settings.halation)
        wait(lambda:not ctrl.busy);capture('film-1440');check('independent film-effect switches preserve parameter amounts')
        from .batch import plan_recipe_exports
        from shared.output_recipes import OutputRecipe
        with __import__('tempfile').TemporaryDirectory() as temporary:
            recipe=OutputRecipe(naming='{date}_{name}_{film}_{paper}_{index}')
            planned=plan_recipe_exports(ctrl._photos,[ctrl.currentIndex],recipe,temporary)
            name=Path(planned[0][1]).name
            assert name.endswith('_0001.jpg') and '{' not in name and '}' not in name
            assert Path(planned[0][1]).parent.name==recipe.subfolder
        check('date/material/index filename template planned without pixel decode, source-relative type folder contract')
        from .imaging import Settings
        from .native_spectral import render_spectral
        from dataclasses import replace
        import numpy as np
        calibration=np.empty((8,24,3),dtype=np.float32)
        calibration[:,:8]=[.08,.12,.8];calibration[:,8:16]=[.3,.5,.1];calibration[:,16:]=[.6,.14,.08]
        sample=Settings(film_enabled=True,grain=0,halation=0,lens_correction=False,defringe=False)
        low=render_spectral(calibration,replace(sample,exposure=-8))
        high=render_spectral(calibration,replace(sample,exposure=8))
        assert Settings.from_mapping({'exposure':8}).exposure==8
        assert np.isfinite(low).all() and np.isfinite(high).all() and float(high.mean())>float(low.mean())
        di0=render_spectral(calibration,sample,digital_intermediate=True,output_color_space='ProPhoto RGB')
        di1=render_spectral(calibration,sample,digital_intermediate=True,output_color_space='ProPhoto RGB',di_blue_compensation=True)
        assert np.isfinite(di1).all() and float(np.max(np.abs(di1-di0)))>1e-6
        report['di_blue_compensation_delta']=float(np.max(np.abs(di1-di0)))
        check('native +/-8 EV finite response and genuine DI blue compensation changes Cineon samples')
        ctrl.updatePreference('frame_body_seed',451923)
        composition=ctrl.composition
        selected=[ctrl._photos[ctrl.currentIndex]]
        assert composition.open_selection(selected)
        wait(lambda:not composition.state['busy'])
        assert composition.frame_seed==451923
        ctrl.updatePreference('frame_body_seed',91625)
        assert composition.frame_seed==451923,'Changing new-photo defaults must not rewrite an open layout'
        assert composition.open_selection(selected)
        wait(lambda:not composition.state['busy'])
        assert composition.frame_seed==91625
        ctrl.updatePreference('frame_body_seed',0)
        assert composition.open_selection(selected)
        wait(lambda:not composition.state['busy'])
        deterministic_seed=composition.frame_seed
        assert composition.open_selection(selected)
        wait(lambda:not composition.state['busy'])
        assert composition.frame_seed==deterministic_seed
        check('new composition body default is consumed without changing an open layout; per-photo body remains deterministic')
        ctrl.setFilmOption('digital_intermediate',True)
        wait(lambda:not ctrl.busy)
        assert js(item('paperSelector'),'value')=='di'
        assert ctrl.directScan
        ctrl.undo();assert not ctrl._settings.digital_intermediate
        check('DI paper-list entry binds the real alternative view and restores by undo')
        ctrl.setPaper('auto');ctrl.setFilmOption('hdr_enabled',True)
        ctrl.updateParameter('hdr_peak_stops',2.5)
        wait(lambda:not ctrl.busy)
        assert ctrl._settings.hdr_enabled and ctrl._settings.hdr_peak_stops==2.5
        assert not ctrl.outputRecipeError({'format':'jpeg','color_space':'sRGB'})
        assert ctrl.outputRecipeError({'format':'tiff'})
        reveal(item('hdrPeak'));capture('hdr-controls-1440')
        from .output import export_recipe
        from .hdr_output import decode_jpeg
        from .imaging import photo_dimensions
        target=directory/'exact-build-hdr.jpg'
        export_recipe(ctrl.currentPath,target,replace(sample,hdr_enabled=True,hdr_peak_stops=2.5),OutputRecipe())
        decoded,info=decode_jpeg(target)
        expected=photo_dimensions(ctrl.currentPath)
        assert (info['width'],info['height'])==expected
        assert (info['map_width'],info['map_height'])==expected
        assert np.isfinite(decoded).all() and abs(info['headroom']-2**2.5)<1e-5
        report['hdr_container']=info
        check('current-build HDR controls, recipe compatibility and source-size gain-map JPEG independently decoded')
        ctrl.setFilmOption('hdr_enabled',False)
        display=ctrl.colorDisplay;previous_space=display.canvasSpace
        display.setCanvasSpace('Display P3');assert display.snapshot()['canvas_space']=='Display P3'
        display.setCanvasSpace(previous_space)
        wait(lambda:not ctrl.busy)
        window.setProperty('activeTask','color')
        QTest.qWait(100)
        scroll=item('parameterScroll')
        if scroll:scroll.property('contentItem').setProperty('contentY',0)
        QTest.qWait(100)
        styles=item('styleLibrary');entry=item('openStylesButton')
        reveal(entry)
        assert ctrl.stylePresets[0]['id']=='none'
        assert len([p for p in ctrl.stylePresets if p['kind']=='original'])==18
        assert entry.property('text')!='浏览精选'
        def click(control):
            QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,point(control,control.width()/2,control.height()/2))
            app.processEvents()
        click(entry);wait(lambda:styles.property('opened'))
        listing=item('stylePresetList')
        js(listing,'positionViewAtIndex(5,ListView.Center)');QTest.qWait(100)
        portrait=item('stylePreset_portrait-window');assert portrait and portrait.isVisible()
        click(portrait);assert styles.property('chosenId')=='portrait-window'
        click(item('applyStyleButton'));wait(lambda:not styles.property('opened') and not ctrl.busy)
        assert entry.property('text')=='窗边自然光'
        capture('style-selected-1440')
        ctrl.setChannelMixer('red','blue',18)
        preserved={key:ctrl.settings[key] for key in ('exposure','temperature','tint','stock','masks','geometry')}
        click(entry);wait(lambda:styles.property('opened'))
        js(listing,'positionViewAtBeginning()');QTest.qWait(100)
        click(item('stylePreset_none'));click(item('applyStyleButton'))
        wait(lambda:not styles.property('opened') and not ctrl.busy)
        assert ctrl.currentStyleName=='无预设' and ctrl._settings.channel_mixer.red.blue==0
        assert preserved=={key:ctrl.settings[key] for key in preserved}
        capture('style-none-1440')
        check('18 practical styles, actual picker clicks and current name; none resets mixer and retains photo-specific settings')
        report['ok']=True
    finally:
        for popup_name in ('settingsPanel','outputRecipeDialog','exportDialog','styleLibrary'):
            popup=item(popup_name)
            if popup:js(popup,'close()')
        js(view,'fit()');window.setProperty('comparing',False)
        ctrl._settings_clipboard,ctrl._copied_categories,ctrl._clipboard_categories,ctrl._clipboard_source=clipboard
        ctrl._save_settings_clipboard()
        for key,value in original_preferences.items():
            if ctrl.preferences[key]!=value:ctrl.updatePreference(key,value)
        ctrl._selected=original_selection
        ctrl._replace_tools(**{field.name:getattr(original_settings,field.name) for field in fields(original_settings)})
        window.setProperty('activeTask',original_task)
        window.resize(*original_size)
        (directory/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


def point_delta(x,y):
    from PySide6.QtCore import QPoint
    return QPoint(x,y)
