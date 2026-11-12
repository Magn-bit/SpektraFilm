import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Column {
    id: root
    property string title: ''
    property string detail: ''
    property bool expanded: false
    signal toggled()
    default property alias content: body.data
    width: parent.width; spacing: expanded ? 16 : 0
    Button {
        width: parent.width; height: 38; padding: 0; hoverEnabled: true
        Accessible.name: qsTr(String(root.title)); Accessible.description: qsTr(String(root.expanded ? '已展开，点击收起' : '点击展开'))
        onClicked: root.toggled()
        contentItem: RowLayout {
            spacing: 10
            MinchoText { text: qsTr(String(root.title)); font.pixelSize: Theme.heading; Layout.fillWidth: true }
            MinchoText { text: qsTr(String(root.detail)); font.pixelSize: Theme.caption; color: Theme.secondary }
            MinchoText { text: qsTr(String(root.expanded ? '−' : '+')); font.pixelSize: Theme.heading; color: Theme.secondary }
        }
        background: Rectangle { color: parent.down ? Theme.selection : parent.hovered ? Theme.hover : 'transparent'; radius: 4; border.width: parent.visualFocus ? 1 : 0; border.color: Theme.accent }
    }
    Column { id: body; width: parent.width; spacing: 16; visible: root.expanded }
}
