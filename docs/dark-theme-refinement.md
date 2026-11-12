# Windows 深色主题收尾

保留现有业务布局、照片尺寸、字体与字阶，仅修主题配对和绘图重绘。

- 导出主按钮使用独立buttonSurface/buttonInk及hover/pressed颜色，深色主题为浅纸色面配深色字；不再把Theme.ink同时当背景和字色。
- 编辑任务选中态用accentInk/毫不透明的accentText配对；ToolSection悬停与按下使用主题表面，替换固定浅白底。
- 直方图使用独立plotSurface和深色通道线，切换主题会请求Canvas重绘。
- Settings/Orientation/下拉箭头、曲线、色阶手柄和勾选图形补主题重绘；蒙版列表、预设选择与错误表面替换固定浅色。
- `desktop/icon_provider.py`以QSvgRenderer渲染原SVG透明度，再通过QPainter SourceIn替换RGB；纯黑stroke也能准确变浅。`PhotoProvider.requestImage`仅新增`ui-icon/`前缀分支，照片路径与缓存逻辑不变。VectorIcon按实际DPR请求并利用有界缓存，取消每个图标的MultiEffect离屏层。

关键节点仅运行`scripts/verify_dark_theme.py`：原有1200×800预览源、1366×768逻辑窗口、实际1.5DPR，同一窗口light→dark→light→dark。截图已人工查看。导出/选中任务/分组悬停实际控件颜色对比度分别：浅色14.29/6.18/12.02，深色11.83/8.23/8.46，全部高于4.5:1。另检查深色直方图表面、纯黑SVG准确着色、Settings Canvas实际浅色笔画，QML错误0。没有重复导出、完整细节或大RAW性能检查。

证据：`output/dark-theme-review/verification.json`、`dark-editor-1366.png`、`light-editor-1366.png`。
