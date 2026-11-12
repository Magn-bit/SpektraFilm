"""One UI milestone: four-language workflows, live switch and state retention."""
from pathlib import Path
import json,sys,tempfile,time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
from PySide6.QtCore import QUrl,QObject,QSettings,qInstallMessageHandler,Qt
from PySide6.QtWidgets import QApplication,QFileDialog
from PySide6.QtQml import QQmlApplicationEngine,QQmlExpression,QQmlEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from desktop.controller import Controller,PhotoProvider
from desktop.localization import install_localization,preferred_language,CatalogTranslator,tr
from desktop.typography import load_mincho
from desktop.dialogs import StudioFileDialog

out=ROOT/'output/localization';out.mkdir(parents=True,exist_ok=True)
report={};messages=[]
qInstallMessageHandler(lambda kind,context,message:messages.append(message))
app=QApplication([]);app.setOrganizationName('SpektraFilmVerification');app.setApplicationName('Localization')
QQuickStyle.setStyle('Basic');family=load_mincho(app,ROOT)
temporary=tempfile.TemporaryDirectory();provider=PhotoProvider();ctrl=Controller(provider,temporary.name)
engine=QQmlApplicationEngine();engine.addImageProvider('photos',provider);ctx=engine.rootContext()
settings=QSettings(str(Path(temporary.name)/'language.ini'),QSettings.IniFormat)
localizer=install_localization(app,engine,'zh-Hans',settings)
for name,value in [('ctrl',ctrl),('minchoFamily',family),('interfaceDisplayFamily',family),('interfaceEditorialFamily',family),('interfaceFontDescription',''),('assetsUrl',QUrl.fromLocalFile(str(ROOT/'assets')+'/').toString()),('systemReduceMotion',True)]:ctx.setContextProperty(name,value)
engine.load(QUrl.fromLocalFile(str(ROOT/'desktop/qml/Studio.qml')))
assert engine.rootObjects(),messages
window=engine.rootObjects()[0];window.resize(1366,768);window.show();QTest.qWait(120)

def js(code,owner=None):
    expression=QQmlExpression(QQmlEngine.contextForObject(owner or window),owner or window,code);result=expression.evaluate()
    assert not expression.hasError(),expression.error().toString()
    if isinstance(result,tuple) and len(result)==2:result=result[0]
    return result.toVariant() if hasattr(result,'toVariant') else result

def texts(root):
    seen=set();result=[]
    def walk(obj):
        if obj in seen:return
        seen.add(obj)
        if obj.metaObject().indexOfProperty('text')>=0:
            value=obj.property('text')
            if value:result.append(str(value))
        for child in obj.children():walk(child)
        if hasattr(obj,'childItems'):
            for child in obj.childItems():walk(child)
    walk(root);return result

try:
    checks={
        'en':('High dynamic range','Masks','Choose photos','Source development'),
        'ja':('ハイダイナミックレンジ','マスク','写真を選択','元画像の現像'),
        'zh-Hant':('高動態範圍','蒙版','選擇照片','原片顯影'),
        'zh-Hans':('高动态范围','蒙版','选择照片','原片显影'),
    }
    # No photo is processed here; this milestone only changes presentation.
    source_settings=ctrl._settings;settings_key=repr(source_settings)
    per_language={}
    for language in checks:
        localizer.setLanguage(language);QTest.qWait(50)
        assert js("qsTr('正在打开 12 张照片…')")==localizer.text('正在打开 12 张照片…')
        assert js("qsTr('Cineon DI 需要开启胶片显影')")==localizer.text('Cineon DI 需要开启胶片显影')
        translated=js("qsTr('裁切预览不可用')");assert translated!= '裁切预览不可用' or language=='zh-Hans'
        assert js("qsTr('请先为所选照片开启负片显影')")==localizer.text('请先为所选照片开启负片显影')
        assert js("qsTr('文件扩展名与配方不一致')")==localizer.text('文件扩展名与配方不一致')
        assert js('stock.id || ctrl.parameters.stock')==ctrl._settings.stock
        all_text=texts(window)
        for value in checks[language]:assert value in all_text,(language,value)
        window.grabWindow().save(str(out/(language+'-editor-1366x768.png')))
        js("settingsPanel.category='interface';settingsPanel.open()")
        QTest.qWait(50);all_text=texts(window)
        assert localizer.text('语言') in all_text,(language,'language control')
        window.grabWindow().save(str(out/(language+'-settings-1366x768.png')))
        js('settingsPanel.close()')
        ctrl.toast.emit('Cineon DI 需要开启胶片显影');QTest.qWait(20)
        assert localizer.text('Cineon DI 需要开启胶片显影') in texts(window)
        js("outputRecipeDialog.open();outputRecipeDialog.createRecipe();outputRecipeDialog.setValue('name','导出')")
        # Editable user values must not turn into translated filenames on save.
        assert js('outputRecipeDialog.draft.name')=='导出'
        js('outputRecipeDialog.close()')
        # QWidget labels and validation errors share the same translator.
        dialog=StudioFileDialog('选择照片',temporary.name)
        dialog._show_error('所选文件不存在，请检查路径。')
        assert dialog.windowTitle()==localizer.text('选择照片')
        assert dialog.picker.labelText(QFileDialog.Reject)==localizer.text('取消')
        assert dialog.errorLabel.text()==localizer.text('所选文件不存在，请检查路径。')
        dialog.deleteLater();js('settingsPanel.close()');QTest.qWait(20)
        assert repr(ctrl._settings)==settings_key
        assert settings.value('interface/language')==language
        per_language[language]={'editor_labels':list(checks[language]),'dialog_labels':True,'dynamic_status':localizer.text('正在打开 12 张照片…'),'disabled_reason':translated,'settings_persisted':True,'edit_state_unchanged':True}
    assert preferred_language(['fr-FR','zh-HK','en-US'])=='zh-Hant'
    assert preferred_language(['de-DE'])=='en'
    translator=CatalogTranslator('en')
    filename='胶片_原图 01.ARW'
    assert translator.text(filename)==filename
    assert translator.text('照片已导出：'+filename)=='Photo exported: '+filename
    assert translator.text('自动调整失败：未找到可靠的自动调整')=='Automatic adjustment failed: No reliable automatic adjustment found'
    assert translator.text('批量导出完成 · 2/2 张；原片保持不变。')=='Batch export Complete · 2/2 photos; originals are unchanged.'
    assert tr('Expected token %1')=='Expected token %1'
    report.update(passed=True,languages=per_language,catalog_entries=len(translator.entries),dynamic_templates=len(translator.templates),filename_preserved=True)
finally:
    ctrl.close();window.setProperty('closeApproved',True);window.close();QTest.qWait(30)
    report['qt_font_warnings']=len([message for message in messages if message.startswith('QFont::setPointSize:')])
    relevant=[message for message in messages if not message.startswith(('QQuickItem: Cannot set activeFocusOnTab','QFont::setPointSize:'))]
    report['qml_messages']=relevant
    (out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    temporary.cleanup()
