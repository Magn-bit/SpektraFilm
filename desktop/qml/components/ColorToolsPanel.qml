import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Column {
    id: root
    objectName: 'colorToolsPanel'
    property string openGroup: 'calibration'
    property string zone: 'shadows'
    property string hslBand: 'orange'
    signal stylesRequested()
    width: parent.width; spacing: 18
    enabled: ctrl.currentIndex>=0 && !ctrl.exporting
    RowLayout {
        readonly property string sectionTitle:qsTr('风格预设')
        width:parent.width;spacing:12
        MinchoText{text:qsTr(String('风格预设'));font.pixelSize:Theme.heading;Layout.fillWidth:true}
        StudioButton {
            objectName:'openStylesButton';text:qsTr(String(ctrl.currentStyleName || '无预设'))
            quiet:true;framed:true;iconName:'chevron';implicitWidth:156;implicitHeight:34
            Accessible.name:qsTr(String('风格预设'))
            onClicked:root.stylesRequested()
        }
    }
    Column {
        width:parent.width;spacing:18;visible:!!ctrl.parameters.look_lut
        RowLayout {
            width:parent.width;spacing:12
            MinchoText{objectName:'currentStyleName';text:qsTr(String(ctrl.currentStyleName));font.pixelSize:Theme.body;Layout.fillWidth:true;elide:Text.ElideRight}
            StudioButton{objectName:'clearStyleButton';text:qsTr(String('移除'));quiet:true;implicitHeight:28;Accessible.description:qsTr(String('移除此照片的创作者色彩风格，保留其它编辑'));onClicked:ctrl.clearStyleLut()}
        }
        FineParameter{objectName:'lookStrengthControl';label:qsTr(String('风格强度'));parameter:'look_strength';minimum:0;maximum:100;unit:'%'}
    }
    ToolSection {
        title:qsTr(String('色彩校准'));detail:qsTr('原色');expanded:root.openGroup==='calibration'
        onToggled:root.openGroup=expanded ? '' : 'calibration'
        CalibrationPanel {}
    }
    ToolSection {
        title: qsTr(String('色彩混合')); detail: qsTr('HSL · 八色'); expanded: root.openGroup==='hsl'
        onToggled: root.openGroup=expanded ? '' : 'hsl'
        RowLayout {
            width:parent.width;spacing:4
            Repeater {
                model:[{id:'red',name:'红',color:'#B95D57'},{id:'orange',name:'橙',color:'#C48D58'},
                    {id:'yellow',name:'黄',color:'#BAAF63'},{id:'green',name:'绿',color:'#7C9975'},
                    {id:'aqua',name:'青',color:'#699F9B'},{id:'blue',name:'蓝',color:'#6D87AC'},
                    {id:'purple',name:'紫',color:'#9381AD'},{id:'magenta',name:'洋红',color:'#B7789A'}]
                delegate: Rectangle {
                    required property var modelData
                    Layout.fillWidth:true;implicitHeight:38;radius:8
                    color:root.hslBand===modelData.id ? Theme.canvas : 'transparent'
                    border.width:root.hslBand===modelData.id || hit.activeFocus ? 1 : 0
                    border.color:Theme.accent
                    Rectangle{anchors.centerIn:parent;width:14;height:14;radius:7;color:modelData.color}
                    MouseArea {
                        id:hit;anchors.fill:parent;hoverEnabled:true;cursorShape:Qt.PointingHandCursor
                        activeFocusOnTab:true
                        Accessible.role:Accessible.RadioButton
                        Accessible.name:qsTr(String(modelData.name+'色混合'));Accessible.checked:root.hslBand===modelData.id
                        onClicked:root.hslBand=modelData.id
                        Keys.onSpacePressed:root.hslBand=modelData.id
                        Keys.onReturnPressed:root.hslBand=modelData.id
                        ToolTip.visible:containsMouse;ToolTip.text:qsTr(String(modelData.name))
                    }
                }
            }
        }
        RowLayout {
            width:parent.width
            MinchoText{text:qsTr(String(({red:'红色',orange:'橙色',yellow:'黄色',green:'绿色',aqua:'青色',blue:'蓝色',purple:'紫色',magenta:'洋红色'})[root.hslBand]));color:Theme.secondary;Layout.fillWidth:true}
            StudioButton{text:qsTr(String('重置此色'));quiet:true;implicitHeight:30;onClicked:ctrl.resetHsl(root.hslBand)}
        }
        MaskParameter{scope:'hsl';zone:root.hslBand;label:qsTr(String('色相'));parameter:'hue'}
        MaskParameter{scope:'hsl';zone:root.hslBand;label:qsTr(String('饱和度'));parameter:'saturation'}
        MaskParameter{scope:'hsl';zone:root.hslBand;label:qsTr(String('明亮度'));parameter:'luminance'}
    }
    ToolSection {
        title: qsTr(String('色调曲线')); detail: qsTr('RGB · 亮度'); expanded: root.openGroup==='curves'
        onToggled: root.openGroup=expanded ? '' : 'curves'
        CurveEditor { objectName: 'curveEditor' }
    }
    ToolSection {
        title: qsTr(String('色彩分级')); detail: qsTr('全局 · 三区'); expanded: root.openGroup==='grading'
        onToggled: root.openGroup=expanded ? '' : 'grading'
        RowLayout {
            width: parent.width; spacing: 5
            Repeater {
                model: [{id:'master',name:'全局'},{id:'shadows',name:'阴影'},{id:'midtones',name:'中间调'},{id:'highlights',name:'高光'}]
                delegate: StudioButton {required property var modelData;text:qsTr(String(modelData.name));quiet:true;selected:root.zone===modelData.id;Layout.fillWidth:true;implicitHeight:32;onClicked:root.zone=modelData.id}
            }
        }
        ColorWheel {objectName:'colorWheel';zone:root.zone}
        MaskParameter {scope:'grading';label:qsTr(String('混合'));parameter:'blending';minimum:0;maximum:100}
        MaskParameter {scope:'grading';label:qsTr(String('平衡'));parameter:'balance'}
    }
    ToolSection {
        title:qsTr('通道混合');detail:'RGB';expanded:root.openGroup==='mixer'
        onToggled:root.openGroup=expanded ? '' : 'mixer'
        ChannelMixerPanel {}
    }
}
