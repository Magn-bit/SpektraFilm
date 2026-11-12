"""One bounded UI milestone for navigation, film hover and live mask input.

Uses an existing photo proxy, real controller/rendering and actual Qt pointer
events. No full-size export, historical benchmark replay or hash checks.
"""
from pathlib import Path
import argparse
import json
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'vendor')]
from PySide6.QtCore import QObject, QPoint, QPointF, QUrl, Qt
from PySide6.QtGui import QCursor
from PySide6.QtQml import QQmlApplicationEngine, QQmlEngine, QQmlExpression
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from desktop.controller import Controller, PhotoProvider
from desktop.typography import load_mincho
from desktop.imaging import read_thumbnail


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--photo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setOrganizationName('SpektraFilm UI refinement')
    app.setApplicationName('SpektraFilm UI refinement')
    app.setStyle('Fusion'); QQuickStyle.setStyle('Basic')
    family = load_mincho(app, ROOT)
    photo = out / 'photo-proxy.jpg'
    read_thumbnail(str(args.photo.resolve()), 1080).save(photo, quality=95)
    report = {'scope': 'Bounded UI input/overlay milestone; no output quality or universal FPS claim', 'checks': []}
    warnings = []

    def wait(predicate, seconds=25):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            app.processEvents(); time.sleep(.004)
            if predicate(): return
        raise AssertionError(('timeout', warnings[-12:]))

    def settle(seconds=.18):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            app.processEvents(); time.sleep(.004)

    def js(obj, code):
        expression = QQmlExpression(QQmlEngine.contextForObject(obj), obj, code)
        result = expression.evaluate()
        if expression.hasError(): raise AssertionError(expression.error().toString())
        return result[0] if isinstance(result, tuple) else result

    with tempfile.TemporaryDirectory(prefix='spektrafilm-ui-') as folder:
        ctrl = Controller(PhotoProvider(), folder)
        ctrl.updatePreference('appearance', 'light')
        ctrl.updatePreference('preview_long_edge', 800)
        engine = QQmlApplicationEngine(); engine.addImageProvider('photos', ctrl.provider)
        engine.warnings.connect(lambda items: warnings.extend(item.toString() for item in items))
        for key, value in dict(ctrl=ctrl, minchoFamily=family,
                interfaceDisplayFamily=app._interface_font_selection['display'],
                interfaceEditorialFamily=app._interface_font_selection['editorial'],
                systemReduceMotion=False,
                assetsUrl=QUrl.fromLocalFile(str(ROOT / 'assets') + '/').toString()).items():
            engine.rootContext().setContextProperty(key, value)
        engine.load(QUrl.fromLocalFile(str(ROOT / 'desktop/qml/Studio.qml')))
        assert engine.rootObjects(), warnings
        window = engine.rootObjects()[0]; window.resize(1366, 768); window.show()

        def walk(parent):
            for child in parent.childItems():
                yield child; yield from walk(child)

        def item(name):
            value = next((child for child in walk(window.contentItem()) if child.objectName() == name), None)
            if value is None: value = window.findChild(QObject, name)
            assert value is not None, name
            return value

        def click(target):
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier,
                             target.mapToScene(QPointF(target.width()/2, target.height()/2)).toPoint())
            settle()

        def shot(name):
            QCursor.setPos(window.mapToGlobal(QPoint(window.width()-3, window.height()-3)))
            settle(); assert window.grabWindow().save(str(out / name))

        try:
            ctrl.add_paths([str(photo)])
            wait(lambda: ctrl.frame and not ctrl.busy and item('photoViewport').property('hasImage'))
            window.setProperty('activeTask', 'basic'); settle()
            nav = item('toolSectionNavigator')
            assert js(nav, 'sections.length') >= 8
            click(nav)
            menu = item('toolSectionMenu'); assert menu.property('opened')
            option = item('toolSectionOption_4'); click(option)
            settle(.6)
            wait(lambda: js(nav, 'currentTitle') == '高动态范围', 2)
            assert js(nav, 'sections[4].item.expanded')
            shot('navigation-hdr-1366.png')
            # Expanded controls retain a fixed, reachable section directory.
            scroll = item('parameterScroll').property('contentItem')
            scroll.setProperty('contentY', scroll.property('contentHeight') - scroll.height()); settle()
            assert js(nav, 'currentTitle') != '曝光'
            click(nav); assert menu.property('opened'); click(item('toolSectionOption_1'))
            wait(lambda: js(nav, 'currentTitle') == '白平衡')
            report['checks'].append('Real menu clicks jump to and expand HDR/WB; scrolling updates fixed current-section label')
            toggle = item('toggleToolsButton'); gutter = item('toolsGutter')
            assert toggle.parentItem() == gutter
            click(toggle); assert not window.property('toolsVisible') and toggle.isVisible()
            click(toggle); assert window.property('toolsVisible')
            toggle.forceActiveFocus(); QTest.keyClick(window, Qt.Key_Space); settle()
            assert not window.property('toolsVisible')
            QTest.keyClick(window, Qt.Key_Space); settle(); assert window.property('toolsVisible')
            report['checks'].append('Gutter triangle click/Space collapse and restore; always reachable')
            for width, height in ((1366, 768), (1440, 900)):
                window.resize(width, height); settle(); shot(f'workspace-{width}.png')
            window.setProperty('activeTask', 'color'); settle()
            nav = item('toolSectionNavigator'); click(nav); click(item('toolSectionOption_3'))
            settle(.5)
            assert js(nav, 'currentTitle') == '色调曲线'
            wait(lambda: js(nav, 'sections[3].item.expanded'), 2)
            point_mode = item('pointCurveMode'); parameter_mode = item('parametricCurveMode')
            click(parameter_mode); assert item('curveEditor').property('parametricMode')
            click(point_mode); assert not item('curveEditor').property('parametricMode')
            shot('curve-modes-1440.png')
            report['checks'].append('Point/parametric curve labels and actual switching')

            window.setProperty('activeTask', 'film'); settle()
            click(item('filmArchiveButton'))
            popup = item('libraryPopup').property('item') or item('libraryPopup')
            wait(lambda: ctrl.filmLibrary.diagnostics['completed'] >= 3)
            stock_list = item('stockList')
            stock_list.setProperty('contentY', 22*104.); settle()
            wait(lambda: all(row['url'] for row in ctrl.filmLibrary.model.rows[22:26]))
            samples = []
            for row in ctrl.filmLibrary.model.rows[23:26]:
                card = item('filmCard_' + row['id'])
                pos = card.mapToScene(QPointF(card.width()-35, card.height()/2)).toPoint()
                QTest.mouseMove(window, pos)
                for delay in (.015, .035, .06):
                    settle(delay); image = window.grabWindow(); dpr = image.devicePixelRatio()
                    p = card.mapToScene(QPointF(card.width()-35, 15))
                    color = image.pixelColor(round(p.x()*dpr), round(p.y()*dpr))
                    samples.append(min(color.red(), color.green(), color.blue()))
            assert min(samples) >= 205, samples
            report['film_hover_min_channel'] = min(samples)
            report['checks'].append('Scrolled live film thumbnails and moving hover: no gray/black interpolated background')
            shot('film-library-1440.png'); js(popup, 'close()'); settle()

            window.setProperty('activeTask', 'local'); settle()
            viewport = item('photoViewport')
            frames = []
            window.frameSwapped.connect(lambda: frames.append(time.perf_counter()))
            for kind in ('brush', 'linear', 'radial'):
                ctrl.addMaskOfKind(kind); ctrl.updateMaskParameter('exposure', .8); settle()
                start = viewport.mapToScene(QPointF(viewport.property('imageX') + viewport.property('imageWidth')*.28,
                                                    viewport.property('imageY') + viewport.property('imageHeight')*.35)).toPoint()
                end = viewport.mapToScene(QPointF(viewport.property('imageX') + viewport.property('imageWidth')*.67,
                                                  viewport.property('imageY') + viewport.property('imageHeight')*.65)).toPoint()
                history = len(ctrl._history.get(ctrl.currentIndex, [])); versions = []
                costs = []; frames.clear()
                QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
                for i in range(1, 81):
                    position = start + (end-start)*(i/80)
                    before = time.perf_counter(); QTest.mouseMove(window, position); app.processEvents()
                    costs.append((time.perf_counter()-before)*1000)
                    time.sleep(.008); app.processEvents(); versions.append(ctrl._mask_overlay.version)
                QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, end); settle()
                assert ctrl._before is None
                assert len(ctrl._history.get(ctrl.currentIndex, [])) == history+1
                if kind == 'brush':
                    assert len(set(versions)) >= 3, 'Brush overlay starved until release'
                else:
                    assert item('gradientMaskOverlay').isVisible()
                    assert not ctrl._mask_overlay.visible
                ctrl.undo(); ctrl.redo(); settle()
                costs.sort()
                gaps = [(b-a)*1000 for a,b in zip(frames,frames[1:])]
                gaps.sort()
                report[kind] = {'pointer_dispatch_median_ms': round(costs[len(costs)//2], 3),
                                'pointer_dispatch_p95_ms': round(costs[int(len(costs)*.95)], 3),
                                'presented_frames_during_input': len(frames),
                                'frame_gap_p95_ms': round(gaps[int(len(gaps)*.95)], 3) if gaps else None,
                                'brush_prefix_versions': len(set(versions)) if kind == 'brush' else None,
                                'single_undo': True}
                shot('mask-'+kind+'-1440.png')
                if kind=='brush':
                    # Erasure remains in source coordinates and is one undo step.
                    from dataclasses import replace
                    import numpy as np
                    from shared.local_masks import rasterize_mask
                    layer=ctrl._settings.masks[-1]
                    before=rasterize_mask(layer, 160, 100).copy()
                    token=ctrl.beginMaskStroke(.5,.5,.08,.5,1.,True)
                    ctrl.appendMaskPoints(token,[[.6,.6]])
                    ctrl.endMaskStroke(token)
                    assert np.sum(rasterize_mask(ctrl._settings.masks[-1],160,100))<np.sum(before)
                    ctrl.undo(); assert ctrl._settings.masks[-1]==layer
                    report['checks'].append('Brush erasure reduces true coverage; undo restores full stroke')
                else:
                    # Inspect the isolated GPU overlay, not a composited screenshot.
                    overlay=item('gradientMaskOverlay')
                    grab=overlay.grabToImage(); wait(lambda: not grab.image().isNull())
                    image=grab.image(); width,height=image.width(),image.height()
                    layer=ctrl._settings.masks[-1]
                    alpha=rasterize_mask(layer,width,height)
                    # Item grabs exclude the item's own opacity/parent transform.
                    opacity=1.
                    errors=[]
                    for y in range(height//10,height, max(1,height//9)):
                        for x in range(width//10,width,max(1,width//9)):
                            errors.append(abs(image.pixelColor(x,y).alpha()/255-opacity*alpha[y,x]))
                    assert max(errors)<.015,(kind,max(errors))
                    report[kind]['overlay_alpha_max_error']=round(float(max(errors)),5)
                    ctrl.invertMask(); settle()
                    reverse=overlay.grabToImage(); wait(lambda: not reverse.image().isNull())
                    other=reverse.image()
                    assert max(abs((image.pixelColor(x,y).alpha()+other.pixelColor(x,y).alpha())/255-opacity)
                        for x,y in ((width//3,height//3),(width//2,height//2),(width*2//3,height*2//3)))<.012
                    ctrl.invertMask()
            report['checks'].append('Brush/linear/radial real drags, completed brush prefixes during input, one undo/redo each')
            ctrl.updateGeometry('rotation',7)
            ctrl.updateGeometry('vertical',12)
            ctrl.rotateQuarterTurn(1)
            ctrl.setGeometryFlag('flip_horizontal',True)
            ctrl.applyCrop([.08,.1,.9,.94])
            wait(lambda: not ctrl.busy)
            from PIL import Image
            from shared.geometry import apply_geometry_image
            geometry_errors={}
            for layer in ctrl._settings.masks[-2:]:
                ctrl.selectMask(layer.id); settle()
                overlay=item('gradientMaskOverlay')
                grab=overlay.grabToImage(); wait(lambda: not grab.image().isNull())
                image=grab.image(); width,height=image.width(),image.height()
                reference=apply_geometry_image(Image.fromarray(rasterize_mask(layer,*ctrl.sourceDimensions)),ctrl._settings.geometry)
                alpha=np.asarray(reference.resize((width,height),Image.Resampling.BILINEAR))
                error=max(abs(image.pixelColor(x,y).alpha()/255-alpha[y,x])
                    for y in range(height//10,height,max(1,height//9))
                    for x in range(width//10,width,max(1,width//9)))
                assert error<.025,(layer.kind,'transformed coverage',error)
                geometry_errors[layer.kind]=round(float(error),5)
            report['transformed_overlay_alpha_max_error']=geometry_errors
            report['checks'].append('GPU selection matches final mask raster after crop, rotation, perspective, flip and quarter turn')
            shot('mask-transformed-1440.png')
            ctrl.resetGeometry();settle()
            ctrl.updatePreference('appearance', 'dark'); settle(); shot('dark-masks-1440.png')
            report['qml_warnings'] = warnings
            assert not warnings, warnings
            report['ok'] = True
            (out/'review.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        finally:
            if not report.get('ok'):
                (out/'partial-review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            window.setProperty('closeApproved', True); window.close(); ctrl.close()
            engine.deleteLater(); app.processEvents()


if __name__ == '__main__': main()
