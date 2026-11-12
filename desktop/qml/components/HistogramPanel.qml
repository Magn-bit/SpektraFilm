import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Column {
    id:root
    objectName:'globalHistogramPanel'
    property bool expanded:true
    readonly property var bins:ctrl.levelHistogram || ({})
    readonly property bool dataReady:{var values=root.bins.master||[];for(var i=0;i<values.length;i++)if(Number(values[i])>0)return true;return false}
    visible:ctrl.currentIndex>=0&&dataReady
    width:parent.width;spacing:4
    onBinsChanged:plot.requestPaint()
    Connections {target:Theme;function onDarkChanged(){plot.requestPaint()}}
    RowLayout {
        width:parent.width;spacing:8
        MinchoText {text:qsTr(String('直方图'));font.pixelSize:Theme.caption;color:Theme.secondary;Layout.fillWidth:true}
        StudioButton {
            objectName:'toggleHistogramButton';text:qsTr(String(root.expanded ? '−' : '+'));quiet:true;implicitHeight:24;implicitWidth:30
            Accessible.name:qsTr(String(root.expanded ? '收起直方图' : '展开直方图'))
            Accessible.description:qsTr(String(root.expanded ? '已展开' : '已收起'))
            onClicked:root.expanded=!root.expanded
        }
    }
    Item {
        width:parent.width;height:64;visible:root.expanded
        Rectangle {anchors.fill:parent;radius:3;color:Theme.plotSurface}
        Canvas {
            id:plot;objectName:'globalHistogramPlot';anchors.fill:parent
            onWidthChanged:requestPaint();onHeightChanged:requestPaint();onVisibleChanged:if(visible)requestPaint()
            onPaint:{
                var c=getContext('2d');c.reset();c.clearRect(0,0,width,height)
                var channels=['red','green','blue','master'],colors=Theme.dark ? ['#D79282','#A5BC84','#8DAACC',Theme.ink] : ['#B96D62','#789472','#6D88A7',Theme.ink],maximum=0
                for(var k=0;k<channels.length;k++){var values=root.bins[channels[k]] || [];for(var i=0;i<values.length;i++)maximum=Math.max(maximum,Number(values[i]) || 0)}
                if(!maximum)return
                for(k=0;k<channels.length;k++){
                    values=root.bins[channels[k]] || [];if(!values.length)continue
                    c.beginPath();c.moveTo(0,height-1)
                    for(i=0;i<values.length;i++)c.lineTo(i*width/Math.max(1,values.length-1),height-2-(height-6)*Math.sqrt(Math.max(0,Number(values[i]) || 0)/maximum))
                    c.lineTo(width,height-1);c.closePath();c.fillStyle=colors[k];c.globalAlpha=k===3 ? .12 : .16;c.fill()
                    c.strokeStyle=colors[k];c.globalAlpha=k===3 ? .68 : .7;c.lineWidth=1;c.stroke()
                }
            }
        }
        MouseArea {
            id:hit;anchors.fill:parent;hoverEnabled:true;acceptedButtons:Qt.NoButton
            readonly property int sample:Math.max(0,Math.min(255,Math.round(mouseX/Math.max(1,width)*255)))
            readonly property string statistics:{
                var values=root.bins.master || [],low=Math.max(0,sample-4),high=Math.min(255,sample+4),count=0,total=0
                for(var i=0;i<values.length;i++){var n=Number(values[i]) || 0;total+=n;if(i>=low && i<=high)count+=n}
                return low+'–'+high+' · '+(total ? 100*count/total : 0).toFixed(2)+'%'
            }
            Rectangle {visible:hit.containsMouse;x:Math.max(0,Math.min(parent.width-1,hit.mouseX));width:1;height:parent.height;color:Theme.secondary;opacity:.65}
            ToolTip.visible:containsMouse;ToolTip.delay:250;ToolTip.text:qsTr(String(statistics))
            Accessible.role:Accessible.Graphic;Accessible.name:qsTr(String('照片 RGB 与亮度直方图'))
        }
    }
}
