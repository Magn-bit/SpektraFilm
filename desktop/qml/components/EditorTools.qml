import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ColumnLayout {
    id:root
    property string task:'basic'
    readonly property bool hasPhoto:ctrl.currentIndex>=0
    property var stock:({name:'选择胶片',maker:'',type:'negative'})
    property string basicGroup:'tone'
    property string previousTask:'basic'
    property string meterMethod:'balanced'
    property string meterTarget:'both'
    property var taskScrollPositions:({})
    property alias maskTools:localTools
    signal libraryRequested()
    signal stylesRequested()
    signal cropRequested()
    signal guidedRequested(string mode)
    onTaskChanged: {
        if(!hasPhoto&&task!=='film'){task='film';return}
        if(parameterScroll.contentItem) {
            taskScrollPositions[previousTask]=parameterScroll.contentItem.contentY
            var y=taskScrollPositions[task] || 0
            Qt.callLater(function(){parameterScroll.contentItem.contentY=Math.max(0,Math.min(y,parameterScroll.contentItem.contentHeight-parameterScroll.availableHeight))})
        }
        previousTask=task
    }
    onHasPhotoChanged:if(!hasPhoto && task!=='film')task='film'
    Component.onCompleted:if(!hasPhoto && task!=='film')task='film'
    spacing:0
    RowLayout {
        Layout.fillWidth:true;Layout.leftMargin:16;Layout.rightMargin:16;Layout.topMargin:12;Layout.bottomMargin:12;spacing:2
        Repeater {
            model:[{id:'basic',name:'基础'},{id:'color',name:'颜色'},{id:'local',name:'局部'},{id:'film',name:'胶片'},{id:'geometry',name:'几何'}]
            delegate:StudioButton {
                required property var modelData
                objectName:'task_'+modelData.id;text:qsTr(String(modelData.name));quiet:true;selected:root.task===modelData.id;enabled:modelData.id==='film'||root.hasPhoto
                Layout.fillWidth:true;implicitWidth:38;implicitHeight:38
                Accessible.role:Accessible.PageTab;Accessible.name:qsTr(String(modelData.name+'工具'));Accessible.selected:selected
                background:Rectangle {
                    radius:4;color:parent.selected ? Theme.accentInk : parent.hovered ? Theme.hover : 'transparent'
                    border.width:parent.visualFocus ? 1 : 0;border.color:Theme.accent
                }
                contentItem:MinchoText {text:qsTr(String(parent.text));horizontalAlignment:Text.AlignHCenter;verticalAlignment:Text.AlignVCenter;color:parent.selected ? Theme.accentText : Theme.secondary}
                onClicked:root.task=modelData.id
            }
        }
    }
    HistogramPanel {
        objectName:'editorHistogram'
        visible:root.hasPhoto
        Layout.fillWidth:true;Layout.leftMargin:24;Layout.rightMargin:24;Layout.bottomMargin:12
    }
    ScrollView {
        id:parameterScroll;objectName:'parameterScroll'
        Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumHeight:0;Layout.preferredHeight:1;Layout.leftMargin:24;Layout.rightMargin:12;clip:true
        rightPadding:Theme.scrollBarGutter;contentWidth:availableWidth
        ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
        ScrollBar.vertical:ScrollBar {
            id:parameterScrollBar;objectName:'parameterScrollBar';parent:parameterScroll
            x:parameterScroll.width-width;y:0;width:Theme.scrollBarLane;height:parameterScroll.height
            orientation:Qt.Vertical;policy:ScrollBar.AsNeeded;padding:4;minimumSize:.08;hoverEnabled:true
            visible:parameterScroll.contentHeight>parameterScroll.availableHeight+.5
            Accessible.name:qsTr(String('参数面板滚动条'))
            contentItem:Rectangle {implicitWidth:4;implicitHeight:36;radius:2;color:Theme.secondary;opacity:parameterScrollBar.pressed || parameterScrollBar.hovered || parameterScrollBar.active ? .75 : .35;Behavior on opacity{NumberAnimation{duration:Theme.fast}}}
            background:Item{}
        }
        Column {
            width:parameterScroll.availableWidth;spacing:24
            Column {
                width:parent.width;spacing:20;visible:root.task==='basic'&&root.hasPhoto;enabled:ctrl.currentIndex>=0 && !ctrl.exporting
                MinchoText {text:qsTr(String('基础调整'));font.pixelSize:Theme.heading;height:32}
                FineParameter {label:qsTr(String('曝光'));parameter:'exposure';minimum:-8;maximum:8;step:.01;unit:'EV';signedValue:true}
                ToolSection {
                    title:qsTr(String('白平衡'));expanded:root.basicGroup==='wb';onToggled:root.basicGroup=expanded ? '' : 'wb'
                    StudioButton {objectName:'autoWhiteBalanceButton';text:qsTr(String('自动白平衡'));quiet:true;implicitHeight:30;enabled:!ctrl.autoAdjustBusy;onClicked:ctrl.autoAdjust('white_balance')}
                    FineParameter {label:qsTr(String('色温'));parameter:'temperature';minimum:2000;maximum:10000;step:10;unit:'K';trackColors:['#7D9BB4','#D1CABA','#CFAD76']}
                    FineParameter {label:qsTr(String('色调'));parameter:'tint';minimum:-100;maximum:100;step:.1;signedValue:true;trackColors:['#83A07C','#C5C4B7','#B1839F']}
                }
                ToolSection {
                    title:qsTr(String('颜色'));expanded:root.basicGroup==='color';onToggled:root.basicGroup=expanded ? '' : 'color'
                    FineParameter {label:qsTr(String('饱和度'));parameter:'saturation';minimum:-100;maximum:100;step:.1;signedValue:true}
                    FineParameter {label:qsTr(String('自然饱和度'));parameter:'vibrance';minimum:-100;maximum:100;step:.1;signedValue:true}
                }
                ToolSection {
                    title:qsTr(String('影调'));expanded:root.basicGroup==='tone';onToggled:root.basicGroup=expanded ? '' : 'tone'
                    StudioButton {objectName:'autoToneButton';text:qsTr(String('自动影调'));quiet:true;implicitHeight:30;enabled:!ctrl.autoAdjustBusy;onClicked:ctrl.autoAdjust('tone')}
                    FineParameter {label:qsTr(String('亮度'));parameter:'brightness';minimum:-100;maximum:100;step:.1;signedValue:true}
                    FineParameter {label:qsTr(String('对比度'));parameter:'contrast';minimum:-100;maximum:100;step:.1;signedValue:true}
                }
                ToolSection {
                    title:qsTr(String('高动态范围'));expanded:root.basicGroup==='hdr';onToggled:root.basicGroup=expanded ? '' : 'hdr'
                    FineParameter {label:qsTr(String('高光'));parameter:'highlights';minimum:-100;maximum:100;step:.1;signedValue:true}
                    FineParameter {label:qsTr(String('阴影'));parameter:'shadows';minimum:-100;maximum:100;step:.1;signedValue:true}
                    FineParameter {label:qsTr(String('白色'));parameter:'whites';minimum:-100;maximum:100;step:.1;signedValue:true}
                    FineParameter {label:qsTr(String('黑色'));parameter:'blacks';minimum:-100;maximum:100;step:.1;signedValue:true}
                }
                ToolSection {
                    title:qsTr(String('色阶'));expanded:root.basicGroup==='levels';onToggled:root.basicGroup=expanded ? '' : 'levels'
                    LevelsEditor {}
                }
                ToolSection {
                    title:qsTr(String('质感'));expanded:root.basicGroup==='detail';onToggled:root.basicGroup=expanded ? '' : 'detail'
                    FineParameter {label:qsTr(String('纹理'));parameter:'texture';minimum:-100;maximum:100;step:.1;signedValue:true}
                    FineParameter {label:qsTr(String('清晰度'));parameter:'clarity';minimum:-100;maximum:100;step:.1;signedValue:true}
                    FineParameter {label:qsTr(String('去雾'));parameter:'dehaze';minimum:-100;maximum:100;step:.1;signedValue:true}
                }
                ToolSection {
                    title:qsTr(String('细节'));expanded:root.basicGroup==='noise';onToggled:root.basicGroup=expanded ? '' : 'noise'
                    FineParameter {label:qsTr(String('锐化'));parameter:'sharpening';minimum:0;maximum:100;step:.1}
                    FineParameter {label:qsTr(String('明度降噪'));parameter:'noise_luminance';minimum:0;maximum:100;step:.1}
                    FineParameter {label:qsTr(String('彩色降噪'));parameter:'noise_color';minimum:0;maximum:100;step:.1}
                }
                ToolSection {
                    title:qsTr(String('镜头与光学'));expanded:root.basicGroup==='optics';onToggled:root.basicGroup=expanded ? '' : 'optics'
                    RowLayout {
                        width:parent.width
                        MinchoText {text:qsTr(String('镜头校正'));Layout.fillWidth:true}
                        StudioSwitch {Accessible.name:qsTr('镜头校正');objectName:'lensCorrectionToggle';checked:ctrl.parameters.lens_correction;enabled:ctrl.currentIndex>=0 && !ctrl.exporting;onToggled:ctrl.setCorrection('lens_correction',checked)}
                    }
                    RowLayout {
                        width:parent.width
                        MinchoText {text:qsTr(String('去除紫边'));Layout.fillWidth:true}
                        StudioSwitch {Accessible.name:qsTr('去除紫边');objectName:'defringeToggle';checked:ctrl.parameters.defringe;enabled:ctrl.currentIndex>=0 && !ctrl.exporting;onToggled:ctrl.setCorrection('defringe',checked)}
                    }
                    MinchoText {text:qsTr(String(ctrl.sourceDimensions[0]+' × '+ctrl.sourceDimensions[1]));font.pixelSize:Theme.caption;color:Theme.secondary}
                    MinchoText {
                        objectName:'lensCorrectionStatus';text:qsTr(String(ctrl.lensStatus));font.pixelSize:Theme.caption;color:Theme.secondary;wrapMode:Text.Wrap;width:parent.width
                        Accessible.name:text
                        HoverHandler {id:lensStatusHover}
                        ToolTip.visible:lensStatusHover.hovered && ctrl.lensProfilePath.length>0
                        ToolTip.delay:700;ToolTip.text:ctrl.lensProfilePath
                    }
                }
            }
            ColorToolsPanel {width:parent.width;visible:root.task==='color'&&root.hasPhoto;onStylesRequested:root.stylesRequested()}
            MaskPanel {id:localTools;width:parent.width;visible:root.task==='local'&&root.hasPhoto}
            Column {
                width:parent.width;spacing:24;visible:root.task==='film'
                RowLayout {
                    width:parent.width;visible:root.hasPhoto
                    MinchoText {text:qsTr(String('胶片显影'));font.pixelSize:Theme.heading;Layout.fillWidth:true}
                    StudioSwitch {Accessible.name:qsTr('胶片显影');objectName:'filmEnabledButton';checked:ctrl.parameters.film_enabled;enabled:ctrl.currentIndex>=0 && !ctrl.exporting;onToggled:ctrl.setFilmEnabled(checked)}
                }
                Column {
                    width:parent.width;spacing:8
                    MinchoText {objectName:'filmTitle';text:qsTr(String(root.stock.name));displayRole:true;font.pixelSize:26;font.weight:Font.Normal;wrapMode:Text.WordWrap;maximumLineCount:2;elide:Text.ElideRight;width:parent.width}
                    RowLayout {
                        width:parent.width
                        MinchoText {objectName:'filmMetadata';text:qsTr(String(root.stock.maker+' / '+(root.stock.type==='bw' ? '黑白负片' : root.stock.type==='slide' ? '反转片' : '彩色负片')));font.pixelSize:Theme.caption;color:Theme.secondary;Layout.fillWidth:true;elide:Text.ElideRight}
                        StudioButton {objectName:'filmArchiveButton';text:qsTr(String('胶片档案'));quiet:true;iconName:'chevron';implicitHeight:34;onClicked:root.libraryRequested()}
                    }
                }
                Column {
                    width:parent.width;spacing:24;visible:root.hasPhoto;enabled:ctrl.currentIndex>=0 && ctrl.parameters.film_enabled && !ctrl.exporting
                    MaterialSelector {
                        objectName:'paperSelector';label:qsTr(String('相纸'));fillField:true
                        choices:{var r=[{id:'scan',name:'不印相 · 直接扫描'}];for(var i=0;i<ctrl.papers.length;i++)r.push(ctrl.papers[i]);if(ctrl.diSupported)r.push({id:'di',name:'数字中间片 · DI'});return r}
                        value:ctrl.parameters.digital_intermediate ? 'di' : ctrl.parameters.scan_film ? 'scan' : ctrl.parameters.paper;enabled:root.stock.type!=='slide'
                        onSelected:function(value){if(value==='scan')ctrl.setFilmOption('scan_film',true);else if(value==='di')ctrl.setFilmOption('digital_intermediate',true);else ctrl.setPaper(value)}
                    }
                    Column {
                        width:parent.width;spacing:10
                        MinchoText {text:qsTr(String('成像'));font.pixelSize:Theme.heading;color:Theme.secondary;height:30}
                        FineParameter {label:qsTr(String('胶片强度'));parameter:'strength';step:.1;unit:'%'}
                        RowLayout {width:parent.width;MinchoText {text:qsTr('高光光晕');Layout.fillWidth:true}StudioSwitch {Accessible.name:qsTr('高光光晕');objectName:'halationToggle';checked:ctrl.parameters.halation_enabled;onToggled:ctrl.setFilmOption('halation_enabled',checked)}}
                        FineParameter {label:qsTr('光晕强度');parameter:'halation';step:.1;unit:'%';enabled:ctrl.parameters.halation_enabled}
                        FineParameter {label:qsTr(String('暗角'));parameter:'vignette';step:.1;unit:'%'}
                        RowLayout {
                            width:parent.width
                            MinchoText {text:qsTr('HDR 增益图');Layout.fillWidth:true}
                            StudioSwitch {Accessible.name:qsTr('HDR 增益图');objectName:'hdrEnabled';checked:ctrl.parameters.hdr_enabled;enabled:ctrl.hdrSupported||ctrl.parameters.hdr_enabled;onToggled:ctrl.setFilmOption('hdr_enabled',checked)}
                        }
                        FineParameter {objectName:'hdrPeak';label:qsTr('HDR 峰值');parameter:'hdr_peak_stops';minimum:.5;maximum:4;step:.1;fineStep:.01;unit:'EV';enabled:ctrl.parameters.hdr_enabled}
                    }
                    Column {
                        width:parent.width;spacing:12
                        RowLayout {width:parent.width;MinchoText {text:qsTr('颗粒');font.pixelSize:Theme.heading;color:Theme.secondary;Layout.fillWidth:true}StudioSwitch {Accessible.name:qsTr('颗粒');objectName:'grainToggle';checked:ctrl.parameters.grain_enabled;onToggled:ctrl.setFilmOption('grain_enabled',checked)}}
                        Column {
                            width:parent.width;spacing:12;enabled:ctrl.parameters.grain_enabled
                            GrainSelector {}
                            FilmFormatControl {}
                            RowLayout {width:parent.width;MinchoText {text:qsTr(String('分层颗粒'));Layout.fillWidth:true}StudioSwitch {Accessible.name:qsTr('分层颗粒');objectName:'layeredGrainToggle';checked:ctrl.parameters.grain_layered;onToggled:ctrl.setFilmOption('grain_layered',checked)}}
                            FineParameter {label:qsTr(String('颗粒强度'));parameter:'grain';step:.1;unit:'%'}
                            FineParameter {label:qsTr(String('颗粒大小'));parameter:'grain_size';minimum:.25;maximum:2.5;step:.01;unit:'×'}
                        }
                    }
                    ToolSection {
                        objectName:'printSection';title:qsTr(String('印相'));detail:ctrl.directScan ? qsTr('直接扫描') : '';expanded:false;onToggled:expanded=!expanded
                        Column {
                            width:parent.width;spacing:12;enabled:!ctrl.directScan
                            RowLayout {width:parent.width;MinchoText {text:qsTr(String('相纸效果'));Layout.fillWidth:true}StudioSwitch {Accessible.name:qsTr('相纸效果');objectName:'printEffectsToggle';checked:ctrl.parameters.print_effects;onToggled:ctrl.setFilmOption('print_effects',checked)}}
                            RowLayout {width:parent.width;MinchoText {text:qsTr(String('扩展印相范围'));Layout.fillWidth:true}StudioSwitch {Accessible.name:qsTr('扩展印相范围');objectName:'edrToggle';checked:ctrl.parameters.extended_dynamic_range;enabled:ctrl.edrSupported;onToggled:ctrl.setFilmOption('extended_dynamic_range',checked)}}
                            MaterialSelector {label:qsTr(String('印放方式'));value:ctrl.parameters.minilab_active ? 'fast' : 'spectral';choices:ctrl.minilabSupported ? [{id:'spectral',name:'完整光谱'},{id:'fast',name:'快速印放 · 标定 LUT'}] : [{id:'spectral',name:'完整光谱'}];onSelected:function(value){ctrl.setMinilab(value==='fast')}}
                            FineParameter {label:qsTr(String('印相曝光'));parameter:'print_exposure';minimum:-3;maximum:3;step:.01;unit:'EV';signedValue:true}
                            FineParameter {label:qsTr(String('黄色滤色'));parameter:'print_y';minimum:-100;maximum:100;step:.1;signedValue:true}
                            FineParameter {label:qsTr(String('品红滤色'));parameter:'print_m';minimum:-100;maximum:100;step:.1;signedValue:true}
                            FineParameter {label:qsTr(String('相纸预闪'));parameter:'preflash_exposure';minimum:0;maximum:1;step:.01;fineStep:.001;directParameter:false;controllerReset:true;externalValue:ctrl.parameters.preflash_exposure/.2;onValueEdited:function(value){ctrl.updateParameter('preflash_exposure',value*.2)}}
                            FineParameter {label:qsTr(String('眩光'));parameter:'glare';maximum:30;step:.1;unit:'%'}
                            StudioButton {
                                objectName:'exportPaperLutButton';text:ctrl.paperLutInfo.busy ? qsTr('正在导出…') : qsTr('导出相纸 LUT…');quiet:true
                                enabled:ctrl.paperLutInfo.available&&!ctrl.paperLutInfo.busy&&!ctrl.exporting
                                onClicked:ctrl.exportPaperLut()
                                ToolTip.visible:hovered||visualFocus;ToolTip.delay:600
                                ToolTip.text:ctrl.paperLutInfo.available ? qsTr('配套归一化负片密度；不用于普通 RGB 照片') : qsTr(String(ctrl.paperLutInfo.reason))
                                Accessible.description:ToolTip.text
                            }
                        }
                    }
                    ToolSection {
                        objectName:'meterSection';title:qsTr(String('自动配光'));expanded:false;onToggled:expanded=!expanded
                        MaterialSelector {label:qsTr(String('测光'));value:root.meterMethod;choices:[{id:'balanced',name:'均衡'},{id:'center',name:'中央重点'},{id:'protect_highlights',name:'保护高光'},{id:'protect_shadows',name:'保护阴影'}];onSelected:function(value){root.meterMethod=value}}
                        MaterialSelector {label:qsTr(String('调整'));value:root.meterTarget;choices:[{id:'both',name:'曝光与滤色'},{id:'exposure',name:'曝光'},{id:'filter_pack',name:'滤色'}];onSelected:function(value){root.meterTarget=value}}
                        StudioButton {text:qsTr(String(ctrl.analysisBusy ? '计算中…' : '自动配光'));quiet:true;enabled:!ctrl.analysisBusy && !ctrl.parameters.minilab_active;onClicked:ctrl.autoMeter(root.meterTarget,root.meterMethod)}
                    }
                    ToolSection {
                        objectName:'sceneCurveSection';title:qsTr(String('场景曲线'));expanded:false;onToggled:expanded=!expanded
                        SceneHistogram {channel:decodeCurve.channel}
                        CurveEditor {id:decodeCurve;scene:true}
                    }
                    ToolSection {
                        objectName:'latitudeSection';title:qsTr(String('宽容度'));expanded:false;onToggled:expanded=!expanded
                        LatitudePanel {}
                    }
                    ToolSection {
                        objectName:'opticsSection';title:qsTr(String('光学'));expanded:false;onToggled:expanded=!expanded
                        RowLayout {
                            width:parent.width
                            MinchoText {text:qsTr(String('散射强度'));Layout.fillWidth:true}
                            StudioButton {text:qsTr(String(ctrl.parameters.halation_scatter_amount===null ? '跟随光晕' : '恢复跟随'));quiet:true;selected:ctrl.parameters.halation_scatter_amount===null;onClicked:ctrl.resetParameter('halation_scatter_amount')}
                        }
                        FineParameter {
                            label:qsTr(String('散射'));parameter:'halation_scatter_amount';minimum:0;maximum:100;step:.1;unit:'%'
                            directParameter:false;controllerReset:true
                            externalValue:100*(ctrl.parameters.halation_scatter_amount===null ? Math.min(1,ctrl.parameters.halation/25) : ctrl.parameters.halation_scatter_amount)
                            defaultValue:100*Math.min(1,ctrl.parameters.halation/25)
                            onValueEdited:function(value){ctrl.updateParameter('halation_scatter_amount',value/100)}
                        }
                        FineParameter {label:qsTr(String('散射尺度'));parameter:'halation_scatter_scale';minimum:.25;maximum:4;step:.01;unit:'×';defaultValue:1;enabled:(ctrl.parameters.halation_scatter_amount===null ? ctrl.parameters.halation>0 : ctrl.parameters.halation_scatter_amount>0)}
                        FineParameter {label:qsTr(String('空间尺度'));parameter:'halation_spatial_scale';minimum:.25;maximum:4;step:.01;unit:'×';defaultValue:1;enabled:ctrl.parameters.halation>0}
                        FineParameter {label:qsTr(String('光晕增益'));parameter:'halation_boost_ev';minimum:0;maximum:8;step:.01;unit:'EV'}
                        FineParameter {label:qsTr(String('高光保护'));parameter:'halation_protect_ev';minimum:0;maximum:8;step:.01;unit:'EV';defaultValue:4;enabled:ctrl.parameters.halation_boost_ev>0}
                        FineParameter {label:qsTr(String('高光余量'));parameter:'halation_headroom_ev';minimum:0;maximum:8;step:.01;unit:'EV';enabled:ctrl.backReflectionSupported && ctrl.parameters.halation>0}
                        RowLayout {
                            width:parent.width
                            enabled:ctrl.parameters.halation>0 && !ctrl.backReflectionSupported
                            MinchoText {text:qsTr(String('移除防光晕层'));Layout.fillWidth:true}
                            StudioSwitch {Accessible.name:qsTr('移除防光晕层');objectName:'antihalationToggle';checked:ctrl.parameters.antihalation_removed;onToggled:ctrl.setCorrection('antihalation_removed',checked)}
                        }
                        FineParameter {label:qsTr(String('层间耦合'));parameter:'dir_couplers_amount';minimum:0;maximum:4;step:.01;unit:'×';defaultValue:1;enabled:ctrl.couplersSupported}
                        FineParameter {label:qsTr(String('密度曲线'));parameter:'density_curve_gamma';minimum:.2;maximum:4;step:.01;unit:'×';defaultValue:1}
                    }
                }
            }
            GeometryPanel {objectName:'geometryPanel';width:parent.width;visible:root.task==='geometry'&&root.hasPhoto;onCropRequested:root.cropRequested();onGuidedRequested:function(mode){root.guidedRequested(mode)}}
            Item {width:1;height:16}
        }
    }
    RowLayout {
        Layout.fillWidth:true;Layout.margins:16;spacing:6
        StudioButton {objectName:'undoButton';text:qsTr(String('撤销'));quiet:true;visible:root.hasPhoto;enabled:ctrl.canUndo && !ctrl.exporting;onClicked:ctrl.undo();ToolTip.visible:hovered || visualFocus;ToolTip.delay:600;ToolTip.text:qsTr(String('撤销 · Ctrl+Z'))}
        StudioButton {objectName:'redoButton';text:qsTr(String('重做'));quiet:true;visible:root.hasPhoto;enabled:ctrl.canRedo && !ctrl.exporting;onClicked:ctrl.redo();ToolTip.visible:hovered || visualFocus;ToolTip.delay:600;ToolTip.text:qsTr(String('重做 · Ctrl+Y'))}
        Item {Layout.fillWidth:true}
        StudioButton {objectName:'resetPhotoButton';text:qsTr(String('恢复默认'));quiet:true;visible:root.hasPhoto;enabled:ctrl.canReset && !ctrl.exporting;onClicked:ctrl.reset();ToolTip.visible:hovered || visualFocus;ToolTip.delay:600;ToolTip.text:qsTr(String('恢复当前照片全部参数；可撤销'))}
    }
}
