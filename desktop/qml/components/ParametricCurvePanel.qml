import QtQuick
import QtQuick.Layouts

Column {
    id:root
    property string channel:'master'
    property bool scene:false
    readonly property var values:(scene ? ctrl.sceneCurveParametric : ctrl.curveParametric)[channel]
    width:parent.width;spacing:12
    Repeater {
        model:[{id:'highlights',name:qsTr('高光')},{id:'lights',name:qsTr('亮调')},{id:'darks',name:qsTr('暗调')},{id:'shadows',name:qsTr('阴影')}]
        delegate:FineParameter {
            required property var modelData
            parameter:modelData.id;label:modelData.name;minimum:-100;maximum:100;step:.1
            signedValue:true;directParameter:false;defaultValue:0
            externalValue:root.values[modelData.id]
            onValueEdited:function(value){ctrl.setParametricCurve(root.channel,modelData.id,value,root.scene)}
        }
    }
    ToolSection {
        title:qsTr('分区');expanded:false;onToggled:expanded=!expanded
        Repeater {
            model:[{id:'shadow_split',name:qsTr('阴影边界'),defaultValue:.25},{id:'midtone_split',name:qsTr('中调边界'),defaultValue:.5},{id:'highlight_split',name:qsTr('高光边界'),defaultValue:.75}]
            delegate:FineParameter {
                required property var modelData
                parameter:modelData.id;label:modelData.name;step:.1;unit:'%';directParameter:false
                minimum:modelData.id==='shadow_split' ? 5 : modelData.id==='midtone_split' ? (root.values.shadow_split+.05)*100 : (root.values.midtone_split+.05)*100
                maximum:modelData.id==='highlight_split' ? 95 : modelData.id==='midtone_split' ? (root.values.highlight_split-.05)*100 : (root.values.midtone_split-.05)*100
                defaultValue:modelData.defaultValue*100;externalValue:root.values[modelData.id]*100
                onValueEdited:function(value){ctrl.setParametricCurve(root.channel,modelData.id,value/100,root.scene)}
            }
        }
    }
    RowLayout {
        width:parent.width;Item {Layout.fillWidth:true}
        StudioButton {text:qsTr('重置参数曲线');quiet:true;implicitHeight:28;onClicked:ctrl.resetParametricCurve(root.channel,root.scene)}
    }
}
