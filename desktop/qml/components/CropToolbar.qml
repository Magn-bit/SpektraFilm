import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQml.Models

RowLayout {
    id:root
    property var cropTool
    property bool ready:false
    signal applyRequested()
    signal cancelRequested()
    spacing:8
    StudioButton {
        id:ratioButton;objectName:'cropRatioButton';text:qsTr(String(root.cropTool ? root.cropTool.ratioName : '自由'));iconName:'chevron';quiet:true;implicitWidth:140;implicitHeight:40
        Accessible.name:qsTr(String('裁切比例'));Accessible.description:qsTr(String('选择自由、原图、方形或 XPan 等比例'))
        enabled:root.ready && !!root.cropTool
        onClicked:ratioMenu.opened ? ratioMenu.close() : ratioMenu.open()
        Menu {
            id:ratioMenu;objectName:'cropRatioMenu'
            // Instantiated MenuItems do not supply an implicit menu width.
            // Anchor explicitly: popup() without a point follows the OS cursor.
            x:0;y:ratioButton.height+4;width:196
            topPadding:6;bottomPadding:6;leftPadding:4;rightPadding:4
            popupType:Popup.Item
            closePolicy:Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent
            background:ShadowSurface {elevation:2;cornerRadius:Theme.popupRadius;color:Theme.surface}
            Instantiator {
                model:[{name:'自由',r:0},{name:'原图',r:root.cropTool ? root.cropTool.sourceRatio : 1},{name:'1:1',r:1},{name:'3:2',r:3/2},{name:'4:3',r:4/3},{name:'16:9',r:16/9},{name:'XPan 65:24',r:65/24}]
                delegate:MenuItem {
                    id:ratioItem
                    required property var modelData;objectName:'cropRatioItem_'+modelData.name;text:qsTr(String(modelData.name));font.family:Theme.family;font.pixelSize:Theme.body
                    width:ratioMenu.width-ratioMenu.leftPadding-ratioMenu.rightPadding;implicitHeight:38;hoverEnabled:true
                    checkable:true;checked:root.cropTool && root.cropTool.ratioName===modelData.name
                    contentItem:MinchoText {
                        text:qsTr(String(ratioItem.text));leftPadding:28;rightPadding:12
                        verticalAlignment:Text.AlignVCenter;color:ratioItem.enabled ? Theme.ink : Theme.muted
                    }
                    indicator:Rectangle {x:12;y:(ratioItem.height-height)/2;width:5;height:5;radius:2.5;visible:ratioItem.checked;color:Theme.accentInk}
                    background:Rectangle {radius:4;color:ratioItem.highlighted || ratioItem.down ? Theme.selection : 'transparent';border.width:ratioItem.visualFocus ? 1 : 0;border.color:Theme.accent}
                    onTriggered:root.cropTool.chooseRatio(modelData.name,root.cropTool.transposed && modelData.r>0 ? 1/modelData.r : modelData.r)
                }
                onObjectAdded:function(index,object){ratioMenu.insertItem(index,object)}
                onObjectRemoved:function(index,object){ratioMenu.removeItem(object)}
            }
        }
    }
    StudioButton {
        objectName:'transposeCropButton';quiet:true;implicitWidth:44;implicitHeight:44
        enabled:root.ready && root.cropTool && root.cropTool.ratio>0 && Math.abs(root.cropTool.ratio-1)>.001
        Accessible.name:qsTr(String(root.cropTool && root.cropTool.ratio>1 ? '切换为纵向裁切' : '切换为横向裁切'))
        ToolTip.visible:hovered || visualFocus;ToolTip.delay:500;ToolTip.text:qsTr(String(Accessible.name))
        contentItem:Item {OrientationIcon {anchors.centerIn:parent;opacity:parent.parent.enabled ? 1 : .4}}
        onClicked:{root.cropTool.transposed=!root.cropTool.transposed;root.cropTool.chooseRatio(root.cropTool.ratioName,1/root.cropTool.ratio)}
    }
    MinchoText {text:qsTr(String(root.cropTool ? root.cropTool.outputWidth+' × '+root.cropTool.outputHeight : ''));font.pixelSize:Theme.caption;color:Theme.secondary;Layout.fillWidth:true;Layout.minimumWidth:0;elide:Text.ElideRight;font.features:{'tnum':1}}
    StudioButton {objectName:'resetCropButton';text:qsTr(String('恢复原图'));quiet:true;implicitHeight:36;onClicked:root.cropTool.resetDraft()}
    StudioButton {text:qsTr(String('取消'));quiet:true;implicitHeight:36;onClicked:root.cancelRequested()}
    StudioButton {objectName:'applyCropButton';text:qsTr(String('应用'));primary:true;implicitHeight:36;implicitWidth:68;enabled:root.ready;onClicked:root.applyRequested()}
}
