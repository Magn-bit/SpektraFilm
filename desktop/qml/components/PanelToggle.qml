import QtQuick
import QtQuick.Controls.Basic

Button {
    id:control
    property bool expanded:true
    property bool sidePanel:false
    property string panelName:''
    property string shortcut:''
    implicitWidth:sidePanel ? 16 : 40
    implicitHeight:sidePanel ? 44 : 28
    padding:0
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
            anchors.centerIn:parent;width:12;height:12;name:'triangle-down'
            iconColor:control.down || control.visualFocus ? Theme.accentInk : Theme.secondary
            rotation:control.sidePanel ? (control.expanded ? -90 : 90) : (control.expanded ? 0 : 180)
            Behavior on rotation {NumberAnimation {duration:Theme.fast;easing.type:Theme.easing}}
        }
    }
    background:Rectangle {
        anchors.centerIn:parent
        width:control.sidePanel ? control.width : 32;height:control.sidePanel ? 32 : 20;radius:4
        color:control.down ? Theme.selection : Theme.hover
        opacity:control.hovered || control.down || control.visualFocus ? 1 : 0
        border.width:control.visualFocus ? 1 : 0;border.color:Theme.accent
        Behavior on opacity {NumberAnimation {duration:Theme.fast}}
    }
}
