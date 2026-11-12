import QtQuick
import QtQuick.Layouts

Column {
    id:root
    width:parent.width;spacing:14
    readonly property var latitude:ctrl.analysis.latitude || ({})
    readonly property var medium:root.latitude.medium || ({})
    readonly property var scene:root.latitude.scene || ({})
    readonly property var fit:root.latitude.fit || ({})
    readonly property var histogram:(latitude.scene || {}).histogram || ({})
    Connections {target:Theme;function onDarkChanged(){graph.requestPaint()}}
    function issueMessage(issue) {
        var side=issue.side==='shadow' ? '暗部' : issue.side==='highlight' ? '高光' : '两端';
        var names={pull_back_below_minimum:side+'压缩不足，无法落入胶片范围',
            pull_back_exceeds_max_lift:'暗部提升超过上限',room_below_minimum:side+'过渡空间不足',
            out_of_range:'场景范围超出可用拟合范围',knees_cross:'场景反差超过当前材料可容纳范围',
            knee_past_midgrey:side+'压缩已影响中间调'};
        return names[issue.code] || '当前场景无法可靠拟合';
    }
    RowLayout {
        width:parent.width;spacing:8
        StudioButton {text:qsTr(String(ctrl.analysisBusy ? '分析中…' : '分析'));quiet:true;enabled:ctrl.currentIndex>=0 && !ctrl.analysisBusy;onClicked:ctrl.measureLatitude()}
        StudioButton {text:qsTr(String('应用'));quiet:true;enabled:!ctrl.analysisBusy && ctrl.analysisIsCurrent && !!(root.latitude.fit || {}).valid;onClicked:ctrl.applyLatitude()}
        Item {Layout.fillWidth:true}
        StudioButton {text:qsTr(String('恢复'));quiet:true;enabled:!!ctrl.parameters.scene_latitude_active;onClicked:ctrl.resetLatitude()}
    }
    Canvas {
        id:graph;width:parent.width;height:112
        onWidthChanged:requestPaint()
        onPaint: {
            var c=getContext('2d');c.reset();c.clearRect(0,0,width,height)
            var bins=root.histogram.fractions || [],placed=root.histogram.placed_fractions || [],peak=.00001
            for(var i=0;i<bins.length;i++)peak=Math.max(peak,bins[i],placed[i] || 0)
            c.fillStyle=Theme.hover;c.fillRect(0,0,width,height)
            // The upper band makes the usable paper latitude and the scene
            // span visible without adding another control. Both use the same
            // EV domain as the histogram below.
            var lo=Number(root.histogram.lo_ev===undefined ? -8 : root.histogram.lo_ev),hi=Number(root.histogram.hi_ev===undefined ? 8 : root.histogram.hi_ev),span=Math.max(.001,hi-lo)
            function x(ev){return Math.max(0,Math.min(width,(Number(ev)-lo)/span*width))}
            var mediumLo=Number(root.medium.shadow_ev),mediumHi=Number(root.medium.highlight_ev)
            if(isFinite(mediumLo)&&isFinite(mediumHi)) { c.fillStyle='#87977E55';c.fillRect(x(mediumLo),4,Math.max(1,x(mediumHi)-x(mediumLo)),8) }
            var sceneLo=Number(root.scene.p0_1),sceneHi=Number(root.scene.p99_9)
            if(isFinite(sceneLo)&&isFinite(sceneHi)) { c.fillStyle='#6B736D88';c.fillRect(x(sceneLo),14,Math.max(1,x(sceneHi)-x(sceneLo)),5) }
            c.strokeStyle=Theme.rule;c.lineWidth=1;c.beginPath();c.moveTo(0,height-1);c.lineTo(width,height-1);c.stroke()
            function plot(values,color) {
                if(!values.length)return
                c.fillStyle=color;c.beginPath();c.moveTo(0,height)
                for(var j=0;j<values.length;j++)c.lineTo((j+.5)/values.length*width,height-8-values[j]/peak*(height-18))
                c.lineTo(width,height);c.closePath();c.fill()
            }
            plot(bins,'#73817A71');plot(placed,'#80667C65')
        }
        Connections {target:ctrl;function onStateChanged(){graph.requestPaint()}}
        MinchoText {anchors.centerIn:parent;text:qsTr(String('尚未分析'));visible:!(root.histogram.fractions || []).length;font.pixelSize:Theme.caption;color:Theme.secondary}
    }
    RowLayout {
        width:parent.width
        MinchoText {text:qsTr(String(root.medium.shadow_ev===undefined ? '' : '胶片 '+Number(root.medium.shadow_ev).toFixed(1)+'—'+Number(root.medium.highlight_ev).toFixed(1)+' EV'));font.pixelSize:Theme.caption;color:Theme.secondary;elide:Text.ElideRight;Layout.fillWidth:true}
        MinchoText {text:qsTr(String(root.scene.p50===undefined ? '' : '场景中值 '+Number(root.scene.p50).toFixed(1)));font.pixelSize:Theme.caption;color:Theme.secondary;horizontalAlignment:Text.AlignRight}
    }
    RowLayout {
        width:parent.width
        MinchoText {text:qsTr(String(root.histogram.lo_ev===undefined ? '' : Number(root.histogram.lo_ev).toFixed(1)+' EV'));font.pixelSize:Theme.caption;color:Theme.secondary}
        Item {Layout.fillWidth:true}
        MinchoText {text:qsTr(String(root.histogram.hi_ev===undefined ? '' : Number(root.histogram.hi_ev).toFixed(1)+' EV'));font.pixelSize:Theme.caption;color:Theme.secondary}
    }
    MinchoText {
        width:parent.width;visible:(root.fit.issues || []).length>0 || (root.fit.warnings || []).length>0
        text:qsTr(String((root.fit.issues || []).length>0 ? '无法应用：'+root.issueMessage(root.fit.issues[0]) :
            (root.fit.warnings || []).length>0 ? root.issueMessage(root.fit.warnings[0]) : ''))
        wrapMode:Text.WordWrap;font.pixelSize:Theme.caption;color:Theme.secondary
    }
    MinchoText {
        width:parent.width;visible:!!root.latitude.scene && !ctrl.analysisIsCurrent
        text:qsTr(String('参数已更改，需重新分析'));wrapMode:Text.WordWrap;font.pixelSize:Theme.caption;color:Theme.secondary
    }
}
