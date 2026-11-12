import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

StudioDialog {
    id:root
    objectName:'styleLibrary'
    property string chosenId:''
    property string seenImport:''
    property string category:'all'
    readonly property var filteredPresets:{
        var items=[];for(var i=0;i<ctrl.stylePresets.length;i++){
            var item=ctrl.stylePresets[i],kind=item.category || 'general'
            if(category==='all' || kind===category || item.id==='none')items.push(item)
        }
        return items
    }
    readonly property var chosenPreset:{for(var i=0;i<ctrl.stylePresets.length;i++)if(ctrl.stylePresets[i].id===chosenId)return ctrl.stylePresets[i];return {}}
    onOpened:{if(!chosenId && ctrl.stylePresets.length)chosenId=ctrl.stylePresets[0].id}
    Connections {
        target:ctrl
        function onStateChanged(){
            if(ctrl.importedStyleId && ctrl.importedStyleId!==root.seenImport){
                root.seenImport=ctrl.importedStyleId;root.category='all';root.chosenId=ctrl.importedStyleId
                for(var i=0;i<root.filteredPresets.length;i++)if(root.filteredPresets[i].id===root.chosenId)styles.positionViewAtIndex(i,ListView.Contain)
            }
        }
    }
    contentItem:ColumnLayout {
        spacing:20
        RowLayout {
            Layout.fillWidth:true
            MinchoText{text:qsTr(String('风格预设'));font.pixelSize:Theme.heading;Layout.fillWidth:true}
            StudioButton{objectName:'importStyleButton';text:qsTr(String('导入'));quiet:true;implicitHeight:30;onClicked:ctrl.importStyle()}
            StudioButton{text:qsTr(String('关闭'));quiet:true;implicitHeight:30;onClicked:root.close()}
        }
        RowLayout {
            Layout.fillWidth:true;spacing:5
            Repeater {
                model:[{id:'all',name:'全部'},{id:'portrait',name:'人像'},{id:'landscape',name:'风光'}]
                delegate:StudioButton {
                    required property var modelData
                    text:qsTr(String(modelData.name));quiet:true;selected:root.category===modelData.id;implicitHeight:30
                    onClicked:{root.category=modelData.id;var current=root.filteredPresets.some(function(item){return item.id===root.chosenId});if(!current)root.chosenId=root.filteredPresets.length ? root.filteredPresets[0].id : ''}
                }
            }
            Item{Layout.fillWidth:true}
        }
        ListView {
            id:styles;objectName:'stylePresetList';Layout.fillWidth:true;Layout.fillHeight:true
            clip:true;spacing:0;model:root.filteredPresets
            ScrollBar.vertical:ScrollBar{policy:ScrollBar.AsNeeded}
            delegate:Item {
                required property var modelData;required property int index
                objectName:'stylePreset_'+modelData.id
                width:styles.width;height:110;activeFocusOnTab:true
                Accessible.role:Accessible.RadioButton;Accessible.name:qsTr(String(modelData.name))
                Accessible.description:qsTr(String(modelData.description))
                Accessible.checked:root.chosenId===modelData.id
                function choose(){root.chosenId=modelData.id}
                Keys.onReturnPressed:choose()
                Keys.onSpacePressed:choose()
                Rectangle{anchors.fill:parent;anchors.margins:1;radius:4;color:root.chosenId===modelData.id ? Theme.selection : mouse.containsMouse ? Theme.hover : 'transparent';border.width:parent.activeFocus ? 1 : 0;border.color:Theme.accent}
                RowLayout {
                    anchors.fill:parent;anchors.leftMargin:14;anchors.rightMargin:16;spacing:15
                    Rectangle {
                        width:13;height:13;radius:7;color:'transparent';border.width:1;border.color:root.chosenId===modelData.id ? Theme.accent : Theme.border
                        Rectangle{anchors.centerIn:parent;width:5;height:5;radius:3;color:Theme.accent;visible:root.chosenId===modelData.id}
                    }
                    ColumnLayout {
                        Layout.fillWidth:true;spacing:7
                        MinchoText{text:qsTr(String(modelData.name));textFormat:Text.PlainText;font.pixelSize:Theme.heading;Layout.fillWidth:true;elide:Text.ElideRight}
                        MinchoText{visible:modelData.id!=='none';text:qsTr(String((modelData.kind==='original' ? '原创' : modelData.kind==='creative-hald' || modelData.kind==='community-hald' ? '创作者风格' : modelData.kind==='xmp-partial' ? 'XMP 部分转换' : '本地预设')+(modelData.author ? ' · '+modelData.author : '')));textFormat:Text.PlainText;font.pixelSize:Theme.caption;color:Theme.secondary;Layout.fillWidth:true;elide:Text.ElideRight}
                        MinchoText{text:qsTr(String(modelData.description));textFormat:Text.PlainText;font.pixelSize:Theme.caption;color:Theme.secondary;Layout.fillWidth:true;wrapMode:Text.WordWrap;maximumLineCount:2;elide:Text.ElideRight;lineHeight:1.3}
                    }
                }
                Rectangle{anchors.bottom:parent.bottom;width:parent.width;height:1;color:Theme.rule}
                MouseArea{id:mouse;anchors.fill:parent;hoverEnabled:true;cursorShape:Qt.PointingHandCursor;onClicked:parent.choose()}
            }
            MinchoText{anchors.centerIn:parent;text:qsTr(String('暂无可用风格'));visible:styles.count===0;color:Theme.secondary;font.pixelSize:Theme.caption}
        }
        RowLayout {
            Layout.fillWidth:true;visible:!!root.chosenPreset.source
            MinchoText {
                Layout.fillWidth:true;text:/^https?:\/\//i.test(root.chosenPreset.source || '') ? '' : root.chosenPreset.source || ''
                textFormat:Text.PlainText;font.pixelSize:Theme.caption;color:Theme.secondary;elide:Text.ElideRight
            }
            StudioButton {
                text:qsTr(String('查看来源'));quiet:true;implicitHeight:28;visible:/^https?:\/\//i.test(root.chosenPreset.source || '')
                Accessible.description:qsTr(String('在浏览器中打开此风格的原始出处'))
                onClicked:Qt.openUrlExternally(root.chosenPreset.source)
            }
        }
        ScrollView {
            Layout.fillWidth:true;Layout.preferredHeight:Math.min(150,warningLabel.implicitHeight)
            visible:(root.chosenPreset.warnings || []).length>0;clip:true
            ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
            MinchoText {
                id:warningLabel;width:parent.width;text:qsTr(String((root.chosenPreset.warnings || []).join('\n')))
                textFormat:Text.PlainText;font.pixelSize:Theme.caption;color:Theme.secondary;wrapMode:Text.WordWrap;lineHeight:1.4
            }
        }
        MinchoText {
            Layout.fillWidth:true;wrapMode:Text.WordWrap;lineHeight:1.5
            text:qsTr(String(ctrl.selectedCount>1 ? '应用至已选 '+ctrl.selectedCount+' 张。保留各张曝光、白平衡、胶片、几何与蒙版。' : '保留当前曝光、白平衡、胶片、几何与蒙版。'))
            font.pixelSize:Theme.caption;color:Theme.secondary
        }
        StudioButton {
            objectName:'applyStyleButton';Layout.fillWidth:true;implicitHeight:42;primary:true
            text:qsTr(String(ctrl.selectedCount>1 ? '应用至 '+ctrl.selectedCount+' 张' : '应用风格'))
            enabled:root.chosenId.length>0 && ctrl.currentIndex>=0 && !ctrl.exporting
            onClicked:{if(ctrl.applyStyle(root.chosenId))root.close()}
        }
    }
}
