import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ColumnLayout {
    id:root
    objectName:'librarySourcesPanel'
    required property var workspace
    property string removeId:''
    property string removePath:''
    spacing:12
    RowLayout {
        Layout.fillWidth:true;spacing:8
        StudioButton {objectName:'addWatchedSource';text:qsTr(String('添加'));quiet:true;enabled:root.workspace.originKind==='none' && !root.workspace.busy;onClicked:root.workspace.chooseWatchedFolder()}
        StudioButton {objectName:'syncAllSources';text:qsTr(String(root.workspace.foldersSyncing ? '正在刷新…' : '全部刷新'));quiet:true;enabled:root.workspace.originKind==='none' && !root.workspace.foldersSyncing && (root.workspace.folders.length>0 || root.workspace.kind==='session');onClicked:root.workspace.syncFolders()}
    }
    ScrollView {
        id:scroll;Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumHeight:0;clip:true;contentWidth:availableWidth;rightPadding:10
        ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
        Column {
            width:scroll.availableWidth;spacing:24
            Column {
                width:parent.width;spacing:8;visible:root.workspace.originKind!=='none' || root.workspace.isCaptureOneCopy
                MinchoText {width:parent.width;text:root.workspace.isCaptureOneCopy ? qsTr(String('Capture One 独立副本')) : qsTr(String('Capture One 只读来源'));font.pixelSize:Theme.caption;wrapMode:Text.Wrap}
                MinchoText {width:parent.width;text:(root.workspace.info.copied_from || root.workspace.info.origin || {}).path || '';font.pixelSize:12;color:Theme.secondary;wrapMode:Text.WrapAnywhere}
                StudioButton {text:qsTr(String('同步来源'));quiet:true;enabled:!root.workspace.busy;onClicked:root.workspace.syncCaptureOne()}
            }
            MinchoText {width:parent.width;visible:root.workspace.folders.length===0 && root.workspace.originKind==='none';text:qsTr(String('未监视文件夹'));color:Theme.secondary;font.pixelSize:Theme.caption}
            Repeater {
                model:root.workspace.folders
                delegate:Column {
                    id:source
                    required property var modelData
                    readonly property string locationId:{var rows=root.workspace.locations;for(var i=0;i<rows.length;i++)if(rows[i].path===modelData.path)return rows[i].uuid;return ''}
                    width:parent.width;spacing:8
                    Button {
                        id:chooseFolder;width:parent.width;implicitHeight:pathLabel.implicitHeight+12;hoverEnabled:true;leftPadding:6;rightPadding:6
                        Accessible.name:source.modelData.path
                        contentItem:MinchoText {id:pathLabel;text:source.modelData.path.split(/[\\/]/).filter(function(value){return value.length>0}).pop() || source.modelData.path;elide:Text.ElideRight;font.pixelSize:Theme.caption;color:Theme.ink}
                        background:Rectangle {radius:4;color:chooseFolder.hovered || chooseFolder.down ? Theme.hover : 'transparent';border.width:chooseFolder.visualFocus ? 1 : 0;border.color:Theme.accentInk}
                        onClicked:if(source.modelData.collection)root.workspace.selectCollection(source.modelData.collection)
                    }
                    MinchoText {
                        width:parent.width;text:source.modelData.path;elide:Text.ElideMiddle;font.pixelSize:12;color:Theme.secondary
                        ToolTip.visible:sourcePathHover.hovered;ToolTip.text:text
                        HoverHandler {id:sourcePathHover}
                    }
                    MinchoText {width:parent.width;text:qsTr(String((source.modelData.online ? '在线' : '离线')+' · '+source.modelData.image_count+' 张'+(source.modelData.recursive ? ' · 含子文件夹' : '')));color:source.modelData.online ? Theme.secondary : (Theme.dark ? '#E6B69C' : '#8B4D35');font.pixelSize:12;wrapMode:Text.Wrap}
                    MinchoText {width:parent.width;visible:!!source.modelData.synced_at;text:source.modelData.synced_at ? qsTr(String('上次刷新 '+new Date(source.modelData.synced_at).toLocaleString(Qt.locale(),'MM-dd hh:mm'))) : '';font.pixelSize:12;color:Theme.secondary}
                    RowLayout {
                        width:parent.width;spacing:8
                        StudioButton {objectName:'syncSource_'+source.modelData.folder;text:qsTr(String('刷新'));quiet:true;implicitHeight:30;enabled:!root.workspace.foldersSyncing && root.workspace.originKind==='none';onClicked:root.workspace.syncWatchedFolder(source.modelData.folder)}
                        StudioButton {objectName:'unwatchSource_'+source.modelData.folder;text:qsTr(String('取消监视'));quiet:true;implicitHeight:30;enabled:!root.workspace.busy && !root.workspace.foldersSyncing && root.workspace.originKind==='none';onClicked:{root.removeId=source.modelData.folder;root.removePath=source.modelData.path;confirm.open()}}
                    }
                    StudioButton {text:qsTr(String('重新定位'));quiet:true;implicitHeight:30;visible:source.locationId.length>0;enabled:!root.workspace.busy;onClicked:root.workspace.chooseRelinkLocation(source.locationId)}
                }
            }
            Column {
                width:parent.width;spacing:8;visible:root.workspace.unwatchedLocations.length>0
                MinchoText {text:qsTr(String('原片位置'));font.pixelSize:Theme.caption;color:Theme.secondary}
                Repeater {
                    model:root.workspace.unwatchedLocations
                    delegate:Column {
                        required property var modelData
                        width:parent.width;spacing:4
                        MinchoText {width:parent.width;text:(modelData.online ? '' : qsTr('离线')+' · ')+modelData.path;wrapMode:Text.WrapAnywhere;font.pixelSize:12;color:Theme.secondary}
                        StudioButton {objectName:'relinkSource_'+modelData.uuid;text:qsTr(String('重新定位'));quiet:true;implicitHeight:30;enabled:!root.workspace.busy;onClicked:root.workspace.chooseRelinkLocation(modelData.uuid)}
                    }
                }
            }
        }
    }
    StudioDialog {
        id:confirm;objectName:'confirmUnwatchSource';parent:Overlay.overlay;anchors.centerIn:parent;width:Math.min(440,parent.width-48)
        contentItem:ColumnLayout {
            spacing:20
            MinchoText {text:qsTr(String('停止监视文件夹'));font.pixelSize:Theme.heading}
            MinchoText {text:root.removePath;Layout.fillWidth:true;wrapMode:Text.WrapAnywhere;color:Theme.secondary;font.pixelSize:Theme.caption}
            MinchoText {text:qsTr(String('仅停止自动刷新。已导入的照片、调整和磁盘原文件都会保留。'));Layout.fillWidth:true;wrapMode:Text.Wrap}
            RowLayout {
                Layout.fillWidth:true;spacing:12
                Item {Layout.fillWidth:true}
                StudioButton {text:qsTr(String('返回'));quiet:true;onClicked:confirm.close()}
                StudioButton {objectName:'confirmStopWatching';text:qsTr(String('停止监视'));primary:true;onClicked:{root.workspace.unwatchFolder(root.removeId);confirm.close()}}
            }
        }
    }
}
