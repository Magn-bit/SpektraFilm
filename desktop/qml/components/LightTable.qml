import QtQuick
import QtQuick.Window
import QtQuick.Controls.Basic
import QtQuick.Layouts

ColumnLayout {
    id:root
    signal editRequested()
    readonly property real physicalScale:Screen.pixelDensity>0 ? Screen.pixelDensity/Screen.devicePixelRatio : 3.78
    property real mmScale:physicalScale
    spacing:0
    onVisibleChanged: {ctrl.lightTable.setActive(visible);if(visible)Qt.callLater(refreshViewport)}
    function refreshViewport() {
        if(visible && board.width>0)ctrl.lightTable.setViewport(board.contentX/mmScale,board.contentY/mmScale,board.width/mmScale,board.height/mmScale)
    }
    onMmScaleChanged:Qt.callLater(refreshViewport)
    Connections {target:ctrl.lightTable;function onChanged(){Qt.callLater(root.refreshViewport)}}
    RowLayout {
        Layout.fillWidth:true;Layout.leftMargin:24;Layout.rightMargin:24;Layout.preferredHeight:54;spacing:16
        MinchoText {text:qsTr(String('看片台'));font.pixelSize:Theme.heading;Layout.fillWidth:true}
        StudioButton {text:qsTr(String('排列'));quiet:true;enabled:ctrl.photoCount>0;onClicked:ctrl.lightTable.arrange()}
        StudioButton {text:'−';quiet:true;implicitWidth:36;enabled:root.mmScale>1;onClicked:root.mmScale=Math.max(1,root.mmScale/1.25);Accessible.name:qsTr(String('缩小看片台'))}
        MinchoText {text:qsTr(String(Math.round(root.mmScale/root.physicalScale*100)+'%'));Layout.preferredWidth:48;horizontalAlignment:Text.AlignHCenter;font.pixelSize:Theme.caption}
        StudioButton {text:'+';quiet:true;implicitWidth:36;enabled:root.mmScale<16;onClicked:root.mmScale=Math.min(16,root.mmScale*1.25);Accessible.name:qsTr(String('放大片台'))}
    }
    Flickable {
        id:board;objectName:'lightTableBoard';Layout.fillWidth:true;Layout.fillHeight:true;clip:true
        contentWidth:4200*root.mmScale;contentHeight:3200*root.mmScale
        boundsBehavior:Flickable.StopAtBounds;pixelAligned:true
        ScrollBar.horizontal:ScrollBar {policy:ScrollBar.AsNeeded}
        ScrollBar.vertical:ScrollBar {policy:ScrollBar.AsNeeded}
        onContentXChanged:root.refreshViewport();onContentYChanged:root.refreshViewport()
        onWidthChanged:root.refreshViewport();onHeightChanged:root.refreshViewport()
        Rectangle {width:board.contentWidth;height:board.contentHeight;color:'#F0F1E9'}
        Repeater {
            model:ctrl.lightTable.rows
            delegate:Item {
                id:frame
                required property var modelData
                x:modelData.x*root.mmScale;y:modelData.y*root.mmScale
                width:modelData.width_mm*root.mmScale;height:modelData.height_mm*root.mmScale
                rotation:modelData.angle
                activeFocusOnTab:true
                Accessible.role:Accessible.Button;Accessible.name:qsTr(String(modelData.name))
                Accessible.description:qsTr(String('拖动摆放，方向键移动；R 旋转，Enter 编辑'))
                Keys.onReturnPressed:{ctrl.selectPhoto(modelData.index);root.editRequested()}
                Keys.onPressed:function(e){
                    var dx=0,dy=0,angle=modelData.angle
                    if(e.key===Qt.Key_R)angle+=e.modifiers&Qt.ShiftModifier ? -90 : 90
                    else if(e.key===Qt.Key_Left)dx=-1
                    else if(e.key===Qt.Key_Right)dx=1
                    else if(e.key===Qt.Key_Up)dy=-1
                    else if(e.key===Qt.Key_Down)dy=1
                    else return
                    var step=e.modifiers&Qt.ShiftModifier ? 10 : 1
                    ctrl.lightTable.place(modelData.id,modelData.x+dx*step,modelData.y+dy*step,angle);e.accepted=true
                }
                ShadowSurface {anchors.fill:parent;anchors.margins:-3;cornerRadius:1;elevation:frame.activeFocus ? 2 : 1;color:Theme.white}
                Image {anchors.fill:parent;source:frame.modelData.source || '';fillMode:Image.PreserveAspectFit;asynchronous:true;cache:false}
                MinchoText {anchors.centerIn:parent;visible:!frame.modelData.source;text:qsTr(String(frame.modelData.error ? '无法显影' : '…'));color:Theme.secondary}
                MouseArea {
                    anchors.fill:parent;acceptedButtons:Qt.LeftButton | Qt.RightButton
                    drag.target:frame;preventStealing:true;cursorShape:pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                    onPressed:function(e){frame.forceActiveFocus();if(e.button===Qt.RightButton){rotationMenu.open();e.accepted=false}}
                    onReleased:{ctrl.lightTable.place(frame.modelData.id,frame.x/root.mmScale,frame.y/root.mmScale,frame.rotation);frame.x=Qt.binding(function(){return frame.modelData.x*root.mmScale});frame.y=Qt.binding(function(){return frame.modelData.y*root.mmScale})}
                    onDoubleClicked:{ctrl.selectPhoto(frame.modelData.index);root.editRequested()}
                    Menu {
                        id:rotationMenu
                        font.family:Theme.family
                        MenuItem {text:qsTr(String('旋转 90°'));onTriggered:ctrl.lightTable.place(frame.modelData.id,frame.modelData.x,frame.modelData.y,frame.rotation+90)}
                        MenuItem {text:qsTr(String('恢复方向'));onTriggered:ctrl.lightTable.place(frame.modelData.id,frame.modelData.x,frame.modelData.y,0)}
                    }
                }
                Rectangle {anchors.fill:parent;anchors.margins:-4;color:'transparent';border.width:1.5;border.color:Theme.accent;visible:frame.activeFocus}
            }
        }
    }
}
