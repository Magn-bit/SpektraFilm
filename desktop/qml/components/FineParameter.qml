import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
Column {
    id: root
    objectName: 'parameter_'+parameter
    property string label: ''
    property string parameter: ''
    property real minimum: 0
    property real maximum: 100
    property real step: 1
    // The slider keeps a comfortable coarse travel step. Shift+arrow uses
    // this real value and sends it all the way through Settings unchanged.
    property real fineStep: step / 10
    readonly property real coarseStep: step * 10
    property string unit: ''
    property bool signedValue: false
    property bool emphasized: false
    property bool directParameter: true
    property bool controllerReset: directParameter
    property bool recordEdits: true
    property real externalValue: 0
    property var trackColors: []
    signal valueEdited(real value)
    // Consumers such as the local-adjustment panel can temporarily change
    // visual presentation while a value is being edited. The signal pair is
    // emitted once per pointer/keyboard transaction, not once per frame.
    signal editingStarted()
    signal editingFinished()
    property real defaultValue: ({exposure:0,halation:12,glare:0,vignette:0,strength:100,grain:18,grain_size:1,print_exposure:0,print_y:0,print_m:0,temperature:6500,tint:0,white_point:100,gamma:1,contrast:0,saturation:0,vibrance:0,shadows:0,highlights:0,whites:0,blacks:0,calibration_red_hue:0,calibration_red_saturation:0,calibration_green_hue:0,calibration_green_saturation:0,calibration_blue_hue:0,calibration_blue_saturation:0})[parameter] || 0
    readonly property bool modified: Math.abs(slider.value-defaultValue)>.00001
    readonly property int stepDecimals: decimalPlaces(root.step)
    readonly property int fineDecimals: decimalPlaces(root.fineStep)
    property bool keyboardEditing: false
    property bool pointerEditing: false
    property real pointerValue: 0
    width: parent.width; spacing: 2
    function beginTransaction() {if(recordEdits)ctrl.beginEdit();root.editingStarted()}
    function endTransaction() {if(recordEdits)ctrl.endEdit();root.editingFinished()}
    function sendValue(value) {if(directParameter)ctrl.updateParameter(parameter,value);else valueEdited(value)}
    function queuePointerValue() {if(!pointerCommitTimer.running)pointerCommitTimer.start()}
    function flushPointerValue() {
        pointerCommitTimer.stop()
        if(pointerEditing)sendValue(snap(pointerValue,fineStep))
    }
    function decimalPlaces(value) {
        var amount=Math.abs(Number(value));
        if(!isFinite(amount) || amount<=0)return 0;
        var places=0;
        while(places<6 && Math.abs(amount-Math.round(amount))>0.00000001) { amount*=10; places++; }
        return places;
    }
    function snap(value, increment) {
        increment=Math.abs(Number(increment));
        if(!increment || !isFinite(increment))return value;
        return Math.round((value+1e-9)/increment)*increment;
    }
    function finishKeyboardEdit() {
        keyboardEditTimer.stop();
        if(root.keyboardEditing) { root.keyboardEditing=false; root.endTransaction(); }
    }
    function adjustByKeyboard(delta) {
        if(!root.enabled || !isFinite(delta))return;
        var next=Math.max(root.minimum,Math.min(root.maximum,root.snap(Number(slider.value)+delta,root.fineStep)));
        if(Math.abs(next-slider.value)<0.00000001)return;
        if(!root.keyboardEditing) { root.beginTransaction(); root.keyboardEditing=true; }
        root.sendValue(next);
        valueField.editingDirty=false;
        valueField.text=root.formatValue(next);
        keyboardEditTimer.restart();
    }
    function keyboardDelta(event) {
        if(event.modifiers & (Qt.ControlModifier | Qt.MetaModifier))return 0;
        var positive=event.key===Qt.Key_Right || event.key===Qt.Key_Up;
        var negative=event.key===Qt.Key_Left || event.key===Qt.Key_Down;
        if(!positive && !negative)return 0;
        var increment=(event.modifiers & Qt.ShiftModifier) ? root.fineStep :
                     (event.modifiers & Qt.AltModifier) ? root.coarseStep : root.step;
        return (positive ? 1 : -1)*increment;
    }
    function commit(value) {
        if(!root.enabled || !isFinite(value))return;
        root.finishKeyboardEdit();
        value=Math.max(root.minimum,Math.min(root.maximum,root.snap(Number(value),root.fineStep)));
        if(Math.abs(value-slider.value)>.00001) {root.beginTransaction();root.sendValue(value);root.endTransaction()}
    }
    function resetValue() {root.finishKeyboardEdit();if(controllerReset)ctrl.resetParameter(parameter);else commit(defaultValue)}
    function formatValue(value) {
        // Keep the compact coarse display for ordinary values, but expose a
        // finer value as soon as a Shift+arrow or precise entry created one.
        var coarse=root.snap(Number(value),root.step);
        var digits=Math.abs(Number(value)-coarse)>.00000001 ? root.fineDecimals : root.stepDecimals;
        var result=Number(value).toFixed(digits);
        if(root.signedValue && Number(value)>0) result='+'+result;
        return result;
    }
    RowLayout {
        width: parent.width
        MinchoText {
            text: qsTr(String(root.label)); Layout.fillWidth: true
            color: root.enabled ? Theme.ink : Theme.muted
            MouseArea {
                anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.LeftButton | Qt.RightButton
                onDoubleClicked: root.resetValue()
                onClicked: function(mouse) {if(mouse.button===Qt.RightButton)parameterMenu.popup()}
                ToolTip.visible: containsMouse
                ToolTip.delay: 700
                ToolTip.text: qsTr(String('双击标签恢复默认值；右键可重置'))
            }
        }
        TextField {
            id: valueField; objectName: 'parameterValue_'+root.parameter
            property bool editingDirty: false
            text: qsTr(String(root.formatValue(slider.value))); implicitWidth: 76; implicitHeight: 28
            font.family: Theme.family; font.pixelSize: Theme.body; font.weight: Font.Normal
            font.hintingPreference: Font.PreferVerticalHinting
            renderType: TextInput.QtRendering
            font.features: { 'tnum': 1 }
            color: root.enabled ? Theme.ink : Theme.secondary; horizontalAlignment: Text.AlignRight
            selectByMouse: true; inputMethodHints: Qt.ImhFormattedNumbersOnly
            onTextEdited: editingDirty=true
            validator: DoubleValidator { bottom: root.minimum; top: root.maximum; decimals: root.fineDecimals; locale: 'en_US'; notation: DoubleValidator.StandardNotation }
            Accessible.name: qsTr(String(root.label+'数值')); Accessible.description: qsTr(String('可直接输入精确数值；方向键按步进调整，Shift 为细调，Alt 为粗调'))
            Keys.onEscapePressed: { root.finishKeyboardEdit(); editingDirty=false; text=root.formatValue(slider.value); focus=false }
            Keys.onPressed: function(event) {
                var delta=(event.key===Qt.Key_Up || event.key===Qt.Key_Down) ? root.keyboardDelta(event) : 0;
                if(delta!==0) { root.adjustByKeyboard(delta); event.accepted=true; }
            }
            Keys.onReleased: function(event) { if(!event.isAutoRepeat && root.keyboardDelta(event)!==0)root.finishKeyboardEdit(); }
            onActiveFocusChanged: if(!activeFocus) {root.finishKeyboardEdit();editingDirty=false; text=root.formatValue(slider.value)}
            onEditingFinished: {
                if(acceptableInput && text.trim().length>0)root.commit(Number(text.trim()));
                editingDirty=false;
                text=root.formatValue(slider.value)
            }
            background: Rectangle { radius: 4; color: valueField.activeFocus ? Theme.selection : 'transparent'; border.width: valueField.activeFocus ? 1 : 0; border.color: Theme.accent }
        }
        MinchoText { visible: root.unit.length>0; text: qsTr(String(root.unit)); Layout.preferredWidth: root.unit==='EV' ? 22 : 14; color: root.enabled ? Theme.secondary : Theme.muted; horizontalAlignment: Text.AlignRight }
    }
    Slider {
        id: slider; objectName: 'parameterSlider_'+root.parameter; width: parent.width; height: 32; hoverEnabled: true; activeFocusOnTab: true
        from: root.minimum; to: root.maximum; stepSize: root.step
        value: root.pointerEditing ? root.pointerValue : root.directParameter ? (ctrl.parameters[root.parameter] || 0) : root.externalValue
        Accessible.name: qsTr(String(root.label)); Accessible.description: qsTr(String(root.formatValue(value)+' '+root.unit+'；方向键按步进，Shift 细调，Alt 粗调；双击圆点恢复默认值'))
        onValueChanged: if(!valueField.activeFocus || !valueField.editingDirty) valueField.text=root.formatValue(value)
        // Pointer input has one owner. A TapHandler in the handle used to
        // compete with Slider's implicit grab and could consume the first drag.
        // Keep Slider's native keyboard/accessibility semantics and handle the
        // complete mouse transaction in the MouseArea below.
        onMoved: { if(!pressed)root.beginTransaction();root.sendValue(value);if(!pressed)root.endTransaction() }
        Keys.onPressed: function(event) {
            var delta=root.keyboardDelta(event);
            if(delta!==0) {root.adjustByKeyboard(delta);event.accepted=true}
            else if(event.key===Qt.Key_Home) {root.commit(root.minimum);event.accepted=true}
            else if(event.key===Qt.Key_End) {root.commit(root.maximum);event.accepted=true}
            else if(event.key===Qt.Key_Menu) {parameterMenu.popup();event.accepted=true}
        }
        Keys.onReleased: function(event) { if(!event.isAutoRepeat && root.keyboardDelta(event)!==0)root.finishKeyboardEdit(); }
        onActiveFocusChanged: if(!activeFocus)root.finishKeyboardEdit()
        background: Item {
            x: slider.leftPadding; y: slider.topPadding+slider.availableHeight/2-1
            width: slider.availableWidth; height: 4
            Rectangle { width: parent.width; height: 3; radius: 2; color: Theme.rule; y: .5; visible: root.trackColors.length===0 }
            Rectangle {
                width: parent.width; height: 4; radius: 2; visible: root.trackColors.length>0
                opacity: root.enabled ? 1 : .4
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop {position:0;color:root.trackColors.length ? root.trackColors[0] : Theme.rule}
                    GradientStop {position:.5;color:root.trackColors.length ? root.trackColors[Math.min(1,root.trackColors.length-1)] : Theme.rule}
                    GradientStop {position:1;color:root.trackColors.length ? root.trackColors[root.trackColors.length-1] : Theme.rule}
                }
            }
            Rectangle { visible: root.trackColors.length===0; width: slider.visualPosition*parent.width; height: 3; radius: 2; color: root.enabled ? Theme.accentInk : Theme.border; y: .5 }
            Rectangle { visible: root.minimum<0; width: 1; height: 8; x: (-root.minimum/(root.maximum-root.minimum))*parent.width; y: -2; color: Theme.secondary }
        }
        handle: Rectangle {
            objectName: 'parameterHandle_'+root.parameter
            x: slider.leftPadding+slider.visualPosition*(slider.availableWidth-width)
            y: slider.topPadding+slider.availableHeight/2-height/2
            width: 12; height: 12; radius: 6; color: !root.enabled ? Theme.border : root.pointerEditing || slider.pressed ? Theme.accentInk : Theme.ink
            scale: root.pointerEditing || slider.pressed ? 1.22 : slider.hovered ? 1.1 : 1
            Behavior on scale { NumberAnimation { duration: Theme.fast; easing.type: Theme.easing } }
            Rectangle { anchors.fill: parent; anchors.margins: -5; radius: 10; color: 'transparent'; border.width: 1; border.color: Theme.accent; visible: slider.visualFocus }
        }
        MouseArea {
            id: pointer; objectName: 'parameterPointer_'+root.parameter
            anchors.fill: parent; z: 2; acceptedButtons: Qt.LeftButton | Qt.RightButton
            preventStealing: true; hoverEnabled: true
            property real anchorX: 0
            property real anchorValue: 0
            property bool fine: false
            readonly property real travel: Math.max(1,slider.availableWidth-slider.handle.width)
            function finish() {
                if(!root.pointerEditing)return
                // Commit the final point before ending the one undo transaction.
                root.flushPointerValue()
                root.pointerEditing=false
                root.endTransaction()
            }
            function update(px,modifiers) {
                var nextFine=!!(modifiers & Qt.ShiftModifier)
                if(nextFine!==fine) {anchorX=px;anchorValue=root.pointerValue;fine=nextFine}
                var next=anchorValue+(px-anchorX)*(root.maximum-root.minimum)/travel*(fine ? .1 : 1)
                root.pointerValue=Math.max(root.minimum,Math.min(root.maximum,next))
                // Keep pointer feedback local; coalesce backend preview work
                // below while always flushing the final value on release.
                root.queuePointerValue()
            }
            onPressed: function(mouse) {
                if(mouse.button===Qt.RightButton) {parameterMenu.popup();return}
                root.finishKeyboardEdit();slider.forceActiveFocus(Qt.MouseFocusReason)
                anchorValue=slider.value;anchorX=mouse.x;fine=!!(mouse.modifiers & Qt.ShiftModifier)
                root.pointerValue=anchorValue;root.pointerEditing=true;root.beginTransaction()
                var center=slider.leftPadding+slider.handle.width/2+slider.position*travel
                if(Math.abs(mouse.x-center)>16) {
                    root.pointerValue=Math.max(root.minimum,Math.min(root.maximum,root.minimum+(mouse.x-slider.leftPadding-slider.handle.width/2)/travel*(root.maximum-root.minimum)))
                    anchorValue=root.pointerValue
                    root.queuePointerValue()
                }
            }
            onPositionChanged: function(mouse) {if(pressed && root.pointerEditing)update(mouse.x,mouse.modifiers)}
            onReleased: function(mouse) {if(root.pointerEditing){update(mouse.x,mouse.modifiers);finish()}}
            onCanceled: finish()
            onDoubleClicked: function(mouse) {
                if(mouse.button===Qt.LeftButton) {finish();root.resetValue()}
            }
        }
    }
    Menu {
        id: parameterMenu
        background: ShadowSurface { elevation: 2; cornerRadius: Theme.popupRadius; color: Theme.white }
        MenuItem { text: qsTr(String('恢复默认值')); enabled: root.modified; onTriggered: root.resetValue(); font.family: Theme.family }
    }
    Timer { id: keyboardEditTimer; interval: 1200; repeat: false; onTriggered: root.finishKeyboardEdit() }
    Timer { id: pointerCommitTimer; interval: 32; repeat: false; onTriggered: root.flushPointerValue() }
}
