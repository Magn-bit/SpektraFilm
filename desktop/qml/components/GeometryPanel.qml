import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Column {
    id:root
    signal cropRequested()
    signal guidedRequested(string mode)
    width: parent.width; spacing: 22
    Column {
        objectName:'geometryControls'
        width: parent.width; spacing: 16; enabled: ctrl.currentIndex>=0 && !ctrl.exporting
        RowLayout {
            readonly property string sectionTitle:qsTr('裁切与自动校正')
            width:parent.width;spacing:6
            MinchoText{objectName:'geometryDimensions';visible:ctrl.imageWidth>0&&ctrl.imageHeight>0;text:qsTr(String(ctrl.imageWidth+' × '+ctrl.imageHeight));font.pixelSize:Theme.caption;color:Theme.secondary;Layout.fillWidth:true;elide:Text.ElideRight}
            StudioButton {objectName:'autoGeometryButton';text:qsTr(String('自动拉直'));quiet:true;implicitHeight:34;Accessible.name:qsTr(String('自动检测直线并拉直'));enabled:!ctrl.autoAdjustBusy;onClicked:ctrl.autoAdjust('geometry')}
            StudioButton {text:qsTr(String('裁切画幅'));quiet:true;implicitHeight:34;onClicked:cropRequested()}
        }
        RowLayout {
            width: parent.width; spacing: 6
            StudioButton { objectName: 'autoVerticalButton'; text: qsTr(String('自动垂直')); quiet: true; implicitHeight: 32; Layout.fillWidth: true; Accessible.name: qsTr(String('根据垂直线自动校正透视')); enabled: !ctrl.autoAdjustBusy; onClicked: ctrl.autoAdjust('geometry_vertical') }
            StudioButton { objectName: 'autoPerspectiveButton'; text: qsTr(String('自动透视')); quiet: true; implicitHeight: 32; Layout.fillWidth: true; Accessible.name: qsTr(String('根据水平与垂直线自动校正完整透视')); enabled: !ctrl.autoAdjustBusy; onClicked: ctrl.autoAdjust('geometry_full') }
        }
        RowLayout {
            width:parent.width;spacing:6
            MinchoText {text:qsTr(String('参考线'));font.pixelSize:Theme.caption;color:Theme.secondary}
            Repeater {
                model:[{id:'horizontals',name:'水平'},{id:'verticals',name:'垂直'},{id:'rectangle',name:'矩形'}]
                delegate:StudioButton {
                    required property var modelData
                    objectName:'guidedGeometry_'+modelData.id;text:qsTr(String(modelData.name));quiet:true;implicitHeight:36;Layout.fillWidth:true
                    Accessible.name:qsTr(String('使用'+modelData.name+'参考线校正透视'))
                    onClicked:root.guidedRequested(modelData.id)
                }
            }
        }
        RowLayout {
            width:parent.width;spacing:8
            MinchoText {text:qsTr(String('画面方向'));Layout.fillWidth:true}
            Repeater {
                model:[{direction:-1,name:'向左旋转 90°'},{direction:1,name:'向右旋转 90°'}]
                delegate:StudioButton {
                    required property var modelData
                    objectName:modelData.direction===1 ? 'rotateClockwiseButton' : 'rotateCounterclockwiseButton'
                    implicitWidth:44;implicitHeight:40;quiet:true
                    Accessible.name:qsTr(String(modelData.name))
                    ToolTip.visible:hovered || visualFocus;ToolTip.delay:600;ToolTip.text:qsTr(String(modelData.name))
                    contentItem:Canvas {
                        width:20;height:20
                        onPaint: {
                            var c=getContext('2d');c.reset();c.translate(width/2,height/2)
                            c.scale(modelData.direction,1)
                            c.lineWidth=1.3;c.strokeStyle=Theme.ink;c.lineJoin='round';c.lineCap='round'
                            c.beginPath();c.arc(0,0,6.5,.35,5.5,false);c.stroke()
                            c.beginPath();c.moveTo(1,-7.5);c.lineTo(5.4,-5.1);c.lineTo(5.9,-9.6);c.stroke()
                            c.strokeRect(-2.5,-2.5,5,5)
                        }
                    }
                    onClicked:ctrl.rotateQuarterTurn(modelData.direction)
                }
            }
        }
        MaskParameter {readonly property string sectionTitle:qsTr('旋转与透视');scope: 'geometry'; label: qsTr(String('旋转')); parameter: 'rotation'; minimum: -45; maximum: 45; step: .1; unit: '°' }
        MaskParameter { scope: 'geometry'; label: qsTr(String('垂直透视')); parameter: 'vertical' }
        MaskParameter { scope: 'geometry'; label: qsTr(String('水平透视')); parameter: 'horizontal' }
        MaskParameter { scope: 'geometry'; label: qsTr(String('纵横比例')); parameter: 'aspect' }
        MaskParameter { scope: 'geometry'; label: qsTr(String('缩放')); parameter: 'scale'; minimum: 100; maximum: 200; unit: '%' }
        RowLayout {
            width: parent.width
            readonly property string sectionTitle:qsTr('翻转与画幅')
            StudioButton { text: qsTr(String(ctrl.parameters.geometry.flip_horizontal ? '取消水平翻转' : '水平翻转')); quiet: true; selected: ctrl.parameters.geometry.flip_horizontal; onClicked: ctrl.setGeometryFlag('flip_horizontal',!ctrl.parameters.geometry.flip_horizontal) }
            StudioButton { text: qsTr(String(ctrl.parameters.geometry.flip_vertical ? '取消垂直翻转' : '垂直翻转')); quiet: true; selected: ctrl.parameters.geometry.flip_vertical; onClicked: ctrl.setGeometryFlag('flip_vertical',!ctrl.parameters.geometry.flip_vertical) }
        }
        RowLayout {
            width: parent.width
            MinchoText { text: qsTr(String('自动填满画幅')); Layout.fillWidth: true }
            StudioSwitch {Accessible.name:qsTr('自动填满画幅'); objectName: 'autoCropToggle';  checked:ctrl.parameters.geometry.auto_crop; onToggled: ctrl.setGeometryFlag('auto_crop',checked) }
            StudioButton { text: qsTr(String('重置几何')); quiet: true; onClicked: ctrl.resetGeometry() }
        }
    }
}
