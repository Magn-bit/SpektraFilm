# Windows 0.8 发布静态预检 · 2026-11-11

这是源码与打包规则的静态检查，未执行候选构建、启动、发布、照片处理或哈希测试。正式发布仍需主线程在确切候选包上完成关键聚合验收。

后续节点已完成：Windows 0.8.0 冻结候选构建及13项成品验收通过。本文保留静态预检时的口径，最终范围见 [成品验收记录](windows-0.8-release-verification.md)。

- `scripts/publish_windows_update.py` 当前收集28个源码专项证据；包括2.3.2 native、Decode场景直方图、深色主题与HDR容器。`layout-boundaries.json`保留排版最后参数/独立footer在1366×768与1440×900的节点。HDR容器报告明确为小图编码fixture；另存320×213真实film-session和source-workspace新增11项整合节点，不冒充成品验收。专项来源与冻结成品结果在review中分开。
- `source_files()` 静态枚举通过，检查时4058个文件（含240个HDR源码/通知文件）；新图标provider、FullDetail/DiskCache、refinement probe、QML组件、认可字体和构建脚本均会进入源码包。该数量不是功能完成率，也不是要求最终包保持固定文件数。
- ExifTool 13.61不是只携带Windows exe：提取的官方Perl源码（含`exiftool`入口及`lib/Image/ExifTool.pm`）与`native/metadata/UPSTREAM.json`均在源码范围内。最终产物由spec带完整runtime目录。
- `windows.spec`包含`PySide6.QtSvg` hiddenimport；PhotoProvider到`icon_provider`的窄导入是可见源码依赖，SVG以QSvgRenderer实际着色。`candidate_metadata`现有检查要求qsvg插件、qwindows插件、libheif及关键QML/运行时文件。HDR runtime DLL与完整runtime目录已加spec/build检查；对应libultrahdr/桥代码/构建和许可已入source_files，构建说明写明NASM与随源码保留的libjpeg-turbo依赖。最终包节点仍须实际核对资源可用。
- 源码版本与Windows版本资源均为0.8.0，尚不能因此称为已发布。GUI与CLI使用同一Analysis/PYZ/依赖目录；发布review要求`workspace.refinements.ok`，不接受仅smoke退出0。

`EditorTools.qml`、`SettingsPanel.qml`、`OutputRecipeDialog.qml`与`SceneHistogram.qml`的可见中文短串已静态核对新增翻译；HDR增益图/峰值、DI和画布色域均有英文、繁体与日文。此次没有重复全量语言运行节点。

已过：source-workspace新增±8EV/DI蓝补偿/默认机身，HDR真实film-session含负片/正片/Layer2/取景/ICC/独立解码节点。新增lab-232-desktop真实照片节点已验证四画布域与DI专用view/原log分离。待关闭：冻结候选构建/运行。深色实际截图与对比度专项已过，不能因此替代确切成品主题检查。review的`reference`已更新2.3.2/1952c635，并保留原2.2.0 baseline_commit，不能将两者或Apple运行状态混淆。

当前未发现证据路径或新增源码资源缺失造成的静态发布阻塞。历史`export-results-ui/verification.json`保留一次已报告的`customNaming` QML警告，不修改旧证据来抹掉它；新聚合与最终候选要验证修正后的实际代码。完整差异以`docs/spektralab-complete-audit.md`为准，尤其半格Data/LUT输入域/Apple平台及有意不加的图库流程。

最终翻译收尾：HDR validate完整错误、两个带参数错误模板、排版HDR拒绝及物理片边DI拒绝已入en/繁中/ja。输出配方动态错误沿现有qsTr全句处理；本次未修改Controller/渲染/业务代码。
