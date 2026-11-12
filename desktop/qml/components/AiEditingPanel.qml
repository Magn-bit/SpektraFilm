import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ColumnLayout {
    id:root
    objectName:'aiEditingPanel'
    readonly property var ai:ctrl.aiEditor
    readonly property bool hasPhoto:ctrl.currentIndex>=0 && !ctrl.exporting
    readonly property bool configured:!!ai.activeProvider.hasKey
    readonly property bool hasSelection:ai.selectedStyle.length>0
    readonly property bool hasResults:ai.styles.length>0 && (ai.state==='recommended'||ai.state==='refined'||ai.state==='applied')
    property bool analysisExpanded:false
    property bool providerSettingsVisible:false
    Layout.minimumWidth:0;Layout.minimumHeight:0;spacing:0
    function loadProvider(id) {
        var provider=null
        for(var i=0;i<ai.providers.length;i++)if(ai.providers[i].id===id)provider=ai.providers[i]
        providerDraftId=provider ? provider.id : ''
        savedKey=provider ? provider.hasKey : false
        nameInput.text=provider ? provider.name : ''
        addressInput.text=provider ? provider.address : ''
        modelInput.text=provider ? provider.model : ''
        protocolInput.value=provider ? provider.protocol : 'responses'
        keyInput.text=''
    }
    function toggleProviderSettings() {
        loadProvider(ai.activeProvider.id||'')
        providerSettingsVisible=!providerSettingsVisible
    }
    function addProvider() {loadProvider('');nameInput.forceActiveFocus()}
    property string providerDraftId:''
    property bool savedKey:false
    Connections {target:root.ai;function onChanged(){if(!root.hasResults)root.analysisExpanded=false}}
    Component.onCompleted:if(!configured){loadProvider(ai.activeProvider.id||'');providerSettingsVisible=true}

    component ProviderField: TextField {
        Layout.fillWidth:true
        implicitHeight:36;leftPadding:10;rightPadding:10
        selectByMouse:true
        font.family:Theme.family;font.pixelSize:Theme.caption;font.hintingPreference:Font.PreferVerticalHinting
        color:Theme.ink;placeholderTextColor:Theme.muted;selectionColor:Theme.selection;selectedTextColor:Theme.ink
        background:Rectangle {
            radius:5;color:Theme.surface;border.width:1
            border.color:parent.activeFocus ? Theme.accentInk : parent.hovered ? Theme.border : Theme.rule
        }
    }

    ScrollView {
        id:scroll;objectName:'aiEditingScroll'
        Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumWidth:0;Layout.minimumHeight:0
        clip:true;contentWidth:availableWidth
        leftPadding:24;rightPadding:24;topPadding:8;bottomPadding:24
        ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
        ScrollBar.vertical:ScrollBar {policy:ScrollBar.AsNeeded;minimumSize:.08;hoverEnabled:true}
        ColumnLayout {
            id:content;width:scroll.availableWidth;spacing:20
            ColumnLayout {
                objectName:'aiProviderSettingsInline'
                Layout.fillWidth:true;spacing:10;visible:root.providerSettingsVisible
                RowLayout {
                    Layout.fillWidth:true;spacing:8
                    MinchoText {text:qsTr('服务商');font.pixelSize:Theme.caption;color:Theme.secondary}
                    MaterialSelector {
                        id:providerSelector;objectName:'aiProviderSelector';Layout.fillWidth:true;fillField:true;label:''
                        value:root.providerDraftId;enabled:!ai.busy;visible:ai.providers.length>0
                        choices:{var values=[];for(var i=0;i<ai.providers.length;i++)values.push({id:ai.providers[i].id,name:ai.providers[i].name});if(!root.providerDraftId)values.unshift({id:'',name:qsTr('新服务商')});return values}
                        onSelected:function(value){if(value.length){ai.selectProvider(value);root.loadProvider(value)}}
                        Accessible.name:qsTr('切换服务商')
                    }
                    StudioIconButton {
                        objectName:'addAiProviderButton';glyph:'plus';description:qsTr('添加服务商')
                        enabled:!ai.busy&&ai.providers.length<16;onClicked:root.addProvider()
                    }
                }
                ProviderField {
                    id:nameInput;objectName:'aiProviderName';Layout.fillWidth:true;maximumLength:64
                    placeholderText:qsTr('服务商名称');enabled:!ai.busy;Accessible.name:qsTr('服务商名称')
                }
                ProviderField {
                    id:addressInput;objectName:'aiProviderAddress';Layout.fillWidth:true;maximumLength:2048
                    placeholderText:qsTr('API 地址');enabled:!ai.busy;Accessible.name:qsTr('API 地址')
                }
                MaterialSelector {
                    id:protocolInput;objectName:'aiProviderProtocol';Layout.fillWidth:true;fillField:true;height:36
                    label:qsTr('协议');enabled:!ai.busy
                    choices:[{id:'responses',name:'OpenAI Responses'},{id:'chat',name:'Chat Completions'},{id:'anthropic',name:'Anthropic Messages'}]
                }
                RowLayout {
                    Layout.fillWidth:true;spacing:8
                    ProviderField {
                        id:modelInput;objectName:'aiProviderModel';Layout.fillWidth:true;maximumLength:160
                        placeholderText:qsTr('视觉模型 ID');enabled:!ai.busy;Accessible.name:qsTr('视觉模型 ID')
                    }
                    ProviderField {
                        id:keyInput;objectName:'aiProviderKey';Layout.fillWidth:true;maximumLength:8192
                        echoMode:TextInput.Password;passwordMaskDelay:0
                        placeholderText:root.savedKey ? qsTr('已保存密钥') : qsTr('API 密钥')
                        enabled:!ai.busy;Accessible.name:qsTr('API 密钥')
                    }
                }
                MinchoText {
                    objectName:'aiProviderError';text:ai.message
                    visible:ai.state==='error';Layout.fillWidth:true;wrapMode:Text.WordWrap
                    color:Theme.errorInk;font.pixelSize:Theme.caption
                }
                RowLayout {
                    Layout.fillWidth:true;Layout.topMargin:2;spacing:8
                    StudioIconButton {
                        objectName:'removeAiProviderButton';glyph:'trash';description:qsTr('移除此服务商')
                        visible:root.providerDraftId.length>0;enabled:!ai.busy
                        onClicked:{ai.removeProvider(root.providerDraftId);root.loadProvider(ai.activeProvider.id||'')}
                    }
                    Item {Layout.fillWidth:true}
                    StudioButton {
                        text:qsTr('取消');quiet:true;implicitHeight:34
                        onClicked:{root.loadProvider(ai.activeProvider.id||'');keyInput.text='';root.providerSettingsVisible=false}
                    }
                    StudioButton {
                        objectName:'saveAiProviderButton';text:qsTr('保存');primary:true;implicitWidth:68;implicitHeight:34
                        enabled:!ai.busy&&nameInput.text.trim().length>0&&addressInput.text.trim().length>0&&modelInput.text.trim().length>0&&(root.savedKey||keyInput.text.trim().length>0)
                        onClicked:{
                            ai.saveProvider(nameInput.text,addressInput.text,protocolInput.value,modelInput.text,keyInput.text,root.providerDraftId)
                            if(ai.state==='error')return
                            root.loadProvider(ai.activeProvider.id||'');keyInput.text='';root.providerSettingsVisible=false
                        }
                    }
                }
            }
            ColumnLayout {
                Layout.fillWidth:true;spacing:10;visible:!root.providerSettingsVisible
                TextArea {
                    id:intentInput;objectName:'aiPhotoIntent'
                    Layout.fillWidth:true;Layout.preferredHeight:76
                    enabled:root.hasPhoto && !ai.busy
                    wrapMode:TextEdit.Wrap;selectByMouse:true
                    onTextChanged:if(length>2000)remove(2000,length)
                    font.family:Theme.family;font.pixelSize:Theme.caption;font.hintingPreference:Font.PreferVerticalHinting
                    color:Theme.ink;placeholderTextColor:Theme.muted;selectionColor:Theme.selection;selectedTextColor:Theme.ink
                    placeholderText:qsTr('修图意图（可选）');Accessible.name:qsTr('修图意图，可选')
                    background:Rectangle {
                        radius:6;color:Theme.surface;border.width:1
                        border.color:intentInput.activeFocus ? Theme.accentInk : intentInput.hovered ? Theme.border : Theme.rule
                    }
                    padding:12
                }
                RowLayout {
                    Layout.fillWidth:true;spacing:8
                    StudioButton {
                        objectName:'analyzeAndRecommendButton'
                        text:qsTr(ai.busy ? '正在分析' : root.hasResults ? '重新分析' : '分析照片')
                        primary:true;Layout.fillWidth:true;implicitHeight:36
                        enabled:root.configured&&root.hasPhoto&&!ai.busy
                        ToolTip.visible:(hovered||visualFocus)&&!root.configured
                        ToolTip.text:qsTr('请先完成服务商配置');ToolTip.delay:550
                        onClicked:ai.analyze(intentInput.text)
                    }
                    StudioIconButton {objectName:'cancelAiRequestButton';glyph:'close';description:qsTr('取消分析');visible:ai.busy;onClicked:ai.cancel()}
                }
                RowLayout {
                    visible:ai.busy;Layout.fillWidth:true;spacing:8
                    BusyIndicator {running:ai.busy;implicitWidth:16;implicitHeight:16}
                    MinchoText {text:ai.message;Layout.fillWidth:true;wrapMode:Text.WordWrap;color:Theme.secondary;font.pixelSize:Theme.caption}
                }
                MinchoText {
                    objectName:'aiStatusText';text:ai.message;visible:ai.state==='error'
                    Layout.fillWidth:true;wrapMode:Text.WordWrap;color:Theme.errorInk;font.pixelSize:Theme.caption
                }
            }
            ColumnLayout {
                Layout.fillWidth:true;spacing:12;visible:root.hasResults&&!root.providerSettingsVisible
                RowLayout {
                    Layout.fillWidth:true;spacing:8
                    MinchoText {text:qsTr('照片分析');color:Theme.secondary;font.pixelSize:Theme.caption;Layout.fillWidth:true}
                    StudioIconButton {
                        objectName:'toggleAiAnalysisButton';glyph:'chevron';glyphSize:12;rotation:root.analysisExpanded ? 180 : 0
                        description:qsTr(root.analysisExpanded ? '收起分析详情' : '展开分析详情')
                        onClicked:root.analysisExpanded=!root.analysisExpanded
                    }
                }
                MinchoText {text:ai.summary;Layout.fillWidth:true;wrapMode:Text.WordWrap;color:Theme.ink;font.pixelSize:Theme.body}
                ColumnLayout {
                    Layout.fillWidth:true;spacing:8;visible:root.analysisExpanded
                    Repeater {
                        model:ai.observations
                        delegate:MinchoText {required property string modelData;text:modelData;Layout.fillWidth:true;wrapMode:Text.WordWrap;color:Theme.secondary;font.pixelSize:Theme.caption}
                    }
                }
                ColumnLayout {
                    Layout.fillWidth:true;Layout.topMargin:4;spacing:8
                    Repeater {
                        model:ai.styles
                        delegate:ColumnLayout {
                            id:styleEntry;required property var modelData
                            readonly property bool chosen:ai.selectedStyle===modelData.id
                            Layout.fillWidth:true;spacing:8
                            Button {
                                id:styleCard;objectName:'aiStyle_'+styleEntry.modelData.id
                                Layout.fillWidth:true;implicitHeight:cardBody.implicitHeight+24
                                padding:12;hoverEnabled:true;focusPolicy:Qt.StrongFocus
                                enabled:!ai.busy && ai.state!=='applied'
                                Accessible.name:String(styleEntry.modelData.name);Accessible.description:String(styleEntry.modelData.reason)
                                Accessible.role:Accessible.RadioButton;Accessible.checked:styleEntry.chosen
                                onClicked:ai.chooseStyle(styleEntry.modelData.id)
                                background:Rectangle {
                                    radius:6;color:styleEntry.chosen ? Theme.selection : styleCard.hovered ? Theme.hover : Theme.surface
                                    border.width:1;border.color:styleCard.visualFocus ? Theme.accentInk : styleEntry.chosen ? Theme.accent : Theme.rule
                                    Rectangle {anchors.fill:parent;anchors.margins:-3;radius:8;color:'transparent';border.width:1;border.color:Theme.accent;visible:styleCard.visualFocus}
                                }
                                contentItem:ColumnLayout {
                                    id:cardBody;spacing:6
                                    RowLayout {
                                        Layout.fillWidth:true;spacing:10
                                        MinchoText {text:String(styleEntry.modelData.name);font.pixelSize:Theme.body;Layout.fillWidth:true;wrapMode:Text.WordWrap}
                                        Rectangle {
                                            width:14;height:14;radius:7;color:'transparent';border.width:1;border.color:styleEntry.chosen ? Theme.accentInk : Theme.border
                                            Rectangle {anchors.centerIn:parent;width:6;height:6;radius:3;color:Theme.accentInk;visible:styleEntry.chosen}
                                        }
                                    }
                                    MinchoText {
                                        text:String(styleEntry.modelData.reason);Layout.fillWidth:true;wrapMode:Text.WordWrap;color:Theme.secondary;font.pixelSize:Theme.caption
                                        maximumLineCount:styleEntry.chosen ? 12 : 2;elide:Text.ElideRight
                                    }
                                }
                            }
                            ColumnLayout {
                                Layout.fillWidth:true;Layout.leftMargin:12;Layout.rightMargin:12;Layout.topMargin:2;Layout.bottomMargin:6;spacing:6
                                visible:styleEntry.chosen
                                Repeater {
                                    model:styleEntry.chosen ? styleEntry.modelData.changes : []
                                    delegate:RowLayout {
                                        required property var modelData;Layout.fillWidth:true;spacing:8
                                        MinchoText {text:String(modelData.label);Layout.fillWidth:true;color:Theme.secondary;font.pixelSize:Theme.caption;elide:Text.ElideRight}
                                        MinchoText {text:String(modelData.before)+' → '+String(modelData.after);color:Theme.ink;font.pixelSize:Theme.caption;horizontalAlignment:Text.AlignRight}
                                    }
                                }
                            }
                        }
                    }
                }
                RowLayout {
                    Layout.fillWidth:true;Layout.topMargin:4;spacing:8
                    StudioButton {
                        objectName:'applyAiSuggestionButton';visible:ai.state!=='applied';text:qsTr(ai.state==='refined'?'应用微调':'应用方案')
                        primary:true;Layout.fillWidth:true;implicitHeight:36;enabled:root.hasSelection&&!ai.busy&&root.hasPhoto;onClicked:ai.apply()
                    }
                    MinchoText {visible:ai.state==='applied';text:qsTr('已应用');color:Theme.accentInk;font.pixelSize:Theme.caption;Layout.fillWidth:true}
                    StudioButton {
                        objectName:'refineAiSuggestionButton';text:qsTr('继续微调');quiet:true;implicitHeight:36
                        enabled:root.hasSelection&&!ai.busy&&root.hasPhoto&&intentInput.text.trim().length>0
                        ToolTip.visible:(hovered||visualFocus)&&!enabled;ToolTip.text:qsTr('在上方填写微调意图');ToolTip.delay:550
                        onClicked:ai.refine(intentInput.text)
                    }
                }
            }
        }
    }
}
