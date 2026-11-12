import QtQuick

Canvas {
    objectName:'settingsGlyph'
    property color iconColor:Theme.ink
    width:18;height:18
    onIconColorChanged:requestPaint()
    onWidthChanged:requestPaint()
    onHeightChanged:requestPaint()
    onPaint: {
        var c=getContext('2d');c.reset();c.scale(width/18,height/18);c.strokeStyle=iconColor;c.lineWidth=1.2;c.lineCap='round';c.lineJoin='round'
        for(var i=0;i<3;i++){var y=3+i*6,x=i===1 ? 11 : 6;c.beginPath();c.moveTo(1,y);c.lineTo(x-2.3,y);c.moveTo(x+2.3,y);c.lineTo(17,y);c.stroke();c.beginPath();c.arc(x,y,2,0,Math.PI*2);c.stroke()}
    }
}
