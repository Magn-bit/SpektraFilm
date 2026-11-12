import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ColumnLayout {
    id:root
    signal editRequested()
    signal syncRequested()
    signal libraryRequested()
    property real cellSize:160
    spacing:16
    RowLayout {
        Layout.fillWidth:true;spacing:8
        MinchoText {text:qsTr(String('图库'));font.pixelSize:Theme.heading;Layout.fillWidth:true}
        MinchoText {text:qsTr(String(ctrl.selectedCount+' / '+ctrl.photoCount));font.pixelSize:Theme.caption;color:Theme.secondary}
        StudioButton {text:qsTr(String('资料库'));quiet:true;onClicked:root.libraryRequested()}
        StudioButton {objectName:'galleryEditButton';text:qsTr(String('返回照片'));quiet:true;enabled:ctrl.currentIndex>=0;onClicked:root.editRequested()}
    }
    TextField {
        objectName:'browserSearch';Layout.fillWidth:true;implicitHeight:36
        placeholderText:qsTr(String('搜索文件名或文件夹'));selectByMouse:true
        font.family:Theme.family;font.pixelSize:Theme.caption;color:Theme.ink
        onTextEdited:ctrl.browserModel.query=text
        Accessible.name:qsTr(String('搜索当前会话照片'))
        background:Rectangle {radius:4;color:Theme.canvas;border.width:parent.activeFocus ? 1 : 0;border.color:Theme.accent}
    }
    MaterialSelector {
        Layout.fillWidth:true;label:qsTr(String('排列'));fillField:true;value:ctrl.browserModel.order
        choices:[{id:'import',name:'导入顺序'},{id:'name',name:'文件名 A—Z'},{id:'name_desc',name:'文件名 Z—A'}]
        onSelected:function(v){ctrl.browserModel.order=v}
    }
    GridView {
        id:grid;objectName:'sessionBrowserGrid';Layout.fillWidth:true;Layout.fillHeight:true
        clip:true;model:ctrl.browserModel;cacheBuffer:cellHeight
        cellWidth:width/Math.max(1,Math.floor(width/root.cellSize));cellHeight:cellWidth*.78+36
        ScrollBar.vertical:ScrollBar {policy:ScrollBar.AsNeeded}
        delegate:Item {
            id:tile;required property var photo;required property int sourceIndex
            width:grid.cellWidth;height:grid.cellHeight
            readonly property bool selected:ctrl.selectedIndices.indexOf(sourceIndex)>=0
            readonly property bool current:sourceIndex===ctrl.currentIndex
            activeFocusOnTab:true
            Accessible.role:Accessible.Button;Accessible.name:qsTr(String(photo.name))
            Accessible.description:qsTr(String((selected ? '已选中，' : '')+'双击编辑；Ctrl或Shift多选'))
            Keys.onReturnPressed:{ctrl.selectWithModifiers(sourceIndex,0);root.editRequested()}
            Keys.onSpacePressed:function(e){ctrl.selectWithModifiers(sourceIndex,e.modifiers)}
            Rectangle {
                x:3;y:3;width:parent.width-10;height:parent.height-8;radius:5
                color:tile.selected ? Theme.selection : mouse.containsMouse ? Theme.hover : 'transparent'
                border.width:tile.current || tile.activeFocus ? 1.5 : 0;border.color:Theme.accent
            }
            Image {
                x:11;y:11;width:parent.width-26;height:parent.height-58
                source:photo.thumbnail;asynchronous:true;cache:true
                sourceSize.width:Math.ceil(width*2);sourceSize.height:Math.ceil(height*2)
                fillMode:Image.PreserveAspectFit
            }
            MinchoText {x:12;y:parent.height-42;width:parent.width-28;text:qsTr(String(photo.name));elide:Text.ElideMiddle;font.pixelSize:Theme.caption;color:tile.current ? Theme.ink : Theme.secondary}
            MouseArea {
                id:mouse;anchors.fill:parent;hoverEnabled:true;cursorShape:Qt.PointingHandCursor
                enabled:!ctrl.exporting
                onClicked:function(e){tile.forceActiveFocus();ctrl.selectWithModifiers(tile.sourceIndex,e.modifiers)}
                onDoubleClicked:root.editRequested()
            }
        }
        MinchoText {anchors.centerIn:parent;visible:grid.count===0;text:qsTr(String(ctrl.photoCount ? '没有匹配的照片' : '选择照片'));color:Theme.secondary}
    }
    RowLayout {
        Layout.fillWidth:true
        StudioButton {text:qsTr(String('全选'));quiet:true;enabled:ctrl.photoCount>0&&!ctrl.exporting;onClicked:ctrl.selectAllPhotos()}
        StudioButton {text:qsTr(String('移除'));quiet:true;enabled:ctrl.selectedCount>0&&!ctrl.exporting;onClicked:ctrl.removeSelectedPhotos();Accessible.description:qsTr(String('仅从当前会话移除，保留磁盘原片'))}
        Item {Layout.fillWidth:true}
        StudioButton {text:qsTr(String('同步'));quiet:true;enabled:ctrl.selectedCount>0&&!ctrl.exporting;onClicked:root.syncRequested()}
    }
}
