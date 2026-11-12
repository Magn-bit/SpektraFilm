"""Bounded real QML drag probe; measures dispatch and presented frames, not RAW export."""
from pathlib import Path
import argparse
import json
import math
import statistics
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'vendor')]
from PySide6.QtCore import QTimer, QUrl, Qt, QPoint, QObject, qInstallMessageHandler
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
import desktop.controller as controller_module
from desktop.controller import Controller, PhotoProvider
from desktop.typography import load_mincho


def summary(values):
    values = sorted(values)
    if not values:
        return dict(count=0)
    return dict(count=len(values), median_ms=round(statistics.median(values), 3),
                p95_ms=round(values[math.ceil(len(values)*.95)-1], 3), max_ms=round(max(values), 3))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--label', required=True)
    parser.add_argument('--qml-root', type=Path, default=ROOT/'desktop/qml')
    args = parser.parse_args()
    out = ROOT/'output/slider-interaction'
    out.mkdir(parents=True, exist_ok=True)
    messages = []
    qInstallMessageHandler(lambda kind, context, message: messages.append(str(message)))
    app = QApplication([])
    app.setStyle('Fusion')
    QQuickStyle.setStyle('Basic')
    family = load_mincho(app, ROOT)
    store = tempfile.TemporaryDirectory()
    provider = PhotoProvider()
    ctrl = Controller(provider, store.name)
    engine = QQmlApplicationEngine()
    engine.addImageProvider('photos', provider)
    ctx = engine.rootContext()
    for key, value in dict(ctrl=ctrl, minchoFamily=family,
            interfaceDisplayFamily=family, interfaceEditorialFamily=family,
            interfaceFontDescription='朱雀仿宋 / Noto Serif SC', systemReduceMotion=False,
            assetsUrl=QUrl.fromLocalFile(str(ROOT/'assets')+'/').toString()).items():
        ctx.setContextProperty(key, value)
    engine.load(QUrl.fromLocalFile(str(args.qml_root/'Studio.qml')))
    assert engine.rootObjects(), messages
    window = engine.rootObjects()[0]
    window.resize(1366, 768)
    window.show()
    report = dict(label=args.label, size_dp=[1366, 768],
                  scope='Actual Qt pointer input / 640px native spectral preview; Windows host, not Android')
    current = None
    result = 0
    deadline = time.perf_counter()+60
    original_asdict = controller_module.asdict
    original_changed = ctrl._changed

    def measured_asdict(value):
        start = time.perf_counter()
        answer = original_asdict(value)
        if current is not None:
            current['asdict_ms'].append((time.perf_counter()-start)*1000)
        return answer

    def measured_changed():
        start = time.perf_counter()
        original_changed()
        if current is not None:
            current['changed_ms'].append((time.perf_counter()-start)*1000)

    controller_module.asdict = measured_asdict
    ctrl._changed = measured_changed

    def frame():
        if current is not None:
            current['frames'].append(time.perf_counter())
    window.frameSwapped.connect(frame)

    def drag(parameter, task, finished):
        nonlocal current
        window.setProperty('activeTask', task)
        QTest.qWait(80)
        handle = window.findChild(QQuickItem, 'parameterHandle_'+parameter)
        assert handle is not None, parameter
        scroll = window.findChild(QObject, 'parameterScroll')
        flick = scroll.property('contentItem')
        position = handle.mapToItem(flick, handle.boundingRect().center())
        flick.setProperty('contentY', max(0, min(float(flick.property('contentHeight'))-flick.height(),
                                               position.y()-flick.height()/2)))
        QTest.qWait(50)
        start = handle.mapToScene(handle.boundingRect().center()).toPoint()
        top = flick.mapToScene(flick.boundingRect().topLeft()).y()
        assert top < start.y() < top+flick.height(), (parameter, start, top, flick.height())
        initial_value = ctrl.settings[parameter]
        initial_history = len(ctrl._history.get(ctrl.currentIndex, []))
        current = dict(asdict_ms=[], changed_ms=[], frames=[], dispatch_ms=[], ticks=[],
                       initial_generation=ctrl._generation)
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
        positions = [int(65*math.sin(math.pi*i/160)) for i in range(1, 81)]
        index = 0
        timer = QTimer()
        timer.setTimerType(Qt.PreciseTimer)
        timer.setInterval(8)

        def tick():
            nonlocal index, current
            try:
                current['ticks'].append(time.perf_counter())
                begin = time.perf_counter()
                QTest.mouseMove(window, start+QPoint(positions[index], 0))
                current['dispatch_ms'].append((time.perf_counter()-begin)*1000)
                index += 1
                if index < len(positions):
                    return
                timer.stop()
                QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, start+QPoint(positions[-1], 0))
                data = current
                current = None
                deltas = lambda values: [(b-a)*1000 for a,b in zip(values, values[1:])]
                report[parameter] = dict(pointer_dispatch=summary(data['dispatch_ms']),
                    controller_change=summary(data['changed_ms']), asdict=summary(data['asdict_ms']),
                    input_intervals=summary(deltas(data['ticks'])),
                    presented_frame_intervals=summary(deltas(data['frames'])),
                    presented_frames=len(data['frames']), final_value=ctrl.settings[parameter],
                    settings_changes=ctrl._generation-data['initial_generation'],
                    history_entries=len(ctrl._history.get(ctrl.currentIndex, [])))
                assert report[parameter]['settings_changes'] > 0, report[parameter]
                assert report[parameter]['final_value'] > initial_value+.5, report[parameter]
                assert report[parameter]['history_entries'] == initial_history+1, report[parameter]
                report[parameter]['single_drag_undo'] = True
                QTimer.singleShot(350, finished)
            except Exception:
                import traceback
                traceback.print_exc()
                timer.stop()
                app.exit(2)
        timer.timeout.connect(tick)
        # Retain the QTimer until the pointer transaction finishes.
        window._drag_timer = timer
        timer.start()

    def finish():
        nonlocal result
        if ctrl.busy and time.perf_counter()<deadline:
            QTimer.singleShot(30, finish)
            return
        assert not ctrl.busy, ctrl.status
        final_grain = ctrl.settings['grain']
        ctrl.undo()
        assert ctrl.settings['grain'] == 18
        ctrl.redo()
        assert ctrl.settings['grain'] == final_grain
        window.setProperty('activeTask', 'basic')
        QTest.qWait(60)
        scroll = window.findChild(QObject, 'parameterScroll').property('contentItem')
        scroll.setProperty('contentY', 0)
        QTest.qWait(40)
        slider = window.findChild(QQuickItem, 'parameterSlider_exposure')
        slider.forceActiveFocus()
        exposure = ctrl.settings['exposure']
        QTest.keyClick(window, Qt.Key_Right, Qt.ShiftModifier)
        assert abs(ctrl.settings['exposure']-exposure-.001) < 1e-8, ctrl.settings['exposure']
        handle = window.findChild(QQuickItem, 'parameterHandle_exposure')
        QTest.mouseDClick(window, Qt.LeftButton, Qt.NoModifier,
                         handle.mapToScene(handle.boundingRect().center()).toPoint())
        assert ctrl.settings['exposure'] == 0, ctrl.settings['exposure']
        ctrl.undo()
        assert abs(ctrl.settings['exposure']-exposure-.001) < 1e-8
        report['precision_and_history'] = dict(undo_redo=True, fine_keyboard_step=.001,
                                               double_click_reset=True, reset_undo=True)
        errors=[s for s in messages if 'Error' in s or 'ReferenceError' in s or 'Binding loop' in s]
        report['qml_errors']=errors
        report['ok']=not errors
        (out/(args.label+'.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        window.grabWindow().save(str(out/(args.label+'.png')))
        print(json.dumps(report, ensure_ascii=False), flush=True)
        result=0 if report['ok'] else 2
        window.close()
        app.quit()

    def film():
        if ctrl.busy:
            QTimer.singleShot(30, film)
            return
        drag('grain', 'film', finish)

    def enable_film():
        ctrl.setFilmEnabled(True)
        QTimer.singleShot(100, film)

    def loaded():
        if not ctrl.frame or ctrl.busy:
            assert time.perf_counter()<deadline, ctrl.status
            QTimer.singleShot(30, loaded)
            return
        drag('exposure', 'basic', enable_film)

    ctrl.add_paths([str(ROOT/'output/grain-refinement/no-grain.png')])
    QTimer.singleShot(100, loaded)
    status=app.exec()
    ctrl.close()
    controller_module.asdict=original_asdict
    del engine
    store.cleanup()
    return status or result


if __name__ == '__main__':
    raise SystemExit(main())
