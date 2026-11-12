import QtQuick
import QtQuick.Controls.Basic

Control {
    id: control
    property url originalSource
    property url detailSource
    property var detailRect:[0,0,0,0]
    property real position: .5
    property real viewLeft: 0
    property real viewTop: 0
    property real viewWidth: width
    property real viewHeight: height
    property bool smoothImage: true
    readonly property real dividerX: viewLeft + viewWidth * position
    readonly property real handleY: viewTop + viewHeight / 2
    readonly property bool interacting: dividerMouse.containsMouse || dividerMouse.pressed || visualFocus
    signal positionRequested(real value)

    padding: 0
    background: null
    focusPolicy: Qt.StrongFocus
    activeFocusOnTab: visible
    Accessible.role: Accessible.Slider
    Accessible.name: qsTr(String('原图与编辑结果分界'))
    Accessible.description: qsTr(String('左侧为原图，右侧为编辑结果。左右方向键移动，Home 和 End 查看两侧，双击或按 0 居中，B 退出对比。'))

    function requestPosition(value) {
        var inset = Math.min(.25, (Theme.compareHandleSize / 2 + 3) / Math.max(1, viewWidth));
        positionRequested(Math.max(inset, Math.min(1 - inset, value)));
    }
    Keys.onLeftPressed: function(event) { requestPosition(position - (event.modifiers & Qt.ShiftModifier ? .1 : .02)); }
    Keys.onRightPressed: function(event) { requestPosition(position + (event.modifiers & Qt.ShiftModifier ? .1 : .02)); }
    Keys.onPressed: function(event) {
        if(event.key===Qt.Key_Home) { requestPosition(0); event.accepted=true; }
        else if(event.key===Qt.Key_End) { requestPosition(1); event.accepted=true; }
        else if(event.key===Qt.Key_0) { requestPosition(.5); event.accepted=true; }
    }
    Accessible.onIncreaseAction: requestPosition(position + .05)
    Accessible.onDecreaseAction: requestPosition(position - .05)

    contentItem: Item {
        Item {
            objectName: 'comparisonOriginalClip'
            width: Math.max(0, control.dividerX); height: control.height
            clip: true
            Image {
                anchors.left: parent.left; anchors.top: parent.top
                width: control.width; height: control.height
                source: control.originalSource; cache: false
                fillMode: Image.Stretch; smooth: control.smoothImage
            }
            Image {
                objectName:'comparisonDetailTile'
                x:control.detailRect[0]*control.width;y:control.detailRect[1]*control.height
                width:control.detailRect[2]*control.width;height:control.detailRect[3]*control.height
                source:control.detailSource;visible:source.toString().length>0;cache:false
                fillMode:Image.Stretch;smooth:control.smoothImage
            }
        }
        Rectangle {
            x: Math.round(control.dividerX) - 1
            y: control.viewTop; width: 3; height: control.viewHeight
            color: Theme.compareEdge
        }
        Rectangle {
            objectName: 'comparisonDivider'
            x: Math.round(control.dividerX)
            y: control.viewTop; width: 1; height: control.viewHeight
            color: Theme.compareLine
        }
        Item {
            id: handle
            objectName: 'comparisonHandle'
            x: control.dividerX - width / 2
            y: control.handleY - height / 2
            width: Theme.compareHandleSize; height: width
            scale: dividerMouse.pressed ? .94 : (control.interacting ? 1.08 : 1)
            Behavior on scale { NumberAnimation { duration: Theme.fast; easing.type: Theme.easing } }
            Rectangle {
                anchors.fill: parent; anchors.topMargin: 1; anchors.bottomMargin: -1
                radius: width / 2; color: '#25252725'
            }
            Rectangle {
                anchors.fill: parent; radius: width / 2
                color: Theme.compareSurface
                border.width: 1; border.color: '#38FFFFFF'
                Row {
                    anchors.centerIn: parent; spacing: 3
                    Rectangle { width: 1; height: 8; radius: .5; color: Theme.ink }
                    Rectangle { width: 1; height: 8; radius: .5; color: Theme.ink }
                }
            }
            Rectangle {
                anchors.fill: parent; anchors.margins: -4; radius: width / 2
                color: 'transparent'; border.width: 2; border.color: Theme.accent
                visible: control.visualFocus
            }
        }
        MouseArea {
            id: dividerMouse
            objectName: 'comparisonDragTarget'
            x: control.dividerX - width / 2
            y: control.viewTop
            width: Theme.compareHitWidth; height: control.viewHeight
            hoverEnabled: true
            cursorShape: Qt.SizeHorCursor
            preventStealing: true
            acceptedButtons: Qt.LeftButton
            function moveDivider(mouse) {
                var point = mapToItem(control, mouse.x, mouse.y);
                control.requestPosition((point.x - control.viewLeft) / Math.max(1, control.viewWidth));
            }
            onPressed: function(mouse) { control.forceActiveFocus(Qt.MouseFocusReason); }
            onPositionChanged: function(mouse) { if (pressed) moveDivider(mouse); }
            onReleased: function(mouse) { moveDivider(mouse); }
            onDoubleClicked: control.requestPosition(.5)
        }
    }
}
