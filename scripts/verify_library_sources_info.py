"""New sources / EXIF paths only; previously verified facets are not rerun."""
import json
from pathlib import Path
import sys,tempfile
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from PIL import Image,TiffImagePlugin
from PySide6.QtCore import QPoint,Qt,QUrl,QSettings,qInstallMessageHandler
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from desktop.controller import Controller,PhotoProvider
from desktop.library_workspace import LibraryWorkspace
from desktop.typography import load_mincho
from verify_library_workspace import wait_until


def main():
    out=ROOT/'output/library-sources-info';out.mkdir(parents=True,exist_ok=True)
    app=QApplication([]);app.setApplicationName('LibrarySourcesReview');app.setOrganizationName('SpektraFilmVerification')
    QQuickStyle.setStyle('Basic');family=load_mincho(app,ROOT);errors=[]
    qInstallMessageHandler(lambda kind,context,text:errors.append(text));report={}
    with tempfile.TemporaryDirectory(prefix='sources-',dir=out,ignore_cleanup_errors=True) as directory:
        folder=Path(directory);source_a=folder/'外拍原片';source_b=folder/'后续选片';source_a.mkdir();source_b.mkdir()
        first=source_a/'有拍摄信息的照片.jpg';exif=Image.Exif()
        exif[271]='SONY';exif[272]='ILCE-7CR';exif[42036]='FE 35mm F1.4 GM';exif[36867]='2026:11:09 14:30:00'
        exif[34855]=100;exif[33437]=TiffImagePlugin.IFDRational(28,10);exif[33434]=TiffImagePlugin.IFDRational(1,125);exif[37386]=TiffImagePlugin.IFDRational(35)
        with Image.open(ROOT/'output/current-ui/source-preview.jpg') as image:
            image.thumbnail((480,320));image.convert('RGB').save(first,quality=95,exif=exif)
        second=source_b/'第二张.jpg';Image.new('RGB',(480,320),(130,110,90)).save(second)
        provider=PhotoProvider();ctrl=Controller(provider,folder/'editor')
        workspace=LibraryWorkspace(thumbnail_provider=provider,view_settings=QSettings(str(folder/'views.ini'),QSettings.IniFormat))
        def settle():wait_until(lambda:not workspace._requests and not workspace._metadata_loading and not workspace._metadata_refresh.isActive(),timeout=20)
        workspace.createLibrary(str(folder/'资料库'),'catalog');settle()
        workspace.watchFolder(str(source_a));settle();workspace.watchFolder(str(source_b));settle()
        assert workspace.total==2 and len(workspace.folders)==2
        watched_a=next(row for row in workspace.folders if Path(row['path'])==source_a)
        watched_b=next(row for row in workspace.folders if Path(row['path'])==source_b)
        assert watched_a['online'] and watched_a['synced_at'] and not workspace.unwatchedLocations
        workspace.selectImage(next(row['uuid'] for row in workspace.images if Path(row['path'])==first),False)
        info={row['label']:row['value'] for row in workspace.photoInfo['rows']}
        assert info['相机']=='ILCE-7CR' and info['镜头']=='FE 35mm F1.4 GM' and info['光圈']=='f/2.8' and info['快门']=='1/125 s',info
        assert info['感光度']=='100 ISO' and info['焦距']=='35 mm',info
        opened=[];workspace.openPhoto.connect(lambda *values:opened.append(values))
        selected=workspace.selectedImages[0]
        workspace.activateVariant(selected,'');wait_until(lambda:len(opened)==1)
        workspace.saveEdit(str(first),{'version':4,'settings':{'exposure':.35}});settle()
        engine=QQmlApplicationEngine();engine.addImageProvider('photos',provider);ctx=engine.rootContext()
        for name,value in [('ctrl',ctrl),('library',workspace),('minchoFamily',family),('interfaceDisplayFamily',app._interface_font_selection['display']),('interfaceEditorialFamily',app._interface_font_selection['editorial']),('systemReduceMotion',True),('assetsUrl',QUrl.fromLocalFile(str(ROOT/'assets')+'/').toString())]:ctx.setContextProperty(name,value)
        qml=b'''import QtQuick\nimport QtQuick.Window\nimport "../../desktop/qml/components"\nWindow {visible:true;width:1366;height:768;LibraryWorkspace {anchors.fill:parent;workspace:library}}'''
        engine.loadData(qml,QUrl.fromLocalFile(str(out/'SourcesProbe.qml')));assert engine.rootObjects(),errors
        window=engine.rootObjects()[0]
        def find(item,name):
            if item.objectName()==name:return item
            for child in item.childItems():
                result=find(child,name)
                if result:return result
        def click(name):
            QTest.qWait(80)
            item=find(window.contentItem(),name);assert item,name
            position=item.mapToScene(item.boundingRect().center())
            QTest.mouseClick(window,Qt.LeftButton,pos=QPoint(round(position.x()),round(position.y())));QTest.qWait(25)
        def capture(name):
            wait_until(lambda:all(('library_'+row['uuid']) in provider.images for row in workspace.images))
            QTest.mouseMove(window,QPoint(1200,700));QTest.qWait(100);assert window.grabWindow().save(str(out/(name+'.png')))
        try:
            click('librarySourcesToggle');click('libraryInfoToggle');capture('sources-info-1366x768')
            click('syncSource_'+watched_a['folder']);settle()
            assert not workspace.foldersSyncing
            click('unwatchSource_'+watched_a['folder']);capture('unwatch-confirm-1366x768')
            assert Path(find(window.contentItem(),'librarySourcesPanel').property('removePath'))==source_a
            click('confirmStopWatching');settle()
            assert len(workspace.folders)==1 and workspace.folders[0]['folder']==watched_b['folder']
            assert first.is_file() and workspace.total==2 and workspace.photoInfo['name']==first.name
            workspace.activateVariant(selected,'');wait_until(lambda:len(opened)==2)
            assert opened[-1][1]['settings']['exposure']==.35
            # A new file in the unmonitored root must not be picked up by refresh.
            Image.new('RGB',(32,24),(80,90,70)).save(source_a/'停止监视后.jpg')
            third=source_b/'仍在监视.jpg';Image.new('RGB',(32,24),(80,90,70)).save(third)
            workspace.syncFolders();settle();assert workspace.total==3
            assert source_a/'停止监视后.jpg' not in {Path(row['path']) for row in workspace.images}
            assert {Path(row['path']) for row in workspace.unwatchedLocations}=={source_a}
            workspace.selectPage();common={row['label']:row['value'] for row in workspace.photoInfo['rows']};assert common['相机']=='多种'
            capture('unwatched-retained-1366x768')
            report=dict(status='passed',native_watched_sources=2,real_exif_info=info,
                        checks=['online/sync counts from native helper','actual refresh button','actual unwatch confirmation',
                                'unwatch retains imported photos, persisted edit and disk sources','only still-watched root discovers new files',
                                'multi-selection mixed/unknown values','no duplicate source paths'],window=[1366,768])
        finally:
            window.close();workspace.shutdown();ctrl.close();wait_until(lambda:workspace.service._process.state().name=='NotRunning')
            engine.deleteLater();app.processEvents()
    serious=[message for message in errors if any(token in message for token in ('ReferenceError','TypeError','Cannot','Binding loop','Unable to assign','is not defined'))]
    assert not serious,serious
    report['qml_messages']=errors;(out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
