import QtQuick
import QtQuick.Controls.Basic

Switch {
    id: control
    property bool showState: true
    readonly property string stateText: checked ? qsTr('开启') : qsTr('关闭')
    implicitWidth: Math.max(48, (text.length ? label.implicitWidth + 16 : 0)
                            + (showState ? stateLabel.width + 10 : 0) + 48)
    implicitHeight: Math.max(36, label.implicitHeight + 8)
    padding: 4
    spacing: 10
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    opacity: enabled ? 1 : .46
    Accessible.name: text
    Accessible.description: stateText
    Accessible.role: Accessible.CheckBox
    Accessible.checked: checked
    HoverHandler { cursorShape: control.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor }
    background: Item {}
    indicator: Rectangle {
        id: track
        objectName: control.objectName + '_track'
        implicitWidth: 40; implicitHeight: 22
        x: control.width - control.rightPadding - width
        y: (control.height - height) / 2
        radius: height / 2
        color: control.checked ? Theme.accentInk : Theme.switchOff
        border.width: 1
        border.color: control.checked ? Theme.accentInk : control.hovered ? Theme.secondary : Theme.border
        Rectangle {
            anchors.fill: parent; anchors.margins: -4
            radius: height / 2; color: 'transparent'
            border.width: 2; border.color: Theme.accent
            visible: control.visualFocus
        }
        Rectangle {
            objectName: control.objectName + '_thumb'
            x: 2; y: 2; width: 18; height: 18; radius: 9
            color: control.checked ? Theme.accentText : Theme.switchThumb
            scale: control.down ? .9 : 1
            transform: Translate {
                x: control.visualPosition * 18
                Behavior on x { NumberAnimation { duration: control.down ? 0 : Theme.fast; easing.type: Theme.easing } }
            }
            Behavior on scale { NumberAnimation { duration: Theme.fast; easing.type: Theme.easing } }
        }
    }
    contentItem: Item {
        MinchoText {
            id: label
            anchors.left: parent.left; anchors.right: stateLabel.left
            anchors.rightMargin: control.text.length ? 16 : 0
            anchors.verticalCenter: parent.verticalCenter
            text: control.text; color: Theme.ink; elide: Text.ElideRight
        }
        MinchoText {
            id: stateLabel
            anchors.right: parent.right; anchors.rightMargin: track.width + 10
            anchors.verticalCenter: parent.verticalCenter
            text: control.stateText; visible: control.showState
            width: control.showState ? Math.max(onText.width, offText.width) : 0
            font.pixelSize: Theme.caption; horizontalAlignment: Text.AlignRight
            color: control.checked ? Theme.accentInk : Theme.secondary
            TextMetrics { id: onText; font: stateLabel.font; text: qsTr('开启') }
            TextMetrics { id: offText; font: stateLabel.font; text: qsTr('关闭') }
        }
    }
}
