import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Column {
    id:root
    objectName:'levelsEditor'
    property string channel:'master'
    readonly property var stored:(ctrl.parameters.levels || {})[channel] || ({black:0,white:1,gamma:1,output_black:0,output_white:1})
    property var draft:({})
    property string editingKey:''
    property string queuedKey:''
    readonly property var current:editingKey ? draft : stored
    readonly property var histogram:(ctrl.levelHistogram || {})[channel] || []
    readonly property color channelColor:({master:Theme.secondary,red:Theme.dark ? '#D79282' : '#B96D62',green:Theme.dark ? '#A5BC84' : '#789472',blue:Theme.dark ? '#8DAACC' : '#6D88A7'})[channel]
    width:parent.width;spacing:12
    function number(key){var value=current[key];return value===undefined ? ((key==='white' || key==='gamma' || key==='output_white') ? 1 : 0) : Number(value)}
    function defaultValue(key){return key==='white' || key==='gamma' || key==='output_white' ? 1 : 0}
    function formatValue(key){return key==='gamma' ? number(key).toFixed(3) : (number(key)*255).toFixed(2)}
    function position(key){return key==='gamma' ? number('black')+(number('white')-number('black'))*Math.pow(.5,number('gamma')) : number(key)}
    function begin(key){
        if(editingKey===key)return
        finish();draft=Object.assign({},stored);editingKey=key;ctrl.beginEdit()
    }
    function bounded(key,value){
        var gap=.0001
        if(key==='gamma')return Math.max(.1,Math.min(10,value))
        if(key==='black')return Math.max(0,Math.min(number('white')-gap,value))
        if(key==='white')return Math.max(number('black')+gap,Math.min(1,value))
        return Math.max(0,Math.min(1,value))
    }
    function change(key,value){
        var next=Object.assign({},draft);next[key]=bounded(key,value);draft=next;queuedKey=key
        if(!commitTimer.running)commitTimer.start()
    }
    function drag(key,value){
        if(!editingKey)begin(key)
        if(key==='gamma') {
            var span=Math.max(.0001,number('white')-number('black'))
            var relative=Math.max(.0001,Math.min(.9999,(value-number('black'))/span))
            value=Math.log(relative)/Math.log(.5)
        }
        change(key,value)
    }
    function flush(){commitTimer.stop();if(queuedKey){var key=queuedKey;queuedKey='';ctrl.setLevelParameter(channel,key,number(key))}}
    function finish(){if(editingKey){flush();editingKey='';ctrl.endEdit()}}
    function commit(key,value){if(!isFinite(value))return;begin(key);change(key,value);finish()}
    function reset(key){commit(key,defaultValue(key))}
    onChannelChanged:{finish();histogramCanvas.requestPaint()}
    onHistogramChanged:histogramCanvas.requestPaint()
    onChannelColorChanged:histogramCanvas.requestPaint()
    Timer {id:commitTimer;interval:16;repeat:false;onTriggered:root.flush()}
    RowLayout {
        width:parent.width;spacing:2
        Repeater {
            model:[{id:'master',name:'RGB'},{id:'red',name:'红'},{id:'green',name:'绿'},{id:'blue',name:'蓝'}]
            delegate:StudioButton {
                required property var modelData;objectName:'levelChannel_'+modelData.id
                text:qsTr(String(modelData.name));quiet:true;selected:root.channel===modelData.id;Layout.fillWidth:true;implicitHeight:32
                Accessible.role:Accessible.RadioButton;Accessible.checked:selected;Accessible.name:qsTr(String(modelData.name+'通道色阶'))
                onClicked:root.channel=modelData.id
            }
        }
        StudioButton {objectName:'autoLevelsButton';text:qsTr(String('自动'));quiet:true;implicitHeight:32;enabled:!ctrl.autoAdjustBusy;Accessible.name:qsTr(String('自动色阶'));onClicked:ctrl.autoAdjust('levels')}
    }
    Item {
        width:parent.width;height:152
        Rectangle {anchors.fill:parent;anchors.bottomMargin:24;color:Theme.white;radius:3}
        Canvas {
            id:histogramCanvas;objectName:'levelsHistogram';x:18;y:0;width:parent.width-36;height:128
            onWidthChanged:requestPaint();onVisibleChanged:if(visible)requestPaint()
            onPaint:{
                var c=getContext('2d');c.reset();c.clearRect(0,0,width,height)
                var bins=root.histogram,max=0
                for(var i=0;i<bins.length;i++)max=Math.max(max,Number(bins[i]) || 0)
                if(!max)return
                c.fillStyle=root.channelColor;c.globalAlpha=.62;c.beginPath();c.moveTo(0,height)
                for(i=0;i<bins.length;i++){var y=height-5-(height-12)*Math.sqrt(Math.max(0,Number(bins[i]) || 0)/max);var x=(i+.5)*width/bins.length;c.lineTo(x,y)}
                c.lineTo(width,height);c.closePath();c.fill()
            }
        }
        Repeater {
            model:[{key:'black',name:'输入黑场',color:Theme.ink},{key:'gamma',name:'输入中间调',color:Theme.secondary},{key:'white',name:'输入白场',color:Theme.surface}]
            delegate:LevelHandle {
                required property var modelData;objectName:'levelHandle_'+modelData.key
                position:root.position(modelData.key);trackWidth:parent.width-36;x:18+position*trackWidth-width/2;y:113
                label:qsTr(String(modelData.name));fillColor:modelData.color
                onEditingStarted:root.begin(modelData.key)
                onValueDragged:function(value){root.drag(modelData.key,value)}
                onEditingFinished:root.finish()
                onResetRequested:root.reset(modelData.key)
            }
        }
    }
    RowLayout {
        width:parent.width;spacing:8
        Repeater {
            model:[{key:'black',name:'输入黑场'},{key:'gamma',name:'中间调'},{key:'white',name:'输入白场'}]
            delegate:Column {
                required property var modelData;Layout.fillWidth:true;Layout.preferredWidth:1;spacing:4
                MinchoText {text:qsTr(String(modelData.name));font.pixelSize:Theme.caption;color:Theme.secondary}
                TextField {
                    id:inputValue;objectName:'levelInput_'+modelData.key;width:parent.width;height:32
                    readonly property string formatted:root.formatValue(modelData.key)
                    text:qsTr(String(formatted));color:Theme.ink;font.family:Theme.family;font.pixelSize:Theme.body;font.features:{'tnum':1}
                    horizontalAlignment:Text.AlignRight;selectByMouse:true;renderType:TextInput.QtRendering;font.hintingPreference:Font.PreferVerticalHinting
                    validator:DoubleValidator {bottom:modelData.key==='gamma' ? .1 : 0;top:modelData.key==='gamma' ? 10 : 255;decimals:3;locale:'C';notation:DoubleValidator.StandardNotation}
                    Accessible.name:qsTr(String(modelData.name+'精确数值'))
                    onFormattedChanged:if(!activeFocus)text=formatted
                    onEditingFinished:{if(acceptableInput && text.trim().length)root.commit(modelData.key,Number(text)/(modelData.key==='gamma' ? 1 : 255));text=formatted}
                    Keys.onEscapePressed:{text=formatted;focus=false}
                    background:Rectangle {radius:3;color:inputValue.activeFocus ? Theme.selection : Theme.surface;border.width:1;border.color:inputValue.activeFocus ? Theme.accent : Theme.border}
                }
            }
        }
    }
    Item {
        width:parent.width;height:40
        Rectangle {
            x:18;y:9;width:parent.width-36;height:8;radius:2;border.width:1;border.color:Theme.rule
            gradient:Gradient {orientation:Gradient.Horizontal;GradientStop {position:0;color:'#252725'}GradientStop {position:1;color:'#FFFFFF'}}
        }
        Repeater {
            model:[{key:'output_black',name:'输出黑场',color:Theme.ink},{key:'output_white',name:'输出白场',color:Theme.surface}]
            delegate:LevelHandle {
                required property var modelData;objectName:'levelHandle_'+modelData.key
                position:root.position(modelData.key);trackWidth:parent.width-36;x:18+position*trackWidth-width/2;y:11
                label:qsTr(String(modelData.name));fillColor:modelData.color;pointingUp:false
                onEditingStarted:root.begin(modelData.key)
                onValueDragged:function(value){root.drag(modelData.key,value)}
                onEditingFinished:root.finish()
                onResetRequested:root.reset(modelData.key)
            }
        }
    }
    RowLayout {
        width:parent.width;spacing:12
        Repeater {
            model:[{key:'output_black',name:'输出黑场'},{key:'output_white',name:'输出白场'}]
            delegate:Column {
                required property var modelData;Layout.fillWidth:true;Layout.preferredWidth:1;spacing:4
                MinchoText {text:qsTr(String(modelData.name));font.pixelSize:Theme.caption;color:Theme.secondary}
                TextField {
                    id:outputValue;objectName:'levelInput_'+modelData.key;width:parent.width;height:32
                    readonly property string formatted:root.formatValue(modelData.key)
                    text:qsTr(String(formatted));color:Theme.ink;font.family:Theme.family;font.pixelSize:Theme.body;font.features:{'tnum':1}
                    horizontalAlignment:Text.AlignRight;selectByMouse:true;renderType:TextInput.QtRendering;font.hintingPreference:Font.PreferVerticalHinting
                    validator:DoubleValidator {bottom:0;top:255;decimals:3;locale:'C';notation:DoubleValidator.StandardNotation}
                    Accessible.name:qsTr(String(modelData.name+'精确数值'))
                    onFormattedChanged:if(!activeFocus)text=formatted
                    onEditingFinished:{if(acceptableInput && text.trim().length)root.commit(modelData.key,Number(text)/255);text=formatted}
                    Keys.onEscapePressed:{text=formatted;focus=false}
                    background:Rectangle {radius:3;color:outputValue.activeFocus ? Theme.selection : Theme.surface;border.width:1;border.color:outputValue.activeFocus ? Theme.accent : Theme.border}
                }
            }
        }
    }
}
