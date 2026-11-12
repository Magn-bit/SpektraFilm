import QtQuick
import QtQuick.Controls.Basic

StudioDialog {
    // A focused task replaces the client area; the window's title strip stays.
    x:0;y:34;width:parent.width;height:parent.height-34
    padding:28
    background:Rectangle {color:Theme.surface;radius:14}
    Overlay.modal:Rectangle {color:'transparent'}
}
