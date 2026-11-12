import QtQuick
import QtQuick.Window
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Effects
import QtCore
import 'components'

ApplicationWindow {
    id: window
    width: 1480; height: 960
    minimumWidth: 1120; minimumHeight: 760
    visible: false
    title: qsTr(String('SpektraFilm · 光影暗房'))
    color: 'transparent'
    flags: Qt.Window | Qt.FramelessWindowHint
    font.family: Theme.family
    font.pixelSize: Theme.body
    property bool toolsVisible:true
    property bool stripVisible:true
    property real sidebarWidth:380
    property bool cropping:false
    property string workspaceMode:'edit'
    property bool importReturnPending:false
    property string importReturnPreviousPath:''
    property string toastSource:''
    property bool quickLibrary:true
    property bool closeApproved:false
    Component.onCompleted: if(ctrl.pendingBatchRecovery) Qt.callLater(function(){batchRecoveryDialog.open()})
    onClosing:function(event){if(!closeApproved){event.accepted=false;ctrl.libraryWorkspace.prepareToClose()}}
    Connections {
        target:ctrl.libraryWorkspace
        function onCloseReady(){window.closeApproved=true;Qt.callLater(function(){window.close()})}
        function onQuickSessionRequested(){window.quickLibrary=true;window.setWorkspace('library')}
    }
    Connections {target:ctrl;function onLibraryPhotoOpened(){window.setWorkspace('edit')}}
    Connections {target:ctrl;function onImportWorkspaceRequested(){window.importReturnPreviousPath=ctrl.currentPath;window.setWorkspace('import')}}
    Connections {target:ctrl;function onFrameChanged(){window.finishImportWhenReady()}function onStateChanged(){window.finishImportWhenReady()}}
    Connections {target:ctrl.importWorkspace;function onImported(count){if(count>0){window.importReturnPending=true;window.finishImportWhenReady()}}}
    function finishImportWhenReady() {
        if(!window.importReturnPending || ctrl.currentIndex<0 || ctrl.currentPath===window.importReturnPreviousPath)return
        if(!ctrl.frame.length && ctrl.status.indexOf('失败')<0)return
        window.importReturnPending=false
        window.setWorkspace('edit')
    }
    function setWorkspace(mode) {
        if(mode!=='import')window.importReturnPending=false
        if(window.cropping)window.cancelCrop();viewport.finishStroke()
        workspaceMode=mode
        if(mode==='develop')editorTools.task='film'
        if(mode==='edit' && editorTools.task==='film')editorTools.task='basic'
        window.toolsVisible=true
    }
    property alias activeTask:editorTools.task
    Settings {
        category:'editorWorkspace'
        property alias toolWidth:window.sidebarWidth
        property alias toolsExpanded:window.toolsVisible
        property alias photosExpanded:window.stripVisible
        property alias selectedTask:editorTools.task
    }
    property bool comparing: false
    property real comparePosition: .5
    onComparingChanged: { if (comparing) { viewport.finishStroke();comparePosition = .5; } }
    property alias actualSize: viewport.actualSize
    onActualSizeChanged:if(!window.cropping)ctrl.setActualSize(actualSize)
    property string filterText: ''
    property string filmCategory: '全部'
    readonly property var filmCategories: {
        var result=['全部'];
        for(var i=0;i<ctrl.stocks.length;i++) if(ctrl.stocks[i].maker && result.indexOf(ctrl.stocks[i].maker)<0) result.push(ctrl.stocks[i].maker);
        result.push('电影');result.push('黑白');return result;
    }
    readonly property var filteredStocks: {
        var result=[];
        for(var i=0;i<ctrl.stocks.length;i++) {
            var item=ctrl.stocks[i];
            var categoryMatch=filmCategory==='全部' || filmCategory===item.maker || (filmCategory==='电影' && item.category==='cinema') || (filmCategory==='黑白' && item.type==='bw');
            if(categoryMatch && (item.name+' '+item.maker+' '+item.description+' '+item.id).toLowerCase().indexOf(filterText)>=0) result.push(item);
        }
        return result;
    }
    readonly property bool maximized: visibility===Window.Maximized || visibility===Window.FullScreen
    signal restoreRequested()
    function toggleMaximize() { if(maximized) restoreRequested(); else showMaximized() }
    readonly property var stock: {
        for(var i=0;i<ctrl.stocks.length;i++) if(ctrl.stocks[i].id===ctrl.parameters.stock) return ctrl.stocks[i];
        return {name:'选择胶片',maker:'',description:'',type:'negative'};
    }

    Shortcut { sequence: 'Ctrl+O'; onActivated: ctrl.importPhotos() }
    readonly property bool editingText: !!(activeFocusItem && activeFocusItem.selectByMouse!==undefined)
    readonly property bool modalActive:library.opened || exportDialog.opened || aboutDialog.opened || styleLibrary.opened || settingsPanel.opened || syncDialog.opened || outputRecipeDialog.opened || compositionDialog.opened || batchRecoveryDialog.opened
    Shortcut { sequence: 'Ctrl+V'; enabled: !window.editingText && !ctrl.exporting; onActivated: ctrl.pastePhotos() }
    Shortcut { sequence: 'Ctrl+A'; enabled: !window.editingText && !ctrl.exporting; onActivated: ctrl.selectAllPhotos() }
    Shortcut { objectName:'exportShortcut';sequence: 'Ctrl+E'; enabled: ctrl.canStartExport && !window.cropping && !window.modalActive; onActivated: exportDialog.open() }
    Shortcut { objectName:'undoShortcut';sequence: 'Ctrl+Z'; enabled: !window.editingText && !window.cropping && !window.modalActive && ctrl.canUndo; onActivated: ctrl.undo() }
    Shortcut { objectName:'redoShiftShortcut';sequence: 'Ctrl+Shift+Z'; enabled: !window.editingText && !window.cropping && !window.modalActive && ctrl.canRedo; onActivated: ctrl.redo() }
    Shortcut { objectName:'redoShortcut';sequence: 'Ctrl+Y'; enabled: !window.editingText && !window.cropping && !window.modalActive && ctrl.canRedo; onActivated: ctrl.redo() }
    Shortcut { objectName:'zoomFitShortcut';sequence: 'Ctrl+0'; enabled: ctrl.currentIndex>=0 && !window.cropping; onActivated: viewport.fit() }
    Shortcut { objectName:'zoom100Shortcut';sequence: 'Ctrl+1'; enabled: ctrl.currentIndex>=0 && !window.cropping; onActivated: viewport.setZoom(1) }
    Shortcut { objectName:'zoom200Shortcut';sequence: 'Ctrl+2'; enabled: ctrl.currentIndex>=0 && !window.cropping; onActivated: viewport.setZoom(2) }
    Shortcut { objectName:'zoomInShortcut';sequence: 'Ctrl++'; enabled: ctrl.currentIndex>=0 && !window.cropping; onActivated: viewport.stepZoom(1) }
    Shortcut { objectName:'zoomOutShortcut';sequence: 'Ctrl+-'; enabled: ctrl.currentIndex>=0 && !window.cropping; onActivated: viewport.stepZoom(-1) }
    Shortcut { sequence: 'Delete'; enabled: !window.editingText && !viewport.maskEditing && !(window.activeFocusItem && window.activeFocusItem.objectName==='curveGraph') && ctrl.currentIndex>=0 && !ctrl.exporting && !window.modalActive && !window.cropping; onActivated: ctrl.removeSelectedPhotos() }
    Connections { target: ctrl; function onPhotosChanged() { var key=ctrl.currentPath; if(window.activePhotoKey!==key) {if(window.cropping)window.cancelCrop();window.activePhotoKey=key;viewport.reset() } } }
    property string activePhotoKey: ''
    Shortcut { objectName:'compareShortcut';sequence: 'B'; enabled: !window.editingText && ctrl.frame.length>0 && !window.cropping; onActivated: window.comparing=!window.comparing }
    function openCrop() {
        if(window.cropping)return
        if(ctrl.currentIndex>=0 && !ctrl.exporting && ctrl.requestCropPreview()) {
            window.comparing=false;viewport.finishStroke();viewport.beginCropView(ctrl.cropBounds);window.cropping=true
        }
    }
    function cancelCrop() {window.cropping=false;viewport.endCropView(true);Qt.callLater(function(){ctrl.setActualSize(viewport.actualSize)})}
    function applyCrop() {if(!ctrl.cropBusy && viewport.hasImage){var bounds=viewport.cropTool.draft.slice();window.cropping=false;ctrl.applyCrop(bounds);viewport.endCropView(false);Qt.callLater(function(){ctrl.setActualSize(viewport.actualSize)})}}
    Shortcut {sequence:'Escape';enabled:window.cropping;onActivated:window.cancelCrop()}
    Shortcut {sequence:'Return';enabled:window.cropping;onActivated:window.applyCrop()}
    Shortcut {sequence:'Enter';enabled:window.cropping;onActivated:window.applyCrop()}
    Shortcut {sequence:'Tab';enabled:!window.editingText && !window.cropping && !window.modalActive;onActivated:window.toolsVisible=!window.toolsVisible}
    Shortcut {objectName:'zoomToggleShortcut';sequence:'Z';enabled:!window.editingText && ctrl.currentIndex>=0 && !window.cropping && !window.modalActive;onActivated:{if(window.actualSize)viewport.fit();else viewport.setZoom(1)}}
    Shortcut { objectName:'cropShortcut';sequence: 'C'; enabled: !window.editingText && ctrl.currentIndex>=0 && !ctrl.exporting && !library.opened && !exportDialog.opened && !window.cropping; onActivated: window.openCrop() }
    DropArea {
        id: importDrop
        anchors.fill: parent; z: 100
        onEntered: function(drag) { drag.accepted=drag.hasUrls && !ctrl.exporting }
        onDropped: function(drop) { if(drop.hasUrls && !ctrl.exporting) { ctrl.dropPhotos(drop.urls); drop.acceptProposedAction() } }
    }
    Rectangle {
        anchors.fill: parent; anchors.margins: 7; z: 101; radius: window.maximized ? 4 : 10
        visible: importDrop.containsDrag; color: '#18667C65'; border.width: 2; border.color: Theme.accent
    }

    Rectangle {
        id: cornerMask; anchors.fill: parent; radius: window.maximized ? 0 : 16
        color: '#FFFFFF'; visible: false; layer.enabled: true
    }
    Item {
        anchors.fill: parent
        layer.enabled: true
        layer.effect: MultiEffect { maskEnabled: true; maskSource: cornerMask; maskThresholdMin: .5; maskSpreadAtMin: 1 }
        Rectangle { anchors.fill: parent; color: Theme.workspace }
        Rectangle {width:parent.width;height:78;color:Theme.surface}
        ColumnLayout {
        anchors.fill: parent; spacing: 0
        Item {
            Layout.fillWidth: true; Layout.preferredHeight: 34
            MouseArea {
                anchors.fill: parent; acceptedButtons: Qt.LeftButton
                onPressed: window.startSystemMove()
                onDoubleClicked: window.toggleMaximize()
            }
            StudioButton {
                id:appearanceToggle;objectName:'toggleAppearanceButton'
                anchors.left:parent.left;anchors.leftMargin:12;anchors.verticalCenter:parent.verticalCenter
                implicitWidth:30;implicitHeight:30;quiet:true
                checkable:true;checked:Theme.dark
                Accessible.name:qsTr(Theme.dark ? '切换浅色模式' : '切换深色模式')
                Accessible.description:qsTr(Theme.dark ? '当前为深色模式' : '当前为浅色模式')
                ToolTip.visible:hovered && !down;ToolTip.delay:600;ToolTip.text:Accessible.name
                contentItem:Item {
                    VectorIcon {
                        anchors.centerIn:parent;width:15;height:15;name:'moon';opacity:Theme.dark ? 0 : 1
                        Behavior on opacity {NumberAnimation {duration:Theme.fast}}
                    }
                    VectorIcon {
                        anchors.centerIn:parent;width:15;height:15;name:'sun';opacity:Theme.dark ? 1 : 0
                        Behavior on opacity {NumberAnimation {duration:Theme.fast}}
                    }
                }
                onClicked:ctrl.updatePreference('appearance',Theme.dark ? 'light' : 'dark')
            }
            Row {
                objectName: 'windowControls'
                anchors.right: parent.right; anchors.rightMargin: 13
                anchors.verticalCenter: parent.verticalCenter; spacing: 0
                WindowDot { dotColor: '#FFBD2E'; windowAction: 'minimize'; Accessible.name: qsTr(String('最小化窗口')); onClicked: window.showMinimized() }
                WindowDot { dotColor: '#28C840'; windowAction: 'maximize'; restoreIcon: window.maximized; Accessible.name: qsTr(String(window.maximized ? '还原窗口' : '最大化窗口')); onClicked: window.toggleMaximize() }
                WindowDot { dotColor: '#FF6058'; windowAction: 'close'; Accessible.name: qsTr(String('关闭窗口')); onClicked: window.close() }
            }
        }
        Item {
            Layout.fillWidth: true; Layout.preferredHeight: 44
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 28; anchors.rightMargin: 28; spacing: 16
                MinchoText {
                    text: 'SpektraFilm'; displayRole: true; font.pixelSize: 26; font.weight: Font.Normal; font.letterSpacing: -.8
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: aboutDialog.open() }
                    Accessible.name: qsTr(String('关于 SpektraFilm'))
                }
                Item { Layout.fillWidth: true }
                StudioButton {objectName:'openImportWorkspaceButton';text:qsTr(String('导入'));quiet:true;visible:ctrl.currentIndex>=0;selected:window.workspaceMode==='import';enabled:!ctrl.exporting;onClicked:ctrl.importPhotos()}
                StudioButton {objectName:'openGalleryButton';text:qsTr(String('图库'));quiet:true;selected:window.workspaceMode==='library';enabled:!ctrl.exporting;onClicked:{window.quickLibrary=true;window.setWorkspace(window.workspaceMode==='library' ? 'edit' : 'library')}}
                StudioButton {objectName:'openCompositionButton';text:qsTr(String('排版'));quiet:true;visible:ctrl.currentIndex>=0;enabled:!ctrl.exporting;onClicked:if(ctrl.prepareComposition())compositionDialog.open()}
                StudioButton {
                    objectName:'openSettingsButton';quiet:true;implicitWidth:40;implicitHeight:40
                    Accessible.name:qsTr(String('设置'));ToolTip.visible:hovered || visualFocus;ToolTip.delay:500;ToolTip.text:qsTr(String('设置'))
                    contentItem:Item {SettingsIcon {anchors.centerIn:parent}}
                    onClicked:settingsPanel.open()
                }
                StudioButton {
                    id: exportButton
                    objectName:'exportActionButton'
            text: qsTr(String(ctrl.exporting ? '导出中…' : ctrl.selectedCount>1 ? '导出 '+ctrl.selectedCount+' 张' : '导出'))
                    primary: true; implicitWidth: 104; implicitHeight: 42
                    opacity: 1
                    enabled: ctrl.canStartExport && !window.cropping
                    Accessible.name: qsTr(String('导出作品'))
                    Accessible.description: qsTr(String(ctrl.currentIndex<0 ? '导入照片后即可导出作品' : '选择格式与目标文件夹；每张使用各自的参数'))
                    contentItem: MinchoText {
                        text: qsTr(String(exportButton.text))
                        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                        font.pixelSize: Theme.body; font.weight: Theme.bodyWeight
                        color: exportButton.enabled ? Theme.buttonInk : Theme.secondary
                    }
                    background: Rectangle {
                        radius: 4
                        color: exportButton.enabled ? (exportButton.down ? Theme.buttonPressed : exportButton.hovered ? Theme.buttonHover : Theme.buttonSurface) : Theme.disabled
                        border.width: exportButton.activeFocus ? 2 : 1
                        border.color: exportButton.activeFocus ? Theme.accent : (exportButton.enabled ? Theme.buttonSurface : Theme.border)
                    }
                    onClicked: exportDialog.open()
                }
            }
        }
        RowLayout {
            visible:window.workspaceMode==='edit' || window.workspaceMode==='develop'
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 0
            Layout.leftMargin:12;Layout.rightMargin:12;Layout.topMargin:10;Layout.bottomMargin:12
            Item {
            Layout.fillWidth:true;Layout.fillHeight:true
            ShadowSurface {anchors.fill:parent;elevation:0;cornerRadius:10;color:Theme.canvas}
            ColumnLayout {
                anchors.fill:parent;spacing:0
                Rectangle {
                    Layout.fillWidth: true; height: 48; color:'transparent'
                    RowLayout {
                        anchors.fill: parent; anchors.leftMargin: 28; anchors.rightMargin: 20; spacing: 12
                        MinchoText { text: qsTr(String(ctrl.filename)); color: Theme.secondary; font.pixelSize: Theme.caption; elide: Text.ElideMiddle; Layout.fillWidth: true; visible:ctrl.currentIndex>=0 }
                        MinchoText { text: qsTr(String(ctrl.dimensions)); font.pixelSize: Theme.caption; color: Theme.muted; visible: ctrl.currentIndex>=0 }
                        StudioButton {
                            objectName:'cropPhotoButton';text:qsTr(String('裁切'));iconName:'crop';quiet:true;implicitHeight:30
                            visible:ctrl.currentIndex>=0;enabled:!ctrl.exporting;selected:window.cropping
                            Accessible.description:qsTr(String('C 键打开裁切；可拖动范围并选择 XPan 等画幅'))
                            ToolTip.visible:hovered || visualFocus;ToolTip.delay:600;ToolTip.text:qsTr(String('裁切 · C'))
                            onClicked:window.openCrop()
                        }
                        StudioButton {
                            objectName: 'compareToggle'
                            text: qsTr(String(comparing ? '退出对比' : '原图对比'))
                            quiet: true; implicitHeight: 30
                            checkable: true; checked: window.comparing
                            visible:ctrl.currentIndex>=0;enabled: ctrl.frame.length>0 && !window.cropping
                            Accessible.description: qsTr(String('B 键切换原图对比；对比时拖动分界线，双击居中'))
                            background: Rectangle {
                                radius: 4
                                color: window.comparing ? Theme.selection : (parent.hovered ? Theme.hover : 'transparent')
                                border.width: parent.visualFocus ? 1 : 0
                                border.color: Theme.accent
                            }
                            onClicked: window.comparing=!window.comparing
                        }
                    }
                }
                CropToolbar {
                    Layout.fillWidth:true;Layout.leftMargin:28;Layout.rightMargin:20;Layout.preferredHeight:48
                    visible:window.cropping;cropTool:viewport.cropTool;ready:viewport.hasImage && !ctrl.cropBusy
                    onApplyRequested:window.applyCrop();onCancelRequested:window.cancelCrop()
                }
                Rectangle {
                    id: stage; Layout.fillWidth: true; Layout.fillHeight: true; color: Theme.canvas
                    Item {
                        id: photoArea; anchors.fill: parent; anchors.leftMargin: 28; anchors.rightMargin: 28; anchors.topMargin: 12; anchors.bottomMargin: 24
                        PhotoViewport {
                            id: viewport; objectName: 'photoViewport'; anchors.fill: parent
                            source: window.cropping ? ctrl.cropSource : ctrl.frame; originalSource: ctrl.original
                            pixelWidth:window.cropping ? ctrl.cropSourceDimensions[0] : ctrl.imageWidth
                            pixelHeight:window.cropping ? ctrl.cropSourceDimensions[1] : ctrl.imageHeight
                            sourcePixelWidth:ctrl.sourceDimensions[0];sourcePixelHeight:ctrl.sourceDimensions[1]
                            geometryForward:ctrl.geometryForward;geometryInverse:ctrl.geometryInverse
                            cropping:window.cropping
                            maskEditing:window.toolsVisible && editorTools.task==='local' && !window.cropping
                            activeMask:ctrl.activeMaskGuide
                            maskOverlaySource:ctrl.maskOverlaySource
                            maskOverlayOpacity:editorTools.maskTools.overlayOpacity
                            maskOverlayColor:editorTools.maskTools.overlayColor==='cyan' ? '#55BFC7' : '#D96B62'
                            brushRadius:editorTools.maskTools.brushRadius;brushFeather:editorTools.maskTools.brushFeather
                            brushFlow:editorTools.maskTools.brushFlow;brushErase:editorTools.maskTools.erasing
                            showMaskOverlay:editorTools.maskTools.showOverlay
                            suppressMaskOverlay:editorTools.maskTools.overlaySuppressed
                            comparing: window.comparing; comparePosition: window.comparePosition
                            photoKey: window.activePhotoKey
                            onPositionRequested: function(value) { window.comparePosition=value }
                        }
                        Navigator {
                            viewport:viewport;anchors.right:parent.right;anchors.bottom:parent.bottom
                            width:176;height:132;visible:viewport.actualSize && !window.cropping && !viewport.guiding
                        }
                        Item {
                            id: comparisonLegend; objectName: 'comparisonLegend'
                            visible: window.comparing && viewport.hasImage
                            x: Math.max(0,viewport.imageX)
                            y: Math.min(viewport.height,viewport.imageY+viewport.imageHeight)+6
                            width: viewport.visibleWidth; height: 18
                            MinchoText {
                                anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
                                width: Math.max(0, parent.width / 2 - 12); elide: Text.ElideRight
                                text: qsTr(String('原图')); font.pixelSize: Theme.caption; color: Theme.secondary
                            }
                            MinchoText {
                                anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                                width: Math.max(0, parent.width / 2 - 12); elide: Text.ElideRight
                                horizontalAlignment: Text.AlignRight
                                text: qsTr(String(ctrl.parameters.film_enabled ? window.stock.name : '编辑结果')); font.pixelSize: Theme.caption; color: Theme.secondary
                            }
                        }
                        MinchoText {
                            anchors.centerIn:parent;visible:window.cropping && ctrl.cropBusy
                            text:qsTr(String('正在准备画幅…'));font.pixelSize:Theme.caption;color:Theme.secondary
                        }
                        Column {
                            anchors.centerIn: parent; anchors.verticalCenterOffset: -12; spacing: 22; visible: ctrl.currentIndex<0
                            Item { width: 48; height: 48; anchors.horizontalCenter: parent.horizontalCenter
                                Rectangle { anchors.fill: parent; color: 'transparent'; border.width: 1; border.color: Theme.border; radius: 2 }
                                VectorIcon { anchors.centerIn: parent; name: 'plus'; width: 18; height: 18 }
                            }
                            MinchoText { anchors.horizontalCenter: parent.horizontalCenter; text: qsTr(String('将照片拖入此处，或选择本地文件')); font.pixelSize: Theme.body; color: Theme.secondary }
                            StudioButton { objectName: 'emptyImportButton'; anchors.horizontalCenter: parent.horizontalCenter; text: qsTr(String('选择照片')); primary: true; implicitWidth: 132; implicitHeight: 42; onClicked: ctrl.importPhotos() }
                        }
                    }
                }
                Rectangle {
                    Layout.fillWidth: true; height: 41; color:'transparent'
                    RowLayout {
                        anchors.fill: parent; anchors.leftMargin: 36; anchors.rightMargin: 25; spacing: 14
                        Rectangle { width: 4; height: 4; radius: 2; visible: ctrl.busy || ctrl.status.indexOf('失败')>=0; color: Theme.accentInk }
                        MinchoText {
                            visible: ctrl.busy || ctrl.status.indexOf('失败')>=0
                            text: qsTr(String(window.actualSize && ctrl.currentIndex>=0 && !ctrl.detailReady && ctrl.status.indexOf('失败')<0 ? '正在加载原始细节…' : ctrl.status.indexOf('失败')>=0 || ctrl.status.indexOf('正在')===0 ? ctrl.status : '正在显影…'))
                            font.pixelSize: Theme.caption; color: Theme.secondary; Layout.fillWidth: true; elide: Text.ElideRight; maximumLineCount: 1
                        }
                        Item { Layout.fillWidth:true; visible: !ctrl.busy && ctrl.status.indexOf('失败')<0 }
                        StudioButton { text: qsTr(String('重试')); visible: ctrl.status.indexOf('失败')>=0; quiet: true; height: 28; onClicked: ctrl.retry() }
                        StudioButton { text: qsTr(String('停止批量')); visible: ctrl.exporting && ctrl.batchTotal>0; quiet: true; implicitHeight: 28; onClicked: ctrl.cancelBatchExport() }
                        TextField {
                            id:zoomValue;objectName:'zoomPercentage';visible:ctrl.currentIndex>=0
                            implicitWidth:64;implicitHeight:28;rightPadding:17;leftPadding:4
                            text:qsTr(String(Math.round(viewport.effectiveRatio*100).toString()))
                            font.family:Theme.family;font.pixelSize:Theme.caption;font.features:{'tnum':1};font.hintingPreference:Font.PreferVerticalHinting
                            renderType:TextInput.QtRendering;color:Theme.secondary;horizontalAlignment:Text.AlignRight;selectByMouse:true
                            validator:DoubleValidator {bottom:5;top:800;decimals:1;locale:'en_US'}
                            Accessible.name:qsTr(String('预览缩放百分比'));Accessible.description:qsTr(String('输入 5 至 800，100% 对应原始像素；不改变导出尺寸'))
                            onEditingFinished:{if(acceptableInput)viewport.setZoom(Number(text)/100);focus=false}
                            onActiveFocusChanged:if(!activeFocus)text=Math.round(viewport.effectiveRatio*100).toString()
                            background:Rectangle {radius:3;color:zoomValue.activeFocus ? Theme.surface : 'transparent';border.width:zoomValue.visualFocus ? 1 : 0;border.color:Theme.accent}
                            MinchoText {anchors.right:parent.right;anchors.verticalCenter:parent.verticalCenter;text:'%';font.pixelSize:Theme.caption;color:Theme.secondary}
                            Connections {target:viewport;function onEffectiveRatioChanged(){if(!zoomValue.activeFocus)zoomValue.text=Math.round(viewport.effectiveRatio*100).toString()}}
                        }
                        Rectangle {
                            objectName: 'zoomControl'; Layout.preferredWidth: 174; Layout.preferredHeight: 28; visible:ctrl.currentIndex>=0
                            radius: 4; color: Theme.rule; border.width: 1; border.color: Theme.border
                            Row {
                                anchors.fill: parent; anchors.margins: 2; spacing: 2
                                Repeater {
                                    model: ['适合','100%','200%']
                                    delegate: Button {
                                        required property string modelData; required property int index
                                        width: 56; height: 24; padding: 0; hoverEnabled: true
                                        enabled: ctrl.frame.length>0
                                        readonly property bool chosen: index===0 ? !window.actualSize : window.actualSize && Math.abs(viewport.zoomRatio-index)<.001
                                        Accessible.name: qsTr(String(index===0 ? '缩放以适合窗口' : index===1 ? '原始像素一比一查看' : '放大至百分之二百，不增加原片细节'))
                                        contentItem: MinchoText { text: qsTr(String(modelData)); font.pixelSize: Theme.caption; color: parent.chosen ? Theme.ink : Theme.secondary; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                                        background: Rectangle { radius: 3; color: parent.chosen ? Theme.surface : parent.hovered ? Theme.hover : 'transparent'; border.width: parent.visualFocus ? 1 : 0; border.color: Theme.accent }
                                        onClicked: { if(index===0) viewport.fit();else viewport.setZoom(index) }
                                    }
                                }
                            }
                        }
                    }
                }
                Item {
                    id:photoStrip;objectName: 'photoStrip'
                    Layout.fillWidth: true; Layout.preferredHeight: 112
                    visible: ctrl.photoCount>0 && window.stripVisible && window.workspaceMode!=='library'
                    ShadowSurface {anchors.fill:parent;elevation:1;cornerRadius:10;color:Theme.panelFooter}
                    RowLayout {
                        anchors.fill: parent; anchors.margins: 18; spacing: 19
                        Column { Layout.preferredWidth: 95; spacing: 7
                            MinchoText { text: qsTr(String('照片')); font.pixelSize: Theme.body }
                            MinchoText { text: qsTr(String('已选 '+ctrl.selectedCount+' / '+ctrl.photoCount)); font.pixelSize: Theme.caption; color: Theme.secondary }
                            Row { spacing: 6
                                StudioButton { text: qsTr(String('全选')); quiet: true; implicitWidth: 40; implicitHeight: 24; enabled: ctrl.photoCount>0 && !ctrl.exporting; onClicked: ctrl.selectAllPhotos() }
                                StudioButton { objectName: 'removePhotosButton'; text: qsTr(String('移除')); quiet: true; implicitWidth: 40; implicitHeight: 24; enabled: ctrl.selectedCount>0 && !ctrl.exporting; Accessible.description: qsTr(String('从列表移除已选照片，保留磁盘原片；Delete 键')); onClicked: ctrl.removeSelectedPhotos() }
                            }
                        }
                        ListView {
                            Layout.fillWidth: true; Layout.fillHeight: true; orientation: ListView.Horizontal; spacing: 13; clip: true; model: ctrl.photoModel
                            delegate: Item {
                                required property int index; required property var photo
                                width: 83; height: 74
                                activeFocusOnTab: !ctrl.exporting
                                Accessible.role: Accessible.Button
                                Accessible.name: qsTr(String(photo.name))
                                property bool chosen: ctrl.selectedIndices.indexOf(index)>=0
                                readonly property bool current: index===ctrl.currentIndex
                                Accessible.description: qsTr(String((current ? '当前编辑。' : '')+(chosen ? '已选中。Ctrl 点击切换，Shift 点击连续多选。' : 'Ctrl 点击多选，Shift 点击连续多选。')))
                                Keys.onReturnPressed: function(event) { ctrl.selectWithModifiers(index,event.modifiers) }
                                Keys.onSpacePressed: function(event) { ctrl.selectWithModifiers(index,event.modifiers) }
                                Image { x: 3; y: 3; width: 77; height: 48; source: photo.thumbnail; fillMode: Image.PreserveAspectCrop;asynchronous:true;cache:true;sourceSize.width:154;sourceSize.height:96 }
                                Rectangle { width: 83; height: 54; color: 'transparent'; border.width: parent.current || parent.activeFocus ? 2 : 1; border.color: parent.current || parent.chosen || parent.activeFocus ? Theme.accentInk : Theme.border }
                                MinchoText { x: 0; y: 58; width: 83; text: qsTr(String(String(index+1).padStart(2,'0')+(parent.current ? ' · 当前' : ''))); horizontalAlignment: Text.AlignHCenter; font.pixelSize: Theme.caption; color: parent.current ? Theme.ink : Theme.secondary }
                                Rectangle { x: 65; y: 5; width: 12; height: 12; radius: 6; color: Theme.surface; border.width: 1; border.color: Theme.accent; visible: parent.chosen; Rectangle { anchors.centerIn: parent; width: 4; height: 4; radius: 2; color: Theme.accent } }
                                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: function(mouse) { ctrl.selectWithModifiers(index,mouse.modifiers) } }
                            }
                        }
                        StudioButton {objectName:'syncSettingsButton';text:qsTr(String('同步'));quiet:true;enabled:ctrl.currentIndex>=0 && !ctrl.exporting;onClicked:syncDialog.open()}
                    }
                }
            }
                PanelToggle {
                    id:stripToggle;objectName:'togglePhotoStripButton'
                    visible:ctrl.photoCount>0
                    anchors.horizontalCenter:parent.horizontalCenter
                    y:window.stripVisible ? photoStrip.y-10 : parent.height-height
                    z:2
                    expanded:window.stripVisible;panelName:qsTr('照片栏')
                    onClicked:window.stripVisible=!window.stripVisible
                }
                PanelToggle {
                    objectName:'toggleToolsButton';sidePanel:true
                    anchors.right:parent.right;anchors.verticalCenter:parent.verticalCenter;z:3
                    expanded:window.toolsVisible;panelName:qsTr('工具区');shortcut:'Tab'
                    onClicked:window.toolsVisible=!window.toolsVisible
                }
            }
            Item {
                Layout.preferredWidth:12;Layout.fillHeight:true;visible:window.toolsVisible
                Rectangle {anchors.centerIn:parent;width:2;height:48;radius:1;visible:resizeTools.containsMouse || resizeTools.pressed;color:Theme.accent}
                MouseArea {
                    id:resizeTools;objectName:'resizeTools';anchors.fill:parent;hoverEnabled:true;cursorShape:Qt.SizeHorCursor;preventStealing:true
                    property real initialWidth:0
                    property real pressX:0
                    onPressed:function(mouse){initialWidth=window.sidebarWidth;pressX=mapToItem(window.contentItem,mouse.x,mouse.y).x}
                    onPositionChanged:function(mouse){if(pressed){var x=mapToItem(window.contentItem,mouse.x,mouse.y).x;window.sidebarWidth=Math.max(320,Math.min(480,window.width-620,initialWidth+pressX-x))}}
                    onDoubleClicked:window.sidebarWidth=380
                    ToolTip.visible:containsMouse && !pressed;ToolTip.delay:700;ToolTip.text:qsTr(String('拖动调整工具区宽度；双击恢复'))
                }
            }
            Item {
                id:toolsPane;objectName:'toolsPane'
                Layout.preferredWidth:Math.max(320,Math.min(window.sidebarWidth,window.width-620));Layout.fillHeight:true
                visible:window.toolsVisible
                ShadowSurface {anchors.fill:parent;elevation:2;cornerRadius:10;color:Theme.toolSurface}
                EditorTools {
                    id:editorTools;anchors.fill:parent;stock:window.stock;enabled:!window.cropping
                    onLibraryRequested:library.open()
                    onStylesRequested:styleLibrary.open()
                    onCropRequested:window.openCrop()
                    onGuidedRequested:function(mode){window.comparing=false;viewport.beginGuides(mode)}
                }
            }
        }
        SessionBrowser {
            Layout.fillWidth:true;Layout.fillHeight:true
            Layout.leftMargin:28;Layout.rightMargin:28;Layout.topMargin:20;Layout.bottomMargin:20
            visible:window.workspaceMode==='library' && window.quickLibrary;cellSize:216
            onEditRequested:window.setWorkspace('edit');onSyncRequested:syncDialog.open();onLibraryRequested:window.quickLibrary=false
        }
        ImportWorkspace {Layout.fillWidth:true;Layout.fillHeight:true;visible:window.workspaceMode==='import';workspace:ctrl.importWorkspace;onCloseRequested:window.setWorkspace('edit')}
        LibraryWorkspace {Layout.fillWidth:true;Layout.fillHeight:true;visible:window.workspaceMode==='library' && !window.quickLibrary;workspace:ctrl.libraryWorkspace;onCloseRequested:window.setWorkspace('edit')}
    }

    }
    Rectangle { anchors.fill: parent; radius: window.maximized ? 0 : 16; color: 'transparent'; border.width: window.maximized ? 0 : 1; border.color: Theme.border }
    Repeater {
        model: [Qt.LeftEdge,Qt.RightEdge,Qt.TopEdge,Qt.BottomEdge]
        delegate: MouseArea {
            required property int modelData
            property bool vertical: modelData===Qt.LeftEdge || modelData===Qt.RightEdge
            x: modelData===Qt.RightEdge ? window.width-6 : 0
            y: modelData===Qt.BottomEdge ? window.height-6 : 0
            width: vertical ? 6 : window.width
            height: vertical ? window.height : 6
            enabled: !window.maximized
            cursorShape: vertical ? Qt.SizeHorCursor : Qt.SizeVerCursor
            onPressed: window.startSystemResize(modelData)
        }
    }
    Repeater {
        model: [Qt.LeftEdge|Qt.TopEdge,Qt.RightEdge|Qt.TopEdge,Qt.LeftEdge|Qt.BottomEdge,Qt.RightEdge|Qt.BottomEdge]
        delegate: MouseArea {
            required property int modelData
            x: (modelData&Qt.RightEdge) ? window.width-12 : 0
            y: (modelData&Qt.BottomEdge) ? window.height-12 : 0
            width: 12; height: 12; enabled: !window.maximized
            cursorShape: ((modelData&Qt.LeftEdge)>0)===((modelData&Qt.TopEdge)>0) ? Qt.SizeFDiagCursor : Qt.SizeBDiagCursor
            onPressed: window.startSystemResize(modelData)
        }
    }
    DeferredPopup {
        id:library;objectName:'libraryPopup'
        sourceComponent:FilmLibrary {controller:ctrl;library:ctrl.filmLibrary;onAccepted:close()}
    }
    Popup {
        id: toastPopup; x: (window.width-width)/2; y: window.height-height-23; width: Math.min(640,toastLabel.implicitWidth+40); padding: 18
        background: ShadowSurface { elevation: 2; cornerRadius: 4; color: Theme.ink }
        contentItem: MinchoText { id: toastLabel; text:qsTr(String(window.toastSource));wrapMode: Text.Wrap; color: '#FFFFFF' }
        Timer { id: toastTimer; interval: 7000; onTriggered: toastPopup.close() }
    }
    Connections { target: ctrl; function onToast(message){ window.toastSource=message; toastPopup.open(); toastTimer.restart() } }
    StudioDialog {
        id:batchRecoveryDialog
        title:qsTr(String('上次的批量出片未完成'))
        width:460
        contentItem:MinchoText {
            text:qsTr(String('已完成的照片不会重复导出。'))
            wrapMode:Text.WordWrap;color:Theme.secondary
        }
        footer:RowLayout {
            spacing:10
            StudioButton {text:qsTr(String('稍后'));quiet:true;onClicked:{ctrl.dismissBatchRecoveryPrompt();batchRecoveryDialog.close()}}
            Item {Layout.fillWidth:true}
            StudioButton {
                text:qsTr(String(ctrl.canResumeBatchExport ? '继续出片' : '查看任务'))
                primary:true
                onClicked:{
                    var canResume=ctrl.canResumeBatchExport
                    ctrl.dismissBatchRecoveryPrompt();batchRecoveryDialog.close()
                    if(canResume)ctrl.resumeBatchExport()
                    else Qt.callLater(function(){exportDialog.open()})
                }
            }
        }
    }
    DeferredPopup {id:styleLibrary;objectName:'styleLibrary';sourceComponent:StyleLibrary {width:Math.min(640,window.width-64);height:Math.min(760,window.height-64);anchors.centerIn:parent}}
    DeferredPopup {id:settingsPanel;objectName:'settingsPanel';sourceComponent:SettingsPanel {}}
    DeferredPopup {id:syncDialog;objectName:'syncSettingsDialog';sourceComponent:SyncSettingsDialog {}}
    DeferredPopup {id:exportDialog;objectName:'exportDialog';sourceComponent:ExportDialog {onRecipesRequested:outputRecipeDialog.open()}}
    DeferredPopup {id:outputRecipeDialog;objectName:'outputRecipeDialog';sourceComponent:OutputRecipeDialog {}}
    StudioDialog {
        id: aboutDialog; objectName: 'aboutDialog'; anchors.centerIn: parent; width: 520
        contentItem: Column {
            spacing: 18
            MinchoText { text: 'SpektraFilm'; displayRole: true; font.pixelSize: Theme.display }
            MinchoText { width: parent.width; text: qsTr(String('光谱引擎基于 Andrea Volpato 的 spektrafilm。\ngithub.com/andreavolpato/spektrafilm\n代码 GPL-3.0 / 胶片数据与 LUT CC BY-SA 4.0')); wrapMode: Text.WrapAnywhere; font.pixelSize: Theme.caption; color: Theme.secondary; lineHeight: 1.8 }
            StudioSwitch {width:parent.width;text:qsTr('减少动态效果');objectName:'aboutReducedMotionToggle';checked:Theme.reducedMotion;onToggled:Theme.reducedMotion=checked}
            StudioButton { text: qsTr(String('返回暗房')); primary: true; width: parent.width; onClicked: aboutDialog.close() }
        }
    }
    DeferredPopup {id:compositionDialog;objectName:'compositionDialog';sourceComponent:CompositionDialog {}}
}
