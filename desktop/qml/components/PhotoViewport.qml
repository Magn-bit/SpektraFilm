import QtQuick
import QtQuick.Window
import QtQuick.Controls.Basic

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
    readonly property bool overlaySourceNeeded:maskEditing && !comparing && !cropping && !guiding && hasImage && showMaskOverlay && !!activeMask.id
    readonly property bool overlayVisible:overlaySourceNeeded && !suppressMaskOverlay
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
    onGuideMaskChanged: gradientOutline.requestPaint()
    onHoveredGradientHandleChanged: gradientOutline.requestPaint()
    onOverlayVisibleChanged: { if(!overlayVisible)hoveredGradientHandle='' }
    onOverlaySourceNeededChanged:ctrl.setMaskOverlayVisible(overlaySourceNeeded)
    onImageXChanged: gradientOutline.requestPaint()
    onImageYChanged: gradientOutline.requestPaint()
    onImageWidthChanged: gradientOutline.requestPaint()
    onImageHeightChanged: gradientOutline.requestPaint()
    onGeometryForwardChanged:{gradientOutline.requestPaint();brushCursor.requestPaint()}

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
        source:root.maskOverlaySource;cache:false;asynchronous:true;fillMode:Image.Stretch;smooth:true
        visible:root.overlayVisible && root.activeMask.enabled!==false
        opacity:root.maskOverlayOpacity*(root.activeMask.opacity===undefined ? 1 : root.activeMask.opacity)
    }
    Canvas {
        id:gradientOutline;objectName:'gradientOutline';anchors.fill:parent;z:3
        visible:root.overlayVisible && root.activeMask.kind!=='brush'
        onWidthChanged:requestPaint()
        onHeightChanged:requestPaint()
        onPaint:{
            var c=getContext('2d');c.reset();c.clearRect(0,0,width,height);var m=root.guideMask;if(!m.id)return
            c.save();c.beginPath();c.rect(root.imageX,root.imageY,root.imageWidth,root.imageHeight);c.clip();c.lineJoin='round';c.lineCap='round'
            var handles=root.gradientControls();if(!handles.length){c.restore();return}
            function outline(inner) {
                c.beginPath()
                var radius=inner ? Math.max(0,1-m.feather) : 1
                for(var sample=0;sample<=96;sample++){var edge=root.viewPoint(root.radialPoint(m,sample*Math.PI/48,radius));if(sample===0)c.moveTo(edge[0],edge[1]);else c.lineTo(edge[0],edge[1])}c.closePath()
                if(!inner){c.moveTo(handles[1].p[0],handles[1].p[1]);c.lineTo(handles[3].p[0],handles[3].p[1])}
            }
            if(m.kind==='linear') {
                // The center moves the gradient. Dashed outer boundaries
                // describe its true 0% and 100% rasterized feather limits.
                var values=[0,.5,1],names=['start','move','end']
                for(var i=0;i<3;i++) {
                    var boundary=root.linearBoundary(m,values[i]);if(boundary.length<2)continue
                    var selected=root.gradientHandle===names[i] || root.hoveredGradientHandle===names[i]
                    c.setLineDash(i===1 ? [] : [5,5]);c.beginPath();c.moveTo(boundary[0][0],boundary[0][1]);c.lineTo(boundary[1][0],boundary[1][1])
                    c.lineWidth=selected ? 3.2 : 2.6;c.strokeStyle='#8C252725';c.stroke()
                    c.lineWidth=selected ? 1.5 : 1;c.strokeStyle=selected ? '#FFFFFF' : '#E6FFFFFF';c.stroke()
                }
                c.setLineDash([]);c.beginPath();c.moveTo(handles[0].p[0],handles[0].p[1]);c.lineTo(handles[1].p[0],handles[1].p[1]);c.lineWidth=1;c.strokeStyle='#99FFFFFF';c.stroke()
            } else {
                c.lineWidth=3;c.strokeStyle='#B3252725';outline(false);c.stroke()
                c.lineWidth=1.15;c.strokeStyle='#F2FFFFFF';outline(false);c.stroke()
                c.setLineDash([4,4]);c.lineWidth=2.6;c.strokeStyle='#80252725';outline(true);c.stroke()
                c.lineWidth=1;c.strokeStyle='#D9FFFFFF';outline(true);c.stroke();c.setLineDash([])
            }
            // Keep guides on the photograph while leaving boundary controls
            // fully visible in its surrounding gutter.
            c.restore()
            for(var h=0;h<handles.length;h++){
                var active=root.gradientHandle===handles[h].id || root.hoveredGradientHandle===handles[h].id,rotation=handles[h].id==='linear_rotation' || handles[h].id==='rotation'
                var r=rotation ? 7 : handles[h].id==='move' || handles[h].id==='center' ? 6 : 4
                c.beginPath();c.arc(handles[h].p[0],handles[h].p[1],r+1.3,0,Math.PI*2);c.fillStyle='#B3252725';c.fill()
                c.beginPath();c.arc(handles[h].p[0],handles[h].p[1],r,0,Math.PI*2);c.fillStyle=active ? Theme.accentInk : Theme.surface;c.fill();c.lineWidth=1.2;c.strokeStyle=active ? '#FFFFFF' : Theme.accentInk;c.stroke()
                if(rotation) {
                    var x=handles[h].p[0],y=handles[h].p[1];c.strokeStyle=active ? '#FFFFFF' : Theme.ink;c.lineWidth=1
                    c.beginPath();c.arc(x,y,3.2,-Math.PI*.8,Math.PI*.7);c.stroke();c.beginPath();c.moveTo(x+1.9,y+3);c.lineTo(x-.1,y+3.5);c.lineTo(x+.5,y+1.4);c.stroke()
                } else if(handles[h].id==='move' || handles[h].id==='center') {
                    c.beginPath();c.arc(handles[h].p[0],handles[h].p[1],1.5,0,Math.PI*2);c.fillStyle=active ? '#FFFFFF' : Theme.accentInk;c.fill()
                }
            }
        }
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
        // Canvas is repainted, or when an image/provider is being replaced.
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
        Canvas {
            id:brushCursor;objectName:'brushCursor'
            readonly property var sourcePoint:root.pointAt(brushMouse.cursorX,brushMouse.cursorY)
            readonly property real cursorRadius: {
                var maximum=1
                for(var i=0;i<4;i++){var p=root.brushCircle(sourcePoint,root.brushRadius,i*Math.PI/2);maximum=Math.max(maximum,Math.hypot(p[0]-brushMouse.cursorX,p[1]-brushMouse.cursorY))}
                return maximum+6
            }
            x:brushMouse.cursorX-cursorRadius;y:brushMouse.cursorY-cursorRadius;width:cursorRadius*2;height:cursorRadius*2
            visible: root.brushEnabled && root.activeMask.kind==='brush' && brushMouse.containsMouse && !brushMouse.panning && !root.temporaryPan && sourcePoint[0]>=0 && sourcePoint[0]<=1 && sourcePoint[1]>=0 && sourcePoint[1]<=1
            onVisibleChanged:requestPaint()
            onPaint: {
                var c=getContext('2d');c.reset();c.clearRect(0,0,width,height)
                var p=sourcePoint
                function circle(radius) {c.beginPath();for(var i=0;i<=48;i++){var v=root.brushCircle(p,radius,i*Math.PI/24);if(i===0)c.moveTo(v[0]-brushCursor.x,v[1]-brushCursor.y);else c.lineTo(v[0]-brushCursor.x,v[1]-brushCursor.y)}c.closePath()}
                c.lineWidth=2;c.strokeStyle='#8C252725';circle(root.brushRadius);c.stroke()
                c.lineWidth=1;c.strokeStyle='#F2FFFFFF';circle(root.brushRadius);c.stroke()
                if(root.brushFeather>0){c.strokeStyle='#A6FFFFFF';circle(root.brushRadius*(1-root.brushFeather));c.stroke()}
                c.beginPath();c.moveTo(width/2-2,height/2);c.lineTo(width/2+2,height/2);c.moveTo(width/2,height/2-2);c.lineTo(width/2,height/2+2);c.lineWidth=2;c.strokeStyle='#8C252725';c.stroke();c.lineWidth=1;c.strokeStyle='#FFFFFF';c.stroke()
            }
            Connections {target:brushMouse;function onCursorXChanged(){brushCursor.requestPaint()}function onCursorYChanged(){brushCursor.requestPaint()}}
            Connections {target:root;function onBrushRadiusChanged(){brushCursor.requestPaint()}function onBrushFeatherChanged(){brushCursor.requestPaint()}}
        }
    }
    GuidedGeometryOverlay {id:geometryGuides;anchors.fill:parent;viewport:root;z:30;onCloseRequested:root.endGuides()}
    HoverHandler { enabled: !root.brushEnabled && !root.cropping && !root.comparing && !root.guiding; cursorShape: root.actualSize ? Qt.OpenHandCursor : Qt.ArrowCursor }
}
