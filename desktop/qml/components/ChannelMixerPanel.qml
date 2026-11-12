import QtQuick
import QtQuick.Layouts

Column {
    id:root
    property string row:'red'
    width:parent.width;spacing:14
    RowLayout {
        width:parent.width;spacing:4
        Repeater {
            model:[{id:'red',name:qsTr('红色输出')},{id:'green',name:qsTr('绿色输出')},{id:'blue',name:qsTr('蓝色输出')}]
            delegate:StudioButton {
                required property var modelData
                text:modelData.name;quiet:true;selected:root.row===modelData.id
                Layout.fillWidth:true;implicitHeight:32;onClicked:root.row=modelData.id
            }
        }
    }
    Repeater {
        model:[{id:'red',name:qsTr('红色')},{id:'green',name:qsTr('绿色')},{id:'blue',name:qsTr('蓝色')}]
        delegate:FineParameter {
            required property var modelData
            parameter:modelData.id;label:modelData.name;minimum:-100;maximum:100;step:.1
            unit:'%';signedValue:true;defaultValue:0;directParameter:false
            externalValue:ctrl.parameters.channel_mixer[root.row][modelData.id]
            onValueEdited:function(value){ctrl.setChannelMixer(root.row,modelData.id,value)}
        }
    }
    RowLayout {
        width:parent.width;Item {Layout.fillWidth:true}
        StudioButton {text:qsTr('重置此通道');quiet:true;implicitHeight:28;onClicked:ctrl.resetChannelMixer(root.row)}
    }
}
