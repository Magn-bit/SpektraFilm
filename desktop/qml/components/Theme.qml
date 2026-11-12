pragma Singleton
import QtQuick
QtObject {
    property SystemPalette systemPalette:SystemPalette {colorGroup:SystemPalette.Active}
    readonly property bool dark:ctrl.preferences.appearance==='dark' || (ctrl.preferences.appearance==='system' && systemPalette.window.hslLightness<.4)
    readonly property string family: minchoFamily
    readonly property string displayFamily: typeof interfaceDisplayFamily==='undefined' ? family : interfaceDisplayFamily
    readonly property string editorialFamily: typeof interfaceEditorialFamily==='undefined' ? family : interfaceEditorialFamily
    readonly property color canvas: dark ? ctrl.preferences.dark_background : ctrl.preferences.light_background
    readonly property color surface: dark ? '#30332E' : '#F8F7F3'
    readonly property color white: dark ? '#373B34' : '#FFFFFF'
    readonly property color ink: dark ? '#E9EAE2' : '#292B27'
    readonly property color secondary: dark ? '#BEC3B5' : '#595B53'
    readonly property color muted: dark ? '#A6AD9C' : '#6B6D65'
    readonly property color rule: dark ? '#454B3F' : '#DDDCD4'
    readonly property color border: dark ? '#68705F' : '#C4C4B9'
    readonly property color accent: dark ? '#A9BA94' : '#68735C'
    readonly property color accentInk: dark ? '#B5C5A2' : '#59654E'
    readonly property color selection: dark ? '#46513D' : '#E6E9DE'
    readonly property color hover: dark ? '#3C4336' : '#EBECE5'
    readonly property color disabled: dark ? '#3A3E35' : '#E7E7DF'
    readonly property color switchOff: dark ? '#50584A' : '#D5D6CE'
    readonly property color switchThumb: '#FFFFFF'
    readonly property color accentText:dark ? '#23281E' : '#FFFFFF'
    readonly property color buttonInk:dark ? '#24291F' : '#FFFFFF'
    readonly property color buttonSurface:dark ? '#E3E7DA' : '#292B27'
    readonly property color buttonHover:dark ? '#F0F2E9' : '#343A33'
    readonly property color buttonPressed:dark ? '#C9D3BC' : '#151815'
    readonly property color plotSurface:dark ? '#252A23' : '#F1F3EE'
    readonly property color errorSurface:dark ? '#49392F' : '#F4EAE4'
    readonly property color errorInk:dark ? '#E6B69C' : '#803F30'
    readonly property color scrim: '#64252725'
    readonly property int dialogRadius: 12
    readonly property int popupRadius: 8
    readonly property int dialogPadding: 28
    readonly property color compareSurface: dark ? '#F4394034' : '#F4FCFCFB'
    readonly property color compareLine: '#F2FFFFFF'
    readonly property color compareEdge: '#34252725'
    readonly property int compareHandleSize: 26
    readonly property int compareHitWidth: 44
    readonly property int display: 32
    readonly property int heading: 18
    readonly property int body: 15
    readonly property int caption: 14
    readonly property int bodyWeight: Font.Normal
    readonly property int scrollBarLane: 12
    readonly property int scrollBarGutter: 20
    property bool reducedMotion: systemReduceMotion
    readonly property int fast: reducedMotion ? 0 : 140
    readonly property int standard: reducedMotion ? 0 : 240
    readonly property int panel: reducedMotion ? 0 : 360
    readonly property int page: reducedMotion ? 0 : 480
    readonly property int easing: Easing.OutCubic
    readonly property var shadows: [
        {ambient:0,key:0,contact:0,blur:0,offset:0},
        {ambient:.025,key:.035,contact:.035,blur:.25,offset:1},
        {ambient:.045,key:.065,contact:.045,blur:.48,offset:4},
        {ambient:.065,key:.09,contact:.055,blur:.68,offset:9},
        {ambient:.085,key:.12,contact:.06,blur:.85,offset:14}
    ]
}
