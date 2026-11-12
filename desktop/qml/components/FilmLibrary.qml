import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Popup {
    id: root
    objectName: "libraryPopup"
    property var controller
    property var library
    property string page: "film"
    property string maker: ""
    property string kind: ""
    signal accepted()
    x: parent ? Math.max(18, parent.width-width-18) : 18
    y: parent ? Math.max(30, (parent.height-height)/2) : 30
    width: parent ? Math.min(540, parent.width-48) : 540
    height: parent ? Math.min(760, parent.height-70) : 700
    padding: 24
    modal: true
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    background: ShadowSurface { elevation:3; cornerRadius:Theme.popupRadius; color:Theme.surface }
    Overlay.modal: Rectangle { color:Theme.scrim }
    enter: Transition { NumberAnimation { property:"opacity"; from:0; to:1; duration:Theme.fast } }
    exit: Transition { NumberAnimation { property:"opacity"; from:1; to:0; duration:Theme.fast } }
    onOpened: { library.activate(); Qt.callLater(reportVisible) }
    onClosed: library.deactivate()
    onPageChanged: { if(page==="film") Qt.callLater(reportVisible); else library.setVisibleRange(0,-1) }
    function filter() { library.setFilters(search.text, maker, kind); Qt.callLater(reportVisible) }
    function reportVisible() {
        if(!opened || page!=="film") return
        var first=Math.max(0, Math.floor(stockList.contentY/104))
        library.setVisibleRange(first, Math.min(stockList.count-1, Math.ceil((stockList.contentY+stockList.height)/104)))
    }
    Connections { target:root.library; function onAccepted(){root.accepted()} }
    Timer { id:visibleTimer; interval:80; onTriggered:root.reportVisible() }

    contentItem: ColumnLayout {
        spacing:16
        RowLayout {
            Layout.fillWidth:true
            MinchoText { objectName:"libraryTitle"; text:qsTr("胶片档案"); editorialRole:true; font.pixelSize:Theme.heading; Layout.fillWidth:true }
            StudioButton { text:qsTr("关闭"); quiet:true; implicitHeight:32; onClicked:root.close() }
        }
        RowLayout {
            Layout.fillWidth:true; spacing:4
            StudioButton { text:qsTr("胶片"); quiet:true; selected:root.page==="film"; implicitHeight:34; onClicked:root.page="film" }
            StudioButton { text:qsTr("已存预设"); quiet:true; selected:root.page==="presets"; implicitHeight:34; onClicked:root.page="presets" }
            Item { Layout.fillWidth:true }
            MinchoText { visible:root.library.selectedCount>1; text:qsTr("已选 ")+root.library.selectedCount+qsTr(" 张"); color:Theme.secondary; font.pixelSize:Theme.caption }
        }
        TextField {
            id:search; objectName:"stockSearch"; visible:root.page==="film"; Layout.fillWidth:true; implicitHeight:38
            placeholderText:qsTr("搜索胶片"); color:Theme.ink; font.family:Theme.family; font.pixelSize:Theme.body
            leftPadding:12; rightPadding:12; selectionColor:Theme.accent; selectedTextColor:Theme.white
            onTextChanged:root.filter()
            background:Rectangle { radius:4; color:Theme.white; border.width:search.activeFocus ? 2 : 1; border.color:search.activeFocus ? Theme.accent : Theme.border }
            Accessible.name:qsTr("搜索胶片")
        }
        RowLayout {
            visible:root.page==="film"; Layout.fillWidth:true; spacing:12
            MaterialSelector {
                objectName:"filmMakerFilter"; Layout.fillWidth:true; fillField:true; label:""; value:root.maker
                choices:{var items=[{id:"",name:qsTr("全部品牌")}];for(var i=0;i<root.library.makers.length;i++)items.push({id:root.library.makers[i],name:root.library.makers[i]});return items}
                onSelected:function(value){root.maker=value;root.filter()}
            }
            MaterialSelector {
                objectName:"filmTypeFilter"; Layout.fillWidth:true; fillField:true; label:""; value:root.kind
                choices:[{id:"",name:qsTr("全部类型")},{id:"negative",name:qsTr("彩色负片")},{id:"slide",name:qsTr("反转片")},{id:"cinema",name:qsTr("电影胶片")},{id:"bw",name:qsTr("黑白胶片")}]
                onSelected:function(value){root.kind=value;root.filter()}
            }
        }
        ListView {
            id:stockList; objectName:"stockList"; visible:root.page==="film"; Layout.fillWidth:true; Layout.fillHeight:true; Layout.minimumHeight:0
            model:root.library.films; clip:true; reuseItems:true; spacing:0; boundsBehavior:Flickable.StopAtBounds
            ScrollBar.vertical:ScrollBar { policy:ScrollBar.AsNeeded }
            onContentYChanged:visibleTimer.restart()
            onHeightChanged:visibleTimer.restart()
            onCountChanged:visibleTimer.restart()
            onMovementEnded:root.reportVisible()
            delegate:Item {
                id:card; required property var entry; required property int index
                objectName:"filmCard_"+entry.id; width:stockList.width; height:104; activeFocusOnTab:true
                function choose(){if(root.library.hasPhoto && !root.controller.exporting)root.library.pickFilm(entry.id)}
                Keys.onReturnPressed:choose()
                Keys.onSpacePressed:choose()
                Accessible.role:Accessible.RadioButton; Accessible.name:entry.name
                Accessible.checked:entry.selected; Accessible.description:entry.error ? qsTr(String(entry.error)) : (entry.loading ? qsTr("正在预览") : "")
                Item {
                    anchors.fill:parent; anchors.topMargin:3; anchors.bottomMargin:3; anchors.rightMargin:12
                    Rectangle {
                        anchors.fill:parent;radius:5;color:Theme.hover
                        opacity:cardMouse.containsMouse && !card.entry.selected ? 1 : 0
                        Behavior on opacity {NumberAnimation {duration:Theme.fast}}
                    }
                    Rectangle {
                        anchors.fill:parent;radius:5;color:Theme.selection
                        opacity:card.entry.selected ? 1 : 0
                    }
                    Rectangle {
                        anchors.fill:parent;radius:5;color:'transparent'
                        border.width:card.activeFocus ? 1 : 0;border.color:Theme.accent
                    }
                }
                RowLayout {
                    anchors.fill:parent; anchors.leftMargin:8; anchors.rightMargin:24; spacing:16
                    Rectangle {
                        Layout.preferredWidth:112; Layout.preferredHeight:84; color:Theme.canvas; radius:3; clip:true
                        Image { anchors.fill:parent; source:card.entry.url; fillMode:Image.PreserveAspectCrop; asynchronous:true; cache:false; retainWhileLoading:true }
                        Rectangle { anchors.fill:parent; color:Theme.surface; opacity:card.entry.loading && card.entry.url ? .12 : 0 }
                        BusyIndicator { anchors.centerIn:parent; width:26; height:26; running:card.entry.loading; visible:running && !card.entry.url }
                        MinchoText { anchors.centerIn:parent; visible:!card.entry.url && !card.entry.loading; text:card.entry.error ? qsTr("重试") : root.library.hasPhoto ? "" : qsTr("未载入照片"); font.pixelSize:12; color:Theme.secondary }
                    }
                    ColumnLayout {
                        Layout.fillWidth:true; spacing:8
                        MinchoText { text:card.entry.name; editorialRole:true; font.pixelSize:Theme.heading; Layout.fillWidth:true; elide:Text.ElideRight; textFormat:Text.PlainText }
                        MinchoText { text:card.entry.maker+" · "+(card.entry.type==="bw" ? qsTr("黑白负片") : card.entry.type==="slide" ? qsTr("反转片") : card.entry.category==="cinema" ? qsTr("电影胶片") : qsTr("彩色负片")); color:Theme.secondary; font.pixelSize:Theme.caption; Layout.fillWidth:true; elide:Text.ElideRight }
                    }
                    Rectangle { width:6; height:6; radius:3; color:Theme.accentInk; visible:card.entry.selected }
                }
                MouseArea { id:cardMouse; anchors.fill:parent; anchors.rightMargin:12; hoverEnabled:true; cursorShape:Qt.PointingHandCursor; onClicked:{card.forceActiveFocus();if(card.entry.error)root.library.retry();else card.choose()} }
            }
            MinchoText { objectName:"stockSearchEmpty"; anchors.centerIn:parent; visible:stockList.count===0; text:qsTr("没有匹配的胶片"); color:Theme.secondary }
        }
        ListView {
            id:presetList; objectName:"savedFilmPresets"; visible:root.page==="presets"; Layout.fillWidth:true; Layout.fillHeight:true; Layout.minimumHeight:0
            model:root.library.presets; clip:true; spacing:4; boundsBehavior:Flickable.StopAtBounds
            ScrollBar.vertical:ScrollBar { policy:ScrollBar.AsNeeded }
            delegate:RowLayout {
                id:presetRow; required property var modelData; width:presetList.width-14; height:60; spacing:6
                StudioButton {
                    Layout.fillWidth:true; implicitHeight:52; quiet:true; enabled:root.library.hasPhoto && !root.controller.exporting
                    text:presetRow.modelData.name; onClicked:root.library.applyPreset(presetRow.modelData.id)
                    contentItem:MinchoText { text:presetRow.modelData.name; textFormat:Text.PlainText; verticalAlignment:Text.AlignVCenter; elide:Text.ElideRight; color:parent.enabled ? Theme.ink : Theme.muted }
                }
                StudioButton { text:qsTr("重命名"); quiet:true; implicitHeight:32; enabled:root.library.canWrite; onClicked:{nameEditor.editId=presetRow.modelData.id;nameField.text=presetRow.modelData.name;nameEditor.open()} }
                StudioButton { text:qsTr("删除"); quiet:true; implicitHeight:32; enabled:root.library.canWrite; onClicked:root.library.deletePreset(presetRow.modelData.id) }
            }
            MinchoText { anchors.centerIn:parent; visible:presetList.count===0; text:qsTr("暂无已存预设"); color:Theme.secondary }
        }
        MinchoText { visible:root.library.error.length>0; text:qsTr(String(root.library.error)); textFormat:Text.PlainText; Layout.fillWidth:true; wrapMode:Text.Wrap; color:Theme.secondary; font.pixelSize:Theme.caption }
        RowLayout {
            visible:root.page==="presets"; Layout.fillWidth:true; spacing:12
            StudioButton { text:qsTr("撤销删除"); quiet:true; visible:root.library.canRestore; onClicked:root.library.restorePreset() }
            Item { Layout.fillWidth:true }
            StudioButton {
                objectName:"saveFilmPreset"; text:qsTr("保存当前预设"); primary:true; enabled:root.library.hasPhoto && root.library.canWrite && !root.controller.exporting
                onClicked:{nameEditor.editId="";nameField.text="";nameEditor.picked=['materials','exposure','WB','film_effects','print_effects'];nameEditor.open()}
            }
        }
    }
    Popup {
        id:nameEditor; objectName:"filmPresetEditor"; parent:Overlay.overlay; anchors.centerIn:parent; width:Math.min(480,parent.width-64); padding:24; modal:true; focus:true
        property string editId:""
        property var picked:['materials','exposure','WB','film_effects','print_effects']
        function toggle(key){var next=picked.slice(),i=next.indexOf(key);if(i<0)next.push(key);else next.splice(i,1);picked=next}
        function save(){var ok=editId ? root.library.renamePreset(editId,nameField.text) : root.library.savePreset(nameField.text,picked);if(ok)close()}
        onOpened:nameField.forceActiveFocus()
        closePolicy:Popup.CloseOnEscape
        background:ShadowSurface { elevation:4; cornerRadius:Theme.popupRadius; color:Theme.surface }
        Overlay.modal:Rectangle { color:Theme.scrim }
        contentItem:ColumnLayout {
            spacing:20
            MinchoText { text:nameEditor.editId ? qsTr("重命名预设") : qsTr("保存预设"); editorialRole:true; font.pixelSize:Theme.heading }
            TextField {
                id:nameField; objectName:"filmPresetName"; Layout.fillWidth:true; implicitHeight:40; maximumLength:80; placeholderText:qsTr("预设名称")
                color:Theme.ink; font.family:Theme.family; font.pixelSize:Theme.body; leftPadding:12; rightPadding:12
                Accessible.name:qsTr("预设名称"); onAccepted:if(text.trim().length && (nameEditor.editId || nameEditor.picked.length))nameEditor.save()
                background:Rectangle { radius:4; color:Theme.white; border.width:nameField.activeFocus ? 2 : 1; border.color:nameField.activeFocus ? Theme.accent : Theme.border }
            }
            GridLayout {
                visible:!nameEditor.editId; Layout.fillWidth:true; columns:2; columnSpacing:12; rowSpacing:4
                Repeater {
                    model:root.library.categories
                    delegate:StudioButton {
                        required property var modelData; text:qsTr(String(modelData.name)); Layout.fillWidth:true; implicitHeight:38; quiet:true; selected:nameEditor.picked.indexOf(modelData.id)>=0
                        Accessible.role:Accessible.CheckBox; Accessible.checked:selected
                        onClicked:nameEditor.toggle(modelData.id)
                        background:Rectangle { radius:4; color:parent.selected ? Theme.selection : parent.hovered ? Theme.hover : "transparent"; border.width:parent.visualFocus || parent.selected ? 1 : 0; border.color:Theme.accent }
                    }
                }
            }
            MinchoText { visible:root.library.error.length>0; text:qsTr(String(root.library.error)); textFormat:Text.PlainText; Layout.fillWidth:true; wrapMode:Text.Wrap; font.pixelSize:Theme.caption; color:Theme.secondary }
            RowLayout {
                Layout.fillWidth:true
                StudioButton { text:qsTr("取消"); quiet:true; onClicked:nameEditor.close() }
                Item { Layout.fillWidth:true }
                StudioButton { objectName:"confirmFilmPreset"; text:qsTr("保存"); primary:true; enabled:nameField.text.trim().length>0 && (nameEditor.editId.length>0 || nameEditor.picked.length>0) && root.library.canWrite; onClicked:nameEditor.save() }
            }
        }
    }
}
