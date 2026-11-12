# Windows 0.8.0 成品验收 · 2026-11-11

验收对象为 `output/windows-080-lab232-candidate/SpektraFilm` 内冻结的 Windows 成品，不是开发环境。完整记录在 `output/windows-080-lab232-release-review`；发布事务将复制到 `release/Evidence/Windows-0.8.0`。

- `review.json` 和 `workspace/workspace.json` 均为 `ok=true`，工作区记录为 `frozen=true`。13 项精修检查通过，涵盖曲线首拖与单次历史、通道混合、全局色轮、剪贴板恢复、原尺寸细节对比、三种缓存预算、暗色主题、独立特效开关、命名、曝光范围、排版默认机身、DI 选择和 HDR 输出。
- 包内 HDR JPEG 经独立解码：SDR 照片 1200×800，增益图 1200×800，headroom 5.656854（2.5 EV），codec 2.0.2。此处是小幅真实照片的功能验收，不是大 RAW 性能结论。
- GUI 导入、完整光谱、历史、源尺寸 TIFF 与 ICC、HEIF、原始 Cineon DI、同窗口 CLI/MCP 及独立控制台输出通过；原片大小和修改时间保持不变。28 项既有源码专项证据单独收集，不冒充本次成品重测。
- 字形运行记录确认沿用 `Spektra Bilingual Serif`。实际查看同尺寸深色编辑页、HDR 控件、输出配方和全局色轮截图，检查可读性及参数与底部操作区分离。
- `windows-smoke.log` 记录首帧 2585.1 ms 和 `SMOKE_OK`，没有 QML 错误日志。该单次结果不代表所有设备冷启动时间。

本次没有重复历史大 RAW 全链测试，也没有执行哈希测试。HDR 当前仅支持 sRGB/Display P3 照片 JPEG，Qt 编辑画布仍为 SDR，排版 HDR 与物理片边 DI 显式拒绝。Android 保持 0.5.0/code23。其余真实差异见 [完整功能审计](spektralab-complete-audit.md)，上游增量见 [2.3.2 更新记录](spektralab-update-2026-11-11.md)。

## 空态与可操作性复查 · 2026-11-11

Windows 0.8.0 的外置 QML 修订为 `2026-11-11-copy-2`。无照片时自动回到胶片页；只保留胶片名称和档案入口，隐藏胶片强度、相纸、颗粒、HDR、印相等依赖照片的参数组。裁切、对比、缩放、直方图、照片条、撤销、重做、恢复默认和导出等入口在无照片时隐藏或禁用，对应键盘操作也不可用；导入后尺寸、几何、直方图、预览操作和导出状态恢复。

`scripts/verify_interface.py` 通过，覆盖空态 1480×960、1366×768、1120×760，导入后的几何分组、字体字形、胶片搜索、最小窗口弹窗和系统文件窗口。正式 `release/Windows/SpektraFilm/SpektraFilm.exe --capture-state empty` 退出码 0，截图为 `release/Evidence/Windows-0.8.0/ui-empty-state/empty-packaged-copy-2.png`。56 个源码 QML 文件与发布目录逐文件内容一致。此修订只更新 QML 资源，不重建影像引擎或 EXE。

批量导出仍未验证：此前综合工作流在 `desktop/controller.py:1843` 的线程池等待路径发生 Windows 堆损坏 `0xC0000374`；本次未重复运行该工作流，不能把它记作通过。

## 首图自动显示与状态开关 · 2026-11-11

- Windows 0.8.0 外置 QML 修订为 `2026-11-11-first-photo`。状态型按钮的文案与选中样式都表示当前值；导入页只在新活动照片有实际预览或失败反馈后返回编辑页。
- 候选包 `output/windows-080-toggle-fix-candidate/SpektraFilm` 的 QML、内置字体和资源通过 `scripts/verify_photo_navigation.py`。真实导入工作区载入两张本地测试照片后，首个活动路径自动进入画布，`PhotoViewport.hasImage` 为真，无需点缩略图；同一节点还确认源分辨率细节瓦片、缩放锚点、对比几何和空态移除。
- 候选经过 `scripts/publish_windows_update.py review`，复用了同一冻结候选的完整 Windows GUI / 原生光谱 / 单张原像素导出 / CLI / MCP 检查；未重复历史大 RAW 或批量导出。截图与报告位于 `output/photo-navigation/`，发布审查报告中的 `checks.photo_navigation` 记录实际断言。
