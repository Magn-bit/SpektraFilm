# Decode 场景直方图

参考 SpektraLab 2.3.2 `1952c63537ec576d24422f1065b12495631346a5`：`Engine/SceneLatitude.swift`、`Features/Develop/Edit/CurvePanel.swift:drawPlaced`和native `Pipeline::scene_latitude_sample`。输入是解码/白平衡及捕获侧预处理后的场景；native在当前纬度和场景曲线真实节点之后重新读取采样像素，统计norm与R/G/B各128格。它不是上方成品RGB直方图，也不能把旧直方图bins映射假装精确多通道曲线结果。

本项目链路：`SceneHistogram`在场景曲线展开时启用 → 当前源的≤256px高精度代理 → 与显影共用的source transfer/基准曝光/镜头准备和pre编辑 → `native_spectral.scene_latitude` → native真实`curved_fractions(_r/_g/_b)` → `SceneHistogram.qml`。横轴为每格中心加`histogram.exposure_ev`，显示−8…+8EV；RGB/亮度用norm，单色通道只读对应真实channel行，无对应数据不冒用norm。材料可承受区间内较亮、区间外淡化。

- 每次实际测量的输入都经过当前变换；只有native确认identity才使用`fractions`。不使用`placed_fractions`，因为那是建议fit而非已提交画面。旧runtime在非identity下缺`curved_*`时显示无数据，避免静默错报。
- 一个单线程低优先级池、一个256px源和一个pre-scene buffer。冷读取/预处理等前台空闲；温热曲线/曝光请求非阻塞尝试共享引擎锁，忙时退让。24/32ms节流而非随输入重置的debounce，滑动期间可以持续发起新测量。
- 相关source stat/epoch、材料/印相范围、WB/校准/捕获修复、曝光、纬度与scene_curves才改变身份；颗粒、成品HDR、成品曲线和蒙版不触发重复scene测量。最新请求覆盖，处理期间切图/参数变化/源被改写的迟到结果不发布。
- 隐藏/折叠停止调度；显影关闭或无照片清空。等待时保留同一来源上一真实分布并明显淡化且显示更新中，不生成假实时形状；换来源立即清空。错误支持重试，导出期间不争用引擎。
- 界面控制器只接一个常量`sceneHistogram`对象，按原生命周期关闭。`data/state/busy`通知QML，`setActive/refresh`为窄入口；内部statistic仅供验证，主区无引擎技术文案。

关键节点已过：`scripts/verify_scene_histogram.py` / `output/scene-histogram-review/report.json`。1200×800真实相机JPEG作为源，实际scene proxy为256×171；四通道各128bins。16次连续曲线输入期间3次真实节点采样、最终当前曲线精确，红通道分布最大变化0.04936；源只读1次。无关颗粒变化不重测、最新请求/3次迟到丢弃、无照片/显影关闭/隐藏状态通过，QML错误0，节点5.85秒。明暗组件截图已实际查看、无截断。这个秒数是整个小节点耗时，不是照片导出或RAW显影速度；确切冻结成品仍由主线程整合，不重复历史大RAW或哈希测试。
