import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQml.Models

Item {
    id: root
    objectName: 'libraryWorkspace'
    required property var workspace
    signal closeRequested()
    property string collectionForRename: ''
    property bool renameExisting: false
    property bool infoExpanded:false

    component LibraryField: TextField {
        implicitHeight: 36
        leftPadding: 12; rightPadding: 12
        font.family: Theme.family; font.pixelSize: Theme.body
        color: Theme.ink; placeholderTextColor: Theme.muted
        selectionColor: Theme.selection; selectedTextColor: Theme.ink
        background: Rectangle {
            radius: 5; color: Theme.white
            border.width: parent.activeFocus ? 2 : 1
            border.color: parent.activeFocus ? Theme.accentInk : Theme.border
        }
    }
    component LibraryMenu: Menu {
        padding: 5; width: 208
        font.family: Theme.family; font.pixelSize: Theme.body
        background: ShadowSurface {
            elevation: 2; cornerRadius: Theme.popupRadius; color: Theme.white
            Rectangle { anchors.fill: parent; radius: Theme.popupRadius; color: 'transparent'; border.width: 1; border.color: Theme.rule }
        }
        enter: Transition { NumberAnimation { property: 'scale'; from: .985; to: 1; duration: Theme.fast; easing.type: Theme.easing } }
        exit: Transition { NumberAnimation { property: 'scale'; from: 1; to: .985; duration: Theme.fast; easing.type: Theme.easing } }
    }
    component LibraryOption: MenuItem {
        id: option
        implicitHeight: 38; leftPadding: 12; rightPadding: 12
        contentItem: MinchoText { text: qsTr(String(option.text)); color: option.enabled ? Theme.ink : Theme.muted; verticalAlignment: Text.AlignVCenter }
        background: Rectangle { radius: 4; color: option.highlighted ? Theme.hover : 'transparent' }
    }

    Rectangle { anchors.fill: parent; color: Theme.surface }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 24; spacing: 16
        RowLayout {
            Layout.fillWidth: true; spacing: 12
            MinchoText { text: qsTr(String('资料库')); editorialRole: true; font.pixelSize: 24 }
            MinchoText {
                text: qsTr(String(root.workspace.name)); Layout.fillWidth: true; elide: Text.ElideRight
                color: Theme.secondary; visible: root.workspace.hasLibrary && root.workspace.name!=='资料库'
                ToolTip.visible: titleHover.hovered; ToolTip.text: qsTr(String(root.workspace.path))
                HoverHandler { id: titleHover }
            }
            Item { Layout.fillWidth: true; visible: !root.workspace.hasLibrary || root.workspace.name==='资料库' }
            StudioButton {
                text: qsTr(String('新建')); quiet: true; enabled: !root.workspace.busy
                onClicked: createMenu.open()
                LibraryMenu {
                    id: createMenu; y: parent.height + 4
                    LibraryOption { text: qsTr(String('资料库')); onTriggered: root.workspace.chooseCreateLibrary('catalog') }
                    LibraryOption { text: qsTr(String('拍摄会话')); onTriggered: root.workspace.chooseCreateLibrary('session') }
                }
            }
            StudioButton { text: qsTr(String('打开')); quiet: true; enabled: !root.workspace.busy; onClicked: root.workspace.chooseOpenLibrary() }
            StudioButton {
                text: qsTr(String('更多')); quiet: true; onClicked: libraryMenu.open()
                LibraryMenu {
                    id: libraryMenu; y: parent.height + 4; x: parent.width - width; width: 236
                    LibraryOption { text: qsTr(String('链接 Capture One 资料库')); enabled: !root.workspace.busy; onTriggered: root.workspace.chooseCaptureOne(false) }
                    LibraryOption { text: qsTr(String('复制为独立资料库')); enabled: !root.workspace.busy; onTriggered: root.workspace.chooseCaptureOne(true) }
                    LibraryOption { text: qsTr(String('同步 Capture One')); visible: root.workspace.originKind !== 'none' || root.workspace.isCaptureOneCopy; enabled: visible && !root.workspace.busy; height: visible ? implicitHeight : 0; onTriggered: root.workspace.syncCaptureOne() }
                    LibraryOption { text: qsTr(String('添加照片文件夹')); enabled: root.workspace.hasLibrary && root.workspace.originKind === 'none'; onTriggered: root.workspace.chooseWatchedFolder() }
                    LibraryOption { text: qsTr(String('刷新照片文件夹')); enabled: root.workspace.hasLibrary; onTriggered: root.workspace.syncFolders() }
                    LibraryOption { text: qsTr(String('直接使用快速会话')); enabled: !root.workspace.busy; onTriggered: root.workspace.quickSession() }
                }
            }
            StudioButton { text: qsTr(String('返回编辑')); quiet: true; onClicked: root.closeRequested() }
        }

        Rectangle {
            Layout.fillWidth: true; implicitHeight: errorLine.implicitHeight + 24
            visible: root.workspace.error.length > 0; color: Theme.errorSurface; radius: 6
            RowLayout {
                id: errorLine; anchors.fill: parent; anchors.margins: 12; spacing: 12
                MinchoText { text: qsTr(String(root.workspace.error)); color: Theme.errorInk; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                StudioButton { text: qsTr(String('重新载入')); quiet: true; visible: root.workspace.hasConflict; onClicked: root.workspace.reloadCurrentEdit() }
                StudioButton { text: qsTr(String('另存变体')); quiet: true; visible: root.workspace.hasConflict; onClicked: root.workspace.saveAsNewVariant() }
                StudioButton { text: qsTr(String('关闭')); quiet: true; visible: !root.workspace.hasConflict; onClicked: root.workspace.dismissError() }
            }
        }

        Item {
            Layout.fillWidth: true; Layout.fillHeight: true; visible: !root.workspace.hasLibrary
            ColumnLayout {
                anchors.centerIn: parent; spacing: 24
                MinchoText { text: qsTr(String('选择照片的工作方式')); editorialRole: true; font.pixelSize: Theme.heading; Layout.alignment: Qt.AlignHCenter }
                RowLayout {
                    spacing: 16
                    StudioButton { text: qsTr(String('打开资料库')); primary: true; onClicked: root.workspace.chooseOpenLibrary() }
                    StudioButton { text: qsTr(String('快速会话')); quiet: true; onClicked: root.workspace.quickSession() }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 24; visible: root.workspace.hasLibrary
            ColumnLayout {
                Layout.preferredWidth: Math.max(176, Math.min(224, root.width * .21))
                Layout.minimumWidth: 176; Layout.maximumWidth: 224
                Layout.fillHeight: true; spacing: 16
                RowLayout {
                    Layout.fillWidth: true
                    MinchoText { text: qsTr(String(root.workspace.sourcesExpanded ? '照片来源' : root.workspace.filtersExpanded ? '筛选' : '相册与文件夹')); font.pixelSize: Theme.caption; color: Theme.secondary; Layout.fillWidth: true }
                    StudioButton {text:qsTr(String('清除'));quiet:true;implicitHeight:32;visible:root.workspace.filtersExpanded && root.workspace.hasFilters;onClicked:root.workspace.clearFilters()}
                    StudioButton {
                        text: '+'; quiet: true; implicitWidth: 32; implicitHeight: 32
                        visible:!root.workspace.filtersExpanded && !root.workspace.sourcesExpanded
                        Accessible.name: qsTr(String('新建相册'))
                        onClicked: { root.renameExisting = false; albumName.text = ''; albumDialog.open() }
                    }
                }
                ListView {
                    id: collectionList
                    visible:!root.workspace.filtersExpanded && !root.workspace.sourcesExpanded
                    objectName: 'libraryCollections'
                    Layout.fillWidth: true; Layout.fillHeight: true
                    clip: true; spacing: 4
                    model: root.workspace.collections
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded; width: 10 }
                    delegate: Button {
                        id: collectionButton
                        required property var modelData
                        width: collectionList.width - 12; implicitHeight: 36
                        hoverEnabled: true; enabled: modelData.supported !== false
                        Accessible.name: qsTr(String(modelData.title))
                        contentItem: RowLayout {
                            spacing: 8
                            Item { Layout.preferredWidth: Math.min(3, collectionButton.modelData.depth) * 10 }
                            MinchoText {
                                text: qsTr(String(collectionButton.modelData.title)); Layout.fillWidth: true; elide: Text.ElideRight
                                font.pixelSize: Theme.caption
                                color: root.workspace.currentCollection === collectionButton.modelData.uuid ? Theme.accentInk : Theme.ink
                            }
                            MinchoText {
                                text: qsTr(String(collectionButton.modelData.image_count === undefined || collectionButton.modelData.image_count === null ? '' : String(collectionButton.modelData.image_count)))
                                color: Theme.secondary; font.pixelSize: Theme.caption
                            }
                            Item { width: 4 }
                        }
                        background: Rectangle {
                            radius: 5
                            color: root.workspace.currentCollection === collectionButton.modelData.uuid ? Theme.selection : collectionButton.hovered ? Theme.hover : 'transparent'
                            border.width: collectionButton.visualFocus ? 1 : 0; border.color: Theme.accentInk
                        }
                        onClicked: root.workspace.selectCollection(modelData.uuid)
                        TapHandler {
                            acceptedButtons: Qt.RightButton
                            onTapped: {
                                if (collectionButton.modelData.editable) {
                                    root.collectionForRename = collectionButton.modelData.uuid
                                    albumName.text = collectionButton.modelData.name
                                    collectionMenu.popup()
                                }
                            }
                        }
                    }
                }
                LibraryFilters {Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumHeight:0;visible:root.workspace.filtersExpanded;workspace:root.workspace}
                LibrarySources {Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumHeight:0;visible:root.workspace.sourcesExpanded;workspace:root.workspace}
                MinchoText { text: qsTr(String('原片位置')); font.pixelSize: Theme.caption; color: Theme.secondary; visible: root.workspace.locations.length > 0 && !root.workspace.filtersExpanded && !root.workspace.sourcesExpanded }
                ListView {
                    visible:!root.workspace.filtersExpanded && !root.workspace.sourcesExpanded
                    Layout.fillWidth: true; Layout.preferredHeight: Math.min(128, contentHeight)
                    clip: true; spacing: 4; model: root.workspace.locations
                    ScrollBar.vertical: ScrollBar { width: 10 }
                    delegate: StudioButton {
                        required property var modelData
                        width: ListView.view.width - 12; implicitHeight: 32; quiet: true
                        Accessible.name: qsTr(String('重新定位 ' + modelData.path))
                        contentItem: MinchoText {
                            text: qsTr(String((modelData.online ? '' : '离线 · ') + modelData.path))
                            elide: Text.ElideMiddle; font.pixelSize: Theme.caption
                            color: modelData.online ? Theme.secondary : '#8B4D35'; verticalAlignment: Text.AlignVCenter
                        }
                        onClicked: root.workspace.chooseRelinkLocation(modelData.uuid)
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true; Layout.fillHeight: true; spacing: 16
                RowLayout {
                    Layout.fillWidth: true; spacing: 8
                    LibraryField {
                        id: searchField; objectName: 'librarySearch'; Layout.fillWidth: true
                        placeholderText: qsTr(String('搜索文件名'))
                        text: qsTr(String(root.workspace.query))
                        onTextEdited: root.workspace.query = text
                        Accessible.name: qsTr(String('搜索资料库'))
                    }
                    StudioButton {
                        objectName:'libraryFiltersToggle';text:qsTr(String('筛选'+(root.workspace.activeFilterCount ? ' '+root.workspace.activeFilterCount : '')))
                        quiet:true;selected:root.workspace.filtersExpanded
                        onClicked:root.workspace.setFiltersExpanded(!root.workspace.filtersExpanded)
                    }
                    StudioButton {
                        objectName:'librarySourcesToggle';text:qsTr(String('来源'));quiet:true;selected:root.workspace.sourcesExpanded
                        onClicked:root.workspace.setSourcesExpanded(!root.workspace.sourcesExpanded)
                    }
                    StudioButton {
                        id: sortButton
                        text: qsTr(String('排序')); quiet: true; onClicked: sortMenu.open()
                        LibraryMenu {
                            id: sortMenu; y: parent.height + 4; x: parent.width - width
                            LibraryOption { text: qsTr(String('拍摄时间')); onTriggered: root.workspace.setSort('captured', false) }
                            LibraryOption { text: qsTr(String('文件名')); onTriggered: root.workspace.setSort('name', false) }
                            LibraryOption { text: qsTr(String('最近加入')); onTriggered: root.workspace.setSort('added', true) }
                        }
                    }
                    StudioButton { text: qsTr(String('加入照片')); primary: true; enabled: !root.workspace.busy; onClicked: root.workspace.chooseAddPhotos() }
                }

                RowLayout {
                    Layout.fillWidth: true; spacing: 8
                    MinchoText {
                        text: qsTr(String(root.workspace.selectedCount ? '已选 ' + root.workspace.selectedCount + ' 张' : root.workspace.total + ' 张照片'))
                        font.pixelSize: Theme.caption; color: Theme.secondary; Layout.fillWidth: true
                    }
                    StudioButton { text: qsTr(String('选择本页')); quiet: true; implicitHeight: 32; enabled: root.workspace.images.length > 0; onClicked: root.workspace.selectPage() }
                    StudioButton {objectName:'libraryInfoToggle';text:qsTr(String('信息'));quiet:true;implicitHeight:32;selected:root.infoExpanded;enabled:root.workspace.selectedCount>0;onClicked:root.infoExpanded=!root.infoExpanded}
                    StudioButton {
                        text: qsTr(String('加入相册')); quiet: true; implicitHeight: 32; enabled: root.workspace.selectedCount > 0 && root.workspace.albums.length > 0
                        onClicked: albumsMenu.open()
                        LibraryMenu {
                            id: albumsMenu; y: parent.height + 4
                            Instantiator {
                                model: root.workspace.albums
                                delegate: LibraryOption { required property var modelData; text: qsTr(String(modelData.title)); onTriggered: root.workspace.addSelectedToAlbum(modelData.uuid) }
                                onObjectAdded: function(index, object) { albumsMenu.insertItem(index, object) }
                                onObjectRemoved: function(index, object) { albumsMenu.removeItem(object) }
                            }
                        }
                    }
                    StudioButton {
                        text: qsTr(String('移出相册')); quiet: true; implicitHeight: 32; visible: root.workspace.canRemoveFromAlbum
                        enabled: root.workspace.selectedCount > 0; onClicked: root.workspace.removeSelectedFromAlbum()
                    }
                    StudioButton { text: qsTr(String('新建变体')); quiet: true; implicitHeight: 32; enabled: root.workspace.selectedCount === 1; onClicked: root.workspace.createVariant() }
                    StudioButton {
                        text: qsTr(String('选片')); quiet: true; implicitHeight: 32; enabled: root.workspace.selectedCount > 0
                        onClicked: selectionMenu.open()
                        LibraryMenu {
                            id: selectionMenu; y: parent.height + 4
                            LibraryOption { text: qsTr(String('留用')); onTriggered: root.workspace.setSelectedRetained(true) }
                            LibraryOption { text: qsTr(String('暂不留用')); onTriggered: root.workspace.setSelectedRetained(false) }
                            LibraryOption { text: qsTr(String('移至 Selects')); visible: root.workspace.kind === 'session'; height: visible ? implicitHeight : 0; enabled: visible; onTriggered: root.workspace.moveSelected('selects') }
                            LibraryOption { text: qsTr(String('还原原位置')); visible: root.workspace.kind === 'session'; height: visible ? implicitHeight : 0; enabled: visible; onTriggered: root.workspace.restoreSelected() }
                        }
                    }
                }

                Item {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    GridView {
                        id: grid; objectName: 'libraryImages'
                        anchors.fill: parent; anchors.rightMargin:info.visible ? info.width+24 : 12;clip: true
                        cellWidth: width / Math.max(2, Math.floor(width / 192)); cellHeight: 202
                        model: root.workspace.images
                        ScrollBar.vertical: ScrollBar { width: 10 }
                        delegate: Item {
                            id: photoCell
                            required property var modelData
                            width: grid.cellWidth; height: grid.cellHeight
                            readonly property bool selected: root.workspace.selectedImages.indexOf(modelData.uuid) >= 0
                            Rectangle {
                                anchors.fill: parent; anchors.rightMargin: 12; anchors.bottomMargin: 12
                                radius: 5; color: photoCell.selected ? Theme.selection : hover.hovered ? Theme.hover : 'transparent'
                                border.width: photoCell.selected ? 1 : 0; border.color: Theme.accentInk
                                ColumnLayout {
                                    anchors.fill: parent; anchors.margins: 8; spacing: 7
                                    Item {
                                        Layout.fillWidth: true; Layout.preferredHeight: 116
                                        Image {
                                            id: thumbnail; anchors.fill: parent; asynchronous: true
                                            source: photoCell.modelData.thumbnail || ''; fillMode: Image.PreserveAspectFit
                                            sourceSize.width: 320; sourceSize.height: 240
                                            Accessible.name: qsTr(String(photoCell.modelData.file_name))
                                        }
                                        MinchoText {
                                            anchors.centerIn: parent; text: qsTr(String(photoCell.modelData.kind === 'raw' ? 'RAW' : '照片'))
                                            visible: thumbnail.status !== Image.Ready; color: Theme.muted; font.pixelSize: Theme.caption
                                        }
                                    }
                                    MinchoText { text: qsTr(String(photoCell.modelData.file_name)); Layout.fillWidth: true; elide: Text.ElideRight; font.pixelSize: Theme.caption }
                                    RowLayout {
                                        Layout.fillWidth: true; spacing: 5
                                        MinchoText {
                                            text: qsTr(String(photoCell.modelData.width && photoCell.modelData.height ? photoCell.modelData.width + ' × ' + photoCell.modelData.height : photoCell.modelData.file_name.split('.').pop().toUpperCase()))
                                            color: Theme.secondary; font.pixelSize: 12; Layout.fillWidth: true
                                        }
                                        Repeater {
                                            model: photoCell.modelData.variants || []
                                            delegate: StudioButton {
                                                required property var modelData
                                                required property int index
                                                text: qsTr(String(String(index + 1))); quiet: true; implicitHeight: 24; implicitWidth: 26
                                                selected: root.workspace.activeVariant === modelData.uuid
                                                Accessible.name: qsTr(String('编辑变体 ' + (index + 1)))
                                                onClicked: root.workspace.activateVariant(photoCell.modelData.uuid, modelData.uuid)
                                            }
                                        }
                                    }
                                }
                            }
                            HoverHandler { id: hover }
                            TapHandler {
                                acceptedButtons: Qt.LeftButton; acceptedModifiers: Qt.NoModifier
                                onTapped: root.workspace.selectImage(photoCell.modelData.uuid, false)
                                onDoubleTapped: root.workspace.activateVariant(photoCell.modelData.uuid, '')
                            }
                            TapHandler { acceptedButtons: Qt.LeftButton; acceptedModifiers: Qt.ControlModifier; onTapped: root.workspace.selectImage(photoCell.modelData.uuid, true) }
                        }
                    }
                    LibraryInfo {
                        id:info;objectName:'libraryPhotoInfo';anchors.top:parent.top;anchors.right:parent.right;anchors.bottom:parent.bottom
                        width:Math.min(256,parent.width*.29);visible:root.infoExpanded && root.workspace.selectedCount>0
                        info:root.workspace.photoInfo
                    }
                    ColumnLayout {
                        anchors.centerIn: parent; spacing: 16; visible: !root.workspace.busy && root.workspace.images.length === 0
                        MinchoText { text: qsTr(String(root.workspace.hasFilters ? '没有匹配的照片' : '此处还没有照片')); color: Theme.secondary; Layout.alignment: Qt.AlignHCenter }
                        StudioButton { text: qsTr(String('清除筛选')); visible:root.workspace.hasFilters;Layout.alignment:Qt.AlignHCenter;onClicked:root.workspace.clearFilters() }
                        StudioButton { text: qsTr(String('选择照片')); visible: !root.workspace.hasFilters;Layout.alignment:Qt.AlignHCenter;onClicked: root.workspace.chooseAddPhotos() }
                    }
                    Rectangle {
                        anchors.fill: parent; color: Theme.selection; opacity: .85; radius: 8
                        visible: photoDrop.containsDrag
                        MinchoText { anchors.centerIn: parent; text: qsTr(String('加入照片')); color: Theme.accentInk; font.pixelSize: Theme.heading }
                    }
                    DropArea {
                        id: photoDrop; anchors.fill: parent
                        onEntered: function(drag) { drag.accepted = drag.hasUrls }
                        onDropped: function(drop) { if (drop.hasUrls) { root.workspace.addPaths(drop.urls, false); drop.acceptProposedAction() } }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true; spacing: 12
                    MinchoText {
                        text: qsTr(String(root.workspace.busy ? '正在读取…' : root.workspace.saving ? '正在保存调整…' : root.workspace.total ? (root.workspace.offset + 1) + '–' + Math.min(root.workspace.offset + root.workspace.pageSize, root.workspace.total) + ' / ' + root.workspace.total : '0 张'))
                        color: Theme.secondary; font.pixelSize: Theme.caption; Layout.fillWidth: true
                    }
                    StudioButton { text: qsTr(String('上一页')); quiet: true; enabled: root.workspace.offset > 0 && !root.workspace.busy; onClicked: root.workspace.setPage(Math.floor(root.workspace.offset / root.workspace.pageSize) - 1) }
                    StudioButton { text: qsTr(String('下一页')); quiet: true; enabled: root.workspace.offset + root.workspace.pageSize < root.workspace.total && !root.workspace.busy; onClicked: root.workspace.setPage(Math.floor(root.workspace.offset / root.workspace.pageSize) + 1) }
                    StudioButton { text: qsTr(String('编辑所选')); enabled: root.workspace.selectedCount === 1 && !root.workspace.busy; onClicked: root.workspace.editSelected() }
                }
            }
        }
    }

    LibraryMenu {
        id: collectionMenu
        LibraryOption { text: qsTr(String('重命名')); onTriggered: { root.renameExisting = true; albumDialog.open() } }
        LibraryOption { text: qsTr(String('删除空相册')); onTriggered: root.workspace.deleteCollection(root.collectionForRename) }
    }
    StudioDialog {
        id: albumDialog; anchors.centerIn: parent; width: Math.min(400, root.width - 64)
        contentItem: ColumnLayout {
            spacing: 20
            MinchoText { text: qsTr(String(root.renameExisting ? '重命名相册' : '新建相册')); font.pixelSize: Theme.heading }
            LibraryField { id: albumName; Layout.fillWidth: true; placeholderText: qsTr(String('相册名称')); selectByMouse: true; Accessible.name: qsTr(String('相册名称')); onAccepted: saveAlbum.clicked() }
            RowLayout {
                Layout.fillWidth: true; spacing: 12
                Item { Layout.fillWidth: true }
                StudioButton { text: qsTr(String('取消')); quiet: true; onClicked: albumDialog.close() }
                StudioButton {
                    id: saveAlbum; text: qsTr(String('保存')); primary: true; enabled: albumName.text.trim().length > 0
                    onClicked: {
                        if (!enabled) return
                        if (root.renameExisting) root.workspace.renameCollection(root.collectionForRename, albumName.text)
                        else root.workspace.createAlbum(albumName.text)
                        albumDialog.close()
                    }
                }
            }
        }
        onOpened: albumName.forceActiveFocus()
    }
}
