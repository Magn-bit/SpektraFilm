import QtQuick
import QtQuick.Controls.Basic

Item {
    id:root
    objectName:'photoNavigator'
    property var viewport
    property url source:viewport ? viewport.source : ''
    readonly property var visibleRect:viewport ? viewport.navigatorRect : [0,0,1,1]
    implicitWidth:176;implicitHeight:132
    enabled:!!viewport && viewport.hasImage && !viewport.cropping
    Accessible.role:Accessible.Graphic
    Accessible.name:qsTr(String('照片导航'))
    Accessible.description:qsTr(String('点击照片定位，拖动范围框平移，双击适合窗口；方向键平移'))
    Rectangle {anchors.fill:parent;color:Theme.canvas;radius:5}
    Image {
        id:mini;objectName:'navigatorImage';anchors.fill:parent;anchors.margins:8
        source:root.source;sourceSize:Qt.size(256,192);fillMode:Image.PreserveAspectFit
        asynchronous:true;cache:false;smooth:true
    }
    Item {
        id:picture;x:mini.x+(mini.width-mini.paintedWidth)/2;y:mini.y+(mini.height-mini.paintedHeight)/2
        width:mini.paintedWidth;height:mini.paintedHeight
        Rectangle {
            id:box;objectName:'navigatorVisibleRect'
            x:root.visibleRect[0]*parent.width;y:root.visibleRect[1]*parent.height
            width:root.visibleRect[2]*parent.width;height:root.visibleRect[3]*parent.height
            visible:root.enabled && mini.status===Image.Ready
            color:interaction.pressed ? '#225F6F57' : 'transparent'
            border.width:2;border.color:Theme.accentInk
            Rectangle {anchors.fill:parent;anchors.margins:2;color:'transparent';border.width:1;border.color:'#CCFFFFFF'}
        }
        MouseArea {
            id:interaction;objectName:'navigatorInteraction';anchors.fill:parent;preventStealing:true;hoverEnabled:true
            activeFocusOnTab:true
            cursorShape:pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
            property real offsetX:0
            property real offsetY:0
            function moveTo(px,py){if(width>0 && height>0 && root.viewport)root.viewport.centerOnNormalized(px/width-offsetX,py/height-offsetY)}
            onPressed:function(mouse){
                forceActiveFocus()
                var r=root.visibleRect,u=mouse.x/width,v=mouse.y/height
                var inside=u>=r[0] && u<=r[0]+r[2] && v>=r[1] && v<=r[1]+r[3]
                offsetX=inside ? u-r[0]-r[2]/2 : 0;offsetY=inside ? v-r[1]-r[3]/2 : 0
                if(!inside)moveTo(mouse.x,mouse.y)
            }
            onPositionChanged:function(mouse){if(pressed)moveTo(mouse.x,mouse.y)}
            onDoubleClicked:root.viewport.fit()
            Keys.onPressed:function(event){
                var r=root.visibleRect,step=event.modifiers&Qt.ShiftModifier ? .1 : .02,dx=0,dy=0
                if(event.key===Qt.Key_Left)dx=-step
                else if(event.key===Qt.Key_Right)dx=step
                else if(event.key===Qt.Key_Up)dy=-step
                else if(event.key===Qt.Key_Down)dy=step
                else if(event.key===Qt.Key_0){root.viewport.fit();event.accepted=true;return}
                else return
                root.viewport.centerOnNormalized(r[0]+r[2]/2+dx,r[1]+r[3]/2+dy);event.accepted=true
            }
        }
    }
    Rectangle {anchors.fill:parent;radius:5;color:'transparent';border.width:interaction.activeFocus ? 2 : 1;border.color:interaction.activeFocus ? Theme.accent : Theme.border}
}
