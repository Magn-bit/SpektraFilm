import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQml.Models

Item {
    id: root
    property string label: ''
    property var choices: []
    property string value: ''
    property bool fillField:false
    signal selected(string value)
    readonly property string chosenName: {
        for(var i=0;i<choices.length;i++) if(String(choices[i].id)===value) return choices[i].name;
        return value.length ? value : choices.length ? choices[0].name : '';
    }
    width: parent.width; height: 36
    MinchoText { visible:!root.fillField; text: qsTr(String(root.label)); anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter }
    Button {
        id: selector
        anchors.right: parent.right; width: root.fillField ? parent.width : Math.min(parent.width*.72,218); height: parent.height
        hoverEnabled: true; padding: 0
        Accessible.name: qsTr(String(root.label))
        Accessible.description: qsTr(String(root.chosenName))
        onClicked: menu.open()
        contentItem: RowLayout {
            spacing: 12
            MinchoText { visible:root.fillField && root.label.length>0; text:qsTr(String(root.label)); Layout.leftMargin:12; color:Theme.secondary; font.pixelSize:Theme.caption }
            MinchoText { text: qsTr(String(root.chosenName)); Layout.fillWidth: true; Layout.leftMargin: root.fillField && root.label.length>0 ? 0 : 12; color: root.enabled ? Theme.ink : Theme.muted; elide: Text.ElideRight }
            Canvas {
                property color iconColor:Theme.secondary
                Layout.preferredWidth: 10; Layout.preferredHeight: 8; Layout.rightMargin: 12
                onIconColorChanged:requestPaint()
                onPaint: {
                    var c=getContext('2d');c.reset();c.strokeStyle=iconColor;c.lineWidth=1;
                    c.beginPath();c.moveTo(1,2);c.lineTo(5,6);c.lineTo(9,2);c.stroke();
                }
            }
        }
        background: Rectangle { radius: 5; color: selector.down || menu.opened ? Theme.selection : selector.hovered ? Theme.hover : Theme.surface; border.width: selector.visualFocus ? 2 : 1; border.color: selector.visualFocus ? Theme.accent : Theme.border }
        Menu {
            id: menu
            y: selector.height+5; x: selector.width-width; width: Math.max(selector.width,228); padding: 5
            font.family: Theme.family; font.pixelSize: Theme.body
            transformOrigin: Item.TopRight
            background: ShadowSurface {
                elevation: 2; cornerRadius: Theme.popupRadius; color: Theme.white
                Rectangle { anchors.fill: parent; radius: Theme.popupRadius; color: 'transparent'; border.width: 1; border.color: Theme.rule }
            }
            enter: Transition { NumberAnimation { property: 'scale'; from: .985; to: 1; duration: Theme.fast; easing.type: Theme.easing } }
            exit: Transition { NumberAnimation { property: 'scale'; from: 1; to: .985; duration: Theme.fast; easing.type: Theme.easing } }
            onClosed: selector.forceActiveFocus()
            onOpened: {for(var i=0;i<root.choices.length;i++)if(String(root.choices[i].id)===root.value){currentIndex=i;break;}}
            Instantiator {
                model: root.choices
                delegate: MenuItem {
                    id: option
                    required property var modelData
                    implicitHeight: 40; checkable: true; checked: root.value===String(modelData.id)
                    text: qsTr(String(modelData.name)); leftPadding: 30; rightPadding: 14
                    indicator: Rectangle { x: 14; y: (option.height-height)/2; width: 5; height: 5; radius: 2.5; color: Theme.accentInk; visible: option.checked }
                    contentItem: MinchoText { text: qsTr(String(option.text)); color: option.checked ? Theme.accentInk : Theme.ink; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
                    background: Rectangle { radius: 4; color: option.highlighted ? Theme.hover : option.checked ? Theme.selection : 'transparent' }
                    onTriggered: root.selected(String(modelData.id))
                }
                onObjectAdded: function(index,object) { menu.insertItem(index,object) }
                onObjectRemoved: function(index,object) { menu.removeItem(object) }
            }
        }
    }
}
