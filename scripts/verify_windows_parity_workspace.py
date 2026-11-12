"""One integrated milestone: live variants, light table, task pages and DI."""
from dataclasses import replace,asdict
import json,os,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from PIL import Image
import numpy as np
import tifffile
from PySide6.QtCore import QObject,QMetaObject,QUrl,Qt,qInstallMessageHandler,QPointF,QSettings
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from desktop.controller import Controller,PhotoProvider
from desktop.typography import load_mincho
from desktop.imaging import Settings,read_photo
from desktop.output import export_recipe
from shared.output_recipes import OutputRecipe
from verify_library_workspace import wait_until
from verify_library_service import Host


def main():
    out=ROOT/'output/parity-workspace';out.mkdir(parents=True,exist_ok=True)
    errors=[];qInstallMessageHandler(lambda kind,context,message:errors.append(message))
    app=QApplication([]);app.setApplicationName('SpektraFilm');app.setOrganizationName('SpektraFilm');QQuickStyle.setStyle('Basic')
    family=load_mincho(app,ROOT);report={}
    with tempfile.TemporaryDirectory(prefix='integrated-',dir=out) as folder:
        temporary=Path(folder);sources=[]
        for i in range(3):
            path=temporary/f'照片-{i+1}.png';y,x=np.mgrid[:240,:360]
            pixels=np.stack((40+x*.45,45+y*.55,np.full_like(x,90+i*25)),axis=2).astype(np.uint8)
            Image.fromarray(pixels).save(path);sources.append(str(path))
        ctrl=Controller(PhotoProvider(),str(temporary/'store'));engine=QQmlApplicationEngine();engine.addImageProvider('photos',ctrl.provider)
        from desktop.localization import install_localization
        install_localization(app,engine,language='zh-Hans',settings=QSettings(str(temporary/'locale.ini'),QSettings.IniFormat))
        context=engine.rootContext()
        for key,value in {'ctrl':ctrl,'minchoFamily':family,'interfaceDisplayFamily':family,'interfaceEditorialFamily':family,'systemReduceMotion':True,'assetsUrl':QUrl.fromLocalFile(str(ROOT/'assets')+'/').toString(),'interfaceFontDescription':family}.items():context.setContextProperty(key,value)
        engine.load(QUrl.fromLocalFile(str(ROOT/'desktop/qml/Studio.qml')));assert engine.rootObjects(),errors
        window=engine.rootObjects()[0];window.setWidth(1366);window.setHeight(768);window.show()
        def settle():QTest.qWait(120)
        def shot(name):
            settle();image=window.grabWindow();assert image.save(str(out/name))
            return {'logical_size':[window.width(),window.height()],'pixel_size':[image.width(),image.height()],'path':name}
        try:
            ctrl.importPhotos();settle();assert window.property('workspaceMode')=='import'
            stage=ctrl.importWorkspace;stage.setSources(sources);wait_until(lambda:stage.state['count']==3 and not stage.state['scanning'])
            report['import_page']=shot('import-integrated-1366x768.png');stage.addSelected()
            wait_until(lambda:ctrl.photoCount==3 and ctrl.frame and not ctrl.busy,20)
            workspace=ctrl.libraryWorkspace;workspace.createLibrary(str(temporary/'图库'),'catalog')
            wait_until(lambda:workspace.hasLibrary and not workspace._requests)
            workspace.addPaths([sources[0]],False);wait_until(lambda:workspace.total==1 and not workspace._requests)
            row=workspace.images[0];image_id=row['uuid'];workspace.activateVariant(image_id,'')
            wait_until(lambda:bool(ctrl._library_context) and ctrl.currentPath==sources[0] and not workspace._requests)
            first=workspace.activeVariant;ctrl.updateParameter('exposure',.35);ctrl.endEdit();ctrl._persist()
            workspace.selectImage(image_id,False) if hasattr(workspace,'selectImage') else workspace.select(image_id,False)
            workspace.createVariant();wait_until(lambda:workspace.activeVariant!=first and not workspace._requests and not workspace.saving)
            second=workspace.activeVariant;assert ctrl._settings.exposure==.35
            ctrl.updateParameter('exposure',.85);ctrl.endEdit();ctrl._persist()
            workspace.activateVariant(image_id,first);wait_until(lambda:workspace.activeVariant==first and not workspace._requests and not workspace.saving)
            assert ctrl._settings.exposure==.35,asdict(ctrl._settings)
            workspace.activateVariant(image_id,second);wait_until(lambda:workspace.activeVariant==second and not workspace._requests)
            assert ctrl._settings.exposure==.85
            ctrl.undo();assert ctrl._settings.exposure==.35
            ctrl.redo();assert ctrl._settings.exposure==.85
            peer=Host(temporary/'peer')
            try:
                handle=peer.call('library.open',{'path':workspace.path})['library'];ctrl._persist();workspace.flushPending();wait_until(lambda:not workspace.saving)
                assert peer.call('edit.get',{'library':handle,'variant':first})['edit']['settings']['exposure']==.35
                assert peer.call('edit.get',{'library':handle,'variant':second})['edit']['settings']['exposure']==.85
            finally:peer.close()
            report['same_path_variants']={'distinct_settings':True,'distinct_history':True,'no_cross_write':True}
            wait_until(lambda:not ctrl.busy,20);window.setProperty('workspaceMode','lighttable');settle()
            wait_until(lambda:len(ctrl.lightTable._rows)==3 and all(r['source'] for r in ctrl.lightTable._visible),20)
            model=ctrl.lightTable.rows;resets=[];model.modelReset.connect(lambda:resets.append(1))
            row=ctrl.lightTable._rows[0];ident=row['id'];ctrl.lightTable.place(ident,44,32,90)
            assert model.rowCount()>0 and not resets
            board=window.findChild(QObject,'lightTableBoard');assert board is not None
            report['light_table']=shot('light-table-integrated-1366x768.png')
            report['light_table'].update(no_reset_on_move=True,developed_visible=len(ctrl.lightTable._visible))
            window.setProperty('workspaceMode','edit');settle()
            for object_name,filename in [('exportDialog','export-integrated-1366x768.png'),('outputRecipeDialog','recipes-integrated-1366x768.png'),('settingsPanel','settings-integrated-1366x768.png')]:
                dialog=window.findChild(QObject,object_name);assert dialog is not None
                assert QMetaObject.invokeMethod(dialog,'open');settle()
                assert dialog.property('width')==window.width() and dialog.property('height')==window.height()-34
                if object_name=='settingsPanel':dialog.setProperty('category','color')
                report[object_name]=shot(filename);QMetaObject.invokeMethod(dialog,'close');settle()
            for width,height in [(1440,900),(1120,760)]:
                window.setWidth(width);window.setHeight(height);settle()
                dialog=window.findChild(QObject,'settingsPanel');QMetaObject.invokeMethod(dialog,'open');settle()
                assert dialog.property('width')==width and dialog.property('height')==height-34
                QMetaObject.invokeMethod(dialog,'close')
            # DI contract: source dimensions, density codes, no RGB ICC, real LUTs.
            di=temporary/'negative.tif';setting=Settings(film_enabled=True,grain=0,halation=0,dir_couplers_amount=0)
            result=export_recipe(sources[0],di,setting,OutputRecipe(format='di',bit_depth=16,color_space='ProPhoto RGB'))
            with tifffile.TiffFile(di) as f:
                page=f.pages[0];samples=page.asarray();assert samples.shape==(240,360,3) and samples.dtype==np.uint16
                assert 34675 not in page.tags and 'Cineon' in page.description
                assert len(np.unique(samples))>256
            assert len(list(temporary.glob('*.cube')))==2
            report['digital_intermediate']={'dimensions':[360,240],'uint16':True,'rgb_icc':False,'view_luts':2}
            # Exercise the caller-owned bounded bridge once, beyond native ABI tests.
            from desktop.film_canvas import render_film_edge
            with read_photo(sources[0]) as image:
                options=dict(style='film',frame_format='135',edge_view='strip',frame_seed=19,camera_seed=23)
                preview,pg=render_film_edge(image,setting,options,preview=True)
                final,fg=render_film_edge(image,setting,options,preview=False)
                assert final.shape==preview.shape and fg['bounded_report']['success']
                assert np.max(np.abs(final-preview))<16/65535
                report['bounded_canvas_bridge']={'size':[final.shape[1],final.shape[0]],'max_error_lsb':float(np.max(np.abs(final-preview))*65535),'file_backed':isinstance(final,np.memmap)}
            window.setProperty('closeApproved',True);window.close()
        finally:
            ctrl.close();engine.deleteLater();app.processEvents()
        report['qml_errors']=[e for e in errors if any(k in e for k in ('Error','Cannot','Unable','Binding loop'))]
        assert not report['qml_errors'],report['qml_errors']
    report['ok']=True;(out/'integrated-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2));qInstallMessageHandler(None)

if __name__=='__main__':main()
