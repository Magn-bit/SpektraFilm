"""One critical node: native facets, bounded header reads, persisted view and QML."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from PIL import Image
from PySide6.QtCore import QSettings,QUrl,QPoint,QObject,qInstallMessageHandler
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from desktop.controller import Controller,PhotoProvider
from desktop.library_workspace import LibraryWorkspace
from desktop.typography import load_mincho
from verify_library_workspace import wait_until
from verify_library_service import make_c1_fixture


def main():
    out=ROOT/'output/library-facets';out.mkdir(exist_ok=True,parents=True)
    app=QApplication([]);app.setApplicationName('SpektraFilm');app.setOrganizationName('SpektraFilm')
    QQuickStyle.setStyle('Basic');family=load_mincho(app,ROOT)
    errors=[];qInstallMessageHandler(lambda kind,context,text:errors.append(text))
    report={}
    with tempfile.TemporaryDirectory(prefix='facets-',dir=out,ignore_cleanup_errors=True) as temp:
        folder=Path(temp);settings=QSettings(str(folder/'view.ini'),QSettings.IniFormat)
        files=[]
        for index,(camera,lens,stamp) in enumerate([
            ('SONY A7CR','35mm','2026:01:10 10:00:00'),('SONY A7CR','85mm','2026:02:10 10:00:00'),
            ('NIKON Z8','35mm','2025:01:10 10:00:00'),('NIKON Z8','85mm','2025:02:10 10:00:00'),
            ('FUJIFILM GFX100','35mm','2024:01:10 10:00:00'),('FUJIFILM GFX100','85mm','2024:02:10 10:00:00')]):
            path=folder/f'照片-{index+1}.jpg';exif=Image.Exif()
            exif[271]=camera.split()[0];exif[272]=camera;exif[42036]=lens;exif[36867]=stamp
            Image.new('RGB',(480,320),(90+index*19,118+index*9,98+index*10)).save(path,exif=exif,quality=95)
            files.append(path)
        provider=PhotoProvider();ctrl=Controller(provider,str(folder/'editor'));workspace=LibraryWorkspace(thumbnail_provider=provider,view_settings=settings)
        def settled():return not workspace._requests and not workspace._metadata_loading and not workspace._metadata_refresh.isActive()
        def settle():wait_until(settled,timeout=20)
        workspace.createLibrary(str(folder/'目录'),'catalog');settle();library_path=workspace.path
        workspace.addPaths([str(p) for p in files],False);settle()
        assert workspace.total==6 and all(row.get('width')==480 and row['described'] for row in workspace.images),workspace.images
        assert sorted((r['value'],r['count']) for r in workspace._facets['camera'])==[('FUJIFILM GFX100',2),('NIKON Z8',2),('SONY A7CR',2)],workspace._facets
        report['header_enrichment']={'real_exif_cameras':3,'files':6,'batch_limit':64,'pixel_decode':False}
        workspace.toggleFilter('camera_models','SONY A7CR');settle();assert workspace.total==2
        workspace.toggleFilter('camera_models','NIKON Z8');settle();assert workspace.total==4
        workspace.toggleFilter('lenses','35mm');settle();assert workspace.total==2
        # Each facet excludes its own selection while preserving other dimensions.
        assert {r['value']:r['count'] for r in workspace._facets['camera']}=={'FUJIFILM GFX100':1,'NIKON Z8':1,'SONY A7CR':1}
        workspace.toggleFilter('date','2026-01');settle();assert workspace.total==1
        workspace.toggleFilter('has_edit',False);settle();assert workspace.total==1
        selected=workspace.images[0];opens=[];workspace.openPhoto.connect(lambda *args:opens.append(args))
        workspace.activateVariant(selected['uuid'],'');wait_until(lambda:len(opens)==1)
        workspace.saveEdit(selected['path'],{'version':4,'settings':{'exposure':.25}})
        wait_until(lambda:workspace.total==0 and settled(),timeout=20)
        workspace.toggleFilter('has_edit',True);settle();assert workspace.total==1
        workspace.setFiltersExpanded(True);workspace.toggleFilterGroup('lens');workspace.setSort('name',True);settle()
        expected=workspace.activeFilters.copy()
        workspace.quickSession();settle();assert not workspace.hasLibrary
        workspace.openLibrary(library_path);settle()
        assert workspace.activeFilters==expected and workspace.filtersExpanded and workspace._descending
        assert workspace.total==1 and workspace.images[0]['uuid']==selected['uuid']
        report['facets']={'within_facet_OR':True,'across_facets_AND':True,'own_facet_counts':True,
                          'month_half_open_range':True,'edit_save_refilters':True,'persisted_view':True}
        # True keyword filter data imported from a native, tiny C1 metadata fixture.
        package,_,_=make_c1_fixture(folder)
        workspace.linkCaptureOne(str(package),'');settle()
        assert {r['value'] for r in workspace._facets['keyword']}=={'portrait','daylight'}
        workspace.toggleFilter('keywords','portrait');settle();assert workspace.total==1
        workspace.toggleFilter('keywords','missing');settle();assert workspace.total==1
        workspace.toggleFilter('keywords','portrait');settle();assert workspace.total==0
        report['keywords']={'C1_metadata_import':True,'native_any_of_filter':True,'zero_result_selection_retained':True}
        workspace.openLibrary(library_path);settle()
        engine=QQmlApplicationEngine();engine.addImageProvider('photos',provider);context=engine.rootContext()
        context.setContextProperty('ctrl',ctrl);context.setContextProperty('library',workspace);context.setContextProperty('minchoFamily',family)
        context.setContextProperty('interfaceDisplayFamily',app._interface_font_selection['display'])
        context.setContextProperty('interfaceEditorialFamily',app._interface_font_selection['editorial'])
        context.setContextProperty('systemReduceMotion',False)
        context.setContextProperty('assetsUrl',QUrl.fromLocalFile(str(ROOT/'assets')+'/').toString())
        source=b'''import QtQuick\nimport QtQuick.Window\nimport "../../desktop/qml/components"\nWindow {visible:true;width:1366;height:768;LibraryWorkspace {anchors.fill:parent;workspace:library}}'''
        engine.loadData(source,QUrl.fromLocalFile(str(out/'FacetsProbe.qml')))
        if not engine.rootObjects():
            workspace.shutdown();wait_until(lambda:workspace.service._process.state().name=='NotRunning')
            raise AssertionError(errors)
        window=engine.rootObjects()[0];wait_until(lambda:window.isVisible())
        frames=[];window.frameSwapped.connect(lambda:frames.append(True));window.update();wait_until(lambda:len(frames)>1)
        assert window.grabWindow().save(str(out/'library-facets-1366x768.png'))
        # Hit actual button once; current Sony row is selected, so OR leaves Nikon.
        def find(item,name):
            if item.objectName()==name:return item
            for child in item.childItems():
                result=find(child,name)
                if result:return result
        target=find(window.contentItem(),'libraryFilter_camera_models_SONY A7CR');assert target
        point=target.mapToScene(target.boundingRect().center())
        QTest.mouseClick(window,__import__('PySide6').QtCore.Qt.LeftButton,pos=QPoint(round(point.x()),round(point.y())))
        settle();assert workspace.activeFilters['camera_models']==['NIKON Z8']
        workspace.clearFilters();settle();assert workspace.total==6 and not workspace.hasFilters
        QTest.mouseMove(window,QPoint(1200,700));QTest.qWait(100)
        assert window.grabWindow().save(str(out/'library-facets-cleared-1366x768.png'))
        report['qml']={'actual_facet_click':True,'clear':True,'window':[1366,768]}
        window.close();engine.deleteLater();app.processEvents();workspace.shutdown();ctrl.close()
        wait_until(lambda:workspace.service._process.state().name=='NotRunning')
    serious=[e for e in errors if any(token in e for token in ('Error','ReferenceError','TypeError','Cannot','is not defined'))]
    report['qml_messages']=errors;assert not serious,serious
    report['status']='passed';(out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
