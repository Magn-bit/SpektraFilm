import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Column {
    id: root
    property string title: ''
    property string detail: ''
    property bool expanded: false
    readonly property string sectionTitle:title
    function reveal() { if(!expanded) toggled() }
    signal toggled()
    default property alias content: body.data
    width: parent.width; spacing: expanded ? 14 : 0
    Button {
        id:header
        width: parent.width; height: 40; padding: 10; hoverEnabled: true
        Accessible.name: qsTr(String(root.title)); Accessible.description: qsTr(String(root.expanded ? '已展开，点击收起' : '点击展开'))
        onClicked: root.toggled()
        contentItem: RowLayout {
            spacing: 10
            VectorIcon {name:'triangle-down';Layout.preferredWidth:10;Layout.preferredHeight:10;rotation:root.expanded ? 0 : -90;iconColor:Theme.secondary}
            MinchoText { text: qsTr(String(root.title)); font.pixelSize: Theme.heading; Layout.fillWidth: true }
            MinchoText { text: qsTr(String(root.detail)); font.pixelSize: Theme.caption; color: Theme.secondary;Layout.maximumWidth:header.width*.38;elide:Text.ElideRight }
        }
        background: Rectangle { color: header.down ? Theme.selection : header.hovered ? Theme.hover : Theme.panelInset; radius: 4; border.width: header.visualFocus ? 1 : 0; border.color: Theme.accent }
    }
    Column { id: body; width: parent.width; spacing: 16; visible: root.expanded }
}
