import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Item {
    id:root
    objectName:'guidedGeometryOverlay'
    property var viewport
    property string mode:''
    property var points:[]
    property var initialPoints:[]
    property int selectedPoint:-1
    property string error:''
    property bool applied:false
    readonly property bool active:mode.length>0 && points.length===4
    readonly property var lines:mode==='rectangle' ? [[0,1],[1,2],[2,3],[3,0]] : [[0,1],[2,3]]
    visible:active;enabled:active && !!viewport && viewport.hasImage
    signal closeRequested()
    function copyPoints(value){return value.map(function(p){return p.slice()})}
    function begin(value){
        if(['horizontals','verticals','rectangle'].indexOf(value)<0 || !viewport || !viewport.hasImage)return false
        mode=value;resetPoints();interaction.forceActiveFocus();return true
    }
    function resetPoints(){
        var positions=mode==='horizontals' ? [[.2,1/3],[.8,1/3],[.2,2/3],[.8,2/3]] : mode==='verticals' ? [[1/3,.2],[1/3,.8],[2/3,.2],[2/3,.8]] : [[.2,.2],[.8,.2],[.8,.8],[.2,.8]]
        points=positions.map(function(p){return root.viewport.project(root.viewport.geometryInverse,p)})
        points=points.map(function(p){return [Math.max(0,Math.min(1,p[0])),Math.max(0,Math.min(1,p[1]))]})
        selectedPoint=0;error='';applied=false
    }
    function end(){mode='';points=[];initialPoints=[];error='';selectedPoint=-1}
    function screen(index){return viewport.viewPoint(points[index])}
    function setPoints(value){points=value;error='';applied=false}
    function apply(){
        var result=ctrl.applyGuidedGeometry(mode,points)
        if(result.ok){error='';applied=true;interaction.forceActiveFocus()}
        else error=result.error||qsTr(String('参考线无法对齐，请重新放置'))
    }
    onPointsChanged:ink.requestPaint()
    onSelectedPointChanged:ink.requestPaint()
    Connections {
        target:root.viewport
        function onImageXChanged(){ink.requestPaint()}
        function onImageYChanged(){ink.requestPaint()}
        function onImageWidthChanged(){ink.requestPaint()}
        function onImageHeightChanged(){ink.requestPaint()}
        function onGeometryForwardChanged(){ink.requestPaint()}
    }
    Canvas {
        id:ink;anchors.fill:parent
        onPaint:{
            var c=getContext('2d');c.reset();if(!root.active || !root.viewport)return
            c.lineCap='round';c.lineJoin='round'
            for(var pass=0;pass<2;pass++){
                c.strokeStyle=pass===0 ? '#D9FFFFFF' : Theme.accentInk;c.lineWidth=pass===0 ? 3.5 : 1.5
                for(var i=0;i<root.lines.length;i++){var pair=root.lines[i],a=root.screen(pair[0]),b=root.screen(pair[1]);c.beginPath();c.moveTo(a[0],a[1]);c.lineTo(b[0],b[1]);c.stroke()}
            }
            for(var n=0;n<4;n++){
                var p=root.screen(n),chosen=n===root.selectedPoint
                c.beginPath();c.arc(p[0],p[1],chosen ? 7 : 5.5,0,Math.PI*2)
                c.fillStyle=chosen ? Theme.accentInk : Theme.surface;c.fill();c.lineWidth=2;c.strokeStyle='#F7FFFFFF';c.stroke()
                c.beginPath();c.arc(p[0],p[1],2,0,Math.PI*2);c.fillStyle=chosen ? '#FFFFFF' : Theme.accentInk;c.fill()
            }
        }
    }
    MouseArea {
        id:interaction;objectName:'geometryGuideInteraction';anchors.fill:parent;anchors.bottomMargin:64;preventStealing:true;hoverEnabled:true;activeFocusOnTab:true
        Accessible.role:Accessible.Pane;Accessible.name:qsTr(String('透视参考线'))
        Accessible.description:qsTr(String('拖动四个控制点或线段，对齐照片中应当水平或垂直的边缘。应用后只校正透视与旋转。方向键精调，Tab 切换控制点，Esc 取消当前拖动。'))
        property int handle:-1
        property int segment:-1
        property var pressPoint:[0,0]
        property string hoverKind:''
        cursorShape:pressed ? Qt.ClosedHandCursor : hoverKind.length ? Qt.OpenHandCursor : Qt.ArrowCursor
        function distance(px,py,a,b){var dx=b[0]-a[0],dy=b[1]-a[1],length=dx*dx+dy*dy,t=length ? Math.max(0,Math.min(1,((px-a[0])*dx+(py-a[1])*dy)/length)) : 0;return Math.hypot(px-a[0]-t*dx,py-a[1]-t*dy)}
        function hit(px,py){
            for(var n=0;n<4;n++){var p=root.screen(n);if(Math.hypot(px-p[0],py-p[1])<=20)return [n,-1]}
            for(var i=0;i<root.lines.length;i++){var line=root.lines[i];if(distance(px,py,root.screen(line[0]),root.screen(line[1]))<=10)return [-1,i]}
            return [-1,-1]
        }
        onPressed:function(mouse){
            forceActiveFocus();var found=hit(mouse.x,mouse.y);handle=found[0];segment=found[1]
            root.initialPoints=root.copyPoints(root.points);pressPoint=root.viewport.pointAt(mouse.x,mouse.y)
            if(handle>=0)root.selectedPoint=handle
        }
        onPositionChanged:function(mouse){
            var found=hit(mouse.x,mouse.y);hoverKind=found[0]>=0 || found[1]>=0 ? 'move' : ''
            if(!pressed || !root.initialPoints.length || (handle<0 && segment<0))return
            var p=root.viewport.pointAt(mouse.x,mouse.y),next=root.copyPoints(root.initialPoints)
            if(handle>=0)next[handle]=[Math.max(0,Math.min(1,p[0])),Math.max(0,Math.min(1,p[1]))]
            else {
                var ids=root.lines[segment],dx=p[0]-pressPoint[0],dy=p[1]-pressPoint[1]
                for(var k=0;k<ids.length;k++){var value=next[ids[k]];dx=Math.max(-value[0],Math.min(1-value[0],dx));dy=Math.max(-value[1],Math.min(1-value[1],dy))}
                for(var j=0;j<ids.length;j++){var index=ids[j];next[index]=[next[index][0]+dx,next[index][1]+dy]}
            }
            root.setPoints(next)
        }
        onReleased:{handle=-1;segment=-1;root.initialPoints=[]}
        onCanceled:{if(root.initialPoints.length)root.points=root.initialPoints;handle=-1;segment=-1;root.initialPoints=[]}
        Keys.onPressed:function(event){
            if(event.key===Qt.Key_Escape){
                if(root.initialPoints.length){root.points=root.initialPoints;root.initialPoints=[];handle=-1;segment=-1}
                else root.closeRequested()
                event.accepted=true;return
            }
            if(event.key===Qt.Key_Tab){root.selectedPoint=(root.selectedPoint+1)%4;event.accepted=true;return}
            if(event.key===Qt.Key_Return || event.key===Qt.Key_Enter){root.apply();event.accepted=true;return}
            var amount=event.modifiers&Qt.ShiftModifier ? 10 : 1,dx=0,dy=0
            if(event.key===Qt.Key_Left)dx=-amount/Math.max(1,root.viewport.sourcePixelWidth)
            else if(event.key===Qt.Key_Right)dx=amount/Math.max(1,root.viewport.sourcePixelWidth)
            else if(event.key===Qt.Key_Up)dy=-amount/Math.max(1,root.viewport.sourcePixelHeight)
            else if(event.key===Qt.Key_Down)dy=amount/Math.max(1,root.viewport.sourcePixelHeight)
            else return
            var next=root.copyPoints(root.points),index=Math.max(0,root.selectedPoint),p=next[index]
            next[index]=[Math.max(0,Math.min(1,p[0]+dx)),Math.max(0,Math.min(1,p[1]+dy))];root.setPoints(next);event.accepted=true
        }
    }
    Column {
        anchors.horizontalCenter:parent.horizontalCenter;anchors.bottom:parent.bottom;anchors.bottomMargin:12
        width:Math.min(parent.width-24,560);spacing:8
        Rectangle {
            width:parent.width;implicitHeight:message.implicitHeight+16;visible:root.error.length>0;color:Theme.surface;radius:6
            MinchoText {id:message;anchors.fill:parent;anchors.margins:8;text:root.error;wrapMode:Text.Wrap;color:Theme.ink;font.pixelSize:Theme.caption}
        }
        Rectangle {
            width:parent.width;height:48;color:Theme.surface;radius:7
            RowLayout {
                anchors.fill:parent;anchors.margins:6;spacing:6
                MinchoText {Layout.fillWidth:true;text:qsTr(String(root.mode==='horizontals' ? '水平参考线' : root.mode==='verticals' ? '垂直参考线' : '矩形参考线'));font.pixelSize:Theme.caption;color:Theme.secondary}
                StudioButton {text:qsTr(String('重新放置'));quiet:true;implicitHeight:34;onClicked:root.resetPoints()}
                StudioButton {objectName:'closeGeometryGuides';text:qsTr(String(root.applied ? '完成' : '取消'));quiet:true;implicitHeight:34;onClicked:root.closeRequested()}
                StudioButton {objectName:'applyGeometryGuides';text:qsTr(String('应用'));primary:true;implicitHeight:34;enabled:!root.applied;onClicked:root.apply()}
            }
        }
    }
}
