"""One small real-export UI node: failure, immutable retry and proof layout."""
from dataclasses import asdict,replace
import json
from pathlib import Path
import sys,tempfile,time
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from PIL import Image
from PySide6 import QtSvg
from PySide6.QtCore import QObject,QPoint,Qt,QUrl,qInstallMessageHandler
from PySide6.QtQml import QQmlApplicationEngine,QQmlExpression
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from desktop.controller import Controller,PhotoProvider
from desktop.imaging import Settings
from desktop.typography import load_mincho
from shared.output_recipes import OutputRecipe
from verify_library_workspace import wait_until


def main():
    out=ROOT/'output/export-results-ui';out.mkdir(parents=True,exist_ok=True)
    app=QApplication([]);app.setApplicationName('ExportResultsReview');app.setOrganizationName('SpektraFilmVerification')
    QQuickStyle.setStyle('Basic');family=load_mincho(app,ROOT);errors=[]
    qInstallMessageHandler(lambda kind,context,text:errors.append(text))
    report={}
    with tempfile.TemporaryDirectory(prefix='results-',dir=out,ignore_cleanup_errors=True) as directory:
        folder=Path(directory);provider=PhotoProvider();ctrl=Controller(provider,folder/'state')
        source=folder/'照片-一.jpg';missing=folder/'照片-二.jpg'
        with Image.open(ROOT/'output/current-ui/source-preview.jpg') as image:
            image.thumbnail((480,320));image.convert('RGB').save(source,quality=98)
        with Image.open(source) as image:width,height=image.size
        settings=replace(Settings(),film_enabled=False,lens_correction=False,defringe=False,grain=0,halation=0)
        ctrl._photo_model.append([dict(path=str(source),name=source.name,width=width,height=height,
                dimensions=f'{width} × {height}',settings=asdict(settings))])
        ctrl._current=0;ctrl._selected={0};ctrl._settings=settings
        recipe=OutputRecipe(format='jpeg',quality=98)
        planned=[(str(source),str(folder/'导出-一.jpg'),settings),(str(missing),str(folder/'导出-二.jpg'),settings)]
        engine=QQmlApplicationEngine();engine.addImageProvider('photos',provider);ctx=engine.rootContext()
        for name,value in [('ctrl',ctrl),('minchoFamily',family),('interfaceDisplayFamily',app._interface_font_selection['display']),('interfaceEditorialFamily',app._interface_font_selection['editorial']),('systemReduceMotion',True),('assetsUrl',QUrl.fromLocalFile(str(ROOT/'assets')+'/').toString())]:ctx.setContextProperty(name,value)
        source_qml=b'''import QtQuick\nimport QtQuick.Window\nimport "../../desktop/qml/components"\nWindow {visible:true;width:1366;height:768;function showRecipes(){recipes.open()} function showExport(){recipes.close();exports.open()} OutputRecipeDialog {id:recipes} ExportDialog {id:exports}}'''
        engine.loadData(source_qml,QUrl.fromLocalFile(str(out/'ResultsProbe.qml')))
        assert engine.rootObjects(),errors
        window=engine.rootObjects()[0]
        def js(obj,expression):
            q=QQmlExpression(ctx,obj,expression);result=q.evaluate();assert not q.hasError(),q.error().toString();return result
        def frame():
            count=[];window.frameSwapped.connect(lambda:count.append(True));window.update();wait_until(lambda:len(count)>0)
        def capture(name):
            wait_until(lambda:ctrl.outputProof.source and not ctrl.outputProof.busy,timeout=30)
            QTest.mouseMove(window,QPoint(1200,700));QTest.qWait(90);frame();assert window.grabWindow().save(str(out/(name+'.png')))
        def walk(item,name):
            if item.objectName()==name:return item
            for child in item.childItems():
                found=walk(child,name)
                if found:return found
        try:
            js(window,'showRecipes()');wait_until(lambda:ctrl.outputProof.source and not ctrl.outputProof.busy,timeout=30)
            assert ctrl._start_recipe_export(planned,recipe)
            wait_until(lambda:not ctrl.exporting,timeout=30)
            assert [item['status'] for item in ctrl.exportItems]==['completed','failed'],ctrl.exportItems
            assert ctrl.canRetryFailedExports and ctrl.exportItems[1]['error']
            capture('recipe-failure-1366x768')
            page=window.findChild(QObject,'outputRecipeDialog');assert page
            proof=next(item for item in page.property('contentItem').childItems() if item.metaObject().className().startswith('OutputProofView'))
            assert proof.width()>400 and proof.height()>300,(proof.width(),proof.height())
            results=walk(window.contentItem(),'exportResultsList');assert results and results.height()>40
            report['recipe_layout']={'proof_logical':[proof.width(),proof.height()],'results_height':results.height()}
            # Restore only the failed source; changing current controls must not change retry settings.
            Image.new('RGB',(width,height),(130,110,90)).save(missing,quality=98)
            ctrl._settings=replace(settings,exposure=2)
            retry=walk(window.contentItem(),'retryFailedExports');assert retry and retry.isEnabled()
            position=retry.mapToScene(retry.boundingRect().center())
            QTest.mouseClick(window,Qt.LeftButton,pos=QPoint(round(position.x()),round(position.y())))
            wait_until(lambda:not ctrl.exporting,timeout=30)
            assert len(ctrl.exportItems)==1 and ctrl.exportItems[0]['status']=='completed',ctrl.exportItems
            assert ctrl._recipe_export_snapshot[1][0][2].exposure==settings.exposure
            with Image.open(folder/'导出-二.jpg') as image:assert image.size==(width,height)
            report['retry']={'actual_button':True,'only_failed_source':True,'original_settings_snapshot':True,'original_dimensions':[width,height]}
            js(window,'showExport()');capture('export-completed-1366x768')
            window.resize(1440,900);capture('export-completed-1440x900')
            report['states']=['completed','failed_with_reason','retry_completed','proof_refreshes_after_export'];report['window_sizes']=[[1366,768],[1440,900]]
        finally:
            window.close();ctrl.close();engine.deleteLater();app.processEvents()
    serious=[message for message in errors if any(token in message for token in ('ReferenceError','TypeError','Cannot','Binding loop','Error decoding','is not defined'))]
    assert not serious,serious
    report.update(status='passed',qml_messages=errors)
    (out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
