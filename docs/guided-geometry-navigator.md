# 引导透视与照片导航 · 2026-11-09

本次沿用Qt Quick和现有几何数据/原源输出链，参考SpektraLab当前`Model/CropGuides.swift`、`Features/Frame/CropStage.swift`与Windows `desktop/src/panels/LeftRail.tsx`，不声称复现Capture One私有算法。

- 几何工具增加水平、垂直、矩形参考线。四个点以原片归一化坐标保存为当前局部draft；控制点和整条参考线可直接拖动，方向键精调，Tab切换点。拖动不发渲染、不记历史；Esc取消正在拖动的draft。
- 应用时拟合本项目现有垂直/水平透视与旋转参数：水平模式保持垂直值，垂直模式保持水平值；矩形共同拟合。裁切、精确90度转向、翻转、纵横比例、缩放和自动填满状态都保留，不另加绕过输出链的矩阵字段。过短、交叉、越界或超出校正范围的参考线返回明确错误。
- Controller只在原几何方法段新增`applyGuidedGeometry`，一次应用产生一次可撤销事务。应用后参考线继续依真实处理矩阵投影到修正照片，结果可见。底部操作条留出独立64逻辑像素，照片与下方控制点不会被挡。
- 新Navigator复用当前预览的小纹理，范围框来自Flickable和实际照片的交集，适配letterbox和系统DPI。拖框保持抓取偏移、点外部直接定位，双击适合，方向键平移；仅放大时显示。没有再次解码原RAW或创建完整源像素副本。

入口由主线程在EditorTools转发`guidedRequested(mode)`到Studio的`viewport.beginGuides(mode)`，Navigator绑定同一viewport。本模块修改shared/geometry.py、controller几何相邻段、GeometryPanel.qml、PhotoViewport.qml、新增GuidedGeometryOverlay.qml/Navigator.qml与qmldir，不改字体或平台技术栈。

一个有界关键节点已通过：`scripts/verify_guided_geometry_navigator.py`，8.26秒，1366×768逻辑窗口、150%DPI，960×640原文件。三个模式从已知扭曲求回原参数，最大角误差8.24e-9度；真实QTest点拖无render/history、Esc恢复、Apply单次撤销/重做、全源float尺寸640×960×3保持且有限、实际Navigator点击/拖框/fit全部通过，QML错误0。该节点不等于稳定60fps、所有相机RAW或最终打包成品的验收。

截图和报告：`output/guided-geometry-navigator/{guides-before,guides-after,navigator-zoom}.png`及`verification.json`，已实际查看。初次截图发现操作条挡住下控制点，已改为独立预留区域后复验。首次测试宿主错误使用未创建的history键/不存在shutdown方法，改为get与close；Navigator异步component须等ready；一次并行颜色面板尚未完成导致解析中断，稳定后聚合通过。没有重复大RAW、无哈希测试。
