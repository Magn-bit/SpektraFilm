import QtQuick
Text {
    property bool displayRole: false
    property bool editorialRole: false
    font.family: editorialRole ? Theme.editorialFamily : displayRole ? Theme.displayFamily : Theme.family
    font.pixelSize: Theme.body
    font.weight: displayRole ? Font.Normal : Theme.bodyWeight
    font.hintingPreference: Font.PreferVerticalHinting
    color: Theme.ink
    // Distance fields remain smooth through the window mask and fractional DPI.
    // Curve rendering breaks the fine Fangsong outlines on some Windows GPUs.
    renderType: Text.QtRendering
    renderTypeQuality: font.pixelSize>=24 ? Text.HighRenderTypeQuality : Text.NormalRenderTypeQuality
}
