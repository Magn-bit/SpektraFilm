"""One bounded scene-histogram integration node; no RAW/export benchmark."""
from pathlib import Path
import json
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'vendor')]

import numpy as np
from PySide6.QtCore import QUrl, qInstallMessageHandler
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication
from PySide6 import QtSvg
from desktop.controller import Controller, PhotoProvider
from desktop.typography import load_mincho


def main():
    output = ROOT / 'output/scene-histogram-review'
    output.mkdir(parents=True, exist_ok=True)
    messages = []
    qInstallMessageHandler(lambda kind, context, message: messages.append(str(message)))
    app = QApplication([])
    app.setApplicationName('SpektraFilmSceneHistogramVerification')
    QQuickStyle.setStyle('Basic')
    family = load_mincho(app, ROOT)
    temporary = tempfile.TemporaryDirectory()
    provider = PhotoProvider()
    ctrl = Controller(provider, temporary.name)
    engine = QQmlApplicationEngine()
    engine.addImageProvider('photos', provider)
    for name, value in [('ctrl', ctrl), ('minchoFamily', family),
        ('interfaceDisplayFamily', app._interface_font_selection['display']),
        ('interfaceEditorialFamily', app._interface_font_selection['editorial']),
        ('systemReduceMotion', True)]:
        engine.rootContext().setContextProperty(name, value)
    # Test the actual reusable component; the full product/frozen-window node
    # is kept separate so a small new feature does not repeat the whole editor.
    source = '''import QtQuick
import "components" as C
Window {
 id:window;visible:true;width:360;height:230;color:C.Theme.surface
 C.SceneHistogram {id:graph;objectName:"sceneGraph";x:24;y:24;width:312}
}
'''
    engine.loadData(source.encode(), QUrl.fromLocalFile(str(ROOT / 'desktop/qml/scene-histogram-verification.qml')))
    assert engine.rootObjects(), messages
    window = engine.rootObjects()[0]
    model = ctrl.sceneHistogram

    def spin(seconds=.03):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            app.processEvents()
            time.sleep(.002)

    def wait(predicate, timeout=20):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            app.processEvents()
            if predicate():
                return
            time.sleep(.003)
        raise AssertionError(dict(state=model.state, statistics=model.statistics, busy=ctrl.busy, qml=messages[-8:]))

    started = time.perf_counter()
    report = {'scope': 'actual QObject/QML and native sampled scene, 1200x800 camera JPEG source with <=256px scene proxy; not RAW/export timing'}
    try:
        wait(lambda: model.state == 'empty')
        ctrl.add_paths([str(ROOT / 'output/current-ui/source-preview.jpg')])
        wait(lambda: ctrl.currentIndex >= 0 and not ctrl.busy)
        ctrl.setFilmEnabled(True)
        wait(lambda: model.state == 'ready' and model.data.get('current'))
        first = model.data
        assert set(first['rows']) == {'master', 'red', 'green', 'blue'}
        assert all(len(row) == 128 for row in first['rows'].values())
        assert max(model._scene.shape[:2]) <= 256
        assert ctrl.sourceDimensions == [1200, 800]
        report['identity'] = dict(real_channels=4, bins=128, scene_shape=list(model._scene.shape), source_dimensions=ctrl.sourceDimensions)

        before = model.statistics['measurements']
        ctrl.beginEdit()
        published = 0
        for index in range(16):
            amount = (index + 1) / 16 / 16
            ctrl.setSceneCurvePoints('red', [[0, amount], [1 - amount, 1], [1, 1]])
            spin(.04)
            published = max(published, model.statistics['measurements'] - before)
        ctrl.endEdit()
        wait(lambda: model.state == 'ready' and model.data.get('current') and not ctrl.busy)
        final = model.data
        assert final['exact'] and model.statistics['measurements'] - before >= 2
        delta = float(np.max(np.abs(np.array(final['rows']['red']) - np.array(first['rows']['red']))))
        assert delta > .005, delta
        assert model.statistics['source_reads'] == 1
        report['curve_drag'] = dict(measurements_during_input=published, total_new_measurements=model.statistics['measurements'] - before,
                                    red_distribution_max_delta=delta, raw_source_reads=1, exact_final=True)

        stable = model.statistics['measurements']
        ctrl.updateParameter('grain', 23)
        wait(lambda: not ctrl.busy)
        spin(.12)
        assert model.statistics['measurements'] == stable
        report['irrelevant_grain_change_does_not_remeasure'] = True

        # A late result from the preceding curve cannot restore it after a
        # new source stamp/request; two rapid current-curve changes coalesce.
        ctrl.setSceneCurvePoints('red', [[0, .03], [.97, 1], [1, 1]])
        ctrl.setSceneCurvePoints('red', [[0, .08], [.92, 1], [1, 1]])
        wait(lambda: model.state == 'ready' and model.data.get('current') and not ctrl.busy)
        assert model._published_key == model._desired['key']
        report['latest_request_publishes_its_own_curve'] = True
        spin(.08)
        assert window.grabWindow().save(str(output / 'scene-light.png'))
        ctrl.updatePreference('appearance', 'dark')
        spin(.1)
        assert window.grabWindow().save(str(output / 'scene-dark.png'))

        ctrl.setFilmEnabled(False)
        wait(lambda: model.state == 'disabled')
        assert not model.data
        model.setActive(False)
        count = model.statistics['measurements']
        ctrl.updateParameter('exposure', .37)
        spin(.12)
        assert model.state == 'inactive' and model.statistics['measurements'] == count
        report['empty_disabled_and_hidden_states'] = True
        errors = [m for m in messages if any(word in m for word in ('Error:', 'Unable to', 'Cannot '))]
        assert not errors, errors
        report.update(ok=True, qml_errors=errors, elapsed_seconds=time.perf_counter() - started,
                      statistics=model.statistics)
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False), flush=True)
    finally:
        ctrl.close()
        window.hide()
        del engine
        temporary.cleanup()


if __name__ == '__main__':
    main()
