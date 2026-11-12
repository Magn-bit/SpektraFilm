import QtQuick
import QtQuick.Layouts

Column {
    id: root
    property string zone: 'shadows'
    readonly property var grade: ctrl.parameters.grading[zone]
    property bool dragging:false
    property string dragZone:''
    property real draftHue:0
    property real draftSaturation:0
    property var initial:({})
    readonly property real shownHue:dragging ? draftHue : grade.hue
    readonly property real shownSaturation:dragging ? draftSaturation : grade.saturation
    function flush(){wheelTimer.stop();if(dragging)ctrl.setGradingWheel(dragZone,draftHue,draftSaturation)}
    function finish(){if(!dragging)return;flush();dragging=false;ctrl.endEdit()}
    function cancel(){if(!dragging)return;wheelTimer.stop();ctrl.setGradingWheel(dragZone,initial.hue,initial.saturation);dragging=false;ctrl.endEdit()}
    onZoneChanged:finish()
    onEnabledChanged:if(!enabled)cancel()
    Timer {id:wheelTimer;interval:16;repeat:false;onTriggered:root.flush()}
    width: parent.width; spacing: 22
    Item {
        width: Math.min(parent.width,230); height: width; anchors.horizontalCenter: parent.horizontalCenter
        Canvas {
            id: wheel; objectName:'gradingWheelCanvas';anchors.fill: parent; anchors.margins: 12
            activeFocusOnTab:true
            Accessible.role:Accessible.Slider
            Accessible.name:qsTr('色轮；左右调整色相，上下调整饱和度，双击重置')
            Keys.onPressed:function(event){
                if(event.key===Qt.Key_Escape && root.dragging){root.cancel();event.accepted=true;return}
                var h=root.grade.hue,s=root.grade.saturation,step=event.modifiers&Qt.ShiftModifier ? .1 : 1
                if(event.key===Qt.Key_Left)h-=step;else if(event.key===Qt.Key_Right)h+=step
                else if(event.key===Qt.Key_Up)s+=step;else if(event.key===Qt.Key_Down)s-=step;else return
                ctrl.beginEdit();ctrl.setGradingWheel(root.zone,(h+360)%360,Math.max(0,Math.min(100,s)));ctrl.endEdit();event.accepted=true
            }
            onPaint: {
                var c=getContext('2d');c.reset();var x=width/2,y=height/2,r=width/2-2;c.clearRect(0,0,width,height)
                // Slight angular overlap prevents antialiased wedge seams.
                for(var i=0;i<360;i++){var a=i*Math.PI/180,b=(i+1)*Math.PI/180;c.fillStyle=Qt.hsva(i/360,1,.94,1);c.beginPath();c.moveTo(x,y);c.arc(x,y,r,a-.008,b+.008);c.closePath();c.fill()}
                var gradient=c.createRadialGradient(x,y,0,x,y,r);gradient.addColorStop(0,'#FCFCFB');gradient.addColorStop(1,'#00FCFCFB');c.fillStyle=gradient;c.beginPath();c.arc(x,y,r,0,Math.PI*2);c.fill()
                c.strokeStyle='#C7D0C2';c.lineWidth=1;c.beginPath();c.arc(x,y,r,0,Math.PI*2);c.stroke()
            }
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
            Rectangle {
                x: parent.width/2+Math.cos(root.shownHue*Math.PI/180)*(parent.width/2-2)*root.shownSaturation/100-width/2
                y: parent.height/2+Math.sin(root.shownHue*Math.PI/180)*(parent.width/2-2)*root.shownSaturation/100-height/2
                width: 11;height: 11;radius: 6;color: 'transparent';border.width: 2;border.color: '#FFFFFF'
                Rectangle { anchors.fill: parent;anchors.margins: -1;radius: 7;color: 'transparent';border.width: 1;border.color: '#6B252725' }
            }
            MouseArea {
                anchors.fill: parent; preventStealing: true; cursorShape: pressed ? Qt.ClosedHandCursor : Qt.CrossCursor
                function updateAt(mouse){var x=mouse.x-width/2,y=mouse.y-height/2;root.draftHue=(Math.atan2(y,x)*180/Math.PI+360)%360;root.draftSaturation=Math.min(100,Math.hypot(x,y)/(width/2-2)*100);if(!wheelTimer.running)wheelTimer.start()}
                onPressed: function(mouse){wheel.forceActiveFocus();root.dragZone=root.zone;root.initial={hue:root.grade.hue,saturation:root.grade.saturation};ctrl.beginEdit();root.dragging=true;updateAt(mouse)}
                onPositionChanged: function(mouse){if(pressed)updateAt(mouse)}
                onReleased:root.finish()
                onCanceled:root.cancel()
                onDoubleClicked:{root.finish();ctrl.resetGrading(root.zone)}
            }
            Rectangle {anchors.fill:parent;anchors.margins:-4;color:'transparent';radius:width/2;border.width:1;border.color:Theme.accent;visible:wheel.activeFocus}
        }
    }
    MaskParameter { scope: 'grading'; zone: root.zone; label: qsTr(String('色相')); parameter: 'hue'; minimum: 0; maximum: 360; unit: '°' }
    MaskParameter { scope: 'grading'; zone: root.zone; label: qsTr(String('饱和度')); parameter: 'saturation'; minimum: 0; maximum: 100 }
    MaskParameter { scope: 'grading'; zone: root.zone; label: qsTr(String('明度')); parameter: 'luminance' }
    RowLayout { width: parent.width; Item {Layout.fillWidth:true} StudioButton {text:qsTr(String('重置当前色轮'));quiet:true;implicitHeight:28;onClicked:ctrl.resetGrading(root.zone)} }
}
