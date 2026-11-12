import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

StudioDialog {
    id: root
    objectName: 'cropDialog'
    anchors.centerIn: parent
    width: Math.min(parent.width-64,1120)
    height: Math.min(parent.height-64,800)
    padding: 24
    property var draft: [0,0,1,1]
    property real ratio: 0
    property string ratioName: '自由'
    property bool transposed: false
    property string photoKey: ''
    readonly property real sourceRatio: ctrl.sourceDimensions[0]/Math.max(1,ctrl.sourceDimensions[1])
    readonly property int outputWidth: Math.max(1,Math.round(draft[2]*ctrl.sourceDimensions[0])-Math.round(draft[0]*ctrl.sourceDimensions[0]))
    readonly property int outputHeight: Math.max(1,Math.round(draft[3]*ctrl.sourceDimensions[1])-Math.round(draft[1]*ctrl.sourceDimensions[1]))
    onOpened: {
        draft=ctrl.cropBounds.slice();ratio=0;ratioName='自由';transposed=false
        photoKey=ctrl.currentPath
        cropArea.forceActiveFocus()
    }
    Connections {
        target: ctrl
        function onPhotosChanged() {
            if(root.opened && (ctrl.currentIndex<0 || ctrl.currentPath!==root.photoKey))root.close()
        }
    }
    function clamp(value,low,high) {return Math.max(low,Math.min(high,value))}
    function chooseRatio(name,value) {
        ratioName=name;ratio=value
        if(!ratio)return
        // Presets fit the source around the current centre; switching them never
        // progressively shrinks a previously chosen rectangle.
        var normalized=ratio/sourceRatio
        var w=Math.min(1,normalized),h=Math.min(1,1/normalized)
        var cx=clamp((draft[0]+draft[2])/2,w/2,1-w/2)
        var cy=clamp((draft[1]+draft[3])/2,h/2,1-h/2)
        draft=[cx-w/2,cy-h/2,cx+w/2,cy+h/2]
    }
    function moveBy(dx,dy) {
        var p=draft.slice()
        dx=clamp(dx,-p[0],1-p[2]);dy=clamp(dy,-p[1],1-p[3])
        draft=[p[0]+dx,p[1]+dy,p[2]+dx,p[3]+dy]
    }
    function resetDraft() {draft=[0,0,1,1];ratio=0;ratioName='自由';transposed=false}
    contentItem: ColumnLayout {
        spacing: 16
        RowLayout {
            Layout.fillWidth:true;spacing:16
            MinchoText {text:qsTr(String('裁切'));font.pixelSize:Theme.heading;Layout.fillWidth:true}
            MinchoText {text:qsTr(String(root.outputWidth+' × '+root.outputHeight));font.pixelSize:Theme.caption;color:Theme.secondary}
        }
        RowLayout {
            Layout.fillWidth:true;spacing:5
            Repeater {
                model:[{name:'自由',r:0},{name:'原图',r:root.sourceRatio},{name:'1:1',r:1},
                       {name:'3:2',r:3/2},{name:'4:3',r:4/3},{name:'16:9',r:16/9},{name:'XPan',r:65/24}]
                delegate: StudioButton {
                    required property var modelData
                    text:qsTr(String(modelData.name));quiet:true;selected:root.ratioName===modelData.name
                    Layout.fillWidth:true;implicitHeight:34
                    Accessible.description:qsTr(String(modelData.name==='XPan' ? 'XPan 65 比 24 宽画幅' : '选择裁切比例 '+modelData.name))
                    onClicked:root.chooseRatio(modelData.name,root.transposed && modelData.r>0 ? 1/modelData.r : modelData.r)
                }
            }
            StudioButton {
                objectName:'transposeCropButton';text:qsTr(String(root.transposed ? '竖向' : '横向'));quiet:true
                implicitHeight:34;enabled:root.ratio>0;selected:root.transposed
                Accessible.description:qsTr(String('切换裁切比例的横向或竖向'))
                onClicked:{root.transposed=!root.transposed;root.chooseRatio(root.ratioName,1/root.ratio)}
            }
        }
        Rectangle {
            id:stage
            Layout.fillWidth:true;Layout.fillHeight:true;color:Theme.canvas;radius:6;clip:true
            Image {
                id:fullImage;objectName:'cropFullImage';source:ctrl.cropSource;cache:false
                width:Math.max(1,Math.min(stage.width-48,(stage.height-48)*root.sourceRatio))
                height:width/Math.max(.001,root.sourceRatio)
                anchors.centerIn:parent;fillMode:Image.Stretch;smooth:true
                Rectangle {x:0;y:0;width:parent.width;height:root.draft[1]*parent.height;color:'#84202520'}
                Rectangle {x:0;y:root.draft[3]*parent.height;width:parent.width;height:(1-root.draft[3])*parent.height;color:'#84202520'}
                Rectangle {x:0;y:root.draft[1]*parent.height;width:root.draft[0]*parent.width;height:(root.draft[3]-root.draft[1])*parent.height;color:'#84202520'}
                Rectangle {x:root.draft[2]*parent.width;y:root.draft[1]*parent.height;width:(1-root.draft[2])*parent.width;height:(root.draft[3]-root.draft[1])*parent.height;color:'#84202520'}
                Rectangle {
                    id:selection
                    x:root.draft[0]*parent.width;y:root.draft[1]*parent.height
                    width:(root.draft[2]-root.draft[0])*parent.width;height:(root.draft[3]-root.draft[1])*parent.height
                    color:'transparent';border.width:1;border.color:'#F2FFFFFF'
                    Repeater {model:[1,2];Rectangle {required property int modelData;x:parent.width*modelData/3;width:1;height:parent.height;color:cropArea.pressed ? '#80FFFFFF' : '#45FFFFFF'}}
                    Repeater {model:[1,2];Rectangle {required property int modelData;y:parent.height*modelData/3;height:1;width:parent.width;color:cropArea.pressed ? '#80FFFFFF' : '#45FFFFFF'}}
                    Repeater {
                        model:[[0,0],[1,0],[0,1],[1,1]]
                        Item {
                            required property var modelData
                            x:modelData[0]*selection.width;y:modelData[1]*selection.height
                            Rectangle {x:modelData[0] ? -17 : -1;y:modelData[1] ? -2 : -1;width:18;height:3;color:'#FFFFFF'}
                            Rectangle {x:modelData[0] ? -2 : -1;y:modelData[1] ? -17 : -1;width:3;height:18;color:'#FFFFFF'}
                        }
                    }
                }
                MouseArea {
                    id:cropArea;objectName:'cropInteraction'
                    anchors.fill:parent;enabled:fullImage.status===Image.Ready && !ctrl.cropBusy
                    preventStealing:true;hoverEnabled:true;activeFocusOnTab:true
                    Accessible.role:Accessible.Pane;Accessible.name:qsTr(String('裁切范围'))
                    Accessible.description:qsTr(String('拖动内部移动范围，拖动边角调整大小；方向键移动，Shift 加速'))
                    property var initial:[]
                    property var pressPoint:[]
                    property string mode:''
                    property string hoverMode:''
                    function hitMode(px,py) {
                        var l=root.draft[0]*width,r=root.draft[2]*width,t=root.draft[1]*height,b=root.draft[3]*height
                        var nearL=Math.abs(px-l)<18,nearR=Math.abs(px-r)<18,nearT=Math.abs(py-t)<18,nearB=Math.abs(py-b)<18
                        if((nearL || nearR) && (nearT || nearB))return (nearL ? 'l' : 'r')+(nearT ? 't' : 'b')
                        if(px>=l && px<=r && py>=t && py<=b)return 'move'
                        return 'draw'
                    }
                    cursorShape:pressed && mode==='move' ? Qt.ClosedHandCursor : hoverMode==='move' ? Qt.OpenHandCursor :
                                hoverMode==='lt' || hoverMode==='rb' ? Qt.SizeFDiagCursor :
                                hoverMode==='rt' || hoverMode==='lb' ? Qt.SizeBDiagCursor : Qt.CrossCursor
                    onPressed:function(mouse) {
                        forceActiveFocus();initial=root.draft.slice();pressPoint=[mouse.x/width,mouse.y/height]
                        mode=hitMode(mouse.x,mouse.y)
                    }
                    onPositionChanged:function(mouse) {
                        hoverMode=hitMode(mouse.x,mouse.y)
                        if(!pressed)return
                        var x=root.clamp(mouse.x/width,0,1),y=root.clamp(mouse.y/height,0,1)
                        var p=initial.slice(),dx=x-pressPoint[0],dy=y-pressPoint[1]
                        if(mode==='move') {
                            dx=root.clamp(dx,-p[0],1-p[2]);dy=root.clamp(dy,-p[1],1-p[3])
                            root.draft=[p[0]+dx,p[1]+dy,p[2]+dx,p[3]+dy];return
                        }
                        var ax=mode==='draw' ? pressPoint[0] : mode.indexOf('l')>=0 ? p[2] : p[0]
                        var ay=mode==='draw' ? pressPoint[1] : mode.indexOf('t')>=0 ? p[3] : p[1]
                        var sx=x>=ax ? 1 : -1,sy=y>=ay ? 1 : -1
                        var maxW=sx>0 ? 1-ax : ax,maxH=sy>0 ? 1-ay : ay
                        var minW=Math.min(24/Math.max(1,width),maxW),minH=Math.min(24/Math.max(1,height),maxH)
                        var w=root.clamp(Math.abs(x-ax),minW,maxW),h=root.clamp(Math.abs(y-ay),minH,maxH)
                        if(root.ratio>0) {
                            var normalized=root.ratio/root.sourceRatio
                            w=Math.max(w,h*normalized)
                            w=Math.min(Math.max(w,minW,minH*normalized),maxW,maxH*normalized);h=w/normalized
                        }
                        var bx=root.clamp(ax+sx*w,0,1),by=root.clamp(ay+sy*h,0,1)
                        root.draft=[Math.min(ax,bx),Math.min(ay,by),Math.max(ax,bx),Math.max(ay,by)]
                    }
                    Keys.onPressed:function(event) {
                        var step=(event.modifiers & Qt.ShiftModifier) ? 10 : 1
                        var dx=step/Math.max(1,ctrl.sourceDimensions[0]),dy=step/Math.max(1,ctrl.sourceDimensions[1])
                        if(event.key===Qt.Key_Left)root.moveBy(-dx,0)
                        else if(event.key===Qt.Key_Right)root.moveBy(dx,0)
                        else if(event.key===Qt.Key_Up)root.moveBy(0,-dy)
                        else if(event.key===Qt.Key_Down)root.moveBy(0,dy)
                        else {event.accepted=false;return}
                        event.accepted=true
                    }
                }
            }
            MinchoText {anchors.centerIn:parent;text:qsTr(String(ctrl.cropBusy ? '正在准备画幅…' : '裁切预览不可用'));visible:fullImage.status!==Image.Ready;color:Theme.secondary}
        }
        RowLayout {
            Layout.fillWidth:true;spacing:12
            StudioButton {objectName:'resetCropButton';text:qsTr(String('恢复原图'));quiet:true;onClicked:root.resetDraft()}
            Item {Layout.fillWidth:true}
            StudioButton {text:qsTr(String('取消'));quiet:true;onClicked:root.close()}
            StudioButton {objectName:'applyCropButton';text:qsTr(String('应用裁切'));primary:true;implicitWidth:108;enabled:fullImage.status===Image.Ready && !ctrl.cropBusy;onClicked:{ctrl.applyCrop(root.draft);root.close()}}
        }
    }
}
