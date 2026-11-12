import QtQuick
import QtQuick.Controls.Basic
Dialog {
    padding: Theme.dialogPadding
    modal: true
    focus: true
    font.family: Theme.family
    font.pixelSize: Theme.body
    background: ShadowSurface { elevation: 4; cornerRadius: Theme.dialogRadius; color: Theme.surface }
    Overlay.modal: Rectangle { color: Theme.scrim }
    enter: Transition { NumberAnimation { property: 'opacity'; from: 0; to: 1; duration: Theme.standard; easing.type: Theme.easing } }
    exit: Transition { NumberAnimation { property: 'opacity'; from: 1; to: 0; duration: Theme.fast; easing.type: Theme.easing } }
}
