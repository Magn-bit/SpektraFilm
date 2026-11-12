import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

StudioPage {
    id:root
    objectName:'settingsPanel'
    property string category:'preview'
    function storageText(category) {
        var usage=ctrl.fullDetail.storageUsage[category]
        if(!usage)return ''
        return (usage.bytes/1073741824).toFixed(2)+' GB / '+(usage.limit/1073741824).toFixed(1)+' GB'
    }
    onCategoryChanged:if(category==='resources')ctrl.fullDetail.refreshStorage()
    contentItem:ColumnLayout {
        spacing:20
        RowLayout {
            Layout.fillWidth:true
            MinchoText {text:qsTr(String('设置'));font.pixelSize:Theme.heading;Layout.fillWidth:true}
            StudioButton {text:qsTr(String('关闭'));quiet:true;onClicked:root.close()}
        }
        RowLayout {
            Layout.fillWidth:true;Layout.fillHeight:true;spacing:40
            ColumnLayout {
                Layout.preferredWidth:168;Layout.fillHeight:true;spacing:8
                Repeater {model:[{id:'preview',name:'预览'},{id:'develop',name:'新照片'},{id:'color',name:'色彩'},{id:'resources',name:'资源'},{id:'interface',name:'界面'},{id:'diagnostics',name:'诊断'},{id:'about',name:'关于'}]
                    delegate:StudioButton {
                        required property var modelData
                        Layout.fillWidth:true;text:qsTr(String(modelData.name));quiet:true;selected:root.category===modelData.id
                        Accessible.role:Accessible.PageTab;Accessible.selected:selected
                        onClicked:{root.category=modelData.id;scroll.contentItem.contentY=0}
                    }
                }
                Item {Layout.fillHeight:true}
            }
        ScrollView {
            id:scroll;Layout.fillWidth:true;Layout.fillHeight:true;clip:true
            contentWidth:availableWidth;rightPadding:14
            ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
            Column {
                width:Math.min(720,scroll.availableWidth);spacing:28
                Column {
                    width:parent.width;spacing:14
                    visible:root.category==='preview'
                    MinchoText {text:qsTr(String('预览'));font.pixelSize:Theme.heading;color:Theme.secondary}
                    MaterialSelector {
                        label:qsTr(String('长边'));value:String(ctrl.preferences.preview_long_edge)
                        choices:[{id:'1080',name:'1080 px'},{id:'1920',name:'1920 px'},{id:'2560',name:'2560 px'},{id:'3840',name:'3840 px'}]
                        onSelected:function(value){ctrl.updatePreference('preview_long_edge',Number(value))}
                    }
                }
                Column {
                    width:parent.width;spacing:14
                    visible:root.category==='color'
                    MinchoText {text:qsTr(String('色彩'));font.pixelSize:Theme.heading;color:Theme.secondary}
                    MaterialSelector {
                        objectName:'canvasColorSpaceSelector';label:qsTr('画布色域');value:ctrl.colorDisplay.canvasSpace
                        choices:[{id:'ProPhoto RGB',name:'ProPhoto RGB'},{id:'Display P3',name:'Display P3'},{id:'Adobe RGB (1998)',name:'Adobe RGB (1998)'},{id:'sRGB',name:'sRGB'}]
                        onSelected:function(value){ctrl.colorDisplay.setCanvasSpace(value)}
                    }
                    StudioSwitch {width:parent.width;text:qsTr('显示器色彩管理');objectName:'displayManagementToggle';checked:ctrl.colorDisplay.enabled;onToggled:ctrl.colorDisplay.setEnabled(checked)}
                    MinchoText {text:qsTr(String(ctrl.colorDisplay.monitorName));width:parent.width;elide:Text.ElideMiddle;color:Theme.secondary;font.pixelSize:Theme.caption}
                    StudioSwitch {width:parent.width;text:qsTr('软打样');objectName:'softProofToggle';checked:ctrl.colorDisplay.proofEnabled;onToggled:ctrl.colorDisplay.setProofEnabled(checked)}
                    MaterialSelector {label:qsTr(String('打样空间'));value:ctrl.colorDisplay.proofSpace;choices:[{id:'sRGB',name:'sRGB'},{id:'Adobe RGB (1998)',name:'Adobe RGB (1998)'},{id:'Display P3',name:'Display P3'},{id:'ProPhoto RGB',name:'ProPhoto RGB'}];onSelected:function(value){ctrl.colorDisplay.setProofSpace(value)}}
                    StudioButton {text:qsTr(String('选择打样 ICC…'));quiet:true;onClicked:ctrl.colorDisplay.chooseProofProfile()}
                    MinchoText {text:qsTr(String(ctrl.colorDisplay.proofName));visible:ctrl.colorDisplay.proofEnabled;width:parent.width;elide:Text.ElideMiddle;color:Theme.secondary;font.pixelSize:Theme.caption}
                    StudioSwitch {width:parent.width;text:qsTr('超色域提示');objectName:'gamutWarningToggle';enabled:ctrl.colorDisplay.proofEnabled;checked:ctrl.colorDisplay.gamutWarning;onToggled:ctrl.colorDisplay.setGamutWarning(checked)}
                }
                Column {
                    width:parent.width;spacing:14
                    visible:root.category==='resources'
                    MinchoText {text:qsTr(String('资源'));font.pixelSize:Theme.heading;color:Theme.secondary}
                    MaterialSelector {
                        label:qsTr(String('内存缓存'));value:String(ctrl.preferences.memory_budget_mb)
                        choices:[{id:'256',name:'256 MB'},{id:'512',name:'512 MB'},{id:'768',name:'768 MB'},{id:'1024',name:'1 GB'},{id:'1536',name:'1.5 GB'},{id:'2048',name:'2 GB'},{id:'3072',name:'3 GB'},{id:'4096',name:'4 GB'}]
                        onSelected:function(value){ctrl.updatePreference('memory_budget_mb',Number(value))}
                    }
                    Repeater {
                        model:[{key:'working_cache_mb',category:'working',name:'原源工作副本'},
                            {key:'preview_cache_mb',category:'preview',name:'磁盘预览'},
                            {key:'full_render_cache_mb',category:'full',name:'原尺寸显影'}]
                        delegate:Column {
                            required property var modelData
                            width:parent.width;spacing:8
                            MaterialSelector {
                                label:qsTr(modelData.name);value:String(ctrl.preferences[modelData.key])
                                choices:[{id:'0',name:qsTr('关闭')},{id:'1024',name:'1 GB'},{id:'2048',name:'2 GB'},
                                    {id:'5120',name:'5 GB'},{id:'8192',name:'8 GB'},{id:'10240',name:'10 GB'},
                                    {id:'20480',name:'20 GB'},{id:'32768',name:'32 GB'},{id:'65536',name:'64 GB'}]
                                onSelected:function(value){ctrl.updatePreference(modelData.key,Number(value))}
                            }
                            RowLayout {
                                width:parent.width
                                MinchoText {text:root.storageText(modelData.category);color:Theme.secondary;font.pixelSize:Theme.caption;Layout.fillWidth:true}
                                StudioButton {text:qsTr('清理');quiet:true;implicitHeight:30;enabled:!ctrl.exporting
                                    onClicked:ctrl.fullDetail.clearCategory(modelData.category)
                                    Accessible.name:qsTr('清理')+qsTr(modelData.name)}
                            }
                        }
                    }
                    StudioButton {text:qsTr(String('清理内存缓存'));quiet:true;enabled:!ctrl.exporting;onClicked:ctrl.clearCaches();Accessible.description:qsTr(String('清理可重建的预览与计算缓存，保留照片及编辑参数'))}
                }
                Column {
                    width:parent.width;spacing:14
                    visible:root.category==='interface'
                    MinchoText {text:qsTr(String('界面'));font.pixelSize:Theme.heading;color:Theme.secondary}
                    MaterialSelector {
                        label:qsTr('外观');value:ctrl.preferences.appearance
                        choices:[{id:'system',name:qsTr('跟随系统')},{id:'light',name:qsTr('浅色')},{id:'dark',name:qsTr('深色')}]
                        onSelected:function(value){ctrl.updatePreference('appearance',value)}
                    }
                    RowLayout {
                        width:parent.width;spacing:12
                        MinchoText {text:qsTr('画布背景');Layout.fillWidth:true}
                        Rectangle {width:24;height:24;radius:4;color:Theme.canvas;border.width:1;border.color:Theme.border}
                        TextField {
                            objectName:'canvasBackgroundHex';Layout.preferredWidth:112;implicitHeight:36
                            text:Theme.dark ? ctrl.preferences.dark_background : ctrl.preferences.light_background
                            color:Theme.ink;font.family:Theme.family;selectByMouse:true
                            validator:RegularExpressionValidator {regularExpression:/#[0-9a-fA-F]{6}/}
                            Accessible.name:qsTr('当前外观的画布背景HEX')
                            onEditingFinished:if(acceptableInput)ctrl.updatePreference(Theme.dark ? 'dark_background' : 'light_background',text)
                            background:Rectangle {radius:4;color:Theme.surface;border.width:1;border.color:parent.activeFocus ? Theme.accent : Theme.border}
                        }
                        StudioButton {text:qsTr('复位');quiet:true;onClicked:ctrl.updatePreference(Theme.dark ? 'dark_background' : 'light_background',Theme.dark ? '#252724' : '#DEDEDA')}
                    }
                    MaterialSelector {
                        objectName:'interfaceLanguageSelector'
                        label:qsTr(String('语言'));value:typeof i18n==='undefined' ? 'zh-Hans' : i18n.language
                        choices:typeof i18n==='undefined' ? [{id:'zh-Hans',name:'简体中文'}] : i18n.languages
                        onSelected:function(value){if(typeof i18n!=='undefined')i18n.setLanguage(value)}
                    }
                    MaterialSelector {
                        label:qsTr(String('界面缩放'));value:String(Math.round(ctrl.preferences.ui_scale*100))
                        choices:[{id:'80',name:'80%'},{id:'90',name:'90%'},{id:'100',name:'100%'},{id:'110',name:'110%'},{id:'125',name:'125%'},{id:'150',name:'150%'}]
                        onSelected:function(value){ctrl.updatePreference('ui_scale',Number(value)/100)}
                    }
                    StudioSwitch {width:parent.width;text:qsTr('减少动态效果');objectName:'reducedMotionToggle';checked:Theme.reducedMotion;onToggled:Theme.reducedMotion=checked}
                }
                Column {
                    width:parent.width;spacing:14
                    visible:root.category==='diagnostics'
                    MinchoText {text:qsTr(String('诊断'));font.pixelSize:Theme.heading;color:Theme.secondary}
                    StudioSwitch {width:parent.width;text:qsTr('本机会话接口');objectName:'guiAutomationToggle';checked:ctrl.guiAutomation.enabled;onToggled:ctrl.guiAutomation.setEnabled(checked)}
                    MaterialSelector {
                        label:qsTr(String('记录保留'));value:String(ctrl.preferences.diagnostic_retention_days)
                        choices:[{id:'1',name:'1 天'},{id:'3',name:'3 天'},{id:'7',name:'7 天'},{id:'14',name:'14 天'},{id:'30',name:'30 天'}]
                        onSelected:function(value){ctrl.updatePreference('diagnostic_retention_days',Number(value))}
                    }
                    StudioButton {text:qsTr(String('导出诊断'));quiet:true;onClicked:ctrl.exportDiagnostics();Accessible.description:qsTr(String('选择本地 ZIP 位置，仅包含版本、设置及可用的汇总计时；不包含照片或源文件路径'))}
                    MinchoText {width:parent.width;text:qsTr(String('不包含照片或源文件路径'));font.pixelSize:Theme.caption;color:Theme.secondary;wrapMode:Text.WordWrap}
                }
                Column {
                    width:parent.width;spacing:16;visible:root.category==='develop'
                    MinchoText {text:qsTr(String('新照片'));font.pixelSize:Theme.heading}
                    MaterialSelector {
                        label:qsTr('默认胶片');value:ctrl.preferences.default_stock
                        choices:{var r=[{id:'saved',name:qsTr('已保存的默认值')},{id:'last',name:qsTr('上次使用')}];for(var i=0;i<ctrl.stocks.length;i++)r.push({id:ctrl.stocks[i].id,name:ctrl.stocks[i].name});return r}
                        onSelected:function(value){ctrl.updatePreference('default_stock',value)}
                    }
                    MaterialSelector {
                        label:qsTr('默认相纸');value:ctrl.preferences.default_paper
                        choices:[{id:'saved',name:qsTr('已保存的默认值')},{id:'last',name:qsTr('上次使用')},{id:'auto',name:qsTr('随胶片')},{id:'kodak_endura_premier',name:'Endura Premier'},{id:'kodak_portra_endura',name:'Portra Endura'},{id:'kodak_supra_endura',name:'Supra Endura'},{id:'kodak_ultra_endura',name:'Ultra Endura'},{id:'kodak_ektacolor_edge',name:'Ektacolor Edge'},{id:'fujifilm_crystal_archive_typeii',name:'Crystal Archive II'},{id:'kodak_2383',name:'Vision 2383'},{id:'kodak_2393',name:'Vision Premier 2393'},{id:'ilford_multigrade_iv_rc',name:'Multigrade IV RC'}]
                        onSelected:function(value){ctrl.updatePreference('default_paper',value)}
                    }
                    StudioButton {text:qsTr(String('使用当前胶片设置'));quiet:true;enabled:ctrl.currentIndex>=0;onClicked:ctrl.saveNewFrameDefaults()}
                    StudioButton {text:qsTr(String('恢复默认值'));quiet:true;onClicked:ctrl.resetNewFrameDefaults()}
                    RowLayout {
                        width:parent.width
                        MinchoText {text:qsTr('片边机身');Layout.fillWidth:true}
                        StudioButton {text:qsTr('按照片区分');quiet:true;selected:ctrl.preferences.frame_body_seed===0;onClicked:ctrl.updatePreference('frame_body_seed',0)}
                        StudioButton {text:ctrl.preferences.frame_body_seed ? qsTr('更换机身') : qsTr('固定机身');quiet:true;selected:ctrl.preferences.frame_body_seed!==0;onClicked:ctrl.updatePreference('frame_body_seed',1+Math.floor(Math.random()*2147483646))}
                    }
                }
                Column {
                    width:parent.width;spacing:16;visible:root.category==='about'
                    MinchoText {text:'SpektraFilm';displayRole:true;font.pixelSize:28}
                    StudioButton {text:qsTr(String('检查参考引擎更新'));quiet:true;enabled:!ctrl.updateCheck.busy;onClicked:ctrl.updateCheck.check()}
                    MinchoText {text:qsTr(String(ctrl.updateCheck.status));width:parent.width;wrapMode:Text.WordWrap;font.pixelSize:Theme.caption;color:Theme.secondary}
                    StudioButton {text:qsTr(String('查看发布页面'));quiet:true;visible:ctrl.updateCheck.available;onClicked:ctrl.updateCheck.openRelease()}
                    StudioButton {text:qsTr(String('许可证与致谢'));quiet:true;onClicked:ctrl.openLicenseFolder()}
                }
                Item {width:1;height:8}
            }
        }
    }
    }
}
