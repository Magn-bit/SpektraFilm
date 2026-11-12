import QtQuick
import QtQuick.Controls.Basic

StudioButton {
    id: control
    property string glyph: ''
    property string description: ''
    property int glyphSize: 16
    quiet: true
    implicitWidth: 32
    implicitHeight: 32
    Accessible.name: description
    ToolTip.visible: hovered || visualFocus
    ToolTip.text: description
    ToolTip.delay: 550
    // Controls owns contentItem geometry; size the glyph inside a wrapper.
    contentItem: Item {
        VectorIcon {
            anchors.centerIn: parent
            name: control.glyph
            width: control.glyphSize; height: control.glyphSize
            iconColor: control.selected ? Theme.accentInk : Theme.secondary
        }
    }
}
