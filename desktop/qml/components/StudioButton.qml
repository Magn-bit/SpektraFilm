import QtQuick
import QtQuick.Controls.Basic
Button {
    id: control
    property bool primary: false
    property string iconName: ''
    property bool quiet: false
    property bool selected: false
    property bool framed: false
    implicitWidth: Math.max(44,label.implicitWidth+(quiet ? 14 : 28))
    implicitHeight: 38
    hoverEnabled: true
    padding: 0
    opacity: enabled ? 1 : .54
    scale: down ? .975 : 1
    transform: Translate { y: control.hovered && control.primary && !control.down ? -1 : 0; Behavior on y { NumberAnimation { duration: Theme.fast; easing.type: Theme.easing } } }
    Behavior on scale { NumberAnimation { duration: Theme.fast; easing.type: Theme.easing } }
    HoverHandler {cursorShape:control.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor}
    background: Item {
        Rectangle {anchors.fill:parent;visible:control.framed&&!control.primary;radius:4;color:control.enabled ? Theme.white : Theme.surface;border.width:1;border.color:control.enabled && (control.selected || control.down) ? Theme.accent : Theme.rule}
        ShadowSurface { anchors.fill: parent; visible: control.primary; elevation: control.enabled ? 1 : 0; cornerRadius: 3; color: !control.enabled ? Theme.disabled : control.down ? Theme.buttonPressed : control.hovered ? Theme.buttonHover : Theme.buttonSurface }
        Rectangle { anchors.fill: parent; anchors.margins:control.framed ? 1 : 0; radius: 3; color: control.selected ? (control.primary ? Theme.accentInk : Theme.selection) : control.framed && control.down ? Theme.selection : Theme.hover; opacity: control.selected || (control.framed && control.down) ? 1 : control.hovered && !control.primary ? 1 : 0; Behavior on opacity { NumberAnimation { duration: Theme.fast } } }
        Rectangle { anchors.fill: parent; anchors.margins: -3; radius: 5; color: 'transparent'; border.color: Theme.accent; border.width: 1; visible: control.visualFocus }
    }
    contentItem: Item {
        Row {
            id: label; anchors.centerIn: parent; spacing: 9
            MinchoText { text: qsTr(String(control.text)); color: control.enabled ? (control.primary ? (control.selected ? Theme.accentText : Theme.buttonInk) : Theme.ink) : Theme.secondary; anchors.verticalCenter: parent.verticalCenter }
            VectorIcon { name: control.iconName;iconColor:control.enabled ? (control.primary ? (control.selected ? Theme.accentText : Theme.buttonInk) : Theme.ink) : Theme.secondary; visible: control.iconName.length>0; opacity: control.enabled ? 1 : .55; anchors.verticalCenter: parent.verticalCenter }
        }
    }
    Accessible.name: qsTr(String(text))
}
