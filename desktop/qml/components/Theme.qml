pragma Singleton
import QtQuick
QtObject {
    property SystemPalette systemPalette:SystemPalette {colorGroup:SystemPalette.Active}
    readonly property bool dark:ctrl.preferences.appearance==='dark' || (ctrl.preferences.appearance==='system' && systemPalette.window.hslLightness<.4)
    readonly property string family: minchoFamily
    readonly property string displayFamily: typeof interfaceDisplayFamily==='undefined' ? family : interfaceDisplayFamily
    readonly property string editorialFamily: typeof interfaceEditorialFamily==='undefined' ? family : interfaceEditorialFamily
    readonly property color canvas: dark ? ctrl.preferences.dark_background : ctrl.preferences.light_background
    readonly property color surface: dark ? '#2A2A29' : '#F8F7F3'
    readonly property color workspace: dark ? '#1C1C1B' : '#ECECE8'
    readonly property color toolSurface: dark ? '#30302F' : '#FCFBF8'
    readonly property color panelInset: dark ? '#242423' : '#F0F0EB'
    readonly property color panelFooter: dark ? '#282827' : '#F2F1ED'
    readonly property color white: dark ? '#373736' : '#FFFFFF'
    readonly property color ink: dark ? '#ECEBE7' : '#292B27'
    readonly property color secondary: dark ? '#C5C2BB' : '#595B53'
    readonly property color muted: dark ? '#AAA79F' : '#6B6D65'
    readonly property color rule: dark ? '#464643' : '#DDDCD4'
    readonly property color border: dark ? '#66655E' : '#C4C4B9'
    readonly property color accent: dark ? '#BDBAA6' : '#68735C'
    readonly property color accentInk: dark ? '#C9C4B1' : '#59654E'
    readonly property color selection: dark ? '#4B4942' : '#E6E9DE'
    readonly property color hover: dark ? '#3B3A36' : '#EBECE5'
    readonly property color disabled: dark ? '#3A3A37' : '#E7E7DF'
    readonly property color switchOff: dark ? '#55554F' : '#D5D6CE'
    readonly property color switchThumb: '#FFFFFF'
    readonly property color accentText:dark ? '#25241F' : '#FFFFFF'
    readonly property color buttonInk:dark ? '#282723' : '#FFFFFF'
    readonly property color buttonSurface:dark ? '#E4E1D8' : '#292B27'
    readonly property color buttonHover:dark ? '#F0EDE5' : '#343A33'
    readonly property color buttonPressed:dark ? '#CDC8BC' : '#151815'
    readonly property color plotSurface:dark ? '#242423' : '#F1F3EE'
    readonly property color errorSurface:dark ? '#49392F' : '#F4EAE4'
    readonly property color errorInk:dark ? '#E6B69C' : '#803F30'
    readonly property color scrim: '#64252725'
    readonly property int dialogRadius: 12
    readonly property int popupRadius: 8
    readonly property int dialogPadding: 28
    readonly property color compareSurface: dark ? '#F4393936' : '#F4FCFCFB'
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
