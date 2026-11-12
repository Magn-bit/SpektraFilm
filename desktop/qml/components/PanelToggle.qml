import QtQuick
import QtQuick.Controls.Basic

Button {
    id:control
    property bool expanded:true
    property bool sidePanel:false
    property string panelName:''
    property string shortcut:''
    implicitWidth:sidePanel ? 28 : 40
    implicitHeight:sidePanel ? 44 : 28
    hoverEnabled:true
    activeFocusOnTab:true
    checked:expanded
    Accessible.name:(expanded ? qsTr('收起') : qsTr('展开'))+panelName
    Accessible.description:panelName+(expanded ? qsTr('已展开') : qsTr('已收起'))
    ToolTip.visible:hovered || visualFocus
    ToolTip.delay:600
    ToolTip.text:Accessible.name+(shortcut ? ' · '+shortcut : '')
    HoverHandler {cursorShape:Qt.PointingHandCursor}
    contentItem:Item {
        VectorIcon {
            anchors.centerIn:parent;width:16;height:16;name:'triangle-down'
            iconColor:control.down ? Theme.accentInk : Theme.ink
            rotation:control.sidePanel ? (control.expanded ? -90 : 90) : (control.expanded ? 0 : 180)
            Behavior on rotation {NumberAnimation {duration:Theme.fast;easing.type:Theme.easing}}
        }
    }
    background:Rectangle {
        anchors.centerIn:parent
        width:control.sidePanel ? 22 : 36;height:control.sidePanel ? 36 : 22;radius:5
        color:control.down ? Theme.selection : control.hovered ? Theme.hover : Theme.panelFooter
        border.width:control.visualFocus ? 1 : 0;border.color:Theme.accent
        Behavior on color {ColorAnimation {duration:Theme.fast}}
    }
}
