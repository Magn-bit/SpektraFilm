import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQml.Models

Button {
    id:root
    property Item contentRoot
    property var flickable
    property string contextKey:''
    property var sections:[]
    property Item jumpTarget
    property real jumpTop:-1
    property real jumpExtent:-1
    property int jumpPasses:0
    readonly property int currentSection:{
        var position=flickable ? flickable.contentY : 0,index=0
        for(var i=0;i<sections.length;i++) {
            // mapToItem does not subscribe to the positions it traverses.
            var localY=sections[i].item.y,parentY=sections[i].item.parent.y
            if(sections[i].item.mapToItem(contentRoot,0,0).y<=position+12)index=i
        }
        return index
    }
    readonly property string currentTitle:sections.length ? sections[currentSection].title : ''
    objectName:'toolSectionNavigator'
    implicitHeight:34;padding:8;hoverEnabled:true;activeFocusOnTab:true
    visible:sections.length>1
    Accessible.name:qsTr('跳转到工具分组')
    Accessible.description:currentTitle
    onContextKeyChanged:{layoutSettle.stop();jumpTarget=null;Qt.callLater(rebuild)}
    function rebuild() {
        var result=[]
        function collect(item) {
            if(!item || !item.visible)return
            if(item.sectionTitle!==undefined && item.sectionTitle.length>0) {
                result.push({title:item.sectionTitle,item:item});return
            }
            for(var i=0;i<item.children.length;i++)collect(item.children[i])
        }
        collect(contentRoot);sections=result
    }
    function jump(index) {
        if(index<0 || index>=sections.length || !flickable)return
        var target=sections[index].item
        if(target.reveal!==undefined)target.reveal()
        jumpTarget=target;jumpTop=-1;jumpExtent=-1;jumpPasses=0;layoutSettle.restart()
    }
    Timer {
        id:layoutSettle;interval:16;repeat:true
        onTriggered:{
            if(!root.jumpTarget || !root.jumpTarget.visible || root.flickable.dragging){stop();return}
            var top=root.jumpTarget.mapToItem(root.contentRoot,0,0).y
            var extent=root.flickable.contentHeight-root.flickable.height
            // Nested implicit heights settle across successive scene polishes.
            // Do not clamp to an intermediate contentHeight during that pass.
            if((top===root.jumpTop && extent===root.jumpExtent) || root.jumpPasses>=8) {
                root.flickable.contentY=Math.max(0,Math.min(top,extent));stop();root.jumpTarget=null
            }else{root.jumpTop=top;root.jumpExtent=extent;root.jumpPasses++}
        }
    }
    onClicked:sectionMenu.open()
    ToolTip.visible:hovered || visualFocus;ToolTip.delay:600;ToolTip.text:Accessible.name
    contentItem:RowLayout {
        spacing:8
        MinchoText {text:root.currentTitle;Layout.fillWidth:true;elide:Text.ElideRight;color:Theme.secondary;font.pixelSize:Theme.caption}
        VectorIcon {name:'triangle-down';Layout.preferredWidth:12;Layout.preferredHeight:12;iconColor:Theme.secondary}
    }
    background:Rectangle {radius:4;color:root.down || sectionMenu.opened ? Theme.selection : root.hovered ? Theme.hover : Theme.panelInset;border.width:root.visualFocus ? 1 : 0;border.color:Theme.accent}
    Menu {
        id:sectionMenu;objectName:'toolSectionMenu';y:root.height+4;width:root.width;padding:5
        closePolicy:Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background:ShadowSurface {elevation:3;cornerRadius:Theme.popupRadius;color:Theme.surface}
        onOpened:currentIndex=root.currentSection
        Instantiator {
            model:root.sections
            delegate:MenuItem {
                id:option;required property int index;required property var modelData
                objectName:'toolSectionOption_'+index
                implicitHeight:36;text:modelData.title;checkable:true;checked:index===root.currentSection
                leftPadding:12;rightPadding:12
                indicator:Item{}
                contentItem:MinchoText {text:option.text;color:option.checked ? Theme.accentInk : Theme.ink;elide:Text.ElideRight;verticalAlignment:Text.AlignVCenter}
                background:Rectangle {radius:3;color:option.highlighted ? Theme.hover : option.checked ? Theme.selection : 'transparent'}
                onTriggered:root.jump(index)
            }
            onObjectAdded:function(index,object){sectionMenu.insertItem(index,object)}
            onObjectRemoved:function(index,object){sectionMenu.removeItem(object)}
        }
    }
}
