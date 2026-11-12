import QtQuick
import QtQuick.Controls.Basic

Item {
    id:root
    property real position:0
    property real trackWidth:1
    property bool pointingUp:true
    property color fillColor:Theme.ink
    property string label:''
    property bool keyboardFocus:false
    signal editingStarted()
    signal valueDragged(real value)
    signal editingFinished()
    signal resetRequested()
    width:36;height:30
    activeFocusOnTab:true
    Accessible.role:Accessible.Slider;Accessible.name:qsTr(String(label))
    Accessible.description:qsTr(String('左右方向键调整，Shift 细调，双击恢复默认值'))
    function adjust(delta){editingStarted();valueDragged(Math.max(0,Math.min(1,position+delta)));editingFinished()}
    Keys.onPressed:function(event){
        keyboardFocus=true
        var step=(event.modifiers & Qt.ShiftModifier) ? 1/65535 : 1/255
        if(event.key===Qt.Key_Left || event.key===Qt.Key_Down){adjust(-step);event.accepted=true}
        else if(event.key===Qt.Key_Right || event.key===Qt.Key_Up){adjust(step);event.accepted=true}
        else if(event.key===Qt.Key_Home){adjust(-1);event.accepted=true}
        else if(event.key===Qt.Key_End){adjust(1);event.accepted=true}
        else if(event.key===Qt.Key_Backspace || event.key===Qt.Key_Delete){resetRequested();event.accepted=true}
    }
    Canvas {
        id:tip;anchors.centerIn:parent;width:14;height:14
        onPaint:{
            var c=getContext('2d');c.reset();c.lineJoin='round';c.lineWidth=1.2
            c.beginPath()
            if(root.pointingUp){c.moveTo(7,2);c.lineTo(12,11);c.lineTo(2,11)}
            else{c.moveTo(2,3);c.lineTo(12,3);c.lineTo(7,12)}
            c.closePath();c.fillStyle=hit.pressed ? Theme.accentInk : root.fillColor;c.fill();c.strokeStyle=root.fillColor===Theme.ink ? '#FFFFFF' : Theme.ink;c.stroke()
        }
    }
    Rectangle {anchors.centerIn:parent;width:25;height:25;radius:4;color:'transparent';border.width:root.activeFocus && root.keyboardFocus ? 1 : 0;border.color:Theme.accent}
    MouseArea {
        id:hit;anchors.fill:parent;hoverEnabled:true;preventStealing:true;cursorShape:Qt.SizeHorCursor
        property real initial:0
        property real pressX:0
        onPressed:function(mouse){root.keyboardFocus=false;root.forceActiveFocus(Qt.MouseFocusReason);initial=root.position;pressX=mapToItem(null,mouse.x,mouse.y).x;root.editingStarted();tip.requestPaint()}
        onPositionChanged:function(mouse){if(pressed){var x=mapToItem(null,mouse.x,mouse.y).x;var gain=(mouse.modifiers & Qt.ShiftModifier) ? .1 : 1;root.valueDragged(Math.max(0,Math.min(1,initial+(x-pressX)/Math.max(1,root.trackWidth)*gain)))}}
        onReleased:{root.editingFinished();tip.requestPaint()}
        onCanceled:{root.editingFinished();tip.requestPaint()}
        onDoubleClicked:{root.editingFinished();root.resetRequested()}
        ToolTip.visible:containsMouse;ToolTip.delay:600;ToolTip.text:qsTr(String(root.label))
    }
    onFillColorChanged:tip.requestPaint()
    Connections {target:Theme;function onDarkChanged(){tip.requestPaint()}}
}
