import QtQuick
import QtQuick.Window
Image {
    id:icon
    property string name: 'plus'
    property color iconColor:Theme.ink
    width: 16; height: 16
    source: name.length>0 ? 'image://photos/ui-icon/'+encodeURIComponent(name)+'/'+encodeURIComponent(String(iconColor)) : ''
    sourceSize.width: Math.max(1,Math.round(width*Screen.devicePixelRatio))
    sourceSize.height: Math.max(1,Math.round(height*Screen.devicePixelRatio))
    fillMode: Image.PreserveAspectFit
}
