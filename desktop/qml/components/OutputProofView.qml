import QtQuick
import QtQuick.Window
import QtQuick.Controls.Basic
import QtQuick.Layouts

Rectangle {
    id:root
    color:Theme.canvas;radius:8
    property var recipe:({})
    property bool active:false
    property bool fullRequested:false
    property bool softProof:true
    property bool gamutWarning:false
    property bool pixelView:false
    property bool exportObserved:false
    readonly property var proof:ctrl.outputProof
    readonly property real dpr:Math.max(1,Screen.devicePixelRatio)
    function refresh(){if(active && !ctrl.exporting && recipe.id && ctrl.currentIndex>=0)debounce.restart()}
    onRecipeChanged:refresh()
    onActiveChanged:{if(active){exportObserved=ctrl.exporting;fullRequested=false;pixelView=false;refresh()}else{debounce.stop();proof.release()}}
    Connections {
        target:ctrl
        function onStateChanged(){
            if(ctrl.exporting){root.exportObserved=true;debounce.stop()}
            else if(root.exportObserved){root.exportObserved=false;root.refresh()}
        }
    }
    Timer {id:debounce;interval:240;onTriggered:proof.request(root.recipe,root.fullRequested,root.softProof,root.gamutWarning)}
    Connections {
        target:root.proof
        function onChanged(){
            if(root.fullRequested && !root.proof.busy && root.proof.source.length){
                if(!root.pixelView){root.pixelView=true;pixels.contentX=Math.max(0,(pixels.contentWidth-pixels.width)/2);pixels.contentY=Math.max(0,(pixels.contentHeight-pixels.height)/2)}
                tileTimer.restart()
            }
        }
    }
    ColumnLayout {
        anchors.fill:parent;anchors.margins:16;spacing:12
        RowLayout {
            Layout.fillWidth:true;spacing:6
            MinchoText {text:qsTr(String('输出打样'));font.pixelSize:Theme.caption;Layout.fillWidth:true}
        }
        Flow {
            Layout.fillWidth:true;spacing:16
            StudioSwitch {objectName:'outputSoftProofToggle';text:qsTr('软打样');checked:root.softProof;enabled:root.recipe.format!=='di' && root.recipe.format!=='raw';onToggled:{root.softProof=checked;root.refresh()} Accessible.description:qsTr('模拟所选输出色域，并使用当前显示器配置')}
            StudioSwitch {objectName:'outputGamutToggle';text:qsTr('色域警告');checked:root.gamutWarning;enabled:root.softProof && root.recipe.format!=='di' && root.recipe.format!=='raw';onToggled:{root.gamutWarning=checked;root.refresh()}}
        }
        Item {
            id:canvas;Layout.fillWidth:true;Layout.fillHeight:true;clip:true
            Image {anchors.fill:parent;source:root.proof.source;fillMode:Image.PreserveAspectFit;asynchronous:true;cache:false;visible:!root.pixelView || root.proof.busy}
            Flickable {
                id:pixels;anchors.fill:parent;clip:true;visible:root.pixelView && !root.proof.busy
                boundsBehavior:Flickable.StopAtBounds
                contentWidth:Math.max(width,root.proof.dimensions[0]/root.dpr)
                contentHeight:Math.max(height,root.proof.dimensions[1]/root.dpr)
                onContentXChanged:tileTimer.restart()
                onContentYChanged:tileTimer.restart()
                onWidthChanged:tileTimer.restart()
                onHeightChanged:tileTimer.restart()
                Image {
                    x:root.proof.tileRect[0]/root.dpr;y:root.proof.tileRect[1]/root.dpr
                    width:root.proof.tileRect[2]/root.dpr;height:root.proof.tileRect[3]/root.dpr
                    source:root.proof.tileSource;cache:false;smooth:false
                }
                ScrollBar.horizontal:ScrollBar {policy:ScrollBar.AsNeeded}
                ScrollBar.vertical:ScrollBar {policy:ScrollBar.AsNeeded}
                Accessible.name:qsTr(String('原像素输出打样，可拖动查看细节'))
            }
            Timer {id:tileTimer;interval:24;onTriggered:{if(root.active && root.pixelView && !root.proof.busy)root.proof.viewTile(Math.floor(pixels.contentX*root.dpr),Math.floor(pixels.contentY*root.dpr),Math.ceil(pixels.width*root.dpr),Math.ceil(pixels.height*root.dpr))}}
            MinchoText {anchors.centerIn:parent;width:parent.width-32;horizontalAlignment:Text.AlignHCenter;wrapMode:Text.WordWrap;color:Theme.secondary;text:qsTr(String(root.proof.busy ? (root.fullRequested ? '正在生成原像素打样…' : '正在更新打样…') : root.proof.error || (ctrl.currentIndex<0 ? '选择照片' : '')));visible:root.proof.busy || root.proof.error.length>0 || ctrl.currentIndex<0;font.pixelSize:Theme.caption}
        }
        RowLayout {
            Layout.fillWidth:true;spacing:8
            MinchoText {Layout.fillWidth:true;font.pixelSize:Theme.caption;color:Theme.secondary;text:root.proof.expectedDimensions[0]>0 ? root.proof.expectedDimensions[0]+' × '+root.proof.expectedDimensions[1]+' px' : '';elide:Text.ElideRight}
            StudioButton {text:qsTr(String('适合'));quiet:true;selected:!root.pixelView;implicitHeight:30;onClicked:root.pixelView=false}
            StudioButton {objectName:'outputProofFullButton';text:qsTr(String('原像素检查'));quiet:true;selected:root.pixelView;implicitHeight:30;enabled:ctrl.currentIndex>=0 && !root.proof.busy;onClicked:{if(root.proof.fullResolution){root.pixelView=true;tileTimer.restart()}else{root.fullRequested=true;root.refresh()}} Accessible.description:qsTr(String('从完整源照片生成真实输出文件，按一个照片像素对应一个屏幕像素检查'))}
        }
        MinchoText {Layout.fillWidth:true;text:ctrl.filename+(root.proof.source.length ? ' · '+(root.proof.fullResolution ? qsTr('原像素打样') : qsTr('代理打样')) : '');font.pixelSize:Theme.caption;color:Theme.secondary;elide:Text.ElideMiddle}
    }
}
