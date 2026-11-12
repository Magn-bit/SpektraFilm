import QtQuick
import QtQuick.Window
import QtQuick.Controls.Basic
import QtQuick.Shapes

Item {
    id: root
    clip:true
    property url source
    property url originalSource
    property int pixelWidth: 0
    property int pixelHeight: 0
    property int sourcePixelWidth:pixelWidth
    property int sourcePixelHeight:pixelHeight
    property var geometryForward:[1,0,0,0,1,0,0,0,1]
    property var geometryInverse:[1,0,0,0,1,0,0,0,1]
    property bool actualSize: false
    property real zoomRatio: 1
    property bool comparing: false
    property bool maskEditing: false
    property bool cropping: false
    property alias cropTool: cropOverlay
    property alias guideTool: geometryGuides
    readonly property bool guiding:geometryGuides.active
    property var savedCropView: ({})
    property var cropSourceBounds:[0,0,1,1]
    property bool cropViewPending:false
    property real previousViewportWidth: width
    property real previousViewportHeight: height
    property var resizeAnchor: []
    property string photoKey: ''
    property var activeMask: ({})
    property real brushRadius: .04
    property real brushFeather: .7
    property real brushFlow: 1
    property bool brushErase: false
    property bool showMaskOverlay: true
    // While a local parameter is being adjusted, hide only the composited
    // overlay. Keep the raster source requested so restoring it is instant and
    // does not start another mask walk or change the provider URL.
    property bool suppressMaskOverlay: false
    property url maskOverlaySource
    property real maskOverlayOpacity: .38
    property color maskOverlayColor: '#D96B62'
    property bool temporaryPan: false
    property string strokeToken: ''
    property var pendingPoints: []
    property var livePoints: []
    property string gradientHandle: ''
    property string gradientMaskId: ''
    property var gradientStart: ({})
    property var gradientDraft: ({})
    property var pendingGradient: ({})
    property var gradientPress: [0,0]
    property var gradientPressPixel: [0,0]
    property string hoveredGradientHandle: ''
    readonly property var guideMask: gradientHandle && gradientMaskId===activeMask.id ? gradientDraft : activeMask
    readonly property bool overlayWanted:maskEditing && !comparing && !cropping && !guiding && hasImage && showMaskOverlay && !!activeMask.id
    readonly property bool overlaySourceNeeded:overlayWanted && activeMask.kind==='brush'
    readonly property bool overlayVisible:overlayWanted && !suppressMaskOverlay
    readonly property bool brushEnabled: maskEditing && !cropping && !comparing && !guiding && hasImage && !!activeMask.id
    property real comparePosition: .5
    signal positionRequested(real value)
    readonly property real dpr: Math.max(1, Screen.devicePixelRatio)
    readonly property real naturalWidth: Math.max(1, pixelWidth || output.sourceSize.width) / dpr
    readonly property real naturalHeight: Math.max(1, pixelHeight || output.sourceSize.height) / dpr
    readonly property real fitRatio: Math.min(view.width/naturalWidth, view.height/naturalHeight)
    readonly property real effectiveRatio: actualSize ? zoomRatio : fitRatio
    readonly property real imageX: output.x - view.contentX
    readonly property real imageY: output.y - view.contentY
    readonly property real imageWidth: output.width
    readonly property real imageHeight: output.height
    readonly property real visibleWidth: Math.max(0,Math.min(width,imageX+imageWidth)-Math.max(0,imageX))
    readonly property var navigatorRect:[Math.max(0,Math.min(1,-imageX/Math.max(1,imageWidth))),
        Math.max(0,Math.min(1,-imageY/Math.max(1,imageHeight))),
        Math.max(0,Math.min(width,imageX+imageWidth)-Math.max(0,imageX))/Math.max(1,imageWidth),
        Math.max(0,Math.min(view.height,imageY+imageHeight)-Math.max(0,imageY))/Math.max(1,imageHeight)]
    readonly property bool hasImage: output.status === Image.Ready
    readonly property bool detailVisible:actualSize && !cropping && !guiding && ctrl.fullDetail.ready
    readonly property var detailRect:ctrl.fullDetail.rect
    function requestDetail() {
        if(!actualSize || cropping || guiding || !hasImage || !visible)return
        var r=navigatorRect
        ctrl.fullDetail.request(r[0],r[1],r[2],r[3],Math.max(1,Math.ceil(visibleWidth*dpr)),
            Math.max(1,Math.ceil(Math.min(view.height,imageY+imageHeight)-Math.max(0,imageY))*dpr),comparing)
    }
    Timer {id:detailTimer;interval:160;repeat:false;onTriggered:root.requestDetail()}
    onNavigatorRectChanged:detailTimer.restart()
    onComparingChanged:detailTimer.restart()
    onGuidingChanged:if(!guiding)detailTimer.restart()
    onVisibleChanged:if(visible)detailTimer.restart()
    Connections {target:ctrl;function onStateChanged(){detailTimer.restart()}}
    Connections {target:ctrl.colorDisplay;ignoreUnknownSignals:true;function onChanged(){detailTimer.restart()}}
    focus: maskEditing
    Accessible.role: Accessible.Graphic
    Accessible.name: qsTr(String('照片预览与蒙版画布'))
    Accessible.description: qsTr(String('空格配合拖动平移。渐变中线移动范围，边线调整羽化，圆形手柄旋转；方向键微移，Shift 加大步进，Escape 取消当前渐变拖动。'))
    Keys.onPressed: function(event) {
        if(event.key===Qt.Key_Space && !event.isAutoRepeat) { temporaryPan=true;event.accepted=true;return }
        if(event.key===Qt.Key_Escape && gradientHandle) { cancelGradient();event.accepted=true;return }
        if(!brushEnabled || activeMask.kind==='brush' || !overlayVisible || gradientHandle)return
        var amount=event.modifiers&Qt.ShiftModifier ? 10 : 1,dx=0,dy=0
        if(event.key===Qt.Key_Left)dx=-amount/sourcePixelWidth
        else if(event.key===Qt.Key_Right)dx=amount/sourcePixelWidth
        else if(event.key===Qt.Key_Up)dy=-amount/sourcePixelHeight
        else if(event.key===Qt.Key_Down)dy=amount/sourcePixelHeight
        else return
        ctrl.beginEdit()
        if(activeMask.kind==='linear')ctrl.updateMaskGeometryMap(translatedLinear(activeMask,dx,dy))
        else ctrl.updateMaskGeometryMap({center:[Math.max(0,Math.min(1,activeMask.center[0]+dx)),Math.max(0,Math.min(1,activeMask.center[1]+dy))]})
        ctrl.endEdit();event.accepted=true
    }
    Keys.onReleased: function(event) { if(event.key===Qt.Key_Space) { temporaryPan=false;event.accepted=true } }
    onActiveFocusChanged: { if(!activeFocus) temporaryPan=false }
    onPhotoKeyChanged: { finishStroke();livePoints=[];endGuides() }
    onCroppingChanged:{if(cropping)endGuides();else detailTimer.restart()}
    onBrushEnabledChanged: { if(!brushEnabled) finishStroke();else forceActiveFocus() }
    onActiveMaskChanged: { if(gradientMaskId && gradientMaskId!==activeMask.id)finishStroke() }
    onOverlayVisibleChanged: { if(!overlayVisible)hoveredGradientHandle='' }
    onOverlaySourceNeededChanged:ctrl.setMaskOverlayVisible(overlaySourceNeeded)

    function flushPoints() {
        if(strokeToken && pendingPoints.length) { var batch=pendingPoints;pendingPoints=[];ctrl.appendMaskPoints(strokeToken,batch) }
    }
    function finishStroke() {
        flushPoints()
        if(strokeToken) ctrl.endMaskStroke(strokeToken)
        strokeToken='';livePoints=[];strokeTimer.stop()
        if(gradientHandle) {flushGradient();gradientHandle='';gradientDraft=({});gradientMaskId='';ctrl.endEdit()}
    }
    function cancelGradient() {
        if(!gradientHandle)return
        gradientTimer.stop();pendingGradient=({})
        if(activeMask.id===gradientMaskId) {
            var m=gradientStart
            ctrl.updateMaskGeometryMap({start:m.start,end:m.end,center:m.center,radius_x:m.radius_x,radius_y:m.radius_y,rotation:m.rotation})
        }
        gradientHandle='';gradientDraft=({});gradientMaskId='';ctrl.endEdit()
    }
    function project(matrix,p) {
        var d=matrix[6]*p[0]+matrix[7]*p[1]+matrix[8]
        if(Math.abs(d)<.0000001)d=d<0 ? -.0000001 : .0000001
        return [(matrix[0]*p[0]+matrix[1]*p[1]+matrix[2])/d,(matrix[3]*p[0]+matrix[4]*p[1]+matrix[5])/d]
    }
    function pointAt(px,py) {return project(geometryInverse,[(px-imageX)/Math.max(1,imageWidth),(py-imageY)/Math.max(1,imageHeight)])}
    function viewPoint(p) {var t=project(geometryForward,p);return [imageX+t[0]*imageWidth,imageY+t[1]*imageHeight]}
    function radialPoint(m,angle,scale) {
        var a=m.rotation*Math.PI/180,x=Math.cos(angle)*m.radius_x*sourcePixelWidth*scale,y=Math.sin(angle)*m.radius_y*sourcePixelHeight*scale
        return [m.center[0]+(Math.cos(a)*x-Math.sin(a)*y)/Math.max(1,sourcePixelWidth),m.center[1]+(Math.sin(a)*x+Math.cos(a)*y)/Math.max(1,sourcePixelHeight)]
    }
    function brushCircle(p,radius,angle) {
        var shortEdge=Math.max(1,Math.min(sourcePixelWidth,sourcePixelHeight))
        return viewPoint([p[0]+Math.cos(angle)*radius*shortEdge/Math.max(1,sourcePixelWidth),p[1]+Math.sin(angle)*radius*shortEdge/Math.max(1,sourcePixelHeight)])
    }
    function brushScreenRadius(p,radius) {
        var c=viewPoint(p),x=brushCircle(p,radius,0),y=brushCircle(p,radius,Math.PI/2)
        return Math.sqrt(Math.max(.01,Math.abs((x[0]-c[0])*(y[1]-c[1])-(x[1]-c[1])*(y[0]-c[0]))))
    }
    function linearValue(m,p) {
        var dx=(m.end[0]-m.start[0])*sourcePixelWidth,dy=(m.end[1]-m.start[1])*sourcePixelHeight
        return ((p[0]-m.start[0])*sourcePixelWidth*dx+(p[1]-m.start[1])*sourcePixelHeight*dy)/Math.max(.00001,dx*dx+dy*dy)
    }
    function linearPolygon(m,low,high) {
        var polygon=[[0,0],[1,0],[1,1],[0,1]]
        function clip(points,bound,above) {
            var next=[]
            for(var i=0;i<points.length;i++) {
                var a=points[i],b=points[(i+1)%points.length],va=root.linearValue(m,a),vb=root.linearValue(m,b)
                var insideA=above ? va>=bound : va<=bound,insideB=above ? vb>=bound : vb<=bound
                if(insideA)next.push(a)
                if(insideA!==insideB) {var t=(bound-va)/(vb-va);next.push([a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])])}
            }
            return next
        }
        return clip(clip(polygon,low,true),high,false)
    }
    function linearBoundary(m,value) {
        var corners=[[0,0],[1,0],[1,1],[0,1]],points=[]
        for(var i=0;i<4;i++) {
            var a=corners[i],b=corners[(i+1)%4],va=linearValue(m,a),vb=linearValue(m,b)
            if(Math.abs(vb-va)>.000001 && value>=Math.min(va,vb) && value<=Math.max(va,vb)) {var t=(value-va)/(vb-va);points.push(viewPoint([a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])]))}
        }
        return points
    }
    function gradientControls() {
        var m=guideMask;if(!m.id || m.kind==='brush')return []
        function pixel(p){return root.viewPoint(p)}
        if(m.kind==='linear') {
            var a=pixel(m.start),b=pixel(m.end),mid=pixel([(m.start[0]+m.end[0])/2,(m.start[1]+m.end[1])/2])
            var line=linearBoundary(m,.5),t=line.length>=2 ? [line[1][0]-line[0][0],line[1][1]-line[0][1]] : [-(b[1]-a[1]),b[0]-a[0]]
            var length=Math.max(1,Math.hypot(t[0],t[1])),rotation=[mid[0]+t[0]*64/length,mid[1]+t[1]*64/length]
            if(rotation[0]<Math.max(0,imageX)+12 || rotation[0]>Math.min(width,imageX+imageWidth)-12 || rotation[1]<Math.max(0,imageY)+12 || rotation[1]>Math.min(height,imageY+imageHeight)-12)
                rotation=[mid[0]-t[0]*64/length,mid[1]-t[1]*64/length]
            return [{id:'start',p:a},{id:'end',p:b},{id:'move',p:mid},{id:'linear_rotation',p:rotation}]
        }
        var c=pixel(m.center),rx=pixel(radialPoint(m,0,1)),ry=pixel(radialPoint(m,Math.PI/2,1)),length=Math.max(1,Math.hypot(rx[0]-c[0],rx[1]-c[1]))
        return [{id:'center',p:c},{id:'radius_x',p:rx},{id:'radius_y',p:ry},{id:'rotation',p:[rx[0]+(rx[0]-c[0])*28/length,rx[1]+(rx[1]-c[1])*28/length]}]
    }
    function distanceToLine(px,py,a,b) {
        var dx=b[0]-a[0],dy=b[1]-a[1],t=Math.max(0,Math.min(1,((px-a[0])*dx+(py-a[1])*dy)/Math.max(.001,dx*dx+dy*dy)))
        return Math.hypot(px-a[0]-t*dx,py-a[1]-t*dy)
    }
    function gradientHit(px,py) {
        var m=guideMask,handles=gradientControls(),best=15,chosen=''
        // The visible control is small; its hit area is deliberately larger.
        for(var i=handles.length-1;i>=0;i--){var d=Math.hypot(px-handles[i].p[0],py-handles[i].p[1]);if(d<best){best=d;chosen=handles[i].id}}
        if(chosen || m.kind!=='linear')return chosen
        var values=[.5,0,1],names=['move','start','end'];best=9
        for(i=0;i<values.length;i++){var line=linearBoundary(m,values[i]);if(line.length<2)continue;d=distanceToLine(px,py,line[0],line[1]);if(d<best){best=d;chosen=names[i]}}
        return chosen
    }
    function gradientCursor(handle) {
        if(handle==='move' || handle==='center')return gradientHandle ? Qt.ClosedHandCursor : Qt.OpenHandCursor
        if(handle==='linear_rotation' || handle==='rotation')return Qt.CrossCursor
        if(handle==='start' || handle==='end') {
            var a=viewPoint(guideMask.start),b=viewPoint(guideMask.end),angle=(Math.atan2(b[1]-a[1],b[0]-a[0])*180/Math.PI+180)%180
            return angle<22.5 || angle>=157.5 ? Qt.SizeHorCursor : angle<67.5 ? Qt.SizeFDiagCursor : angle<112.5 ? Qt.SizeVerCursor : Qt.SizeBDiagCursor
        }
        return Qt.CrossCursor
    }
    function translatedLinear(m,dx,dy) {
        dx=Math.max(-Math.min(m.start[0],m.end[0]),Math.min(1-Math.max(m.start[0],m.end[0]),dx))
        dy=Math.max(-Math.min(m.start[1],m.end[1]),Math.min(1-Math.max(m.start[1],m.end[1]),dy))
        return {start:[m.start[0]+dx,m.start[1]+dy],end:[m.end[0]+dx,m.end[1]+dy]}
    }
    function fitLinearPoint(anchor,delta) {
        var scale=1
        for(var i=0;i<2;i++) {
            if(delta[i]>0)scale=Math.min(scale,(1-anchor[i])/delta[i])
            else if(delta[i]<0)scale=Math.min(scale,-anchor[i]/delta[i])
        }
        scale=Math.max(0,scale)
        return [anchor[0]+delta[0]*scale,anchor[1]+delta[1]*scale]
    }
    function beginGradient(px,py) {
        gradientStart=Object.assign({},activeMask);gradientDraft=Object.assign({},activeMask);gradientMaskId=activeMask.id;gradientPress=pointAt(px,py)
        gradientPressPixel=[px,py]
        var chosen=gradientHit(px,py)
        ctrl.beginEdit()
        if(chosen)gradientHandle=chosen
        // A new drag starts with the fully affected end under the pointer and
        // fades toward the release side. Saved masks keep their native
        // start(0%) -> end(100%) convention; this only fixes the creation UX.
        else if(activeMask.kind==='linear')gradientHandle='drawLinear'
        else gradientHandle='drawRadial'
    }
    function moveGradient(px,py,modifiers) {
        if(!gradientHandle || activeMask.id!==gradientMaskId)return
        var p=pointAt(px,py),m=gradientStart
        p=[Math.max(0,Math.min(1,p[0])),Math.max(0,Math.min(1,p[1]))]
        if(gradientHandle==='drawLinear') {
            if(Math.hypot(px-gradientPressPixel[0],py-gradientPressPixel[1])<3)return
            var dx=p[0]-gradientPress[0],dy=p[1]-gradientPress[1]
            if(modifiers&Qt.ShiftModifier){var angle=Math.round(Math.atan2(dy*sourcePixelHeight,dx*sourcePixelWidth)/(Math.PI/4))*Math.PI/4,length=Math.hypot(dx*sourcePixelWidth,dy*sourcePixelHeight);p=fitLinearPoint(gradientPress,[Math.cos(angle)*length/sourcePixelWidth,Math.sin(angle)*length/sourcePixelHeight])}
            queueGradient({start:p,end:gradientPress.slice()})
        }else if(m.kind==='linear' && (gradientHandle==='start' || gradientHandle==='end')) {
            // A boundary moves only along the original gradient normal. A
            // tangential drag must not accidentally rotate the whole mask.
            var dx=(m.end[0]-m.start[0])*sourcePixelWidth,dy=(m.end[1]-m.start[1])*sourcePixelHeight,length=Math.max(.001,Math.hypot(dx,dy))
            var distance=((p[0]-gradientPress[0])*sourcePixelWidth*dx+(p[1]-gradientPress[1])*sourcePixelHeight*dy)/length
            var isStart=gradientHandle==='start',anchor=isStart ? m.end : m.start
            var newLength=Math.max(2,length+(isStart ? -distance : distance)),sign=isStart ? -1 : 1
            var point={};point[gradientHandle]=fitLinearPoint(anchor,[sign*dx/length*newLength/sourcePixelWidth,sign*dy/length*newLength/sourcePixelHeight]);queueGradient(point)
        }else if(gradientHandle==='linear_rotation') {
            var center=[(m.start[0]+m.end[0])/2,(m.start[1]+m.end[1])/2],sx=(gradientPress[0]-center[0])*sourcePixelWidth,sy=(gradientPress[1]-center[1])*sourcePixelHeight
            var ex=(p[0]-center[0])*sourcePixelWidth,ey=(p[1]-center[1])*sourcePixelHeight,turn=Math.atan2(ey,ex)-Math.atan2(sy,sx)
            if(modifiers&Qt.ShiftModifier)turn=Math.round(turn/(Math.PI/12))*Math.PI/12
            var dx=(m.end[0]-m.start[0])*sourcePixelWidth/2,dy=(m.end[1]-m.start[1])*sourcePixelHeight/2
            var delta=[(dx*Math.cos(turn)-dy*Math.sin(turn))/sourcePixelWidth,(dx*Math.sin(turn)+dy*Math.cos(turn))/sourcePixelHeight]
            var end=fitLinearPoint(center,delta),start=fitLinearPoint(center,[-delta[0],-delta[1]])
            var factor=Math.min(Math.hypot((end[0]-center[0])*sourcePixelWidth,(end[1]-center[1])*sourcePixelHeight),Math.hypot((start[0]-center[0])*sourcePixelWidth,(start[1]-center[1])*sourcePixelHeight))/Math.max(.001,Math.hypot(dx,dy))
            queueGradient({start:[center[0]-delta[0]*factor,center[1]-delta[1]*factor],end:[center[0]+delta[0]*factor,center[1]+delta[1]*factor]})
        }else if(gradientHandle==='center')queueGradient({center:[Math.max(0,Math.min(1,m.center[0]+p[0]-gradientPress[0])),Math.max(0,Math.min(1,m.center[1]+p[1]-gradientPress[1]))]})
        else if(gradientHandle==='move'){
            queueGradient(translatedLinear(m,p[0]-gradientPress[0],p[1]-gradientPress[1]))
        }else if(gradientHandle==='drawRadial'){
            if(Math.hypot(px-gradientPressPixel[0],py-gradientPressPixel[1])<3)return
            queueGradient({center:[(gradientPress[0]+p[0])/2,(gradientPress[1]+p[1])/2],radius_x:Math.max(.002,Math.abs(p[0]-gradientPress[0])/2),radius_y:Math.max(.002,Math.abs(p[1]-gradientPress[1])/2)})
        }else{
            var x=(p[0]-m.center[0])*sourcePixelWidth,y=(p[1]-m.center[1])*sourcePixelHeight,a=m.rotation*Math.PI/180
            if(gradientHandle==='rotation')queueGradient({rotation:Math.atan2(y,x)*180/Math.PI})
            else {var size={};size[gradientHandle]=Math.max(.002,Math.min(2,Math.abs(gradientHandle==='radius_x' ? x*Math.cos(a)+y*Math.sin(a) : -x*Math.sin(a)+y*Math.cos(a))/(gradientHandle==='radius_x' ? sourcePixelWidth : sourcePixelHeight)));queueGradient(size)}
        }
    }
    function queueGradient(values) {
        gradientDraft=Object.assign({},gradientDraft,values)
        pendingGradient=Object.assign({},pendingGradient,values)
        if(!gradientTimer.running)gradientTimer.start()
    }
    function flushGradient() {
        gradientTimer.stop();var changes=pendingGradient;pendingGradient=({})
        if(activeMask.id===gradientMaskId)ctrl.updateMaskGeometryMap(changes)
    }
    Timer {id:gradientTimer;interval:16;repeat:false;onTriggered:root.flushGradient()}
    Timer { id: strokeTimer; interval: 16; repeat: true; onTriggered: root.flushPoints() }

    function clampPosition() {
        view.contentX=Math.max(0,Math.min(view.contentX,view.contentWidth-view.width))
        view.contentY=Math.max(0,Math.min(view.contentY,view.contentHeight-view.height))
    }
    function setZoom(ratio, px, py) {
        if (!hasImage) return
        if (px===undefined) px=width/2
        if (py===undefined) py=height/2
        var u=Math.max(0,Math.min(1,(view.contentX+px-output.x)/Math.max(1,output.width)))
        var v=Math.max(0,Math.min(1,(view.contentY+py-output.y)/Math.max(1,output.height)))
        zoomRatio=Math.max(.05,Math.min(8,ratio))
        actualSize=true
        // The image's logical geometry uses source pixels even while a finer
        // frame is loading, so replacing the texture cannot shift the anchor.
        view.contentX=output.x+u*output.width-px
        view.contentY=output.y+v*output.height-py
        clampPosition()
    }
    function fit() { actualSize=false;view.contentX=0;view.contentY=0 }
    function reset() { zoomRatio=1;fit() }
    function centerOnNormalized(u,v) {
        if(!hasImage || cropping)return
        if(!actualSize)setZoom(Math.max(1,fitRatio*2))
        view.contentX=output.x+Math.max(0,Math.min(1,u))*output.width-width/2
        view.contentY=output.y+Math.max(0,Math.min(1,v))*output.height-height/2
        clampPosition()
    }
    function beginGuides(mode) {
        if(cropping || comparing || !hasImage)return false
        finishStroke();fit();return geometryGuides.begin(mode)
    }
    function endGuides(){geometryGuides.end()}
    function beginCropView(bounds) {
        savedCropView={actual:actualSize,ratio:zoomRatio,x:view.contentX,y:view.contentY,
                       scale:effectiveRatio,imageX:imageX,imageY:imageY,bounds:bounds.slice()}
        cropOverlay.begin(bounds);cropSourceBounds=bounds.slice();cropViewPending=true
        // Keep the existing crop at the same pixel scale and screen position
        // when the uncropped source replaces it. The same Flickable is used.
    }
    function alignCropView() {
        if(!cropping || !cropViewPending || output.status!==Image.Ready)return
        cropViewPending=false;zoomRatio=savedCropView.scale;actualSize=true
        view.contentX=output.x+cropSourceBounds[0]*output.width-savedCropView.imageX
        view.contentY=output.y+cropSourceBounds[1]*output.height-savedCropView.imageY
        clampPosition()
    }
    function endCropView(cancelled) {
        cropViewPending=false
        if(cancelled && savedCropView.actual!==undefined) {
            var saved=savedCropView
            Qt.callLater(function(){root.zoomRatio=saved.ratio;root.actualSize=saved.actual;view.contentX=saved.x;view.contentY=saved.y;root.clampPosition()})
        } else Qt.callLater(fit)
    }
    function stepZoom(direction,px,py) { setZoom(effectiveRatio*Math.pow(1.2,direction),px,py) }
    function queueViewportResize() {
        if(actualSize && !resizeAnchor.length) {
            var oldX=(Math.max(previousViewportWidth,output.width)-output.width)/2
            var oldY=(Math.max(previousViewportHeight,output.height)-output.height)/2
            resizeAnchor=[(view.contentX+previousViewportWidth/2-oldX)/Math.max(1,output.width),
                          (view.contentY+previousViewportHeight/2-oldY)/Math.max(1,output.height)]
        }
        previousViewportWidth=width;previousViewportHeight=height;resizeTimer.restart()
    }
    onWidthChanged:queueViewportResize()
    onHeightChanged:queueViewportResize()
    Timer {
        id:resizeTimer;interval:0;repeat:false
        onTriggered: {
            if(root.actualSize && root.resizeAnchor.length) {
                view.contentX=output.x+root.resizeAnchor[0]*output.width-root.width/2
                view.contentY=output.y+root.resizeAnchor[1]*output.height-root.height/2
            }
            root.resizeAnchor=[];root.clampPosition()
        }
    }
    onPixelWidthChanged: Qt.callLater(clampPosition)
    onActualSizeChanged: { if(!actualSize) { view.contentX=0;view.contentY=0 } else detailTimer.restart() }

    Flickable {
        id: view; objectName: 'photoFlickable'
        anchors.fill: parent; clip: true
        anchors.bottomMargin:root.guiding ? 64 : 0
        contentWidth: Math.max(width,output.width)
        contentHeight: Math.max(height,output.height)
        interactive: root.actualSize && !root.brushEnabled && !root.cropping && !root.guiding
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.AutoFlickDirection
        ShadowSurface {
            visible: output.visible; x: output.x; y: output.y
            width: output.width; height: output.height
            elevation: 2; cornerRadius: 0; color: '#FFFFFF'
        }
        Image {
            id: output; objectName: 'photoOutput'
            source: root.source; cache: false
            onStatusChanged:if(status===Image.Ready)Qt.callLater(root.alignCropView)
            width: root.naturalWidth*root.effectiveRatio
            height: root.naturalHeight*root.effectiveRatio
            x: (view.contentWidth-width)/2; y: (view.contentHeight-height)/2
            fillMode: Image.Stretch; smooth: root.effectiveRatio<1
            visible: root.source.toString().length>0
            MouseArea {
                anchors.fill: parent; acceptedButtons: Qt.LeftButton;enabled:!root.cropping && !root.guiding
                hoverEnabled:true
                cursorShape:root.actualSize ? (pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor) : Qt.ArrowCursor
                onWheel: function(event) {
                    var point=mapToItem(root,event.x,event.y)
                    var delta=event.angleDelta.y || event.pixelDelta.y
                    if(delta) root.stepZoom(delta/120,point.x,point.y)
                    event.accepted=true
                }
                onDoubleClicked: function(mouse) {
                    var point=mapToItem(root,mouse.x,mouse.y)
                    if(root.actualSize) root.fit();else root.setZoom(1,point.x,point.y)
                }
            }
        }
        Image {
            objectName:'fullDetailTile'
            visible:root.detailVisible
            x:output.x+root.detailRect[0]*output.width;y:output.y+root.detailRect[1]*output.height
            width:root.detailRect[2]*output.width;height:root.detailRect[3]*output.height
            source:visible ? ctrl.fullDetail.source : '';cache:false;fillMode:Image.Stretch
            smooth:root.effectiveRatio<1
        }
        PhotoCompare {
            objectName: 'comparisonView'
            visible: root.comparing && output.visible
            x: output.x; y: output.y; width: output.width; height: output.height
            originalSource: root.originalSource; position: root.comparePosition
            detailSource:root.detailVisible ? ctrl.fullDetail.originalSource : ''
            detailRect:root.detailRect
            smoothImage: output.smooth
            viewLeft: Math.max(0,view.contentX-x)
            viewTop: Math.max(0,view.contentY-y)
            viewWidth: Math.max(0,Math.min(width,view.contentX+view.width-x)-viewLeft)
            viewHeight: Math.max(0,Math.min(height,view.contentY+view.height-y)-viewTop)
            onPositionRequested: function(value) { root.positionRequested(value) }
        }
        CropOverlay {
            id:cropOverlay
            x:output.x;y:output.y;width:output.width;height:output.height
            visible:root.cropping;enabled:root.cropping && output.status===Image.Ready
            sourceRatio:root.naturalWidth/root.naturalHeight
            sourcePixelWidth:root.pixelWidth;sourcePixelHeight:root.pixelHeight
        }
        ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AsNeeded }
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
    }
    // The provider uses the final renderer's feather/flow/erase rasterizer.
    // No pointer event serializes or redraws the historical brush strokes.
    Image {
        id:maskOverlay;objectName:'maskOverlay'
        x:root.imageX;y:root.imageY;width:root.imageWidth;height:root.imageHeight
        source:root.maskOverlaySource;cache:false;asynchronous:true;retainWhileLoading:true;fillMode:Image.Stretch;smooth:true
        visible:root.overlayVisible && root.activeMask.kind==='brush' && root.activeMask.enabled!==false
        opacity:root.maskOverlayOpacity*(root.activeMask.opacity===undefined ? 1 : root.activeMask.opacity)
    }
    ShaderEffect {
        objectName:'gradientMaskOverlay'
        x:root.imageX;y:root.imageY;width:root.imageWidth;height:root.imageHeight
        visible:root.overlayVisible && root.activeMask.kind!=='brush' && root.activeMask.enabled!==false
        opacity:root.maskOverlayOpacity*(root.activeMask.opacity===undefined ? 1 : root.activeMask.opacity)
        readonly property var m:root.guideMask
        property vector4d inverseX:Qt.vector4d(root.geometryInverse[0],root.geometryInverse[1],root.geometryInverse[2],0)
        property vector4d inverseY:Qt.vector4d(root.geometryInverse[3],root.geometryInverse[4],root.geometryInverse[5],0)
        property vector4d inverseW:Qt.vector4d(root.geometryInverse[6],root.geometryInverse[7],root.geometryInverse[8],0)
        property vector4d maskPoints:m.kind==='linear' ? Qt.vector4d(m.start[0],m.start[1],m.end[0],m.end[1]) : Qt.vector4d((m.center||[.5,.5])[0],(m.center||[.5,.5])[1],0,0)
        property vector4d maskShape:Qt.vector4d(m.radius_x||.25,m.radius_y||.25,(m.rotation||0)*Math.PI/180,m.feather===undefined ? .75 : m.feather)
        property vector4d maskSpace:Qt.vector4d(Math.max(1,root.sourcePixelWidth-1),Math.max(1,root.sourcePixelHeight-1),m.kind==='radial' ? 1 : 0,m.inverted ? 1 : 0)
        property color tint:root.maskOverlayColor
        fragmentShader:assetsUrl+'shaders/mask-gradient.frag.qsb'
    }
    GradientMaskGuides {
        objectName:'gradientOutline';anchors.fill:parent;z:3;viewport:root
        visible:root.overlayVisible && root.activeMask.kind!=='brush'
    }
    MouseArea {
        id: brushMouse; objectName: 'maskBrushArea'; anchors.fill: parent; z: 5
        enabled: root.brushEnabled; hoverEnabled: true; acceptedButtons: Qt.LeftButton|Qt.RightButton
        preventStealing: true
        property bool panning: false
        property real previousX: 0
        property real previousY: 0
        property real cursorX: 0
        property real cursorY: 0
        // A native cursor remains visible even before/while the brush-ring
        // scene graph updates, or when an image/provider is being replaced.
        cursorShape: panning ? Qt.ClosedHandCursor : root.temporaryPan ? Qt.OpenHandCursor : root.activeMask.kind==='brush' ? Qt.CrossCursor : root.gradientCursor(root.gradientHandle || root.hoveredGradientHandle)
        onPressed: function(mouse) {
            root.forceActiveFocus();cursorX=previousX=mouse.x;cursorY=previousY=mouse.y
            panning=mouse.button===Qt.RightButton || root.temporaryPan
            if(panning) return
            var point=root.pointAt(mouse.x,mouse.y)
            if(point[0]<0 || point[0]>1 || point[1]<0 || point[1]>1) return
            if(root.activeMask.kind!=='brush'){if(root.overlayVisible)root.beginGradient(mouse.x,mouse.y);return}
            root.strokeToken=ctrl.beginMaskStroke(point[0],point[1],root.brushRadius,root.brushFeather,root.brushFlow,root.brushErase)
            if(root.strokeToken) { root.livePoints=[point];strokeTimer.start() }
        }
        onPositionChanged: function(mouse) {
            cursorX=mouse.x;cursorY=mouse.y
            if(panning) { view.contentX-=mouse.x-previousX;view.contentY-=mouse.y-previousY;root.clampPosition() }
            else if(root.gradientHandle)root.moveGradient(mouse.x,mouse.y,mouse.modifiers)
            else if(root.strokeToken) {
                var point=root.pointAt(mouse.x,mouse.y);point=[Math.max(0,Math.min(1,point[0])),Math.max(0,Math.min(1,point[1]))]
                var last=root.livePoints[root.livePoints.length-1]
                if(!last || Math.abs(point[0]-last[0])+Math.abs(point[1]-last[1])>.0003) { root.pendingPoints.push(point);root.livePoints=[point] }
            }
            if(!pressed)root.hoveredGradientHandle=root.overlayVisible && root.activeMask.kind!=='brush' ? root.gradientHit(mouse.x,mouse.y) : ''
            previousX=mouse.x;previousY=mouse.y
        }
        onReleased: function(mouse) { if(root.gradientHandle)root.moveGradient(mouse.x,mouse.y,mouse.modifiers);panning=false;root.finishStroke() }
        onCanceled: { panning=false;root.cancelGradient();root.finishStroke() }
        onExited:root.hoveredGradientHandle=''
        onWheel: function(event) { var delta=event.angleDelta.y || event.pixelDelta.y;if(delta) root.stepZoom(delta/120,event.x,event.y);event.accepted=true }
        Shape {
            id:brushCursor;objectName:'brushCursor'
            readonly property var sourcePoint:root.pointAt(brushMouse.cursorX,brushMouse.cursorY)
            readonly property real sourceRadius:root.brushRadius*Math.min(root.sourcePixelWidth,root.sourcePixelHeight)
            readonly property real diameter:Math.max(2,2*sourceRadius*Math.min(root.imageWidth/Math.max(1,root.sourcePixelWidth),root.imageHeight/Math.max(1,root.sourcePixelHeight)))
            x:root.imageX;y:root.imageY;width:diameter;height:diameter
            preferredRendererType:Shape.CurveRenderer
            visible: root.brushEnabled && root.activeMask.kind==='brush' && brushMouse.containsMouse && !brushMouse.panning && !root.temporaryPan && sourcePoint[0]>=0 && sourcePoint[0]<=1 && sourcePoint[1]>=0 && sourcePoint[1]<=1
            // Geometry stays immutable while the pointer moves. The scene graph
            // projects the source-space circle, including perspective, without
            // repainting/uploading a cursor-sized Canvas on every mouse event.
            transform:Matrix4x4 {
                matrix:{
                    var g=root.geometryForward,rx=brushCursor.sourceRadius/Math.max(1,root.sourcePixelWidth),ry=brushCursor.sourceRadius/Math.max(1,root.sourcePixelHeight)
                    var x=brushCursor.sourcePoint[0]-rx,y=brushCursor.sourcePoint[1]-ry,a=2*rx/brushCursor.diameter,b=2*ry/brushCursor.diameter,w=root.imageWidth,h=root.imageHeight
                    return Qt.matrix4x4(w*g[0]*a,w*g[1]*b,0,w*(g[0]*x+g[1]*y+g[2]),h*g[3]*a,h*g[4]*b,0,h*(g[3]*x+g[4]*y+g[5]),0,0,1,0,g[6]*a,g[7]*b,0,g[6]*x+g[7]*y+g[8])
                }
            }
            ShapePath {
                fillColor:'transparent';strokeColor:'#80252725';strokeWidth:2
                PathAngleArc {centerX:brushCursor.width/2;centerY:brushCursor.height/2;radiusX:brushCursor.width/2;radiusY:brushCursor.height/2;startAngle:0;sweepAngle:360}
            }
            ShapePath {
                fillColor:'transparent';strokeColor:'#F2FFFFFF';strokeWidth:1
                PathAngleArc {centerX:brushCursor.width/2;centerY:brushCursor.height/2;radiusX:brushCursor.width/2;radiusY:brushCursor.height/2;startAngle:0;sweepAngle:360}
            }
            ShapePath {
                fillColor:'transparent';strokeColor:root.brushFeather>0 ? '#A6FFFFFF' : 'transparent';strokeWidth:.8
                PathAngleArc {centerX:brushCursor.width/2;centerY:brushCursor.height/2;radiusX:brushCursor.width/2*(1-root.brushFeather);radiusY:brushCursor.height/2*(1-root.brushFeather);startAngle:0;sweepAngle:360}
            }
        }
    }
    GuidedGeometryOverlay {id:geometryGuides;anchors.fill:parent;viewport:root;z:30;onCloseRequested:root.endGuides()}
    HoverHandler { enabled: !root.brushEnabled && !root.cropping && !root.comparing && !root.guiding; cursorShape: root.actualSize ? Qt.OpenHandCursor : Qt.ArrowCursor }
}
