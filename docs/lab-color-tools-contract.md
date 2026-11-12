# Lab 色彩功能补齐 · 2026-11-09

本增量只涉及 Windows 色彩处理与共享数据，Android 不构建。默认参数旁路、既有三轮与 PCHIP 点曲线外观保留。

## 源码证据

参考目录 `output/reference-spektralab-latest/SpektraLab-2201f5fa4d256b0c742b46b8e31f8176a12ca6ea`：

- `app/SpektraLab/Sources/Model/Adjustments.swift`：MixerRow/ChannelMixer 的九个输入系数是单位矩阵之上的百分比偏移，范围 −100…100；ColorBalance 包括 master、shadows、midtones、highlights。
- `app/SpektraLab/Sources/Engine/Layer2Kernel.swift:204`：HSL → 编码 RGB 通道矩阵 → 调色 → 曲线。通道矩阵不会进行灰轴归一化，不能用 LR 原色校准冒充。
- `app/SpektraLab/Sources/Model/CurveMath.swift:256`：四区参数曲线在每个区间中点偏移 `amount/100*width/2`，分界点取相邻偏移均值，强制不递减，再作 Fritsch–Carlson 单调插值；最终 `point(parametric(x))`。
- 同文件 Curve.move/evaluate：端点可以横向移动，其真实域以外返回相应端点常量，不能补出不可移动的假端点。

## 数据与阶段契约

- `Settings.channel_mixer: ChannelMixer`，red/green/blue 三行分别含 red/green/blue（−100…100，默认0）；编码 RGB、HSL 后、曲线之前；与捕获侧 LR calibration 独立。
- `ColorGrading.master: TonalGrade` 追加在现有字段末尾，色相0…360、饱和度0…100、亮度−100…100。采用现有 OKLab 方向、端点保护与色域压缩，作用于全部色调而无区域权重；已有三轮不变。这是独立的感知色彩实现，不宣称与 Lab 的 cosine RGB 相加公式逐像素一致。
- `CurveSet.parametric: ParametricSet`，master/red/green/blue/luma 各一个 ParametricCurve：shadows/darks/lights/highlights −100…100；shadow_split/midtone_split/highlight_split 默认 .25/.5/.75，间隔至少 .05。
- 相同结构用于 `scene_curves`，在曝光→胶片之前的已有场景曲线消费者中取合成样本。
- `normalize_channel_mixer`、`normalize_parametric`、`normalize_parametric_curve` 负责持久化校验；`evaluate_curve(curves, channel, x)` 返回真正的合成曲线，供预览、最终导出与 UI 曲线绘制共用。
- 点曲线采用已有 PCHIP 以保留旧外观；新增参数曲线使用 Lab 的 Fritsch–Carlson 构造，不把两种插值混为同一种。

## 状态

- CPU 数据结构、归一化、合成曲线、通道矩阵、全局轮已实现。
- Settings、CPU 最终链、post 缓存身份、scene 曲线采样已接。
- Native 参数/合成表/着色器已完成，并已集中构建到 runtime；控制器/QML 由主线程接入。
- 仅在整合节点验证旧行为保真、新链 CPU/native 一致、端点域与参数曲线单调性，不重跑 HDR 或 61 MP 导出。

## 关键验收与修正

- 既有点曲线与三轮15项数值检查通过，未改其既有默认视觉。
- 第一轮新增6项关键集成中5项通过（含真实Vulkan新链、旧color/mask）。参数曲线极端单调性检查发现 Hermite 平坦段存在约 `−2.22e−16` 的浮点下降；改为平坦段精确返回端点常量，而非放宽单调性断言。
- 原生构建日志：`output/lab-color-native-build.log`。最终新增链关键验收结果：`output/lab-color-key-validation.log`。
- 最终6/6关键集成检查全部通过（0.815秒），包含真实Vulkan新通道/全局轮/四区曲线/可移动端点整链与原color/mask消费者；未跳过GPU。未执行大RAW导出、HDR重复回归或Android构建。
