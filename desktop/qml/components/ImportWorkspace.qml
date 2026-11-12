import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

FocusScope {
    id:root;objectName:'importWorkspace'
    required property var workspace
    readonly property var importState:workspace.state
    property bool showPreview:true
    property bool shiftSelection:false
    signal closeRequested()
    function cancel(){workspace.cancelScan();closeRequested()}
    Keys.onPressed:function(event){
        if(event.key===Qt.Key_Shift)root.shiftSelection=true;
        if(event.key===Qt.Key_Escape&&!importState.adding){cancel();event.accepted=true}
        else if(event.key===Qt.Key_A&&(event.modifiers&Qt.ControlModifier)){workspace.selectAll(!(event.modifiers&Qt.ShiftModifier));event.accepted=true}
        else if((event.key===Qt.Key_Return||event.key===Qt.Key_Enter)&&importState.can_import){workspace.addSelected();event.accepted=true}
    }
    Keys.onReleased:function(event){if(event.key===Qt.Key_Shift)root.shiftSelection=false}
    onActiveFocusChanged:if(!activeFocus)root.shiftSelection=false
    component ImportCheck:CheckBox {
        id:control;implicitHeight:36;spacing:10;padding:0;hoverEnabled:true
        indicator:Rectangle {
            x:control.leftPadding;y:(control.height-height)/2;width:19;height:19;radius:3
            color:control.checked ? Theme.accentInk : Theme.white
            border.width:control.visualFocus ? 2 : 1;border.color:control.visualFocus ? Theme.accentInk : Theme.border
            Canvas {property color checkColor:Theme.accentText;anchors.fill:parent;visible:control.checked;onCheckColorChanged:requestPaint();onVisibleChanged:if(visible)requestPaint();onPaint:{var c=getContext('2d');c.reset();c.strokeStyle=checkColor;c.lineWidth=1.7;c.lineCap='round';c.lineJoin='round';c.beginPath();c.moveTo(4,9.5);c.lineTo(8,13);c.lineTo(15,6);c.stroke()}}
        }
        contentItem:MinchoText {text:qsTr(String(control.text));leftPadding:control.indicator.width+control.spacing;verticalAlignment:Text.AlignVCenter;color:control.enabled ? Theme.ink : Theme.secondary}
    }
    Rectangle {anchors.fill:parent;color:Theme.surface}
    ColumnLayout {
        anchors.fill:parent;anchors.margins:28;spacing:24
        RowLayout {
            Layout.fillWidth:true;spacing:16
            MinchoText {text:qsTr(String('导入照片'));editorialRole:true;font.pixelSize:Theme.display;Layout.fillWidth:true}
            MinchoText {text:qsTr(String(importState.scanning ? '正在读取来源' : importState.count ? importState.count+' 张照片' : ''));color:Theme.secondary;font.pixelSize:Theme.caption}
        }
        RowLayout {
            Layout.fillWidth:true;Layout.fillHeight:true;spacing:28
            ScrollView {
                id:sourceOptions;Layout.preferredWidth:224;Layout.minimumWidth:200;Layout.maximumWidth:248;Layout.fillHeight:true
                clip:true;contentWidth:availableWidth;rightPadding:12;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                Column {
                    width:sourceOptions.availableWidth;spacing:28;enabled:!importState.adding
                    Column {
                        width:parent.width;spacing:12
                        TextArea {
                            visible:importState.source_paths.length>0;width:parent.width
                            text:qsTr(String(importState.source_paths.slice(0,2).join('\n')+(importState.source_paths.length>2 ? '\n另 '+(importState.source_paths.length-2)+' 个来源' : '')))
                            readOnly:true;selectByMouse:true;wrapMode:TextEdit.WrapAnywhere;padding:0
                            font.family:Theme.family;font.pixelSize:Theme.caption;color:Theme.secondary;background:null
                        }
                        StudioButton {objectName:'importChooseFolder';text:qsTr(String('选择文件夹'));iconName:'folder';framed:true;width:parent.width;implicitHeight:40;onClicked:workspace.chooseFolder()}
                        StudioButton {objectName:'importChoosePhotos';text:qsTr(String('选择照片'));iconName:'photo';framed:true;width:parent.width;implicitHeight:40;onClicked:workspace.choosePhotos()}
                        ImportCheck {objectName:'importRecursive';text:qsTr(String('包含子文件夹'));checked:importState.recursive;onClicked:workspace.setRecursive(checked)}
                        StudioButton {text:qsTr(String('停止读取'));quiet:true;visible:importState.scanning;onClicked:workspace.cancelScan()}
                    }
                }
            }
            ColumnLayout {
                id:browser;Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumWidth:380;spacing:14
                RowLayout {
                    Layout.fillWidth:true;spacing:8;visible:importState.count>0
                    StudioButton {text:qsTr(String('全选'));quiet:true;enabled:importState.count>0&&!importState.adding;onClicked:workspace.selectAll(true)}
                    StudioButton {text:qsTr(String('取消选择'));quiet:true;enabled:importState.selected>0&&!importState.adding;onClicked:workspace.selectAll(false)}
                    Item {Layout.fillWidth:true}
                    StudioButton {objectName:'importTogglePreview';text:qsTr(String('预览'));framed:true;selected:root.showPreview;onClicked:root.showPreview=!root.showPreview}
                }
                RowLayout {
                    Layout.fillWidth:true;Layout.fillHeight:true;spacing:24
                    Item {
                        Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumWidth:220
                        GridView {
                            id:grid;objectName:'importPhotoGrid';anchors.fill:parent;clip:true;activeFocusOnTab:true
                            model:workspace.photos;cacheBuffer:200;reuseItems:true
                            cellWidth:(width-12)/Math.max(1,Math.floor((width-12)/170));cellHeight:cellWidth*.75+44
                            ScrollBar.vertical:ScrollBar {width:10;policy:ScrollBar.AsNeeded}
                            Keys.onPressed:function(event){
                                if(!importState.count)return;
                                var columns=Math.max(1,Math.floor((width-12)/170));var delta=event.key===Qt.Key_Left ? -1 : event.key===Qt.Key_Right ? 1 : event.key===Qt.Key_Up ? -columns : event.key===Qt.Key_Down ? columns : 0;
                                if(delta){var next=Math.max(0,Math.min(importState.count-1,importState.active_index+delta));workspace.activate(next);positionViewAtIndex(next,GridView.Contain);event.accepted=true}
                                else if(event.key===Qt.Key_Space&&importState.active_index>=0){workspace.toggle(importState.active_index,!!(event.modifiers&Qt.ShiftModifier));event.accepted=true}
                            }
                            delegate:Item {
                                id:tile;required property var entry;required property int index
                                width:grid.cellWidth;height:grid.cellHeight
                                Button {
                                    id:photo;objectName:'importPhoto_'+tile.index
                                    anchors.fill:parent;anchors.rightMargin:12;anchors.bottomMargin:12;padding:7;hoverEnabled:true;activeFocusOnTab:false
                                    Accessible.name:qsTr(String(tile.entry.name));Accessible.description:qsTr(String(tile.entry.already_current ? '已在当前会话' : tile.entry.selected ? '已选择，空格取消' : '未选择，空格选择'))
                                    onClicked:{workspace.activate(tile.entry.index);grid.forceActiveFocus()}
                                    background:Rectangle {radius:6;color:tile.entry.selected ? Theme.selection : photo.hovered ? Theme.hover : 'transparent';border.width:importState.active_index===tile.entry.index ? 1 : 0;border.color:Theme.accentInk}
                                    contentItem:Column {
                                        spacing:7
                                        Rectangle {
                                            id:thumbnailSurface;width:parent.width;height:photo.height-42;color:Theme.canvas;radius:3;clip:true
                                            Image {id:thumbnail;anchors.fill:parent;anchors.margins:3;source:workspace.thumbnail(tile.entry.index);fillMode:Image.PreserveAspectFit;asynchronous:true;cache:true;sourceSize.width:320;opacity:tile.entry.already_current ? .5 : 1}
                                            MinchoText {anchors.centerIn:parent;text:qsTr(String(tile.entry.format));color:Theme.secondary;font.pixelSize:Theme.caption;visible:thumbnail.status===Image.Error||thumbnail.status===Image.Null}
                                            ImportCheck {x:parent.width-width-2;y:1;width:36;height:36;text:'';checked:tile.entry.selected;enabled:!tile.entry.already_current&&!importState.adding;Accessible.name:qsTr(String('选择 '+tile.entry.name));onClicked:workspace.toggle(tile.entry.index,root.shiftSelection)}
                                        }
                                        MinchoText {text:qsTr(String(tile.entry.name));width:parent.width;elide:Text.ElideMiddle;font.pixelSize:Theme.caption;color:tile.entry.already_current ? Theme.secondary : Theme.ink}
                                    }
                                    ToolTip.visible:hovered;ToolTip.delay:650;ToolTip.text:qsTr(String(tile.entry.name+(tile.entry.already_current ? '\n已在当前会话' : '')))
                                }
                            }
                        }
                        MinchoText {anchors.centerIn:parent;visible:importState.count===0&&!importState.scanning&&!importState.error&&!!importState.status;text:qsTr(String(importState.status));color:Theme.secondary;font.pixelSize:Theme.body}
                    }
                    ColumnLayout {
                        visible:root.showPreview&&importState.active_index>=0&&browser.width>650;Layout.preferredWidth:Math.min(340,browser.width*.36);Layout.minimumWidth:230;Layout.maximumWidth:340;Layout.fillHeight:true;spacing:12
                        Rectangle {
                            Layout.fillWidth:true;Layout.fillHeight:true;color:Theme.canvas;radius:5
                            Image {anchors.fill:parent;anchors.margins:12;source:importState.preview;fillMode:Image.PreserveAspectFit;asynchronous:true;cache:false}
                            MinchoText {anchors.centerIn:parent;width:parent.width-32;horizontalAlignment:Text.AlignHCenter;wrapMode:Text.WordWrap;visible:!importState.preview&&importState.active_index>=0;text:qsTr(String(importState.preview_error ? '无法预览' : '正在读取预览'));color:Theme.secondary;font.pixelSize:Theme.caption}
                        }
                        MinchoText {Layout.fillWidth:true;text:qsTr(String(importState.active.name||''));elide:Text.ElideMiddle;font.pixelSize:Theme.body}
                        RowLayout {Layout.fillWidth:true;MinchoText {text:qsTr(String(importState.active.dimensions||''));color:Theme.secondary;font.pixelSize:Theme.caption;Layout.fillWidth:true}MinchoText {text:qsTr(String(importState.active.already_current ? '已在会话中' : importState.active.format||''));color:Theme.secondary;font.pixelSize:Theme.caption}}
                    }
                }
            }
        }
        ColumnLayout {
            Layout.fillWidth:true;spacing:12
            MinchoText {visible:importState.error.length>0;text:qsTr(String(importState.error));Layout.fillWidth:true;wrapMode:Text.WordWrap;color:Theme.errorInk;font.pixelSize:Theme.caption}
            RowLayout {
                Layout.fillWidth:true;spacing:12
                MinchoText {text:qsTr(String(importState.adding ? importState.status : importState.selected ? '已选择 '+importState.selected+' 张' : ''));Layout.fillWidth:true;color:Theme.secondary;font.pixelSize:Theme.caption;elide:Text.ElideRight}
                StudioButton {objectName:'importCancel';text:qsTr(String('取消'));quiet:true;enabled:!importState.adding;onClicked:root.cancel()}
                StudioButton {objectName:'importCommit';text:qsTr(String('导入'));primary:true;enabled:importState.can_import;implicitWidth:120;onClicked:workspace.addSelected()}
            }
        }
    }
    DropArea {id:dropTarget;anchors.fill:parent;enabled:!importState.adding;onDropped:function(drop){if(drop.hasUrls){workspace.receiveDrop(drop.urls);drop.acceptProposedAction()}}}
    Rectangle {anchors.fill:parent;anchors.margins:8;visible:dropTarget.containsDrag;color:'transparent';radius:8;border.width:2;border.color:Theme.accentInk}
}
