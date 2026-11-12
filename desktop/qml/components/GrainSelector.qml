import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQml.Models

Item {
    id: root
    width: parent.width; height: 36
    readonly property var choices: [
        {id:'fine', name:'细腻'}, {id:'classic', name:'经典'},
        {id:'coarse', name:'粗粝'}, {id:'clustered', name:'团簇'}
    ]
    readonly property int chosenIndex: {
        for (var i=0;i<choices.length;i++) if (choices[i].id===ctrl.parameters.grain_type) return i;
        return 1;
    }
    MinchoText { text: qsTr(String('颗粒类型')); anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter }
    Button {
        id: selector; objectName: 'grainTypePicker'
        anchors.right: parent.right; width: Math.min(parent.width*.68,196); height: parent.height
        hoverEnabled: true; padding: 0
        Accessible.name: qsTr(String('颗粒类型'))
        Accessible.description: qsTr(String(root.choices[root.chosenIndex].name+'，展开选择'))
        contentItem: RowLayout {
            spacing: 14
            MinchoText { text: qsTr(String(root.choices[root.chosenIndex].name)); Layout.fillWidth: true; Layout.leftMargin: 12; color: root.enabled ? Theme.ink : Theme.muted }
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
        background: Rectangle {
            radius: 5; color: selector.down || menu.opened ? Theme.selection : selector.hovered ? Theme.hover : Theme.surface
            border.width: selector.visualFocus ? 2 : 1
            border.color: selector.visualFocus ? Theme.accentInk : Theme.border
        }
        onClicked: menu.open()
        Menu {
            id: menu; objectName: 'grainTypeMenu'
            y: selector.height+5; x: selector.width-width; width: 176; padding: 5
            font.family: Theme.family; font.pixelSize: Theme.body
            transformOrigin: Item.TopRight
            background: ShadowSurface {
                elevation: 2; cornerRadius: Theme.popupRadius; color: Theme.white
                Rectangle { anchors.fill: parent; radius: Theme.popupRadius; color: 'transparent'; border.width: 1; border.color: Theme.rule }
            }
            // Keep the paper surface opaque from the first frame so parameters
            // cannot ghost through the open material chooser.
            enter: Transition { NumberAnimation { property: 'scale'; from: .985; to: 1; duration: Theme.fast; easing.type: Theme.easing } }
            exit: Transition { NumberAnimation { property: 'scale'; from: 1; to: .985; duration: Theme.fast; easing.type: Theme.easing } }
            onOpened: currentIndex=root.chosenIndex
            onClosed: selector.forceActiveFocus()
            Instantiator {
                model: root.choices
                delegate: MenuItem {
                    id: option
                    required property var modelData
                    objectName: 'grainType_'+modelData.id
                    implicitHeight: 40; checkable: true
                    checked: ctrl.parameters.grain_type===modelData.id
                    text: qsTr(String(modelData.name))
                    Accessible.name: qsTr(String('颗粒类型：'+modelData.name))
                    leftPadding: 31; rightPadding: 15
                    indicator: Rectangle { x: 14; y: (option.height-height)/2; width: 5; height: 5; radius: 2.5; color: Theme.accentInk; visible: option.checked }
                    contentItem: MinchoText { text: qsTr(String(option.text)); color: option.checked ? Theme.accentInk : Theme.ink; verticalAlignment: Text.AlignVCenter }
                    background: Rectangle { radius: 4; color: option.highlighted ? Theme.hover : option.checked ? Theme.selection : 'transparent' }
                    onTriggered: ctrl.setGrainType(modelData.id)
                }
                onObjectAdded: function(index, object) { menu.insertItem(index, object) }
                onObjectRemoved: function(index, object) { menu.removeItem(object) }
            }
        }
    }
}
