import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic

Column {
    id: root
    property string channel: 'master'
    property bool scene:false
    property bool parametricMode:false
    readonly property var combinedSamples:{var state=scene ? ctrl.sceneCurveParametric : ctrl.curveParametric;var p=points;return ctrl.curveSamples(channel,scene)}
    readonly property var inputSamples:{var state=scene ? ctrl.sceneCurveParametric : ctrl.curveParametric;return ctrl.curveInputSamples(channel,scene)}
    function inputAt(x) {
        x=Math.max(0,Math.min(1,x))*160
        var lo=Math.floor(x),hi=Math.min(160,lo+1)
        return inputSamples[lo]+(inputSamples[hi]-inputSamples[lo])*(x-lo)
    }
    function graphX(x) {
        // Points are edited after the parametric transform. Keep their hit
        // positions on the actual composed curve, including while dragging.
        if(x<=inputSamples[0])return 0
        for(var i=1;i<inputSamples.length;i++)if(inputSamples[i]>=x)
            return (i-1+(x-inputSamples[i-1])/Math.max(.0000001,inputSamples[i]-inputSamples[i-1]))/160
        return 1
    }
    property var points: (scene ? ctrl.sceneCurves : ctrl.colorCurves)[channel] || [[0,0],[1,1]]
    function commit(channel,points){if(scene)ctrl.setSceneCurvePoints(channel,points);else ctrl.setCurvePoints(channel,points)}
    property var draft: []
    property bool dragging: false
    property bool removalPending: false
    property var dragOriginal: []
    property string dragChannel: ''
    property bool previewPending: false
    property int selectedPoint: -1
    readonly property var shown: !dragging ? points : removalPending ? draft.filter(function(p,i){return i!==root.selectedPoint}) : draft
    readonly property color channelColor: channel==='red' ? (Theme.dark ? '#D79282' : '#B16E65') : channel==='green' ? (Theme.dark ? '#A5BC84' : '#6F8C68') : channel==='blue' ? (Theme.dark ? '#8DAACC' : '#6D86A5') : Theme.ink
    width: parent.width; spacing: 16
    onPointsChanged: graph.requestPaint()
    onCombinedSamplesChanged:graph.requestPaint()
    onChannelColorChanged:graph.requestPaint()
    Connections {target:Theme;function onDarkChanged(){graph.requestPaint()}}
    onChannelChanged: { finish();selectedPoint=-1;graph.requestPaint() }
    onEnabledChanged:if(!enabled)cancel()
    function submit() {
        previewTimer.stop()
        if(dragging && previewPending){previewPending=false;root.commit(dragChannel,shown)}
    }
    function finish() {
        if(!dragging)return
        submit()
        if(removalPending)selectedPoint=-1
        dragging=false;removalPending=false;ctrl.endEdit();graph.requestPaint()
    }
    function cancel() {
        if(!dragging)return
        previewTimer.stop();previewPending=false
        root.commit(dragChannel,dragOriginal)
        dragging=false;removalPending=false;ctrl.endEdit();graph.requestPaint()
    }
    function deleteSelected() {
        finish()
        if(selectedPoint<=0 || selectedPoint>=points.length-1)return
        var p=points.map(function(point){return [point[0],point[1]]})
        p.splice(selectedPoint,1);selectedPoint=-1;root.commit(channel,p)
    }
    Timer {id:previewTimer;interval:16;repeat:false;onTriggered:root.submit()}
    function setSelected(x,y) {
        var p=points.map(function(point){return [point[0],point[1]]}),i=selectedPoint
        if(i<0 || i>=p.length)return
        x=Math.max(i===0 ? 0 : p[i-1][0]+.005,Math.min(i===p.length-1 ? 1 : p[i+1][0]-.005,x))
        p[i]=[x,Math.max(0,Math.min(1,y))];root.commit(channel,p)
    }
    function interpolate(values,x) {
        if(x<=values[0][0])return values[0][1]
        if(x>=values[values.length-1][0])return values[values.length-1][1]
        var n=values.length,d=[],h=[],m=[]
        for(var i=0;i<n-1;i++) { h[i]=values[i+1][0]-values[i][0];d[i]=(values[i+1][1]-values[i][1])/Math.max(.000001,h[i]) }
        if(n===2) return values[0][1]+(x-values[0][0])*d[0]
        function endpoint(h0,h1,d0,d1) { var a=((2*h0+h1)*d0-h0*d1)/(h0+h1);if(a*d0<=0)return 0;if(d0*d1<0 && Math.abs(a)>Math.abs(3*d0))return 3*d0;return a }
        m[0]=endpoint(h[0],h[1],d[0],d[1]);m[n-1]=endpoint(h[n-2],h[n-3],d[n-2],d[n-3])
        for(i=1;i<n-1;i++) { if(d[i-1]*d[i]<=0)m[i]=0;else { var w1=2*h[i]+h[i-1],w2=h[i]+2*h[i-1];m[i]=(w1+w2)/(w1/d[i-1]+w2/d[i]) } }
        var k=0;while(k<n-2 && x>values[k+1][0])k++
        var t=(x-values[k][0])/h[k],t2=t*t,t3=t2*t
        return (2*t3-3*t2+1)*values[k][1]+(t3-2*t2+t)*h[k]*m[k]+(-2*t3+3*t2)*values[k+1][1]+(t3-t2)*h[k]*m[k+1]
    }
    RowLayout {
        width:parent.width;spacing:4
        StudioButton {
            objectName:'pointCurveMode';text:qsTr('点曲线');quiet:true;selected:!root.parametricMode;Layout.fillWidth:true;implicitHeight:32
            Accessible.role:Accessible.PageTab;Accessible.selected:selected
            Accessible.description:qsTr('在曲线上添加或拖动控制点')
            ToolTip.visible:hovered || visualFocus;ToolTip.delay:600;ToolTip.text:Accessible.description
            onClicked:{root.finish();root.parametricMode=false}
        }
        StudioButton {
            objectName:'parametricCurveMode';text:qsTr('参数曲线');quiet:true;selected:root.parametricMode;Layout.fillWidth:true;implicitHeight:32
            Accessible.role:Accessible.PageTab;Accessible.selected:selected
            Accessible.description:qsTr('用滑块调整高光、亮调、暗调和阴影')
            ToolTip.visible:hovered || visualFocus;ToolTip.delay:600;ToolTip.text:Accessible.description
            onClicked:{root.finish();root.parametricMode=true}
        }
    }
    RowLayout {
        width: parent.width; spacing: 3
        Repeater {
            model: [{id:'master',name:'RGB'},{id:'red',name:'红'},{id:'green',name:'绿'},{id:'blue',name:'蓝'},{id:'luma',name:'亮度'}]
            delegate: StudioButton { required property var modelData;objectName:'curveChannel_'+modelData.id; text: qsTr(String(modelData.name)); quiet: true; selected: root.channel===modelData.id; Layout.fillWidth: true; implicitHeight: 32; onClicked: {root.finish();root.channel=modelData.id} }
        }
    }
    Rectangle {
        width: parent.width; height: width; radius: 4; color: Theme.white; border.width: 1; border.color: Theme.rule
        Canvas {
            id: graph; objectName: 'curveGraph'; anchors.fill: parent; anchors.margins: 12
            activeFocusOnTab: true
            Accessible.name: qsTr(String('曲线控制点；拖出图表或 Delete 删除中间点，方向键微调，Escape 取消拖动'))
            Keys.onPressed: function(event) {
                if(event.key===Qt.Key_Escape && root.dragging){root.cancel();event.accepted=true;return}
                if(event.key===Qt.Key_Delete || event.key===Qt.Key_Backspace){root.deleteSelected();event.accepted=true;return}
                if(root.selectedPoint<0 || root.selectedPoint>=root.points.length)return
                var p=root.points[root.selectedPoint],step=root.scene ? (event.modifiers&Qt.ShiftModifier ? .1 : .01)/16 : event.modifiers&Qt.ShiftModifier ? .02 : 1/255
                if(event.key===Qt.Key_Left)root.setSelected(p[0]-step,p[1]);else if(event.key===Qt.Key_Right)root.setSelected(p[0]+step,p[1]);else if(event.key===Qt.Key_Up)root.setSelected(p[0],p[1]+step);else if(event.key===Qt.Key_Down)root.setSelected(p[0],p[1]-step);else return
                event.accepted=true
            }
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
            onPaint: {
                var c=getContext('2d');c.reset();c.clearRect(0,0,width,height)
                c.strokeStyle=Theme.rule;c.lineWidth=1;c.beginPath()
                for(var i=0;i<=4;i++){var p=i/4;c.moveTo(p*width,0);c.lineTo(p*width,height);c.moveTo(0,p*height);c.lineTo(width,p*height)}c.stroke()
                c.strokeStyle=Theme.border;c.beginPath();c.moveTo(0,height);c.lineTo(width,0);c.stroke()
                var points=root.shown;if(!points || points.length<2)return
                c.strokeStyle=root.channelColor;c.lineWidth=1.8;c.beginPath()
                for(i=0;i<=160;i++){var x=i/160,y=Math.max(0,Math.min(1,root.dragging ? root.interpolate(points,root.inputSamples[i]) : root.combinedSamples[i]));if(i===0)c.moveTo(x*width,(1-y)*height);else c.lineTo(x*width,(1-y)*height)}c.stroke()
                if(!root.parametricMode)for(i=0;i<points.length;i++){c.beginPath();c.arc(root.graphX(points[i][0])*width,(1-points[i][1])*height,root.selectedPoint===i ? 4.5 : 3.5,0,Math.PI*2);c.fillStyle=Theme.surface;c.fill();c.strokeStyle=root.channelColor;c.lineWidth=1.5;c.stroke()}
            }
            MouseArea {
                anchors.fill: parent; acceptedButtons: Qt.LeftButton|Qt.RightButton; preventStealing: true;enabled:!root.parametricMode
                objectName:'curvePointerArea'
                cursorShape: root.removalPending ? Qt.ForbiddenCursor : pressed ? Qt.ClosedHandCursor : Qt.CrossCursor
                function updateAt(mouse) {
                    var p=root.draft,index=root.selectedPoint;if(index<0)return
                    root.removalPending=index>0 && index<p.length-1 && (mouse.x< -14 || mouse.x>width+14 || mouse.y< -14 || mouse.y>height+14)
                    var x=root.inputAt(mouse.x/width),y=1-Math.max(0,Math.min(1,mouse.y/height))
                    x=Math.max(index===0 ? 0 : p[index-1][0]+.005,Math.min(index===p.length-1 ? 1 : p[index+1][0]-.005,x))
                    p[index]=[x,y];root.draft=p;graph.requestPaint();root.previewPending=true
                    if(!previewTimer.running)previewTimer.start()
                }
                onPressed: function(mouse) {
                    graph.forceActiveFocus()
                    var p=root.points.map(function(point){return [point[0],point[1]]}),nearest=-1,dist=13
                    for(var i=0;i<p.length;i++){var d=Math.hypot(mouse.x-root.graphX(p[i][0])*width,mouse.y-(1-p[i][1])*height);if(d<dist){dist=d;nearest=i}}
                    if(mouse.button===Qt.RightButton){root.selectedPoint=nearest;root.deleteSelected();return}
                    root.dragOriginal=p.map(function(point){return point.slice()});root.dragChannel=root.channel
                    ctrl.beginEdit();root.dragging=true;root.removalPending=false
                    if(nearest<0){
                        var x=Math.max(.01,Math.min(.99,root.inputAt(mouse.x/width)))
                        for(i=0;i<p.length;i++)if(Math.abs(p[i][0]-x)<.01){nearest=i;break}
                        if(nearest<0 && p.length<32){p.push([x,1-Math.max(0,Math.min(1,mouse.y/height))]);p.sort(function(a,b){return a[0]-b[0]});nearest=p.findIndex(function(point){return point[0]===x})}
                    }
                    root.selectedPoint=nearest;root.draft=p;updateAt(mouse)
                }
                onPositionChanged: function(mouse){if(root.dragging)updateAt(mouse)}
                onReleased: root.finish()
                onCanceled: root.cancel()
            }
        }
    }
    RowLayout {
        width: parent.width;visible:!root.parametricMode
        MinchoText { text: qsTr(String(root.removalPending ? '松开删除控制点' : '点击添加 · 拖出删除')); font.pixelSize: Theme.caption; color: root.removalPending ? Theme.ink : Theme.secondary; Layout.fillWidth: true }
        StudioButton { text: qsTr(String('重置曲线')); quiet: true; implicitHeight: 28; onClicked: {root.finish();if(root.scene)ctrl.resetSceneCurve(root.channel);else ctrl.resetCurve(root.channel)} }
    }
    RowLayout {
        width:parent.width;visible:!root.parametricMode && root.selectedPoint>=0 && root.selectedPoint<root.points.length;spacing:10
        Repeater {
            model:['输入','输出']
            delegate:RowLayout {
                required property int index;required property string modelData
                MinchoText{text:qsTr(String(modelData));font.pixelSize:Theme.caption;color:Theme.secondary}
                TextField {
                    Layout.fillWidth:true;implicitHeight:32;padding:5;color:Theme.ink;font.family:Theme.family;font.pixelSize:Theme.body
                    text:qsTr(String(root.selectedPoint>=0 && root.selectedPoint<root.points.length ? (root.scene ? (root.points[root.selectedPoint][index]*16-8).toFixed(2) : Math.round(root.points[root.selectedPoint][index]*255)) : ''))
                    validator:DoubleValidator{bottom:root.scene ? -8 : 0;top:root.scene ? 8 : 255;decimals:root.scene ? 2 : 1}
                    Accessible.name:qsTr(String(modelData+(root.scene ? '场景曲线，负八至八 EV' : '曲线数值，零至二百五十五')))
                    onEditingFinished:{if(acceptableInput && root.selectedPoint>=0){var p=root.points[root.selectedPoint],value=root.scene ? (Number(text)+8)/16 : Number(text)/255;root.setSelected(index===0 ? value : p[0],index===1 ? value : p[1])}}
                    background:Rectangle{color:Theme.white;radius:3;border.width:parent.activeFocus ? 1 : 0;border.color:Theme.accent}
                }
            }
        }
    }
    ParametricCurvePanel {visible:root.parametricMode;channel:root.channel;scene:root.scene}
}
