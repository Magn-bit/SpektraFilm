import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

StudioPage {
    id:root
    objectName:'outputRecipeDialog'
    property var draft:({})
    property bool dirty:false
    property bool customNaming:false
    property string selectedId:''
    readonly property string recipeError:{var hdrEnabled=ctrl.parameters.hdr_enabled;var selected=ctrl.selectedCount;if(selected===0&&ctrl.currentIndex<0)return '';return ctrl.outputRecipeError(draft,hdrEnabled)}
    function createRecipe() {
        selectedId='';customNaming=false;draft={id:'recipe_'+Date.now().toString(36),name:'新配方',format:'jpeg',bit_depth:8,color_space:'sRGB',quality:100,long_edge:0,naming:'{name}_{film}',subfolder:'导出',conflict:'rename',open_after:false};dirty=true
    }
    function setValue(key,value) {var next=Object.assign({},draft);next[key]=value;draft=next;dirty=true}
    function choose(id) {
        for(var i=0;i<ctrl.outputRecipes.length;i++)if(ctrl.outputRecipes[i].id===id){selectedId=id;draft=Object.assign({},ctrl.outputRecipes[i]);customNaming=['{name}_{film}','{name}','{date}_{name}_{film}','{name}_{film}_{paper}'].indexOf(draft.naming)<0;dirty=false;return}
        createRecipe()
    }
    function setFormat(value) {
        setValue('format',value)
        setValue('bit_depth',value==='jpeg' || value==='heif' ? 8 : 16)
        setValue('color_space',value==='di' ? 'ProPhoto RGB' : value==='dng' || value==='raw' ? 'sRGB' : (draft.color_space || 'sRGB'))
        if(value==='raw' || value==='di'){setValue('long_edge',0);setValue('short_edge',0);setValue('megapixels',0)}
    }
    function save() {
        if(!nameInput.text.trim().length)return false
        setValue('name',nameInput.text.trim());ctrl.saveOutputRecipe(draft)
        for(var i=0;i<ctrl.outputRecipes.length;i++) {
            var saved=ctrl.outputRecipes[i],same=saved.id===draft.id
            for(var key in draft)if(saved[key]!==draft[key])same=false
            if(same){selectedId=draft.id;dirty=false;return true}
        }
        // The controller validates path/name/format and emits the useful error.
        // Leave the edited values visible if persistence was rejected.
        return false
    }
    onOpened:{if(ctrl.outputRecipes.length)choose(selectedId || ctrl.outputRecipes[0].id);else createRecipe()}
    contentItem:RowLayout {
        spacing:32
        OutputProofView {Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumWidth:0;Layout.minimumHeight:0;Layout.preferredWidth:1;Layout.preferredHeight:1;recipe:root.draft;active:root.opened}
        ColumnLayout {
        Layout.minimumWidth:320;Layout.preferredWidth:Math.min(480,root.availableWidth*.42);Layout.maximumWidth:480;Layout.fillWidth:false;Layout.fillHeight:true;Layout.minimumHeight:0
        spacing:18
        RowLayout {
            Layout.fillWidth:true
            MinchoText {text:qsTr(String('输出配方'));font.pixelSize:Theme.heading;Layout.fillWidth:true}
            StudioButton {text:qsTr(String('关闭'));quiet:true;onClicked:root.close()}
        }
        RowLayout {
            Layout.fillWidth:true;spacing:10
            MaterialSelector {Layout.fillWidth:true;label:'';fillField:true;value:root.selectedId;choices:{var r=[];for(var i=0;i<ctrl.outputRecipes.length;i++)r.push({id:ctrl.outputRecipes[i].id,name:ctrl.outputRecipes[i].name});if(!r.length)r.push({id:'',name:'新配方'});return r} onSelected:function(value){root.choose(value)}}
            StudioButton {text:qsTr(String('新建'));quiet:true;onClicked:root.createRecipe()}
        }
        ScrollView {
            id:scroll;Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumWidth:0;Layout.minimumHeight:0;Layout.preferredWidth:1;Layout.preferredHeight:1;clip:true;contentWidth:availableWidth;rightPadding:12
            ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
            Column {
                width:scroll.availableWidth;spacing:20
                RowLayout {
                    width:parent.width
                    MinchoText {text:qsTr(String('名称'));Layout.preferredWidth:70}
                    TextField {
                        id:nameInput;Layout.fillWidth:true;implicitHeight:36;text:root.draft.name || '';selectByMouse:true
                        font.family:Theme.family;font.pixelSize:Theme.body;color:Theme.ink;renderType:TextInput.QtRendering;font.hintingPreference:Font.PreferVerticalHinting
                        Accessible.name:qsTr(String('配方名称'));onTextEdited:root.setValue('name',text)
                        background:Rectangle {radius:4;color:Theme.surface;border.width:1;border.color:parent.activeFocus ? Theme.accent : Theme.border}
                    }
                }
                MaterialSelector {label:qsTr(String('格式'));value:root.draft.format || 'jpeg';choices:[{id:'jpeg',name:'JPEG'},{id:'heif',name:'HEIF'},{id:'png',name:'PNG'},{id:'tiff',name:'TIFF'},{id:'dng',name:'线性 DNG'},{id:'di',name:'Cineon DI'},{id:'raw',name:'RAW 原片'}];onSelected:function(value){root.setFormat(value)}}
                MaterialSelector {label:qsTr(String('位深'));visible:root.draft.format==='png' || root.draft.format==='tiff';value:String(root.draft.bit_depth || 16);choices:[{id:'8',name:'8 bit / 通道'},{id:'16',name:'16 bit / 通道'}];onSelected:function(value){root.setValue('bit_depth',Number(value))}}
                MaterialSelector {label:qsTr(String('色彩空间'));visible:root.draft.format!=='dng' && root.draft.format!=='raw' && root.draft.format!=='di';value:root.draft.color_space || 'sRGB';choices:[{id:'sRGB',name:'sRGB'},{id:'Adobe RGB (1998)',name:'Adobe RGB (1998)'},{id:'Display P3',name:'Display P3'},{id:'ProPhoto RGB',name:'ProPhoto RGB'}];onSelected:function(value){root.setValue('color_space',value)}}
                FineParameter {
                    visible:root.draft.format==='jpeg' || root.draft.format==='heif';label:qsTr(String('品质'));parameter:'recipe_quality';minimum:1;maximum:100;step:1;fineStep:1
                    directParameter:false;controllerReset:false;recordEdits:false;defaultValue:100;externalValue:root.draft.quality || 100
                    onValueEdited:function(value){root.setValue('quality',Math.round(value))}
                }
                MaterialSelector {
                    label:qsTr(String('输出尺寸'));enabled:root.draft.format!=='raw' && root.draft.format!=='di'
                    value:root.draft.megapixels ? 'mp' : root.draft.short_edge ? 'short' : root.draft.long_edge ? 'long' : 'full'
                    choices:[{id:'full',name:'原始像素尺寸'},{id:'mp',name:'像素数量'},{id:'long',name:'指定长边'},{id:'short',name:'指定短边'}]
                    onSelected:function(value){root.setValue('long_edge',0);root.setValue('short_edge',0);root.setValue('megapixels',0);if(value==='mp')root.setValue('megapixels',12);else if(value==='long')root.setValue('long_edge',3840);else if(value==='short')root.setValue('short_edge',2160)}
                }
                FineParameter {
                    visible:!!root.draft.long_edge || !!root.draft.short_edge || !!root.draft.megapixels
                    label:qsTr(String(root.draft.megapixels ? '像素数量' : root.draft.short_edge ? '短边' : '长边'))
                    minimum:root.draft.megapixels ? .1 : 64;maximum:root.draft.megapixels ? 200 : 32000
                    step:root.draft.megapixels ? .1 : 1;fineStep:root.draft.megapixels ? .1 : 1
                    unit:root.draft.megapixels ? 'MP' : 'px';parameter:'output_dimension';directParameter:false;controllerReset:false;recordEdits:false
                    externalValue:root.draft.megapixels || root.draft.short_edge || root.draft.long_edge || 3840
                    onValueEdited:function(value){root.setValue(root.draft.megapixels ? 'megapixels' : root.draft.short_edge ? 'short_edge' : 'long_edge',value)}
                }
                MaterialSelector {label:qsTr(String('文件命名'));value:root.draft.naming || '{name}_{film}';choices:[{id:'{name}_{film}',name:'原文件名_胶片名称'},{id:'{name}',name:'原文件名'},{id:'{date}_{name}_{film}',name:'拍摄日期_原文件名_胶片名称'},{id:'{name}_{film}_{paper}',name:'原文件名_胶片名称_相纸'},{id:'custom',name:'自定义'}];onSelected:function(value){if(value==='custom')root.customNaming=true;else{root.customNaming=false;root.setValue('naming',value)}}}
                TextField {
                    visible:root.customNaming;Layout.fillWidth:true;implicitHeight:36
                    text:root.draft.naming || '{name}_{film}';selectByMouse:true;color:Theme.ink
                    font.family:Theme.family;font.pixelSize:Theme.body
                    Accessible.name:qsTr('自定义文件命名')
                    onTextEdited:root.setValue('naming',text)
                    background:Rectangle {radius:4;color:Theme.white;border.width:1;border.color:parent.activeFocus ? Theme.accent : Theme.border}
                    ToolTip.visible:hovered || activeFocus
                    ToolTip.text:'{name}  {film}  {paper}  {index}  {date}  {year}  {month}  {day}'
                }
                RowLayout {
                    width:parent.width
                    MinchoText {text:qsTr(String('子文件夹'));Layout.preferredWidth:90}
                    TextField {
                        Layout.fillWidth:true;implicitHeight:36;text:root.draft.subfolder || '';selectByMouse:true
                        font.family:Theme.family;font.pixelSize:Theme.body;color:Theme.ink;renderType:TextInput.QtRendering;font.hintingPreference:Font.PreferVerticalHinting
                        Accessible.name:qsTr(String('输出子文件夹'));onTextEdited:root.setValue('subfolder',text)
                        background:Rectangle {radius:4;color:Theme.surface;border.width:1;border.color:parent.activeFocus ? Theme.accent : Theme.border}
                    }
                }
                MaterialSelector {label:qsTr(String('文件重名'));value:root.draft.conflict || 'rename';choices:[{id:'rename',name:'自动编号'},{id:'skip',name:'跳过已存在文件'}];onSelected:function(value){root.setValue('conflict',value)}}
                StudioSwitch {width:parent.width;text:qsTr('导出后打开文件夹');objectName:'openAfterToggle';checked:!!root.draft.open_after;onToggled:root.setValue('open_after',checked)}
                StudioSwitch {width:parent.width;text:qsTr('蓝通道补偿');objectName:'diBlueToggle';visible:root.draft.format==='di';checked:!!root.draft.di_blue_compensation;onToggled:root.setValue('di_blue_compensation',checked)}
                MinchoText {visible:root.draft.format==='di';width:parent.width;text:qsTr(String(ctrl.selectionCanExportDI ? '16 bit 底片密度编码，附带显示 LUT。不包含相纸和成品调色。' : '请先为所选照片开启负片显影'));wrapMode:Text.WordWrap;font.pixelSize:Theme.caption;color:Theme.secondary}
                StudioButton {text:qsTr(String('删除配方'));quiet:true;enabled:root.selectedId.length>0;onClicked:{ctrl.removeOutputRecipe(root.selectedId);root.createRecipe()}}
                Item {width:1;height:8}
            }
        }
        ExportResults {Layout.fillWidth:true}
        MinchoText {Layout.fillWidth:true;visible:root.recipeError.length>0;text:qsTr(String(root.recipeError));wrapMode:Text.WordWrap;color:Theme.secondary;font.pixelSize:Theme.caption}
        RowLayout {
            Layout.fillWidth:true;spacing:12
            StudioButton {text:qsTr(String('保存配方'));quiet:true;enabled:root.dirty && (root.draft.name || '').trim().length>0;onClicked:root.save()}
            Item {Layout.fillWidth:true}
            StudioButton {text:qsTr(String('选择位置并导出'));primary:true;implicitHeight:42;enabled:ctrl.canStartExport && !root.recipeError.length && (root.draft.format!=='raw' || ctrl.selectionCanExportRaw) && (root.draft.format!=='di' || ctrl.selectionCanExportDI) && (root.draft.name || '').trim().length>0;onClicked:{if(root.save())ctrl.exportRecipe(root.draft.id)}}
        }
    }
    }
}
