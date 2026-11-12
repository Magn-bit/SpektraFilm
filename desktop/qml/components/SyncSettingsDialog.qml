import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

StudioDialog {
    id:root
    objectName:'syncSettingsDialog'
    anchors.centerIn:parent;width:Math.min(480,parent.width-64);padding:24
    property var selectedCategories:['materials','exposure','WB','film_effects','print_effects']
    onOpened:selectedCategories=ctrl.clipboardInfo.selected_categories.slice()
    function toggle(key) {var values=selectedCategories.slice(),i=values.indexOf(key);if(i>=0)values.splice(i,1);else values.push(key);selectedCategories=values;ctrl.setClipboardCategories(values)}
    contentItem:ColumnLayout {
        spacing:24
        RowLayout {
            Layout.fillWidth:true
            MinchoText {text:qsTr(String('设置剪贴板'));font.pixelSize:Theme.heading;Layout.fillWidth:true}
            StudioButton {text:qsTr(String('关闭'));quiet:true;onClicked:root.close()}
        }
        MinchoText {visible:ctrl.clipboardInfo.fields>0;Layout.fillWidth:true;text:ctrl.clipboardInfo.source_name;elide:Text.ElideMiddle;color:Theme.secondary;font.pixelSize:Theme.caption;Accessible.name:qsTr('已复制来源')+' '+text}
        GridLayout {
            Layout.fillWidth:true;columns:2;columnSpacing:12;rowSpacing:8
            Repeater {
                model:[{id:'materials',name:'胶片与相纸'},{id:'exposure',name:'曝光'},{id:'WB',name:'白平衡'},{id:'film_effects',name:'胶片效果'},{id:'print_effects',name:'相纸效果'},{id:'scene_placement',name:'场景置位'},{id:'basic',name:'基础调整'},{id:'color',name:'调色'},{id:'masks',name:'蒙版'},{id:'geometry',name:'裁切与几何'}]
                delegate:StudioButton {
                    required property var modelData
                    text:qsTr(String(modelData.name));quiet:true;selected:root.selectedCategories.indexOf(modelData.id)>=0
                    Layout.fillWidth:true;implicitHeight:44
                    Accessible.role:Accessible.CheckBox;Accessible.checked:selected
                    contentItem:RowLayout {
                        spacing:12
                        Rectangle {
                            width:16;height:16;radius:3;color:parent.parent.selected ? Theme.accentInk : 'transparent';border.width:1;border.color:parent.parent.selected ? Theme.accentInk : Theme.border
                            Canvas {
                                property color checkColor:Theme.accentText
                                anchors.fill:parent;visible:parent.parent.parent.selected
                                onCheckColorChanged:requestPaint()
                                onVisibleChanged:if(visible)requestPaint()
                                onPaint:{var c=getContext('2d');c.reset();c.strokeStyle=checkColor;c.lineWidth=1.5;c.lineCap='round';c.beginPath();c.moveTo(3,8);c.lineTo(6.5,11);c.lineTo(12.5,4.5);c.stroke()}
                            }
                        }
                        MinchoText {text:qsTr(String(modelData.name));Layout.fillWidth:true}
                    }
                    onClicked:root.toggle(modelData.id)
                }
            }
        }
        RowLayout {
            Layout.fillWidth:true;spacing:8
            StudioButton {text:qsTr(String('复制当前'));quiet:true;enabled:ctrl.currentIndex>=0 && !ctrl.exporting && root.selectedCategories.length>0;onClicked:ctrl.copySettings(root.selectedCategories)}
            StudioButton {text:qsTr(String('粘贴到所选'));quiet:true;enabled:ctrl.canPasteSettings && root.selectedCategories.length>0;onClicked:{ctrl.pasteSettings(root.selectedCategories);root.close()}}
            Item {Layout.fillWidth:true}
        }
        StudioButton {
            text:qsTr(String(ctrl.selectedCount>1 ? '同步至 '+ctrl.selectedCount+' 张' : '同步至所选'))
            primary:true;Layout.fillWidth:true;implicitHeight:42
            enabled:ctrl.currentIndex>=0 && ctrl.selectedCount>1 && !ctrl.exporting && root.selectedCategories.length>0
            Accessible.description:qsTr(String('将当前照片的所选分类应用到已选照片；每张可撤销，未勾选项保持不变'))
            onClicked:{ctrl.copySettings(root.selectedCategories);ctrl.pasteSettings(root.selectedCategories);root.close()}
        }
    }
}
