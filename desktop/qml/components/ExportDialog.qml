import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

StudioPage {
    id:root
    objectName:'exportDialog'
    property string chosenPreset:'JPG_HIGH'
    signal recipesRequested()
    readonly property string recipeId:chosenPreset==='RAW' ? 'raw' : chosenPreset==='TIFF' ? 'tiff' : chosenPreset==='JPG_SHARE' ? 'jpg-share' : 'jpg-high'
    readonly property var proofRecipe:({id:'proof-preset',name:'输出打样',format:chosenPreset==='RAW' ? 'raw' : chosenPreset==='TIFF' ? 'tiff' : 'jpeg',bit_depth:chosenPreset==='RAW' || chosenPreset==='TIFF' ? 16 : 8,color_space:'sRGB',quality:chosenPreset==='JPG_SHARE' ? 85 : 100,long_edge:0})
    onOpened:if(chosenPreset==='RAW' && !ctrl.selectionCanExportRaw)chosenPreset='JPG_HIGH'
    contentItem:ColumnLayout {
        spacing:18
        RowLayout {
            Layout.fillWidth:true
            MinchoText {objectName:'exportTitle';text:qsTr(String(ctrl.selectedCount>1 ? '批量导出 '+ctrl.selectedCount+' 张' : '导出作品'));font.pixelSize:Theme.heading;Layout.fillWidth:true}
            StudioButton {text:qsTr(String('关闭'));quiet:true;onClicked:root.close()}
        }
        RowLayout {
            Layout.fillWidth:true;Layout.fillHeight:true;spacing:32
            OutputProofView {Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumWidth:0;Layout.minimumHeight:0;Layout.preferredWidth:1;Layout.preferredHeight:1;recipe:root.proofRecipe;active:root.opened}
        ScrollView {
            id:scroll;Layout.minimumWidth:320;Layout.preferredWidth:440;Layout.maximumWidth:480;Layout.fillHeight:true;Layout.minimumHeight:0;Layout.preferredHeight:1;clip:true;contentWidth:availableWidth;rightPadding:10
            ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
            Column {
                width:scroll.availableWidth;spacing:16
                Column {
                    width:parent.width;spacing:4
                    Repeater {
                        model:[{key:'JPG_HIGH',label:'高品质 JPG',detail:'原尺寸 · 质量 100 · 4:4:4 · sRGB'},
                               {key:'JPG_SHARE',label:'分享 JPG',detail:'原尺寸 · 质量 85 · 适合微信等平台'},
                               {key:'TIFF',label:'无损 TIFF',detail:'原尺寸 · 16 bit / 通道 · sRGB'},
                               {key:'RAW',label:'RAW 原片',detail:ctrl.selectionCanExportRaw ? '相机原始文件 · 不包含编辑效果' : '需全部为相机 RAW · 不将 JPG 转为 RAW'}]
                        delegate:Button {
                            id:option;required property var modelData
                            width:parent.width;height:76;padding:14;hoverEnabled:true
                            enabled:modelData.key!=='RAW' || ctrl.selectionCanExportRaw
                            checkable:true;checked:root.chosenPreset===modelData.key
                            Accessible.role:Accessible.RadioButton;Accessible.name:qsTr(String(modelData.label));Accessible.description:qsTr(String(modelData.detail))
                            onClicked:root.chosenPreset=modelData.key
                            background:Rectangle {radius:4;color:option.checked ? Theme.selection : option.hovered ? Theme.hover : 'transparent';border.width:option.visualFocus ? 1 : 0;border.color:Theme.accent}
                            contentItem:RowLayout {
                                spacing:14
                                Rectangle {width:14;height:14;radius:7;color:'transparent';border.width:1;border.color:option.enabled ? Theme.secondary : Theme.border;Rectangle {anchors.centerIn:parent;width:6;height:6;radius:3;color:Theme.accentInk;visible:option.checked}}
                                ColumnLayout {
                                    Layout.fillWidth:true;spacing:6
                                    MinchoText {text:qsTr(String(option.modelData.label));color:option.enabled ? Theme.ink : Theme.secondary;Layout.fillWidth:true}
                                    MinchoText {text:qsTr(String(option.modelData.detail));font.pixelSize:Theme.caption;color:Theme.secondary;Layout.fillWidth:true;wrapMode:Text.WordWrap}
                                }
                            }
                        }
                    }
                }
                StudioButton {objectName:'outputRecipesButton';text:qsTr(String('输出配方'));iconName:'chevron';framed:true;width:parent.width;onClicked:{root.close();root.recipesRequested()}}
                Item {width:1;height:8}
            }
        }
        }
        ExportResults {Layout.fillWidth:true}
        StudioButton {
            text:qsTr(String('选择位置并导出'));primary:true;Layout.alignment:Qt.AlignRight;Layout.preferredWidth:440;implicitHeight:44
            enabled:ctrl.canStartExport && (root.chosenPreset!=='RAW' || ctrl.selectionCanExportRaw)
            ToolTip.visible:hovered;ToolTip.delay:650;ToolTip.text:qsTr(String('在所选位置创建「'+ctrl.exportPresetFolders[root.chosenPreset]+'」文件夹；同名文件自动编号。'))
            onClicked:ctrl.exportPreset(root.chosenPreset)
        }
    }
}
