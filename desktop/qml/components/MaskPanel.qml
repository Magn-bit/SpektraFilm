import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Column {
    id: root
    property real brushRadius: .04
    property real brushFeather: .7
    property real brushFlow: 1
    property bool erasing: false
    property bool showOverlay: true
    property string overlayColor:'red'
    property real overlayOpacity:.38
    property bool brushExpanded: false
    property bool overlaySuppressed:false
    width: parent.width; spacing: 22
    enabled: ctrl.currentIndex>=0 && !ctrl.exporting
    function suppressOverlay() {
        if (overlaySuppressed) return
        overlaySuppressed=true
    }
    function restoreOverlay() {
        if (!overlaySuppressed) return
        overlaySuppressed=false
    }
    RowLayout {
        readonly property string sectionTitle:qsTr('蒙版')
        width: parent.width
        MinchoText { text: qsTr(String('局部调整')); font.pixelSize: Theme.caption; color: Theme.secondary; Layout.fillWidth: true }
        MinchoText {text:qsTr(String(ctrl.maskLayers.length+' 层'));font.pixelSize:Theme.caption;color:Theme.secondary}
    }
    RowLayout {
        width: parent.width;spacing:4
        Repeater {
            model:[{id:'brush',name:'画笔'},{id:'linear',name:'线性渐变'},{id:'radial',name:'径向渐变'}]
            delegate:StudioButton {required property var modelData;objectName:'addMask_'+modelData.id;text:qsTr(String(modelData.name));iconName:'plus';quiet:true;Layout.fillWidth:true;implicitHeight:32;onClicked:ctrl.addMaskOfKind(modelData.id)}
        }
    }
    Column {
        width: parent.width; spacing: 4
        Repeater {
            model: ctrl.maskLayers
            delegate: Rectangle {
                required property var modelData
                property bool renaming:false
                width: root.width; height: 42; radius: 4
                color: ctrl.activeMaskId===modelData.id ? Theme.selection : Theme.white
                border.width: ctrl.activeMaskId===modelData.id ? 1 : 0; border.color: Theme.border
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 6; spacing: 5
                    Item {
                        Layout.fillWidth:true;implicitHeight:34
                        StudioButton {anchors.fill:parent;text:qsTr(String(modelData.name));quiet:true;visible:!renameField.visible;selected:ctrl.activeMaskId===modelData.id;Accessible.description:qsTr(String('选择局部调整蒙版；右键可重命名'));onClicked:ctrl.selectMask(modelData.id)}
                        TextField {
                            id:renameField;anchors.fill:parent;visible:parent.parent.parent.renaming;text:modelData.name
                            font.family:Theme.family;font.pixelSize:Theme.body;color:Theme.ink;selectByMouse:true;renderType:TextInput.QtRendering;font.hintingPreference:Font.PreferVerticalHinting
                            Accessible.name:qsTr(String('蒙版名称'))
                            onVisibleChanged:if(visible){forceActiveFocus();selectAll()}
                            onEditingFinished:{if(text.trim().length)ctrl.renameMask(modelData.id,text);parent.parent.parent.renaming=false}
                            Keys.onEscapePressed:{text=modelData.name;parent.parent.parent.renaming=false}
                            background:Rectangle {radius:3;color:Theme.surface;border.width:1;border.color:Theme.accent}
                        }
                        TapHandler {acceptedButtons:Qt.RightButton;onTapped:layerMenu.popup()}
                        Menu {id:layerMenu;background:ShadowSurface {elevation:2;cornerRadius:Theme.popupRadius;color:Theme.surface} MenuItem {text:qsTr(String('重命名'));font.family:Theme.family;onTriggered:renameField.parent.parent.parent.renaming=true}}
                    }
                    StudioSwitch {showState:false;Accessible.name:qsTr('蒙版 ')+modelData.name;objectName:'maskEnabledToggle';  checked:modelData.enabled;   onToggled: ctrl.setMaskEnabled(modelData.id,checked) }
                    StudioButton {
                        objectName:'deleteMask_'+modelData.id;iconName:'trash';quiet:true;implicitWidth:30;implicitHeight:32
                        Accessible.name:qsTr(String('删除蒙版 '+modelData.name))
                        ToolTip.visible:hovered || visualFocus;ToolTip.delay:500;ToolTip.text:qsTr(String('删除此蒙版'))
                        onClicked:{ctrl.selectMask(modelData.id);ctrl.deleteMask()}
                    }
                }
            }
        }
    }
    Column {
        width: parent.width; spacing: 22; visible: ctrl.activeMaskId.length>0
        RowLayout {
            width: parent.width; spacing: 4
            Repeater {
                model: ['添加笔迹','擦除笔迹']
                delegate: StudioButton {
                    required property int index; required property string modelData
                    objectName:'maskBrushMode_'+index;text: qsTr(String(modelData)); quiet: true; selected: root.erasing===(index===1); visible: ctrl.activeMaskGuide.kind==='brush'; Layout.fillWidth: true; implicitHeight: 31
                    onClicked: root.erasing=index===1
                }
            }
        }
        StudioSwitch {readonly property string sectionTitle:qsTr('选区显示');objectName:'toggleMaskOverlayButton';width:parent.width;text:qsTr('选区显示');checked:root.showOverlay;onToggled:root.showOverlay=checked}
        RowLayout {
            width:parent.width;visible:ctrl.activeMaskGuide.kind==='brush';spacing:8
            StudioButton {
                objectName:'removeLastMaskStrokeButton';text:qsTr(String('删除上一笔'));quiet:true;implicitHeight:32
                enabled:(ctrl.activeMaskGuide.strokeCount || 0)>0
                Accessible.description:qsTr(String('仅删除当前蒙版的最后一笔；可撤销'))
                onClicked:ctrl.removeLastMaskStroke()
            }
            Item {Layout.fillWidth:true}
            StudioButton {
                objectName:'clearMaskStrokesButton';text:qsTr(String('清空笔迹'));quiet:true;implicitHeight:32
                enabled:(ctrl.activeMaskGuide.strokeCount || 0)>0
                Accessible.description:qsTr(String('清空当前蒙版的全部笔迹；保留局部调整参数，可撤销'))
                onClicked:ctrl.clearMask()
            }
        }
        RowLayout {
            width:parent.width;spacing:8;visible:root.showOverlay
            MinchoText {text:qsTr(String('选区叠加'));font.pixelSize:Theme.caption;color:Theme.secondary;Layout.fillWidth:true}
            Repeater {
                model:[{id:'red',name:'红色选区',color:'#D96B62'},{id:'cyan',name:'青色选区',color:'#55BFC7'}]
                delegate:StudioButton {
                    required property var modelData
                    objectName:'maskOverlayColor_'+modelData.id;quiet:true;implicitWidth:34;implicitHeight:34
                    Accessible.name:qsTr(String(modelData.name));Accessible.role:Accessible.RadioButton;Accessible.checked:root.overlayColor===modelData.id
                    ToolTip.visible:hovered || visualFocus;ToolTip.delay:600;ToolTip.text:qsTr(String(modelData.name))
                    contentItem:Item {
                        Rectangle {anchors.centerIn:parent;width:15;height:15;radius:7.5;color:modelData.color}
                        Rectangle {anchors.centerIn:parent;width:23;height:23;radius:11.5;color:'transparent';border.width:root.overlayColor===modelData.id ? 1 : 0;border.color:Theme.accentInk}
                    }
                    onClicked:{root.overlayColor=modelData.id;ctrl.setMaskOverlayColor(modelData.id)}
                }
            }
        }
        MaskParameter {visible:root.showOverlay;label:qsTr(String('显示浓度'));minimum:10;maximum:75;step:1;unit:'%';currentValue:root.overlayOpacity*100;localAdjustment:false;onEdited:function(value){root.overlayOpacity=value/100}}
        RowLayout {
            readonly property string sectionTitle:qsTr('画笔设置')
            function reveal(){root.brushExpanded=true}
            width: parent.width;visible:ctrl.activeMaskGuide.kind==='brush'
            StudioButton { text: qsTr(String(root.brushExpanded ? '收起画笔设置' : '画笔设置')); quiet: true; implicitHeight: 28; onClicked: root.brushExpanded=!root.brushExpanded }
            MinchoText { text: qsTr(String((root.brushRadius*100).toFixed(1)+'% · 柔边 '+Math.round(root.brushFeather*100)+'%')); font.pixelSize: Theme.caption; color: Theme.secondary; Layout.fillWidth: true; horizontalAlignment: Text.AlignRight }
        }
        Column {
            width: parent.width; spacing: 18; visible: root.brushExpanded && ctrl.activeMaskGuide.kind==='brush'
            MaskParameter { label: qsTr(String('画笔半径')); minimum: .2; maximum: 20; step: .2; unit: '%'; currentValue: root.brushRadius*100; localAdjustment: false; onEdited: function(value) { root.brushRadius=value/100 } }
            MaskParameter { label: qsTr(String('柔边')); minimum: 0; maximum: 100; unit: '%'; currentValue: root.brushFeather*100; localAdjustment: false; onEdited: function(value) { root.brushFeather=value/100 } }
            MaskParameter { label: qsTr(String('流量')); minimum: 1; maximum: 100; unit: '%'; currentValue: root.brushFlow*100; localAdjustment: false; onEdited: function(value) { root.brushFlow=value/100 } }
            MinchoText { width: parent.width; text: qsTr(String('空格或右键拖动平移 · 滚轮缩放')); font.pixelSize: Theme.caption; color: Theme.secondary; wrapMode: Text.WordWrap }
        }
        RowLayout {
            readonly property string sectionTitle:qsTr('范围设置')
            function reveal(){root.brushExpanded=true}
            width:parent.width;visible:ctrl.activeMaskGuide.kind!=='brush'
            StudioButton{text:qsTr(String(root.brushExpanded ? '收起范围设置' : '范围设置'));quiet:true;implicitHeight:28;onClicked:root.brushExpanded=!root.brushExpanded}
            MinchoText{text:qsTr(String(ctrl.activeMaskGuide.kind==='linear' ? '拖动端点与中点' : '拖动圆心与边缘'));font.pixelSize:Theme.caption;color:Theme.secondary;Layout.fillWidth:true;horizontalAlignment:Text.AlignRight}
        }
        MaskParameter {visible:ctrl.activeMaskGuide.kind==='radial' && root.brushExpanded;scope:'maskGeometry';label:qsTr(String('边缘羽化'));parameter:'feather';minimum:0;maximum:100;valueScale:100;unit:'%'}
        RowLayout {
            width: parent.width; spacing: 2
            StudioSwitch {Layout.fillWidth:true;text:qsTr('反相');objectName:'maskInvertToggle';checked:!!ctrl.activeMaskGuide.inverted;onToggled:ctrl.invertMask()}
            Item { Layout.fillWidth: true }
        }
        MaskParameter {readonly property string sectionTitle:qsTr('局部调整');label: qsTr(String('不透明度')); parameter: 'opacity'; minimum: 0; maximum: 100; valueScale: 100; unit: '%';onEditingStarted:root.suppressOverlay();onEditingFinished:root.restoreOverlay() }
        MaskParameter {objectName:'maskExposureControl';label: qsTr(String('曝光')); parameter: 'exposure'; minimum: -3; maximum: 3; step: .01; unit: 'EV';onEditingStarted:root.suppressOverlay();onEditingFinished:root.restoreOverlay() }
        MaskParameter { label: qsTr(String('冷暖')); parameter: 'temperature';onEditingStarted:root.suppressOverlay();onEditingFinished:root.restoreOverlay() }
        MaskParameter { label: qsTr(String('色调')); parameter: 'tint';onEditingStarted:root.suppressOverlay();onEditingFinished:root.restoreOverlay() }
        MaskParameter { label: qsTr(String('对比度')); parameter: 'contrast';onEditingStarted:root.suppressOverlay();onEditingFinished:root.restoreOverlay() }
        MaskParameter { label: qsTr(String('饱和度')); parameter: 'saturation';onEditingStarted:root.suppressOverlay();onEditingFinished:root.restoreOverlay() }
        MaskParameter { label: qsTr(String('高光')); parameter: 'highlights';onEditingStarted:root.suppressOverlay();onEditingFinished:root.restoreOverlay() }
        MaskParameter { label: qsTr(String('阴影')); parameter: 'shadows';onEditingStarted:root.suppressOverlay();onEditingFinished:root.restoreOverlay() }
    }
}
