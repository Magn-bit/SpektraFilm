import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Column {
    id:root
    objectName:'sceneHistogramPanel'
    property string channel:'master'
    readonly property var model:ctrl.sceneHistogram
    readonly property var measured:model.data || ({})
    readonly property var row:(measured.rows || {})[channel==='luma' ? 'master' : channel] || []
    readonly property bool current:!!measured.current
    width:parent.width;spacing:4
    // Keep empty/film-off states available even when the enclosing controls
    // are disabled; the model itself yields while an export owns the engine.
    function syncActive(){if(model)model.setActive(visible)}
    Component.onCompleted:syncActive()
    Component.onDestruction:if(model)model.setActive(false)
    onVisibleChanged:syncActive()
    onEnabledChanged:syncActive()
    onMeasuredChanged:plot.requestPaint()
    onChannelChanged:plot.requestPaint()
    Connections {target:Theme;function onDarkChanged(){plot.requestPaint()}}
    RowLayout {
        width:parent.width;spacing:8
        MinchoText {text:qsTr('场景直方图');font.pixelSize:Theme.caption;color:Theme.secondary;Layout.fillWidth:true}
        MinchoText {visible:root.model.busy;text:qsTr('更新中…');font.pixelSize:Theme.caption;color:Theme.secondary}
        StudioButton {visible:root.model.state==='error';text:qsTr('重试');quiet:true;implicitHeight:26;onClicked:root.model.refresh()}
    }
    Item {
        width:parent.width;height:88
        Rectangle {anchors.fill:parent;color:Theme.plotSurface;radius:3}
        Canvas {
            id:plot;objectName:'sceneHistogramPlot';anchors.fill:parent
            onWidthChanged:requestPaint();onHeightChanged:requestPaint();onVisibleChanged:if(visible)requestPaint()
            onPaint:{
                var c=getContext('2d');c.reset();c.clearRect(0,0,width,height)
                var values=root.row;if(!values.length)return
                var lo=Number(root.measured.low),hi=Number(root.measured.high),exposure=Number(root.measured.exposure || 0),count=values.length,peak=0
                function ev(i){return lo+(i+.5)*(hi-lo)/count+exposure}
                function x(stop){return (stop+8)/16*width}
                for(var i=0;i<count;i++)if(ev(i)>=-8 && ev(i)<=8)peak=Math.max(peak,Number(values[i]) || 0)
                if(!peak)return
                var color=root.channel==='red' ? '#B96D62' : root.channel==='green' ? '#789472' : root.channel==='blue' ? '#6D88A7' : Theme.ink
                function shape(){
                    c.beginPath();c.moveTo(x(ev(0)),height)
                    for(var j=0;j<count;j++)c.lineTo(x(ev(j)),height-4-(height-10)*Math.sqrt(Math.max(0,Number(values[j]) || 0)/peak))
                    c.lineTo(x(ev(count-1)),height);c.closePath()
                }
                c.save();c.beginPath();c.rect(0,0,width,height);c.clip()
                shape();c.fillStyle=color;c.globalAlpha=root.current ? .15 : .08;c.fill()
                var medium=root.measured.medium || {},left=Number(medium.shadow_ev),right=Number(medium.highlight_ev)
                if(isFinite(left) && isFinite(right)){
                    c.save();c.beginPath();c.rect(x(left),0,Math.max(0,x(right)-x(left)),height);c.clip()
                    shape();c.globalAlpha=root.current ? .42 : .13;c.fill();c.restore()
                }
                c.restore()
            }
        }
        MinchoText {
            anchors.centerIn:parent;visible:!root.row.length
            text:root.model.state==='disabled' ? qsTr('胶片显影已关闭') : root.model.state==='empty' ? qsTr('未导入照片') : root.model.state==='error' ? qsTr('暂无场景数据') : ''
            font.pixelSize:Theme.caption;color:Theme.secondary
        }
        MouseArea {
            id:hover;anchors.fill:parent;hoverEnabled:true;acceptedButtons:Qt.NoButton
            readonly property real stop:Math.max(-8,Math.min(8,mouseX/Math.max(1,width)*16-8))
            ToolTip.visible:containsMouse && root.current;ToolTip.delay:300
            ToolTip.text:(stop>=0 ? '+' : '')+stop.toFixed(2)+' EV'
            Accessible.role:Accessible.Graphic;Accessible.name:qsTr('场景直方图')
            Accessible.description:root.model.state==='ready' ? qsTr('当前场景曲线后的真实分布') : qsTr('场景直方图暂不可用')
        }
    }
    RowLayout {
        width:parent.width
        MinchoText {text:'−8';font.pixelSize:Theme.caption;color:Theme.secondary}
        Item {Layout.fillWidth:true}
        MinchoText {text:'0 EV';font.pixelSize:Theme.caption;color:Theme.secondary}
        Item {Layout.fillWidth:true}
        MinchoText {text:'+8';font.pixelSize:Theme.caption;color:Theme.secondary}
    }
}
