import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ScrollView {
    id:root
    required property var workspace
    property string restoreFocus:''
    clip:true;contentWidth:availableWidth;rightPadding:10
    ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
    ScrollBar.vertical:ScrollBar {width:10}
    Column {
        width:root.availableWidth;spacing:12
        Repeater {
            model:root.workspace.filterGroups
            delegate:Column {
                id:group
                required property var modelData
                width:parent.width;spacing:3
                Button {
                    id:heading
                    objectName:'libraryFilterGroup_'+group.modelData.key
                    width:parent.width;height:34;leftPadding:6;rightPadding:6;hoverEnabled:true
                    Accessible.name:qsTr(String(group.modelData.title))
                    Accessible.description:group.modelData.expanded ? qsTr(String('已展开')) : qsTr(String('已折叠'))
                    onClicked:root.workspace.toggleFilterGroup(group.modelData.key)
                    contentItem:RowLayout {
                        MinchoText {text:qsTr(String(group.modelData.title));Layout.fillWidth:true;font.pixelSize:Theme.caption;color:Theme.secondary}
                        Canvas {
                            width:12;height:12;rotation:group.modelData.expanded ? 90 : 0
                            property color lineColor:Theme.secondary
                            onLineColorChanged:requestPaint()
                            onPaint:{var c=getContext('2d');c.reset();c.strokeStyle=lineColor;c.lineWidth=1.2;c.lineCap='round';c.beginPath();c.moveTo(4,2);c.lineTo(8,6);c.lineTo(4,10);c.stroke()}
                        }
                    }
                    background:Rectangle {radius:4;color:heading.hovered ? Theme.hover : 'transparent';border.width:heading.visualFocus ? 1 : 0;border.color:Theme.accentInk}
                    ToolTip.visible:hovered && group.modelData.key==='edited'
                    ToolTip.text:qsTr(String('是否保存过显影调整，不代表照片已经导出'))
                }
                Repeater {
                    model:group.modelData.expanded ? group.modelData.rows : []
                    delegate:Button {
                        id:facet
                        required property var modelData
                        objectName:'libraryFilter_'+modelData.key+'_'+String(modelData.value)
                        width:group.width;implicitHeight:34
                        leftPadding:8+modelData.depth*14;rightPadding:8;hoverEnabled:true
                        checkable:true;checked:modelData.selected
                        Accessible.name:qsTr(String(modelData.title+'，'+modelData.count+'张'))
                        onClicked:{root.restoreFocus=objectName;root.workspace.toggleFilter(modelData.key,modelData.value)}
                        Component.onCompleted:if(root.restoreFocus===objectName)Qt.callLater(function(){facet.forceActiveFocus()})
                        contentItem:RowLayout {
                            spacing:8
                            Rectangle {
                                width:12;height:12;radius:2
                                color:facet.checked ? Theme.accentInk : 'transparent'
                                border.width:1;border.color:facet.checked ? Theme.accentInk : Theme.muted
                                Rectangle {anchors.centerIn:parent;width:5;height:5;radius:1;color:Theme.surface;visible:facet.checked}
                            }
                            MinchoText {text:qsTr(String(facet.modelData.title));Layout.fillWidth:true;elide:Text.ElideRight;font.pixelSize:Theme.caption;color:facet.checked ? Theme.accentInk : Theme.ink}
                            MinchoText {text:String(facet.modelData.count);font.pixelSize:Theme.caption;color:Theme.secondary;horizontalAlignment:Text.AlignRight}
                        }
                        background:Rectangle {
                            radius:4;color:facet.checked ? Theme.selection : facet.down || facet.hovered ? Theme.hover : 'transparent'
                            border.width:facet.visualFocus ? 1 : 0;border.color:Theme.accentInk
                        }
                        ToolTip.visible:hovered
                        ToolTip.text:qsTr(String(modelData.title))
                    }
                }
            }
        }
        MinchoText {
            width:parent.width;visible:root.workspace.facetsLoading && !root.workspace.filterGroups.length
            text:qsTr(String('正在统计…'));font.pixelSize:Theme.caption;color:Theme.secondary
        }
    }
}
