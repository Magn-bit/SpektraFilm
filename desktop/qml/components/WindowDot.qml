import QtQuick
import QtQuick.Controls.Basic
Button {
    id: control
    property color dotColor: '#FF6058'
    property string windowAction: 'close'
    property bool restoreIcon: false
    objectName: 'windowDot_'+windowAction
    implicitWidth: 28; implicitHeight: 30
    padding: 0; hoverEnabled: true
    opacity: enabled ? 1 : .35
    scale: down ? .93 : 1
    Behavior on scale { NumberAnimation { duration: Theme.fast; easing.type: Theme.easing } }
    background: Item {}
    contentItem: Item {
        Item {
            id: face; objectName: 'dotFace'
            width: 12; height: 12; anchors.centerIn: parent; anchors.alignWhenCentered: false
            Rectangle { anchors.fill: parent; radius: 6; color: control.dotColor; border.width: .7; border.color: Qt.darker(control.dotColor,1.12); antialiasing: true }
            Rectangle { objectName: 'dotFocus'; anchors.centerIn: parent; anchors.alignWhenCentered: false; width: 20; height: 20; radius: 10; color: 'transparent'; border.width: 1; border.color: Theme.accent; antialiasing: true; visible: control.visualFocus }
            Item {
                objectName: 'dotGlyph'; anchors.fill: parent
                opacity: control.hovered || control.visualFocus ? .8 : 0
                Behavior on opacity { NumberAnimation { duration: Theme.fast } }
                Rectangle { anchors.centerIn: parent; anchors.alignWhenCentered: false; width: 6; height: 1; color: '#3B332B'; rotation: control.windowAction==='close' ? 45 : 0; visible: control.windowAction!=='maximize'; antialiasing: true }
                Rectangle { anchors.centerIn: parent; anchors.alignWhenCentered: false; width: 6; height: 1; color: '#3B332B'; rotation: -45; visible: control.windowAction==='close'; antialiasing: true }
                Rectangle { objectName: 'maximizeGlyph'; anchors.centerIn: parent; anchors.alignWhenCentered: false; width: 5; height: 5; border.width: 1; border.color: '#254E23'; color: 'transparent'; visible: control.windowAction==='maximize' && !control.restoreIcon; antialiasing: true }
                Item {
                    anchors.fill: parent; visible: control.windowAction==='maximize' && control.restoreIcon
                    Rectangle { x: 5; y: 3; width: 4; height: 4; color: control.dotColor; border.width: 1; border.color: '#254E23' }
                    Rectangle { x: 3; y: 5; width: 4; height: 4; color: control.dotColor; border.width: 1; border.color: '#254E23' }
                }
            }
        }
    }
    ToolTip.visible: hovered
    ToolTip.delay: 600
    ToolTip.text: qsTr(String(Accessible.name))
}
