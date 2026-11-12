import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ColumnLayout {
    id:root
    property var controller:ctrl
    readonly property var items:controller.exportItems
    readonly property int failed:items.filter(function(item){return ['failed','present','changed'].indexOf(item.status)>=0}).length
    readonly property int retryable:items.filter(function(item){return item.status==='failed'||item.status==='present'}).length
    readonly property int completed:items.filter(function(item){return item.status==='completed'}).length
    readonly property int cancelled:items.filter(function(item){return item.status==='cancelled'}).length
    readonly property color failureInk:Theme.dark ? '#E6B69C' : '#8B4D35'
    visible:items.length>0
    spacing:8
    function stateLabel(item) {
        if(item.status==='completed')return qsTr(String('已完成'))
        if(item.status==='failed')return qsTr(String('失败'))
        if(item.status==='cancelled')return qsTr(String('已取消'))
        if(item.status==='present')return qsTr(String('目标已存在'))
        if(item.status==='changed')return qsTr(String('原片已变化'))
        if(item.status==='running') {
            var phases={decode:'读取原片',render:'正在显影',encode:'写入文件',metadata:'保存元数据',proof:'生成打样',copy:'复制原片'}
            return qsTr(String(phases[item.phase] || '正在导出'))
        }
        return qsTr(String('等待导出'))
    }
    RowLayout {
        Layout.fillWidth:true;spacing:12
        MinchoText {
            text:qsTr(String('已完成 '+root.completed+' / '+root.items.length+(root.failed ? ' · 失败 '+root.failed : '')+(root.cancelled ? ' · 取消 '+root.cancelled : '')))
            Layout.fillWidth:true;font.pixelSize:Theme.caption;color:root.failed ? root.failureInk : Theme.secondary
        }
        StudioButton {
            objectName:'resumeBatchExport';text:qsTr(String('继续剩余'));quiet:true;implicitHeight:32
            visible:root.controller.canResumeBatchExport;enabled:root.controller.canResumeBatchExport
            onClicked:root.controller.resumeBatchExport()
        }
        StudioButton {
            objectName:'retryFailedExports';text:qsTr(String('重试失败项'));quiet:true;implicitHeight:32
            visible:root.retryable>0;enabled:root.controller.canRetryFailedExports
            onClicked:root.controller.retryFailedExports()
        }
        StudioButton {
            objectName:'clearBatchExport';text:qsTr(String('清除记录'));quiet:true;implicitHeight:32
            visible:root.controller.canClearBatchExport
            onClicked:clearBatchConfirm.open()
        }
        StudioButton {
            text:qsTr(String('取消导出'));quiet:true;implicitHeight:32;visible:root.controller.exporting
            onClicked:root.controller.cancelBatchExport()
        }
    }
    ListView {
        id:list;objectName:'exportResultsList'
        Layout.fillWidth:true;Layout.preferredHeight:Math.min(176,contentHeight);Layout.minimumHeight:0
        clip:true;spacing:4;model:root.items;boundsBehavior:Flickable.StopAtBounds
        ScrollBar.vertical:ScrollBar {width:10}
        delegate:Rectangle {
            id:row
            required property var modelData
            width:list.width-12;implicitHeight:content.implicitHeight+14;radius:4
            color:modelData.status==='failed' ? (Theme.dark ? '#49392F' : '#F4EAE4') : Theme.surface
            Accessible.name:modelData.name+'，'+root.stateLabel(modelData)+(modelData.error ? '，'+modelData.error : '')
            ColumnLayout {
                id:content;anchors.fill:parent;anchors.margins:7;spacing:3
                RowLayout {
                    Layout.fillWidth:true;spacing:12
                    MinchoText {text:row.modelData.name;Layout.fillWidth:true;elide:Text.ElideMiddle;font.pixelSize:Theme.caption}
                    MinchoText {text:root.stateLabel(row.modelData);font.pixelSize:Theme.caption;color:row.modelData.status==='failed' ? root.failureInk : Theme.secondary}
                }
                MinchoText {
                    Layout.fillWidth:true;visible:!!row.modelData.error
                    text:qsTr(String(row.modelData.error || ''));wrapMode:Text.Wrap;font.pixelSize:12;color:root.failureInk
                }
                MinchoText {
                    Layout.fillWidth:true;visible:!!row.modelData.output && !row.modelData.error
                    text:row.modelData.output || '';elide:Text.ElideMiddle;font.pixelSize:12;color:Theme.secondary
                    ToolTip.visible:outputHover.hovered;ToolTip.text:text
                    HoverHandler {id:outputHover}
                }
            }
        }
    }
    StudioDialog {
        id:clearBatchConfirm
        title:qsTr(String('清除批量任务记录？'))
        width:420
        contentItem:MinchoText {
            text:qsTr(String('这不会删除已经导出的文件，但未完成项目将无法继续。'))
            wrapMode:Text.WordWrap;color:Theme.secondary
        }
        footer:RowLayout {
            spacing:10
            StudioButton {text:qsTr(String('取消'));quiet:true;onClicked:clearBatchConfirm.close()}
            Item {Layout.fillWidth:true}
            StudioButton {text:qsTr(String('清除记录'));primary:true;onClicked:{root.controller.discardBatchExport();clearBatchConfirm.close()}}
        }
    }
}
