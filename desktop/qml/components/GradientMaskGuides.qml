import QtQuick
import QtQuick.Shapes

Item {
    id:root
    required property var viewport
    readonly property var mask:viewport.guideMask
    readonly property var handles:viewport.gradientControls()
    function ellipse(scale) {
        var points=[]
        for(var i=0;i<=96;i++) {
            var p=viewport.viewPoint(viewport.radialPoint(mask,i*Math.PI/48,scale))
            points.push(Qt.point(p[0]-viewport.imageX,p[1]-viewport.imageY))
        }
        return points
    }
    Item {
        x:root.viewport.imageX;y:root.viewport.imageY
        width:root.viewport.imageWidth;height:root.viewport.imageHeight;clip:true
        Repeater {
            model:root.mask.kind==='linear' ? 3 : 0
            delegate:Shape {
                id:line
                required property int index
                readonly property var edge:root.viewport.linearBoundary(root.mask,index*.5)
                readonly property string handle:['start','move','end'][index]
                readonly property bool highlighted:root.viewport.gradientHandle===handle || root.viewport.hoveredGradientHandle===handle
                readonly property real x1:edge.length>1 ? edge[0][0]-root.viewport.imageX : 0
                readonly property real y1:edge.length>1 ? edge[0][1]-root.viewport.imageY : 0
                readonly property real x2:edge.length>1 ? edge[1][0]-root.viewport.imageX : 0
                readonly property real y2:edge.length>1 ? edge[1][1]-root.viewport.imageY : 0
                width:parent.width;height:parent.height;visible:edge.length>1
                preferredRendererType:Shape.CurveRenderer
                ShapePath {
                    fillColor:'transparent';strokeColor:'#66252725';strokeWidth:2
                    strokeStyle:line.index===1 ? ShapePath.SolidLine : ShapePath.DashLine
                    dashPattern:[2.5,2.5]
                    startX:line.x1;startY:line.y1;PathLine{x:line.x2;y:line.y2}
                }
                ShapePath {
                    fillColor:'transparent';strokeColor:line.highlighted ? '#FFFFFF' : '#D9FFFFFF';strokeWidth:1
                    strokeStyle:line.index===1 ? ShapePath.SolidLine : ShapePath.DashLine
                    dashPattern:[5,5]
                    startX:line.x1;startY:line.y1;PathLine{x:line.x2;y:line.y2}
                }
            }
        }
        Shape {
            id:ellipse
            width:parent.width;height:parent.height;visible:root.mask.kind==='radial'
            preferredRendererType:Shape.CurveRenderer
            readonly property var outer:visible ? root.ellipse(1) : []
            readonly property var inner:visible ? root.ellipse(Math.max(0,1-root.mask.feather)) : []
            ShapePath {fillColor:'transparent';strokeColor:'#66252725';strokeWidth:2;PathPolyline{path:ellipse.outer}}
            ShapePath {fillColor:'transparent';strokeColor:'#E6FFFFFF';strokeWidth:1;PathPolyline{path:ellipse.outer}}
            ShapePath {fillColor:'transparent';strokeColor:'#55252725';strokeWidth:2;strokeStyle:ShapePath.DashLine;dashPattern:[2,3];PathPolyline{path:ellipse.inner}}
            ShapePath {fillColor:'transparent';strokeColor:'#BFFFFFFF';strokeWidth:1;strokeStyle:ShapePath.DashLine;dashPattern:[4,6];PathPolyline{path:ellipse.inner}}
        }
        Shape {
            id:axis
            width:parent.width;height:parent.height;visible:root.handles.length>1
            preferredRendererType:Shape.CurveRenderer
            readonly property var a:root.handles.length>1 ? root.handles[root.mask.kind==='linear' ? 0 : 1].p : [0,0]
            readonly property var b:root.handles.length>1 ? root.handles[root.mask.kind==='linear' ? 1 : 3].p : [0,0]
            ShapePath {
                fillColor:'transparent';strokeColor:'#80FFFFFF';strokeWidth:1
                startX:axis.a[0]-root.viewport.imageX;startY:axis.a[1]-root.viewport.imageY
                PathLine{x:axis.b[0]-root.viewport.imageX;y:axis.b[1]-root.viewport.imageY}
            }
        }
    }
    Repeater {
        model:root.handles.length
        delegate:Rectangle {
            id:handle
            required property int index
            readonly property var modelData:root.handles[index]
            readonly property bool rotationHandle:modelData.id==='linear_rotation' || modelData.id==='rotation'
            readonly property bool centerHandle:modelData.id==='move' || modelData.id==='center'
            readonly property bool highlighted:root.viewport.gradientHandle===modelData.id || root.viewport.hoveredGradientHandle===modelData.id
            width:rotationHandle ? 14 : centerHandle ? 12 : 8;height:width;radius:width/2;antialiasing:true
            x:modelData.p[0]-width/2;y:modelData.p[1]-height/2
            color:highlighted ? Theme.accentInk : '#F2FCFBF8'
            border.width:1;border.color:highlighted ? '#FFFFFF' : '#AA292B27'
            Rectangle {anchors.centerIn:parent;width:3;height:3;radius:1.5;visible:handle.centerHandle;color:handle.highlighted ? '#FFFFFF' : Theme.accentInk}
            VectorIcon {anchors.centerIn:parent;width:9;height:9;name:'rotate';visible:handle.rotationHandle;iconColor:handle.highlighted ? '#FFFFFF' : '#292B27'}
        }
    }
}
