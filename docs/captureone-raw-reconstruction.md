# Capture One RAW 重建状态与验收入口

日期：2026-11-07。目标：本机 Capture One 16.8.6.3784，`ImgCoreDll.dll` SHA-256 `ca02b6ac2786e9a100f63221df7340e5df210416eb0bd53a4bb1bfc2306a44a4`。**尚未完整独立还原 RAW 显影算法，也未接入 SpektraFilm 正式引擎。** 下列结果区分原引擎参考、局部独立实现与仍未完成的链路，不用完成百分比掩盖未知部分。

## 已取得的可复核结果

| 环节 | 当前证据 | 尚不能据此声称 |
| --- | --- | --- |
| 正常完整输出参考 | 原版 wrapper 在隔离进程正常输出 A7CR 6336×9504 RGB16 sRGB TIFF，ProcessToFile 约2.33秒；精确设置、输入/输出SHA、ICC和日志均保存 | 独立引擎、GUI全部默认效果、完整光谱胶片2.33秒 |
| RAW 码值域 | 实际 Bayer 输入64×64裁块的1024个R及1024个B样本，逐值等于文件解包值×4；黑偏置512→2048仍保留 | 全部机型/ISO、白点饱和映射、压缩ARW解包已重建 |
| 分块边界 | 同一裁块通过原CFA唯一序列定位，观测到sensor行倒序及在物理y20处镜像扩展 | 所有边/角/缩放tile规则已恢复 |
| A7CR相机噪声参数 | 34档ISO表、查表/覆盖和阈值公式；64条真实setter数值与重算值完全相同 | 自动白平衡、其他相机标定和全部降噪已恢复 |
| 标量曲线 | 独立自然样条/三点二次/端点切线外延；5324个原生float32采样逐值相同 | FCRV组合及完整RAW色调域已恢复 |
| GPU Bayer四步参考 | 可读参考；76个单阶段对照通过；同一第一阶段输入的后三步级联通过 | 完整四步逐像素等价：仍有3个严格失败场景 |
| CPU Bayer第一步 | 捕获正常运行输入/输出；原生隔离scalar与实际64×64×3输出完全相同；已定位CPU/GPU公式差异 | GPU原式就是Windows实际CPU原式、全去马赛克已恢复 |
| CPU Bayer第二步 | 独立绿色细化公式：7组隔离参数覆盖8个方向；两个正常运行64×64输出块逐float32相同；保留缺失通道负黑偏置 | 辅助细化分支、完整去马赛克已恢复 |
| CPU Bayer第三步局部 | 对角与绿色位置的两个独立标量色差插值器，15组人工场景逐float32相同 | 正常Run使用优化平面/SIMD路径及后续噪声/细节处理；标量通过不等于实际第三步等价 |
| 中性色彩前段 | 实际运行确认曝光原地变换→归一→主曲线→预ICC传递→相机ICC→输出ICC；288个中间标量重放，主曲线最大差5.96e-8，其余已验证前段相同 | 非中性设置、完整ICC转换或所有机型已经等价 |
| ICC融合表 | 原引擎使用49³ RGB16融合表；独立标准ICC生成64个捕获角点，最大差9个16位码值；48个实际RGB输入三通道最大差4.971586e-5 | 融合表生成逐位等价；没有通过捕获的专有表代替独立计算 |
| 高光局部算子 | 独立公式，12组人工参数/90036像素对原GPU最大差7.153e-7，alpha/输入/guards保持 | 真实相机默认阈值、高光处理全链或整图等价 |
| 相机ICC/FCRV资源 | 标准ICC mft2解析、三线性以外的四面体CLUT；FCRV完整字段解析和曲线局部恢复 | ICC是RAW decoder、仅拼这些资源即可得到C1成片 |

## 同片显示与尺寸比较

完整参考：`output/captureone-processor-runtime/raw-render.tiff`，SHA-256 `20d6ebf44528bac63367ccd6c53d3cb71ccc344766dc18c4752b01f784e1b8b6`。本机原引擎资源仅原地读取，没有复制到应用或发布包。

`output/captureone-raw-comparison/compare_same_raw.py` 用项目当前LibRaw显影策略生成16位研究对照；生产`read_photo`当前仍返回8位RGB。这份对照用于区分RAW基础显影差异，不包含胶片模拟，也不是品质评分。C1使用通用native defaults加明确WB、profile、curve和geometry，**未套全部GUI相机默认锐化/降噪**。

LibRaw朝向后为6376×9564，C1有效区为6336×9504。只做平移搜索，共同区取LibRaw `(x20,y28,width6336,height9504)`，边缘相关系数0.99269；没有拉伸、曝光/色彩拟合。共同区采样平均sRGB码值亮度分别0.51433和0.54127；这些平均值不是物理曝光，也不能代替色调/颜色/细节的逐阶段核对。

![同一ARW的RAW基础显影比较](../output/captureone-raw-comparison/same-raw-comparison.jpg)

源研究副本SHA-256始终为 `c0d80fc67e79e84ee5c4d6ba71c11c8407af13356f47ac2fec53176b73cae56e`。原M盘照片不改写；代理、原引擎缓存和实验输出均保存在项目`output/`。

## 必须继续解决的缺口

1. 完整ARW解包、坏点、黑/白电平来源及各种机型/ISO/压缩方式；目前只有单个未压缩A7CR样片的部分码值关系。
2. CPU绿色细化辅助分支、第三步实际平面/SIMD路径及后处理、Bayer CPU与GPU的分别等价性、方向平局/浮点传播及边界调度；不能把OpenCL或标量局部测试当作实际CPU全链。
3. 中性设置色彩链顺序已有运行证据，但非中性WB/曝光/高光修复的完整参数绑定、ICC融合表生成细节、自动WB统计估计器仍未完整恢复。
4. 相机默认降噪/细节/锐化的完整算法及依赖关系；这些影响C1默认RAW观感，不能只看ICC和色调曲线。
5. 用多张A7CR、不同ISO/曝光、彩色/灰阶/高光/边缘/噪声场做端到端独立输出比对；还没有可验收的独立完整成片。
6. 验证后再将可独立离线运行的实现迁入共享原生引擎，分别完成Windows/Android性能、内存和真机验收。当前生产两端仍使用LibRaw。

## 材料与复现

- [原生算法与曲线](captureone-raw-algorithm-analysis.md)
- [相机ICC/FCRV](captureone-a7cr-camera-profile-analysis.md)
- [OpenCL算子与宿主绑定](captureone-raw-resource-analysis.md)
- [受控原引擎输出及ABI](captureone-processor-runtime.md)
- [传感器预处理与真实标定](captureone-sensor-preprocessing.md)
- [Bayer参考、通过项及严格失败](captureone-bayer-reference.md)
- `output/captureone-sensor-runtime/rea-evidence-bundle.json`：实际setter和CPU缓冲区观测的完整REA证据；脚本只读记录，不替换参数/返回值。
- `output/captureone-sensor-runtime/sensor-domain-comparison.json`：唯一CFA匹配、码值×4和边界反射搜索。
- `output/captureone-sensor-runtime/captured-stage-comparison.json`：同一实际CPU输入下GPU/参考差异；原始230级差异保留，不改成“通过”。
- `output/captureone-raw-comparison/report.json`：同片16位研究比较、尺寸、平移、采样统计与限制。
- `output/captureone-highlight-reference/report.json`：12组人工参数的高光GPU对照。
- `output/captureone-bayer-pipeline/rea-evidence-bundle.json`：正常完整渲染首两组GG/Bayer1/2/3输入输出，只读采集。
- `output/captureone-bayer-cpu-stage2/cpu-refine-comparison.json`：CPU第二步隔离和正常运行精确对照。
- `output/captureone-bayer-stage3/chroma-worker-comparison.json`：第三步两个标量工作器，非实际SIMD整阶段等价。
- `output/captureone-color-runtime/README.md`：中性色彩链、预ICC传递和融合表验证范围。
- `output/captureone-bayer-pipeline/independent-icc-nodes.json`：独立生成融合表角点及残余误差，未放宽验收。

独立研究参考集中在`native/reference/`，应用没有导入。测试：

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_recovered_*.py' -v
```

当前22项：21项通过，1项明确的GPU四阶段严格级联已知失败（expectedFailure）。这个状态不能写成“全部通过”或“完整C1 RAW还原”。证据依赖本地原算子的测试在没有本机研究材料时会跳过，普通源代码测试通过不证明原引擎数值对照发生。

0.3.4 Windows/Android候选已构建并验收，但没有以“C1还原完成”的名义发布；当前正式发布仍为0.3.3。完整光谱GPU迁移与RAW算法重建是两项工作，不混用各自耗时或完成状态。
