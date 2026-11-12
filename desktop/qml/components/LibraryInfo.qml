import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ScrollView {
    id:root
    required property var info
    clip:true;contentWidth:availableWidth;rightPadding:10
    ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
    Column {
        width:root.availableWidth;spacing:20
        MinchoText {width:parent.width;text:qsTr(String(root.info.name || ''));wrapMode:Text.WrapAnywhere;font.pixelSize:Theme.body}
        Repeater {
            model:root.info.rows || []
            delegate:Column {
                required property var modelData
                width:parent.width;spacing:5
                MinchoText {text:qsTr(String(modelData.label));color:Theme.secondary;font.pixelSize:12}
                MinchoText {width:parent.width;text:modelData.value==='多种' ? qsTr('多种') : modelData.value;wrapMode:Text.Wrap;font.pixelSize:Theme.caption}
            }
        }
        Column {
            width:parent.width;spacing:5
            MinchoText {text:qsTr(String('原片位置'));font.pixelSize:12;color:Theme.secondary}
            MinchoText {width:parent.width;text:root.info.path==='多种' ? qsTr('多种') : root.info.path || '';wrapMode:Text.WrapAnywhere;font.pixelSize:12}
        }
        Item {width:1;height:8}
    }
}
