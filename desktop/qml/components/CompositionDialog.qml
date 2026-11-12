import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

StudioDialog {
    id:root;objectName:'compositionDialog'
    property var workspace:ctrl.composition
    readonly property var layoutState:workspace.state
    property int tool:0
    property int frameCategory:0
    property bool presetExpanded:false
    property bool linkFrames:false
    readonly property bool filmEdge:layoutState.style==='film'||layoutState.style==='half_frame'
    anchors.centerIn:parent;width:parent.width-40;height:parent.height-40;padding:20
    closePolicy:layoutState.busy ? Popup.NoAutoClose : Popup.CloseOnEscape
    onOpened:{frameCategory=filmEdge ? 0 : 1;presetExpanded=false;workspace.requestFrameTemplates(false)}
    onFilmEdgeChanged:if(opened)frameCategory=filmEdge ? 0 : 1
    onClosed:workspace.requestFrameTemplates(false)
    function selectedPhoto(){return layoutState.photos.length ? layoutState.photos[Math.max(0,Math.min(layoutState.active,layoutState.photos.length-1))] : ({})}
    function source(index){return layoutState.photos.length>index ? layoutState.photos[index].source : ''}
    function focusTemplate(index){var item=templates.itemAt((index+4)%4);if(item&&item.enabled)item.forceActiveFocus(Qt.TabFocusReason)}
    function focusPreset(index){var count=physicalPresets.count;for(var step=0;step<count;step++){var item=physicalPresets.itemAt((index+step+count)%count);if(item&&item.enabled){item.forceActiveFocus(Qt.TabFocusReason);return}}}
    function editZoom(value){var p=selectedPhoto();if(linkFrames)workspace.positionGroup(layoutState.group_pan_x,layoutState.group_pan_y,value);else workspace.position(layoutState.active,Number(p.pan_x),Number(p.pan_y),value)}
    contentItem:ColumnLayout {
        spacing:14
        RowLayout {
            Layout.fillWidth:true;spacing:14
            MinchoText {text:qsTr(String('排版'));font.pixelSize:Theme.heading;Layout.fillWidth:true}
            MinchoText {text:qsTr(String(layoutState.photos.length+' 张 · '+(root.filmEdge ? (layoutState.edge>0 ? '长边 '+layoutState.edge+' px' : '原像素') : layoutState.width+' × '+layoutState.height)));font.pixelSize:Theme.caption;color:Theme.secondary}
            StudioButton {objectName:'openHalfFrame';text:qsTr('打开半格');quiet:true;enabled:!layoutState.busy;onClicked:workspace.openPair()}
            StudioButton {objectName:'saveHalfFrame';text:qsTr('保存半格');quiet:true;visible:layoutState.style==='half_frame';enabled:!layoutState.busy;onClicked:workspace.savePair()}
            StudioButton {text:qsTr(String('返回编辑'));quiet:true;enabled:!layoutState.exporting;onClicked:root.close()}
        }
        RowLayout {
            Layout.fillHeight:true;Layout.fillWidth:true;spacing:20
            Rectangle {
                id:previewSurface;objectName:'compositionPreview'
                Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumWidth:420
                color:Theme.canvas;radius:8;clip:true
                Item {
                    id:canvas;objectName:'compositionCanvas'
                    readonly property real fit:Math.min(Math.max(1,previewSurface.width-48)/Math.max(1,layoutState.width),Math.max(1,previewSurface.height-48)/Math.max(1,layoutState.height))
                    width:Math.max(1,layoutState.width*fit);height:Math.max(1,layoutState.height*fit);anchors.centerIn:parent
                    Rectangle {anchors.fill:parent;color:layoutState.color}
                    Image {objectName:'compositionNativeCanvas';anchors.fill:parent;source:layoutState.native_canvas||'';visible:source.toString().length>0;cache:false;asynchronous:false;smooth:true}
                    Repeater {
                        model:workspace.photoCells
                        delegate:Item {
                            id:cell;required property int index;required property var entry;readonly property var photo:entry
                            objectName:'compositionCell_'+index
                            x:photo.rect[0]*canvas.width;y:photo.rect[1]*canvas.height;width:photo.rect[2]*canvas.width;height:photo.rect[3]*canvas.height;clip:true
                            readonly property real cover:Math.max(width/Math.max(1,photo.width),height/Math.max(1,photo.height))*photo.zoom
                            Item {
                                width:cell.photo.width*cell.cover;height:cell.photo.height*cell.cover
                                x:-(width-cell.width)*cell.photo.pan_x;y:-(height-cell.height)*cell.photo.pan_y
                                Image {
                                    objectName:'compositionImage_'+cell.index;readonly property bool imageReady:status===Image.Ready
                                    anchors.centerIn:parent;width:cell.photo.sourceWidth*cell.cover;height:cell.photo.sourceHeight*cell.cover
                                    rotation:-Number(cell.photo.rotation||0);source:cell.photo.source;asynchronous:true;cache:false;smooth:true;visible:!layoutState.native_canvas
                                }
                            }
                            Rectangle {anchors.fill:parent;color:'transparent';border.width:root.tool===1&&(root.linkFrames||layoutState.active===cell.index) ? 1 : 0;border.color:Theme.accent}
                            MouseArea {
                                anchors.fill:parent;enabled:!layoutState.exporting;preventStealing:true
                                cursorShape:pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                                property real px:0;property real py:0;property real startX:0;property real startY:0
                                onPressed:function(mouse){workspace.select(cell.index);px=mouse.x;py=mouse.y;startX=root.linkFrames ? layoutState.group_pan_x : cell.photo.pan_x;startY=root.linkFrames ? layoutState.group_pan_y : cell.photo.pan_y}
                                onPositionChanged:function(mouse){if(pressed){var dx=(mouse.x-px)/Math.max(1,cell.photo.width*cell.cover-cell.width);var dy=(mouse.y-py)/Math.max(1,cell.photo.height*cell.cover-cell.height);var turn=(layoutState.group_turn+(layoutState.style==='half_frame'&&layoutState.pair_axis==='vertical' ? 3 : 0))%4;var ax=turn===1 ? -dy : turn===2 ? -dx : turn===3 ? dy : dx;var ay=turn===1 ? dx : turn===2 ? -dy : turn===3 ? -dx : dy;var x=startX-ax;var y=startY-ay;if(root.linkFrames)workspace.positionGroup(x,y,layoutState.group_zoom);else workspace.position(cell.index,x,y,cell.photo.zoom)}}
                                onDoubleClicked:{if(root.linkFrames)workspace.resetGroupPosition();else workspace.resetPosition()}
                                onWheel:function(wheel){var z=(root.linkFrames ? layoutState.group_zoom : cell.photo.zoom)*(wheel.angleDelta.y>0 ? 1.08 : 1/1.08);if(root.linkFrames)workspace.positionGroup(layoutState.group_pan_x,layoutState.group_pan_y,z);else workspace.position(cell.index,cell.photo.pan_x,cell.photo.pan_y,z);wheel.accepted=true}
                                Accessible.name:qsTr(String(cell.photo.name+'，拖动取景，滚轮缩放'))
                            }
                        }
                    }
                    Image {objectName:'compositionEdgeOverlay';anchors.fill:parent;source:layoutState.overlay||'';visible:source.toString().length>0;cache:false;asynchronous:false;smooth:true;z:4}
                    Repeater {model:layoutState.decorations ? layoutState.decorations.bands : [];delegate:Rectangle {required property var modelData;x:modelData[0]*canvas.width;y:modelData[1]*canvas.height;width:modelData[2]*canvas.width;height:modelData[3]*canvas.height;color:layoutState.style==='instant' ? '#F5F0E3' : '#262E24';z:4}}
                    Repeater {model:layoutState.decorations ? layoutState.decorations.rules : [];delegate:Rectangle {required property var modelData;x:modelData[0]*canvas.width;y:modelData[1]*canvas.height;width:Math.max(1,(modelData[2]-modelData[0])*canvas.width);height:Math.max(1,(modelData[3]-modelData[1])*canvas.height);color:'transparent';border.width:1;border.color:'#72786E';z:4}}
                    Repeater {model:layoutState.show_info&&layoutState.decorations ? layoutState.decorations.labels : [];delegate:MinchoText {required property var modelData;text:qsTr(String(modelData.text||''));x:modelData.x*canvas.width;y:modelData.y*canvas.height;width:Math.max(1,modelData.width*canvas.width);font.pixelSize:Math.max(1,layoutState.margin*canvas.fit*.32);color:layoutState.style==='contact' ? '#CBD3C3' : '#404339';elide:Text.ElideRight;z:5}}
                }
            }
            Item {
                Layout.preferredWidth:Math.max(300,Math.min(360,parent.width*.29));Layout.maximumWidth:360;Layout.minimumWidth:280;Layout.fillHeight:true
                ShadowSurface {anchors.fill:parent;cornerRadius:10;elevation:1;color:Theme.toolSurface}
                ColumnLayout {
                anchors.fill:parent;anchors.margins:12;spacing:14
                Item {
                    Layout.fillWidth:true;Layout.preferredHeight:42
                    Rectangle {anchors.fill:parent;radius:6;color:Theme.panelInset}
                    RowLayout {
                    anchors.fill:parent;anchors.margins:3;spacing:4
                    Repeater {model:['边框','取景','图饰'];StudioButton {required property int index;required property string modelData;objectName:'compositionTool_'+index;text:qsTr(String(modelData));quiet:true;selected:root.tool===index;Layout.fillWidth:true;onClicked:root.tool=index}}
                }
                }
                ScrollView {
                    id:options;objectName:'compositionOptionsViewport';Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumHeight:0;Layout.preferredHeight:1;clip:true;contentWidth:availableWidth;contentHeight:optionsContent.implicitHeight;rightPadding:12
                    ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                    Column {
                        id:optionsContent;width:options.availableWidth;spacing:18;enabled:!layoutState.exporting
                        Column {
                            visible:root.tool===0;width:parent.width;spacing:14
                            RowLayout {
                                width:parent.width;spacing:4
                                StudioButton {text:qsTr(String('胶片片边'));quiet:true;selected:root.frameCategory===0;Layout.fillWidth:true;onClicked:root.frameCategory=0}
                                StudioButton {text:qsTr(String('纸面排版'));quiet:true;selected:root.frameCategory===1;Layout.fillWidth:true;onClicked:root.frameCategory=1}
                            }
                            ToolSection {
                                id:frameStyleSection;objectName:'compositionPresetSection';visible:root.frameCategory===0
                                title:qsTr(String('样式'));detail:qsTr(String(layoutState.frame_preset_name||''));expanded:root.presetExpanded
                                onToggled:{root.presetExpanded=!root.presetExpanded;workspace.requestFrameTemplates(root.presetExpanded)}
                            GridLayout {
                                objectName:'compositionPhysicalFrameSelector';width:parent.width;columns:2;columnSpacing:8;rowSpacing:8
                                Repeater {
                                    id:physicalPresets;model:layoutState.frame_presets||[]
                                    CompositionFrameTile {
                                        required property int index;required property var modelData
                                        objectName:modelData.id==='film_135' ? 'compositionTemplate_film' : modelData.id==='film_half' ? 'compositionTemplate_half_frame' : 'compositionPreset_'+modelData.id
                                        Layout.fillWidth:true;Layout.preferredWidth:(parent.width-8)/2;Layout.minimumWidth:0;Layout.maximumWidth:(parent.width-8)/2
                                        physicalFrame:true;treatment:modelData.style;title:qsTr(String(modelData.name));nativeSource:modelData.source||''
                                        thumbnailLoading:modelData.loading
                                        chosen:modelData.selected;enabled:modelData.enabled
                                        onClicked:workspace.applyFramePreset(modelData.id)
                                    }
                                }
                            }
                            }
                            Column {
                                visible:root.filmEdge&&root.frameCategory===0;width:parent.width;spacing:12
                                MaterialSelector {objectName:'compositionGauge';label:qsTr(String('片幅'));fillField:true;value:layoutState.style==='half_frame' ? '135_half' : layoutState.frame_format;enabled:layoutState.style!=='half_frame';choices:layoutState.frame_formats||[];onSelected:function(v){workspace.setOption('frame_format',v)}}
                                MaterialSelector {objectName:'compositionEdgeView';visible:layoutState.style!=='half_frame'||layoutState.pair_on_strip;label:qsTr(String('边缘'));fillField:true;value:layoutState.edge_view;choices:[{id:'strip',name:'完整片条'},{id:'filed',name:'片夹开窗'}];onSelected:function(v){workspace.setOption('edge_view',v)}}
                            }
                            GridLayout {
                                objectName:'compositionFrameSelector';visible:root.frameCategory===1;width:parent.width;columns:2;columnSpacing:8;rowSpacing:8
                                Repeater {
                                    id:templates
                                    model:[{id:'plain',name:'无边框'},{id:'paper',name:'留白纸张'},{id:'instant',name:'即影纸边'},{id:'contact',name:'接触印样'}]
                                    CompositionFrameTile {
                                        required property int index;required property var modelData;objectName:'compositionTemplate_'+modelData.id
                                        Layout.fillWidth:true;Layout.preferredWidth:(parent.width-8)/2;Layout.minimumWidth:0;Layout.maximumWidth:(parent.width-8)/2
                                        treatment:modelData.id;title:qsTr(String(modelData.name));photoSource:root.source(0);secondSource:root.source(1)
                                        chosen:layoutState.style===modelData.id
                                        enabled:layoutState.photos.length>0
                                        onClicked:workspace.setOption('style',modelData.id)
                                        Keys.onLeftPressed:root.focusTemplate(index-1)
                                        Keys.onRightPressed:root.focusTemplate(index+1)
                                        Keys.onUpPressed:root.focusTemplate(index-2)
                                        Keys.onDownPressed:root.focusTemplate(index+2)
                                    }
                                }
                            }
                            Column {
                                visible:root.filmEdge&&root.frameCategory===0;width:parent.width;spacing:12
                                MaterialSelector {visible:layoutState.style==='half_frame';label:qsTr(String('双图方向'));fillField:true;value:layoutState.pair_axis;choices:[{id:'horizontal',name:'横向'},{id:'vertical',name:'纵向'}];onSelected:function(v){workspace.setOption('pair_axis',v)}}
                                RowLayout {width:parent.width;visible:layoutState.style==='half_frame';MinchoText {text:qsTr('胶片片边');Layout.fillWidth:true}StudioSwitch {Accessible.name:qsTr('胶片片边');objectName:'pairStripSwitch';checked:layoutState.pair_on_strip;onToggled:workspace.setOption('pair_on_strip',checked)}}
                                FineParameter {objectName:'pairSpacing';label:qsTr('半格间距');directParameter:false;recordEdits:false;defaultValue:1;visible:layoutState.style==='half_frame';enabled:!layoutState.pair_on_strip;externalValue:layoutState.pair_effective_spacing;minimum:.5;maximum:2;step:.01;unit:' mm';onValueEdited:function(v){workspace.setOption('pair_spacing_mm',v)}}
                                Column {width:parent.width;spacing:12;visible:layoutState.style!=='half_frame'||layoutState.pair_on_strip
                                MaterialSelector {visible:layoutState.style!=='half_frame'&&layoutState.photos.length>1;label:qsTr(String('排列'));fillField:true;value:layoutState.layout;choices:[{id:'grid',name:'网格'},{id:'horizontal',name:'横向片条'},{id:'vertical',name:'纵向片条'}];onSelected:function(v){workspace.setOption('layout',v)}}
                                RowLayout {width:parent.width;MinchoText {text:qsTr(String('胶片字样'));Layout.fillWidth:true}StudioSwitch {Accessible.name:qsTr('胶片字样');objectName:'edgePrintToggle';checked:layoutState.edge_print;onToggled:workspace.setOption('edge_print',checked)}}
                                MaterialSelector {label:qsTr(String('片孔'));fillField:true;value:layoutState.holes;enabled:layoutState.frame_format.indexOf('120')!==0||layoutState.style==='half_frame';choices:[{id:'light',name:'透光'},{id:'black',name:'遮黑'}];onSelected:function(v){workspace.setOption('holes',v)}}
                                FineParameter {label:qsTr(String('起始格号'));directParameter:false;recordEdits:false;defaultValue:12;externalValue:layoutState.frame_number;minimum:0;maximum:99;step:1;onValueEdited:function(v){workspace.setOption('frame_number',Math.round(v))}}
                                MaterialSelector {label:qsTr(String('片门'));fillField:true;value:layoutState.gate;choices:[{id:'auto',name:'随片幅'},{id:'square',name:'直角'},{id:'rounded',name:'圆角'},{id:'eared',name:'带耳片门'},{id:'shouldered',name:'肩形片门'},{id:'kicked',name:'切角片门'}];onSelected:function(v){workspace.setOption('gate',v)}}
                                MaterialSelector {label:qsTr(String('片夹'));fillField:true;value:layoutState.carrier;choices:[{id:'none',name:'无片夹'},{id:'black',name:'黑色片夹'},{id:'open',name:'透光片夹'}];onSelected:function(v){workspace.setOption('carrier',v)}}
                                FineParameter {label:qsTr(String('片基雾化'));directParameter:false;recordEdits:false;defaultValue:1;externalValue:layoutState.fog;minimum:0;maximum:4;step:.01;onValueEdited:function(v){workspace.setOption('fog',v)}}
                                FineParameter {objectName:'compositionLeaks';label:qsTr(String('漏光'));directParameter:false;recordEdits:false;externalValue:layoutState.leaks;minimum:0;maximum:4;step:.01;onValueEdited:function(v){workspace.setOption('leaks',v)}}
                                }
                            }
                            Column {
                                visible:!root.filmEdge&&root.frameCategory===1;width:parent.width;spacing:12
                                MaterialSelector {label:qsTr(String('布局'));fillField:true;value:layoutState.layout;enabled:layoutState.photos.length>1;choices:[{id:'grid',name:'网格'},{id:'horizontal',name:'横向'},{id:'vertical',name:'纵向'},{id:'feature',name:'主图与片格'}];onSelected:function(v){workspace.setOption('layout',v)}}
                                MaterialSelector {label:qsTr(String('画幅'));fillField:true;value:String(layoutState.ratio);choices:[{id:'1.5',name:'3:2'},{id:'1',name:'1:1'},{id:'0.8',name:'4:5'},{id:'1.7777777777777777',name:'16:9'},{id:'2.7083333333333335',name:'XPan'}];enabled:layoutState.photos.length>1;onSelected:function(v){workspace.setOption('ratio',Number(v))}}
                                FineParameter {label:qsTr(String('边宽'));directParameter:false;recordEdits:false;defaultValue:3.5;enabled:layoutState.style!=='plain';externalValue:layoutState.border*100;maximum:20;step:.1;unit:'%';onValueEdited:function(v){workspace.setOption('border',v/100)}}
                            }
                            FineParameter {label:qsTr(String('片间距'));directParameter:false;recordEdits:false;defaultValue:1.5;visible:layoutState.style!=='half_frame';enabled:layoutState.photos.length>1;externalValue:layoutState.gap*100;maximum:12;step:.1;unit:'%';onValueEdited:function(v){workspace.setOption('gap',v/100)}}
                        }
                        Column {
                            visible:root.tool===1;width:parent.width;spacing:16
                            RowLayout {width:parent.width;visible:layoutState.photos.length>1;spacing:4;StudioButton {text:qsTr(String('当前照片'));quiet:true;selected:!root.linkFrames;Layout.fillWidth:true;onClicked:root.linkFrames=false}StudioButton {text:qsTr(String(layoutState.photos.length===2 ? '两格联动' : '全部联动'));quiet:true;selected:root.linkFrames;Layout.fillWidth:true;onClicked:root.linkFrames=true}}
                            MaterialSelector {label:qsTr(String('照片'));fillField:true;value:String(layoutState.active);enabled:!root.linkFrames;choices:{var a=[];for(var i=0;i<layoutState.photos.length;i++)a.push({id:String(i),name:(i+1)+' · '+layoutState.photos[i].name});return a}onSelected:function(v){workspace.select(Number(v))}}
                            RowLayout {width:parent.width;visible:layoutState.style==='half_frame';spacing:8
                                StudioButton {objectName:'replaceHalfFrame';text:qsTr('替换当前照片');quiet:true;Layout.fillWidth:true;enabled:!layoutState.busy;onClicked:workspace.replaceHole(layoutState.active)}
                                StudioButton {objectName:'removeHalfFrame';text:qsTr('移除');quiet:true;enabled:!layoutState.busy&&!root.selectedPhoto()._empty;onClicked:workspace.removeHole(layoutState.active)}
                            }
                            RowLayout {width:parent.width;spacing:4;StudioButton {objectName:'compositionSwap';text:qsTr(String('交换'));quiet:true;enabled:layoutState.photos.length>1;Layout.fillWidth:true;onClicked:workspace.swap(layoutState.active,layoutState.active===0 ? 1 : layoutState.active-1)}StudioButton {objectName:'compositionRotatePhoto';text:qsTr(String(root.linkFrames ? '旋转整组' : '旋转照片'));quiet:true;Layout.fillWidth:true;onClicked:{if(root.linkFrames)workspace.rotateGroup(90);else workspace.rotate(layoutState.active,90)}}}
                            FineParameter {objectName:'compositionZoom';label:qsTr(String('取景缩放'));directParameter:false;recordEdits:false;defaultValue:1;externalValue:root.linkFrames ? layoutState.group_zoom : Number(root.selectedPhoto().zoom||1);minimum:1;maximum:5;step:.01;unit:'×';onValueEdited:function(v){root.editZoom(v)}}
                            StudioButton {text:qsTr(String(root.linkFrames ? '恢复两格取景' : '恢复当前取景'));quiet:true;onClicked:{if(root.linkFrames)workspace.resetGroupPosition();else workspace.resetPosition()}}
                            MinchoText {text:qsTr(String(root.selectedPhoto().name||''));font.pixelSize:Theme.caption;color:Theme.secondary;elide:Text.ElideMiddle;width:parent.width}
                        }
                        Column {
                            visible:root.tool===2;width:parent.width;spacing:16
                            Column {visible:root.filmEdge;width:parent.width;spacing:12
                                RowLayout {width:parent.width;MinchoText {text:qsTr(String('日期曝光'));Layout.fillWidth:true}StudioSwitch {Accessible.name:qsTr('日期曝光');objectName:'dateBackSwitch';enabled:layoutState.date_capabilities.available;checked:layoutState.date_imprint_active;onToggled:workspace.setOption('date_imprint_active',checked)}}
                                MinchoText {visible:!layoutState.date_capabilities.available;text:qsTr('此片幅没有日期后背');font.pixelSize:Theme.caption;color:Theme.secondary;width:parent.width;wrapMode:Text.Wrap}
                                Column {width:parent.width;spacing:12;visible:layoutState.date_imprint_active
                                    TextField {width:parent.width;placeholderText:qsTr(String((root.selectedPhoto().metadata||{}).date||'输入日期'));text:layoutState.date;font.family:Theme.family;font.pixelSize:Theme.body;color:Theme.ink;implicitHeight:38;leftPadding:10;rightPadding:10;onTextEdited:workspace.setOption('date',text);background:Rectangle {color:Theme.surface;radius:4;border.width:parent.activeFocus ? 2 : 1;border.color:parent.activeFocus ? Theme.accent : Theme.border}}
                                    TextField {visible:layoutState.date_style==='data'||layoutState.date_also_data;width:parent.width;placeholderText:qsTr(String((root.selectedPhoto().metadata||{}).data_text||'快门与光圈'));text:layoutState.caption;font.family:Theme.family;font.pixelSize:Theme.body;color:Theme.ink;implicitHeight:38;leftPadding:10;rightPadding:10;onTextEdited:workspace.setOption('caption',text);background:Rectangle {color:Theme.surface;radius:4;border.width:parent.activeFocus ? 2 : 1;border.color:parent.activeFocus ? Theme.accent : Theme.border}}
                                    MaterialSelector {label:qsTr(String('字样'));fillField:true;value:layoutState.date_style;choices:{var a=[{id:'lcd',name:'液晶日期'},{id:'dots',name:'点阵日期'},{id:'data',name:'拍摄数据'}];return a.filter(function(item){return layoutState.date_capabilities.faces.indexOf(item.id)>=0})}onSelected:function(v){workspace.setOption('date_style',v)}}
                                    RowLayout {width:parent.width;visible:layoutState.date_style!=='data'&&layoutState.date_capabilities.faces.indexOf('data')>=0
                                        MinchoText {text:qsTr('同时打印拍摄数据');Layout.fillWidth:true}
                                        StudioSwitch {Accessible.name:qsTr('同时打印拍摄数据');objectName:'datePlusData';checked:layoutState.date_also_data;onToggled:workspace.setOption('date_also_data',checked)}
                                    }
                                    MaterialSelector {visible:layoutState.date_style!=='data';label:qsTr('日期顺序');fillField:true;value:layoutState.date_order;choices:[{id:'japan',name:'年 月 日'},{id:'us',name:'月 日 年'}];onSelected:function(v){workspace.setOption('date_order',v)}}
                                    MaterialSelector {visible:layoutState.date_style!=='data';label:qsTr(String('位置'));fillField:true;value:layoutState.date_placement;choices:layoutState.date_capabilities.rebate ? [{id:'frame',name:'画面内'},{id:'rebate',name:'片边'}] : [{id:'frame',name:'画面内'}];onSelected:function(v){workspace.setOption('date_placement',v)}}
                                    MaterialSelector {label:qsTr(String('角落'));fillField:true;value:layoutState.date_corner;choices:[{id:'br',name:'右下'},{id:'bl',name:'左下'},{id:'tr',name:'右上'},{id:'tl',name:'左上'}];onSelected:function(v){workspace.setOption('date_corner',v)}}
                                    FineParameter {label:qsTr(String('曝光'));directParameter:false;recordEdits:false;defaultValue:3.5;externalValue:layoutState.date_exposure;minimum:-2;maximum:8;step:.05;unit:'EV';onValueEdited:function(v){workspace.setOption('date_exposure',v)}}
                                    FineParameter {label:qsTr(String('字号'));directParameter:false;recordEdits:false;defaultValue:1;externalValue:Math.min(layoutState.date_size,layoutState.date_capabilities.max_size);minimum:.4;maximum:layoutState.date_capabilities.max_size;step:.01;unit:'×';onValueEdited:function(v){workspace.setOption('date_size',v)}}
                                }
                            }
                            Column {visible:!root.filmEdge;width:parent.width;spacing:12
                                RowLayout {width:parent.width;MinchoText {text:qsTr(String('拍摄信息'));Layout.fillWidth:true}StudioSwitch {Accessible.name:qsTr('拍摄信息');objectName:'photoInfoToggle';checked:layoutState.show_info;onToggled:workspace.setOption('show_info',checked)}}
                                TextField {width:parent.width;placeholderText:qsTr(String('附加文字'));text:layoutState.caption;font.family:Theme.family;font.pixelSize:Theme.body;color:Theme.ink;leftPadding:10;rightPadding:10;implicitHeight:38;onTextEdited:workspace.setOption('caption',text);background:Rectangle {color:Theme.surface;radius:4;border.width:parent.activeFocus ? 2 : 1;border.color:parent.activeFocus ? Theme.accent : Theme.border}}
                                TextField {width:parent.width;placeholderText:qsTr(String('日期覆盖'));text:layoutState.date;font.family:Theme.family;font.pixelSize:Theme.body;color:Theme.ink;leftPadding:10;rightPadding:10;implicitHeight:38;onTextEdited:workspace.setOption('date',text);background:Rectangle {color:Theme.surface;radius:4;border.width:parent.activeFocus ? 2 : 1;border.color:parent.activeFocus ? Theme.accent : Theme.border}}
                            }
                            Repeater {model:{var m=root.selectedPhoto().metadata||{};return [m.camera,m.lens,m.exposure,m.date].filter(function(v){return !!v})}MinchoText {required property string modelData;text:qsTr(String(modelData));font.pixelSize:Theme.caption;color:Theme.secondary;width:parent.width;wrapMode:Text.Wrap}}
                            MinchoText {visible:!root.filmEdge||layoutState.photos.length>2;text:qsTr(String('图面颜色'));font.pixelSize:Theme.caption;color:Theme.secondary}
                            Row {visible:!root.filmEdge||layoutState.photos.length>2;spacing:10;Repeater {model:['#FCF9F2','#191D18','#DDE4D4','#FFFFFF'];Button {required property string modelData;implicitWidth:36;implicitHeight:36;hoverEnabled:true;Accessible.name:qsTr(String('图面颜色 '+modelData));onClicked:workspace.setOption('color',modelData);background:Rectangle {color:modelData;radius:4;border.width:layoutState.color===modelData||parent.visualFocus ? 2 : 1;border.color:layoutState.color===modelData||parent.visualFocus ? Theme.accent : Theme.border}}}}
                        }
                        Item {width:1;height:12}
                    }
                }
                Rectangle {
                    objectName:'compositionOutputFooter';Layout.fillWidth:true;implicitHeight:outputOptions.implicitHeight+24;color:Theme.panelFooter;radius:6;z:3
                Column {
                    id:outputOptions;anchors.left:parent.left;anchors.right:parent.right;anchors.top:parent.top;anchors.margins:8;anchors.topMargin:12;spacing:8;enabled:!layoutState.exporting
                    MaterialSelector {label:qsTr(String('格式'));fillField:true;value:layoutState.format;choices:[{id:'tiff',name:'TIFF · 16 位'},{id:'png',name:'PNG · 16 位'},{id:'jpeg',name:'JPG · 最高品质'}];onSelected:function(v){workspace.setOption('format',v)}}
                    MaterialSelector {label:qsTr(String('长边'));fillField:true;value:String(layoutState.edge);choices:[{id:'0',name:'原像素排版'},{id:'12000',name:'12000 px'},{id:'6000',name:'6000 px'},{id:'3000',name:'3000 px'}];onSelected:function(v){workspace.setOption('edge',Number(v))}}
                }
                }
            }
            }
        }
        RowLayout {
            Layout.fillWidth:true;spacing:8
            MinchoText {text:qsTr(String(layoutState.status));Layout.fillWidth:true;color:Theme.secondary;elide:Text.ElideRight}
            StudioButton {text:qsTr(String('重试预览'));quiet:true;visible:!!layoutState.preview_error;enabled:!layoutState.busy;onClicked:workspace.retryPreview()}
            ProgressBar {visible:layoutState.busy;value:layoutState.progress;Layout.preferredWidth:120}
            StudioButton {text:qsTr(String('停止'));quiet:true;visible:layoutState.busy;onClicked:workspace.cancel()}
            StudioButton {objectName:'exportCompositionButton';text:qsTr(String('导出排版'));primary:true;enabled:!layoutState.busy&&layoutState.filled_count>0;implicitWidth:130;onClicked:workspace.export()}
        }
    }
}

