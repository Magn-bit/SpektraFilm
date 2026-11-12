import QtQuick

Item {
    id: root
    objectName: 'cropOverlay'
    property var draft: [0,0,1,1]
    property real ratio: 0
    property string ratioName: '自由'
    property bool transposed: false
    property real sourceRatio: 1
    property int sourcePixelWidth: 1
    property int sourcePixelHeight: 1
    readonly property int outputWidth: Math.max(1,Math.round(draft[2]*sourcePixelWidth)-Math.round(draft[0]*sourcePixelWidth))
    readonly property int outputHeight: Math.max(1,Math.round(draft[3]*sourcePixelHeight)-Math.round(draft[1]*sourcePixelHeight))
    function clamp(v,a,b) {return Math.max(a,Math.min(b,v))}
    function begin(bounds) {draft=bounds.slice();ratio=0;ratioName='自由';transposed=false}
    function chooseRatio(name,value) {
        ratioName=name;ratio=value
        if(!ratio)return
        var r=ratio/sourceRatio,w=Math.min(1,r),h=Math.min(1,1/r)
        var cx=clamp((draft[0]+draft[2])/2,w/2,1-w/2),cy=clamp((draft[1]+draft[3])/2,h/2,1-h/2)
        draft=[cx-w/2,cy-h/2,cx+w/2,cy+h/2]
    }
    function resetDraft() {begin([0,0,1,1])}
    function moveBy(dx,dy) {
        var p=draft.slice();dx=clamp(dx,-p[0],1-p[2]);dy=clamp(dy,-p[1],1-p[3])
        draft=[p[0]+dx,p[1]+dy,p[2]+dx,p[3]+dy]
    }
    Rectangle {width:parent.width;height:root.draft[1]*parent.height;color:'#8C202520'}
    Rectangle {y:root.draft[3]*parent.height;width:parent.width;height:(1-root.draft[3])*parent.height;color:'#8C202520'}
    Rectangle {y:root.draft[1]*parent.height;width:root.draft[0]*parent.width;height:(root.draft[3]-root.draft[1])*parent.height;color:'#8C202520'}
    Rectangle {x:root.draft[2]*parent.width;y:root.draft[1]*parent.height;width:(1-root.draft[2])*parent.width;height:(root.draft[3]-root.draft[1])*parent.height;color:'#8C202520'}
    Rectangle {
        id: selection
        x:root.draft[0]*parent.width;y:root.draft[1]*parent.height
        width:(root.draft[2]-root.draft[0])*parent.width;height:(root.draft[3]-root.draft[1])*parent.height
        color:'transparent';border.width:1;border.color:'#F2FFFFFF'
        Repeater {model:[1,2];Rectangle {required property int modelData;x:parent.width*modelData/3;width:1;height:parent.height;color:interaction.pressed ? '#88FFFFFF' : '#45FFFFFF'}}
        Repeater {model:[1,2];Rectangle {required property int modelData;y:parent.height*modelData/3;height:1;width:parent.width;color:interaction.pressed ? '#88FFFFFF' : '#45FFFFFF'}}
        Repeater {
            model:[[0,0],[1,0],[0,1],[1,1]]
            Item {
                required property var modelData;x:modelData[0]*selection.width;y:modelData[1]*selection.height
                Rectangle {x:modelData[0] ? -17 : -1;y:modelData[1] ? -2 : -1;width:18;height:3;color:'#FFFFFF'}
                Rectangle {x:modelData[0] ? -2 : -1;y:modelData[1] ? -17 : -1;width:3;height:18;color:'#FFFFFF'}
            }
        }
        Repeater {
            model:[[.5,0],[.5,1],[0,.5],[1,.5]]
            Rectangle {
                required property var modelData
                x:modelData[0]*selection.width-width/2;y:modelData[1]*selection.height-height/2
                width:modelData[0]===.5 ? 20 : 3;height:modelData[0]===.5 ? 3 : 20;color:'#FFFFFF'
            }
        }
    }
    MouseArea {
        id: interaction;objectName:'cropInteraction';anchors.fill:parent
        preventStealing:true;hoverEnabled:true;activeFocusOnTab:true
        Accessible.role:Accessible.Pane;Accessible.name:qsTr(String('裁切范围'))
        Accessible.description:qsTr(String('拖动内部移动范围，拖动四角或边缘调整大小；方向键移动，Shift 加速，Enter 应用，Esc 取消'))
        property var initial:[]
        property var pressPoint:[]
        property string mode:''
        property string hoverMode:''
        function hitMode(px,py) {
            var l=root.draft[0]*width,r=root.draft[2]*width,t=root.draft[1]*height,b=root.draft[3]*height
            var nearL=Math.abs(px-l)<18,nearR=Math.abs(px-r)<18,nearT=Math.abs(py-t)<18,nearB=Math.abs(py-b)<18
            if((nearL || nearR) && (nearT || nearB))return (nearL ? 'l' : 'r')+(nearT ? 't' : 'b')
            if(py>=t-18 && py<=b+18 && (nearL || nearR))return nearL ? 'l' : 'r'
            if(px>=l-18 && px<=r+18 && (nearT || nearB))return nearT ? 't' : 'b'
            return px>=l && px<=r && py>=t && py<=b ? 'move' : 'draw'
        }
        cursorShape:pressed && mode==='move' ? Qt.ClosedHandCursor : hoverMode==='move' ? Qt.OpenHandCursor :
                    hoverMode==='l' || hoverMode==='r' ? Qt.SizeHorCursor : hoverMode==='t' || hoverMode==='b' ? Qt.SizeVerCursor :
                    hoverMode==='lt' || hoverMode==='rb' ? Qt.SizeFDiagCursor : hoverMode==='rt' || hoverMode==='lb' ? Qt.SizeBDiagCursor : Qt.CrossCursor
        onPressed:function(mouse) {forceActiveFocus();initial=root.draft.slice();pressPoint=[mouse.x/width,mouse.y/height];mode=hitMode(mouse.x,mouse.y)}
        onPositionChanged:function(mouse) {
            hoverMode=hitMode(mouse.x,mouse.y);if(!pressed)return
            var x=root.clamp(mouse.x/width,0,1),y=root.clamp(mouse.y/height,0,1),p=initial.slice()
            var dx=x-pressPoint[0],dy=y-pressPoint[1]
            if(mode==='move') {dx=root.clamp(dx,-p[0],1-p[2]);dy=root.clamp(dy,-p[1],1-p[3]);root.draft=[p[0]+dx,p[1]+dy,p[2]+dx,p[3]+dy];return}
            var minW=Math.min(24/Math.max(1,width),.2),minH=Math.min(24/Math.max(1,height),.2)
            // Free edges move just that edge. Locked edges preserve the ratio
            // about the opposite edge's midpoint rather than rotating a corner.
            if(mode.length===1 && mode!=='draw') {
                if(mode==='l')p[0]=root.clamp(x,0,p[2]-minW)
                else if(mode==='r')p[2]=root.clamp(x,p[0]+minW,1)
                else if(mode==='t')p[1]=root.clamp(y,0,p[3]-minH)
                else p[3]=root.clamp(y,p[1]+minH,1)
                if(root.ratio>0) {
                    var n=root.ratio/root.sourceRatio,cx=(initial[0]+initial[2])/2,cy=(initial[1]+initial[3])/2
                    if(mode==='l' || mode==='r') {var h=Math.min((p[2]-p[0])/n,2*Math.min(cy,1-cy));var w=h*n;p[0]=mode==='l' ? p[2]-w : p[0];p[2]=mode==='r' ? p[0]+w : p[2];p[1]=cy-h/2;p[3]=cy+h/2}
                    else {var w2=Math.min((p[3]-p[1])*n,2*Math.min(cx,1-cx));var h2=w2/n;p[1]=mode==='t' ? p[3]-h2 : p[1];p[3]=mode==='b' ? p[1]+h2 : p[3];p[0]=cx-w2/2;p[2]=cx+w2/2}
                }
                root.draft=p;return
            }
            var ax=mode==='draw' ? pressPoint[0] : mode.indexOf('l')>=0 ? p[2] : p[0]
            var ay=mode==='draw' ? pressPoint[1] : mode.indexOf('t')>=0 ? p[3] : p[1]
            var sx=x>=ax ? 1 : -1,sy=y>=ay ? 1 : -1,maxW=sx>0 ? 1-ax : ax,maxH=sy>0 ? 1-ay : ay
            var w3=root.clamp(Math.abs(x-ax),Math.min(minW,maxW),maxW),h3=root.clamp(Math.abs(y-ay),Math.min(minH,maxH),maxH)
            if(root.ratio>0) {var r=root.ratio/root.sourceRatio;w3=Math.min(Math.max(w3,h3*r,minW,minH*r),maxW,maxH*r);h3=w3/r}
            var bx=root.clamp(ax+sx*w3,0,1),by=root.clamp(ay+sy*h3,0,1)
            root.draft=[Math.min(ax,bx),Math.min(ay,by),Math.max(ax,bx),Math.max(ay,by)]
        }
        Keys.onPressed:function(event) {
            var step=(event.modifiers & Qt.ShiftModifier) ? 10 : 1,dx=step/Math.max(1,root.sourcePixelWidth),dy=step/Math.max(1,root.sourcePixelHeight)
            if(event.key===Qt.Key_Left)root.moveBy(-dx,0)
            else if(event.key===Qt.Key_Right)root.moveBy(dx,0)
            else if(event.key===Qt.Key_Up)root.moveBy(0,-dy)
            else if(event.key===Qt.Key_Down)root.moveBy(0,dy)
            else {event.accepted=false;return}
            event.accepted=true
        }
    }
}
