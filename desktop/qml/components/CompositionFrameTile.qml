import QtQuick
import QtQuick.Controls.Basic

Button {
    id:control
    property string treatment:'paper'
    property string title:''
    property url photoSource:''
    property url secondSource:''
    property url nativeSource:''
    property bool physicalFrame:false
    property bool thumbnailLoading:false
    property bool chosen:false
    readonly property bool dark:physicalFrame||treatment==='contact'
    implicitHeight:98;padding:8;hoverEnabled:true;activeFocusOnTab:true
    HoverHandler {cursorShape:control.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor}
    scale:down ? .985 : 1
    Behavior on scale {NumberAnimation {duration:Theme.fast;easing.type:Theme.easing}}
    opacity:enabled ? 1 : .42
    Accessible.name:qsTr(String(title))
    Accessible.checkable:true
    Accessible.checked:chosen
    Keys.onReturnPressed:clicked()
    Keys.onEnterPressed:clicked()
    background:Rectangle {
        radius:6;color:control.chosen ? Theme.selection : control.down ? Theme.hover : Theme.surface
        border.width:control.visualFocus ? 2 : 1
        border.color:control.chosen||control.visualFocus ? Theme.accent : control.hovered ? Theme.secondary : Theme.rule
        Behavior on color {ColorAnimation {duration:Theme.fast}}
    }
    contentItem:Column {
        spacing:5
        Item {
            width:parent.width;height:56
            Image {
                anchors.fill:parent;visible:control.physicalFrame
                source:control.nativeSource;fillMode:Image.PreserveAspectFit
                asynchronous:false;cache:false;smooth:true
            }
            BusyIndicator {
                anchors.centerIn:parent;width:24;height:24
                visible:control.physicalFrame&&control.thumbnailLoading
                running:visible
            }
            Rectangle {
                id:paper;visible:!control.physicalFrame;anchors.centerIn:parent;width:Math.min(parent.width,108);height:56
                color:control.dark ? '#22281F' : '#F8F4E9'
                readonly property real mat:control.treatment==='plain' ? 0 : control.treatment==='film'||control.treatment==='half_frame' ? 6 : 4
                Item {
                    id:gate;x:paper.mat;y:paper.mat;width:paper.width-paper.mat*2
                    height:paper.height-paper.mat*2-(control.treatment==='instant' ? 8 : control.treatment==='contact' ? 3 : 0);clip:true
                    Rectangle {anchors.fill:parent;color:'#BBC4B6'}
                    Image {visible:control.treatment!=='half_frame'&&control.treatment!=='contact';anchors.fill:parent;source:control.photoSource;fillMode:Image.PreserveAspectCrop;asynchronous:true;sourceSize.width:160}
                    Row {
                        visible:control.treatment==='half_frame';anchors.fill:parent;spacing:2
                        Image {width:(parent.width-2)/2;height:parent.height;source:control.photoSource;fillMode:Image.PreserveAspectCrop;asynchronous:true;sourceSize.width:80}
                        Image {width:(parent.width-2)/2;height:parent.height;source:control.secondSource;fillMode:Image.PreserveAspectCrop;asynchronous:true;sourceSize.width:80}
                    }
                    Grid {
                        visible:control.treatment==='contact';anchors.fill:parent;columns:2;spacing:2
                        Repeater {model:4;Image {width:(gate.width-2)/2;height:(gate.height-2)/2;source:control.photoSource;fillMode:Image.PreserveAspectCrop;asynchronous:true;sourceSize.width:80}}
                    }
                }
            }
        }
        MinchoText {width:parent.width;text:qsTr(String(control.title));font.pixelSize:Theme.caption;horizontalAlignment:Text.AlignHCenter;color:Theme.ink}
    }
}
