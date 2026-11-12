import QtQuick

Canvas {
    property color iconColor:Theme.ink
    width:20;height:20
    onIconColorChanged:requestPaint()
    onWidthChanged:requestPaint()
    onHeightChanged:requestPaint()
    onPaint: {
        var c=getContext('2d');c.reset();c.scale(width/20,height/20);c.lineWidth=1.2;c.lineJoin='round';c.lineCap='round';c.strokeStyle=iconColor
        c.strokeRect(1.5,2,9,5.5);c.strokeRect(12.5,9,5.5,9)
        c.beginPath();c.moveTo(5,11);c.lineTo(5,15);c.lineTo(9.5,15);c.moveTo(7.5,13);c.lineTo(9.5,15);c.lineTo(7.5,17);c.stroke()
        c.beginPath();c.moveTo(15.5,5);c.lineTo(15.5,3);c.lineTo(12.5,3);c.stroke()
    }
}
