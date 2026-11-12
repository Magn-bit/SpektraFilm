import QtQuick
import QtQuick.Effects
Item {
    id: root
    property int elevation: 2
    property real cornerRadius: 4
    property color color: Theme.surface
    readonly property var shadow: Theme.shadows[Math.max(0,Math.min(4,elevation))]
    Repeater {
        model: root.elevation>0 && !Theme.dark ? 3 : 0
        delegate: Rectangle {
            required property int index
            anchors.fill: parent
            radius: root.cornerRadius; color: root.color
            layer.enabled: true
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowColor: '#191918'
                shadowOpacity: index===0 ? root.shadow.ambient : index===1 ? root.shadow.key : root.shadow.contact
                shadowBlur: index===2 ? .13 : root.shadow.blur
                shadowVerticalOffset: index===0 ? 0 : index===1 ? root.shadow.offset : 1
                shadowScale: index===0 ? 1.01 : 1
            }
        }
    }
    Rectangle { anchors.fill: parent; radius: root.cornerRadius; color: Theme.dark && root.elevation>0 ? Qt.lighter(root.color,1+root.elevation*.025) : root.color; border.width:Theme.dark && root.elevation>0 ? 1 : 0;border.color:'#18FFFFFF' }
}
