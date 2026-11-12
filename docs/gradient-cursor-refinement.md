# 图片光标与渐变蒙版专项 · 2026-11-09

本专项对应根计划第 1、3 项，保留当前技术栈与认可字体；只改 PhotoViewport 和专项验证。

- [complete] 恢复规划、现有 UI/坐标/撤销逻辑与历史验证记录。
- [complete] 修复无条件隐藏系统指针；线性三线整线命中、固定法向羽化、中心平移与独立旋转；输入 1:1、16ms 合并、松手最终提交。
- [complete] 小代理真实 Qt 输入验收：方向/平移/羽化/旋转/撤销、缩放与几何映射、正常/画笔/对比/裁切光标、遮罩暂隐、QML 错误与截图。

发现：旧画笔区使用 Qt.BlankCursor 且绘制光标没有可用性回退；线性仅 24px 点命中，其余任意按下均重画，无法直接操作整条边界。CPU/native start=0→end=1 的 smoothstep 栅格契约正确，不因 UI 改向而改算法。端点仍保持原图 [0,1] 模型范围，避免引入跨端序列化变化。

## 当前实现与取证
- 已用原有 QML Canvas/MouseArea 实现：始终保留原生指针；画笔软边环另绘；中线整线平移、外边界固定法向羽化、独立旋转圆柄、45°新建/15°旋转吸附、方向键微移、背景单击无破坏、Escape 恢复；保留16ms合并和单次撤销。
- 同步取证代理提供当前本机 C1 的公开 UI 类型成员证据（P1.C1.ViewModels.dll / LinearGradientMaskViewModel / LinearGradientHittester，REA evidence ev_e73423f1e555775707af1ba77f6967ccbc641366dc69c698ec1c550b1f26789c）：Middle/Opaque/Transparent 三线；AdjustGradient/DragLayer/NewGradient/Rotation 分离；屏幕命中与45°吸附。这里只证明交互结构，没有宣称恢复 C1 私有像素算法。
- 首轮关键行为节点通过：背景单击不改参数/历史、按下端alpha=1松手端=0、中线远离圆点整线移动、一次拖动一次撤销/重做、边线只沿法向、旋转中心不漂移、Esc不增撤销、实际alpha反转互补、透视+缩放坐标往返、参数调整暂隐遮罩、QML0。
- 样本纠正：旧 output/grain-refinement/no-grain.png 实际为灰色夹具，不能当真实照片视觉证据。改用用户 DSC09118.ARW 的内嵌预览一次提取，小代理只做 UI。

## 验证器错误与纠正
- 首轮等待使用 QTest.qWait 紧循环，持有 Python GIL 导致后台 QRunnable 无法执行；改为 processEvents + time.sleep 让出 GIL，不是产品20秒冷启动结论。
- 第二轮坐标表达式误用了不可见 QML id root；改为局部函数取映射点。业务交互步骤已通过，不重做历史大RAW/导出。
- 搜索过不存在的 MaskToolsPanel/LocalAdjustments/render_worker 旧路径，改以现有实际组件与 controller 为准；M盘当前未挂载，历史风向袋文件已不存在。


## 最终专项结果
- 1366×768 逻辑窗口、Windows 150% DPI 的真实照片 UI 代理检查通过，QML 错误0；相片来自 D:/Download/DSC09118.ARW（9564×6376），只提取一次内嵌JPEG为1200×800，界面夹具缩为960×640。来源记录 output/current-ui/source-preview.json。
- 24步真实鼠标拖动：本地控制点最大位置误差1.17e-13逻辑像素；事件派发中位0.20ms、峰值42.49ms（含Qt测试调度，单峰不能据此宣称稳定60fps或全引擎时延）。保留16ms参数提交合并，松手精确提交。
- 输出证据 output/gradient-cursor-refinement/verification.json、visible-brush-cursor-1366x768.png、three-line-gradient-1366x768.png。已目视检查照片上三线/旋转柄、明暗背景笔圈与遮罩。最后将手柄绘制移出图像clip、保留viewport clip，避免落在照片边界的圆柄只显示一半；最终整合截图由主线程统一生成。
- Cursor记录是Qt窗口游标枚举与各分支显式非Blank配置；QWindow.grabWindow截图不包含系统硬件指针，不能把截图当系统指针录像。画笔软边环与中心十字在实际Canvas上可见。
- 原有 start0→end1 smoothstep、CPU/native/最终导出分辨率与字体未改。端点仍限原图[0,1]，超出源图范围的无限渐变需未来跨端模型统一扩展，未暗改序列化。
- 修改文件：desktop/qml/components/PhotoViewport.qml；scripts/verify_gradient_cursor_refinement.py；本记录。RAW预览代理与证据留在output，发布由主线程整合。
