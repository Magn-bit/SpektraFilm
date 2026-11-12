# Capture One RAW 资源与 OpenCL 算子的恢复记录

日期：2026-11-07。目标为本机 Capture One 16.8.6.3784 的 `ImgCoreDll.dll` 与 `coreConfig.cdx`。本记录区分资源字节、宿主静态绑定和合成 GPU 试验；它们均不能单独证明 A7CR 的完整真实运行链。

## 可复核结果

- `ImgCoreDll.dll`：SHA-256 `ca02b6ac2786e9a100f63221df7340e5df210416eb0bd53a4bb1bfc2306a44a4`。发现 119 个 NUL 结尾的 ASCII OpenCL 源块，共 420 个词法 kernel 声明；条件编译分支重复同名声明，因此不是 420 个同时启用的独立处理步骤。
- `output/captureone-camera-profile/opencl-source-manifest.json` 保存全部源块的偏移、RVA、SHA-256、kernel 签名、宏、条件嵌套、相邻可读字符串；28 个 RAW 优先源已在 `opencl-selected/` 做本地研究提取。
- `coreConfig.cdx`：SHA-256 `8f278d10ba1d4aed2b5bf986835a7da2e116fa73346275b14a8ac377e0da4e8e`。前两字节为 `ff ff`，剩余逐字节 XOR `0x81` 后是有效 XML，含 731 个 cameraID。只保留 BASEDEFAULT、A7CR、A7RM5、A7RM4 的有序参数证据，没有复制全数据库。
- 独立原生分析的 `output/captureone-raw-algorithm/opencl-host-constructor-facts.json` 已用构造函数和 RTTI 确认下述 Bayer 类与源块关系，强于邻接字符串猜测。`opencl-host-string-refs.json` 保存实际 RIP 相对 LEA 引用。
- 原始 `ClippingRecovery` 源已在本机 NVIDIA OpenCL 设备执行，29,869 个合成像素与独立公式的最大绝对差 `2.384185791015625e-7`，alpha 与 ROI 外保护值逐位保持；详见 `opencl-highlights-runtime.json`。它只验证此局部算子和人工参数。
- Bayer 四步原 kernel 已在同一 GPU 串联执行：7 个 synthetic 场景及一个真实 A7CR 512×512 传感器裁块，共 32 次 stage 执行。平场颜色的最大绝对误差为 `0.00390625`（65535 幅度域）；原 CFA 采样、finite、各阶段输入不改及 ROI 外 canary 均通过。真实裁块仅 rawpy 解包，没有调用它的去马赛克／白平衡／相机矩阵。详见 `output/captureone-bayer-runtime/README.md` 与 `report.json`。真实传感器数据执行成功仍不证明使用了 C1 默认参数或成片等价。

本地提取的专有源码用于研究，不进入应用、构建依赖或发布物。

## A7CR 实际默认配置

本机条目创建／更新日期均为 2023-11-22：

| 字段 | 存储值 |
|---|---|
| defaultColorProfile | SonyA7CR-ProStandard.icm |
| defaultFilmCurve | SonyA7CR-Auto.fcrv |
| G1G2AdaptiveGainEnabled | 1 |
| sensorRangeGain | 1.0 |

| ISO 条目 | 该条目新增／覆盖的值 |
|---:|---|
| 0 | USM amount 180、radius 0.8、threshold 1.0 |
| 800 | 空条目 |
| 1600 | USM amount 160、antiColorAliasingBlend 0.5 |
| 3200 | USM amount 140、antiColorAliasingBlend 0.75 |
| 6400 | USM amount 120、antiColorAliasingBlend 1、cleanLongExposureAmount 20、FineGrain 10 |
| 12800 | USM amount 100、threshold 1.5、cleanLongExposureAmount 40、FineGrain 20 |
| 25600 | USM amount 80、radius 1.0、cleanLongExposureAmount 60、FineGrain 30 |

同类字段在 A7RM5/A7RM4 条目有相同数值，但不能据此认定三机 RAW 解码流程相同。此处没有 A7CR 特定 black/white 数值或噪声物理标定。

BASEDEFAULT 中存在 `noiseFloorCoeff_ISO=-1`、`noisePoissonCoeff_ISO=-1`、`noiseFloorCoeff_normalisedISO=8`、`noisePoissonCoeff_normalisedISO=0.8`、默认 CNR amount 50、CNR chroma/luma ratio 1.6、noise reduction 50、details 50。`-1` 可能是哨兵；尚未追踪继承、ISO 插值、单位和应用时机，不能将其直接作为数学噪声系数。JSON 保留重复 tag 顺序，避免普通字典吞掉覆盖信息。

## Bayer 三阶段与宿主关系

| 文件偏移／kernel | 已确认宿主类 | 功能与数据形态 |
|---|---|---|
| 41165392 / zb4a41b922a | CLKernelBayerC1v2012_1_Apply | ushort CFA → 稀疏 float4；恢复 R/B 位置的 G，保留原采样 R/B，G 位置仅保留原 G |
| 40790064 / z13bff1d853 | CLKernelBayerC1v2012_2_Standard | float4 → float4；八方向评分，进一步修正 R/B 位置的 G |
| 40797216 / zfff081c06d | CLKernelBayerC1v2012_2_ApplyCA | 第二阶段带 CA 变体，有映射参数及辅助表 |
| 40808560 / zceef100835 | CLKernelBayerC1v2012_2_ComputeCA | 根据给定表和坐标计算 CA 估计；宿主系数还需追踪 |
| 41208528 / z95ba5a4538 | CLKernelBayerC1v2012_3_EstimateRedFromBlue | 对角方向恢复 R 位的 B 与 B 位的 R |
| 41214464 / z48dd14e643 | CLKernelBayerC1v2012_3，mode 6 | 在两个 G 位置恢复 R/B；完成每格 2×2 的三通道颜色 |
| 41182368 / ze99c0282a3 | CLKernelBayerC1v2012_1_SensorPlus | 另一组四种 mode 的 SensorPlus 路径，不能直接替代普通 A7CR stage 1 |

第一阶段源引用位于 `0x181684cf0`，所属构造片段 `0x181684bc0..0x181684d61`；SensorPlus 引用为 `0x18168c58e`。第二阶段两源在 `0x18155e660` 构建的同一个对象内注册；CA 子对象构造 `0x18155e340`。第三阶段主源引用 `0x1816987b9`／`0x181699024`，EstimateRedFromBlue 源引用 `0x181698b9b`，同属 `0x181698680..0x181699251` 构造区域。地址与绑定来自原生静态证据，没有声称观察了 A7CR 调度。

### 第一阶段的核心数学结构

输入在恢复区域以 RGGB 相位解释，两个像素一组，按行选择 `float2 zf184786901` 的 x／y 分量作为比例 `k`。参数 `b=z503f8efd15` 在式中承担参考偏置，`e=z4b359ac3f7` 承担正则项；需要宿主调用才能把它们确定为真实黑电平／噪声参数及单位。

1. 用 `floor(C*k)+int(b-b*k)` 对 CFA 颜色和附近绿色做差，方向评分还用 `floor(k*1024)` 与 `floor(k*1024*1.6)` 的整数运算。
2. 比较水平方向、垂直方向的变化和，包含 ±4 的远邻、3×3 同色采样网格；有歧义时还检查更大 5×5 同色网格。一个可选 8×8 辅助图会改变方向选择的阈值权重。
3. 选水平、垂直或四向混合；以邻近变化的倒数等价权重构造绿色与同色估计的比值。若选定邻居为 `i`，同色中点为 `M_i=(C_0+C_{±2}+1)/2`（源码在若干分支先进行整数除法），则可将主要比值写为：

```text
W = sum(w_i)
N = max(sum(w_i*G_i) - W*b + W*e, W*e)
D = max(sum(w_i*M_i) - W*b + W*e, W*e)
G_est = (N/D)*(C_0 - b + e) - e + b
```

方向权重、整数舍入、分支、辅助图和溢出行为均影响精确结果，不能把上述概括当作完整逐位替代。末尾不做全局除以 65535，也没有白平衡矩阵；它工作在 ushort 对应的幅度域并输出 float。原 G 和已知 CFA R/B 保留。

### 第二阶段

它从已部分插值的 float4 读取 `G_0`，形成八个候选：垂直／水平三点均值、两条对角线以中心权重 2 的四分之一和，以及四个斜向三点均值；评分除 G 差值外还看对应 R 或 B 的一致性。如果最小评分方向是水平或垂直，保留现有 G；否则将最优斜向候选与水平／垂直较优候选各取一半。仍只填 CFA 原 R/B 与 G，不是完整 RGB。

### 第三阶段

EstimateRedFromBlue 在对角线上比较缺失颜色的两条方向变化，按绿色和已知颜色差构造权重，以中心 G 对邻域色绿比进行重建。mode 6 的主阶段改用轴向邻域，分别填 G 位的 R 和 B。两者均有正则项和根据色／绿相对量启用的权重调整，不能简化成无条件双线性插值。

主阶段 helper `z03aeac13a1` 会先将超过 65535 的分量限幅，再按限幅前后 RGB 总和的比值整体重新缩放，以保留 RGB 总和；这不是最后直接裁白。对全零／异常数据的数学边界应以实际 kernel 试验为准。

## Synthetic probe 的布局与边界要求

这是可复核算子的输入约束，不能当作实际 C1 host 默认参数。

- 优先编译 `-Dzbc6516e8d5=0` 以选全局内存路径；另一个值会增加 `__local` 参数并改变 workgroup／边界行为。静态宿主确认该宏来自 context 的布尔属性，不能把两个编译分支混用。
- 第一阶段和第二阶段：global x 的一个线程处理 2 个横向像素；第一阶段原始输入 stride 按 ushort 元素计，输出 stride 按 float 分量计、源码除以 4；第二阶段两个 float4 buffer 的 stride 同样为 float 分量计、源码除以 4。第一阶段 ROI 为 int4，源码以 `(x,y)` 同时偏移源与目标，`.z/.w` 为处理宽高。
- EstimateRedFromBlue 和主 stage 3：global 每线程处理 2×2；stride 直接按 float4 像素数量计，没有除以 4。ROI 是 int8，`.s0/.s1` 是目标起点、`.s2/.s3` 是区域宽高、`.s4/.s5` 是源起点。
- 第一阶段源中 halo 常量为 6；第二阶段与第三阶段为 2。还必须为成对／2×2 读写预留额外位置。整图 `(0,0)` 直接传给无 local 的邻域 kernel 会触及负地址；必须使用充分 padding 的内部 ROI。
- 多阶段不能只给第一阶段写核心区域而让其余 halo 保持零。每一步需生成下一步所需的外围；缩小 ROI 并保持 Bayer 偶数相位。不要 in-place 写读同一个邻域 buffer。
- 建议先用灰阶平场、每色常量平场、横纵边缘、斜边、高光和平滑斜坡做单阶段试验。人工 `k=(1,1)`、`b=512`、`e=16` 只是测试值，没有从 A7CR 调用中观测到。

## 高光算子完整公式

`40814992_z03df67c650.cl` 的 `float16 p`：`p.s0..s2=t_rgb`、`s3=a`、`s4..s6=d_rgb`、`s7..s9=q_rgb`、`sa=h`。所有量的宿主真实默认值和曝光依赖尚未确认。

```text
对每个原始 c_i > t_i：
  w_i = min((c_i-t_i)*(a/t_i)*min(c_j,c_k)/c_i, 1)
  c'_i = (c_j+c_k)*0.5*w_i + c_i*(1-w_i)
否则 c'_i = c_i

若任一 c'_i > t_i：
  v = sum(max(c'_i-t_i,0)/d_i)
  v *= min(c'_R*q_R,c'_G*q_G,c'_B*q_B)*h
  v = min(v*v,1)
  Y = 0.299*c'_R + 0.587*c'_G + 0.114*c'_B
  c''_i = c'_i*(1-v)+Y*v
```

第一步各通道都读取原始 RGB，不按顺序把修改过的 R 再喂给 G；alpha 原样保留，无邻域 halo。负数、零阈值、NaN 和 OpenCL `min` 的语义需要精确处理，不能自行添加 lower clamp 后仍声称是同一算子。此公式已有原 kernel 的 GPU 合成比对。

## 归一化、噪声和错误候选

- `41453216_z1fda381729` 旁虽有 `blackBiasTable` 日志，但源码实际是 **ushort4 → uchar4 的 8×8 有序抖动量化**：表索引为 `((y+oy)&7)*8+((x+ox)&7)`，`add_sat` 后作 `(255*(value+1))>>16`。它不是传感器黑电平恢复，不能按邻接字符串命名。
- `41454576_z0bb5288793` mode 3 确有 ushort4 对标量作 `sub_sat`，mode 0 依据 `sqrt(poisson*max(signal,0)+floor²)` 构造局部幅度修正。但它们的宿主条件／来源未确定，不能直接用于 A7CR 常规传感器归一化。
- `40958784_z78793c83b4` 的 mode 0/1 是 CFA 四平面的横向／纵向插值；mode 2 计算局部结构权重；不能因它输出 float 就命名为黑白电平归一化。
- G1/G2：原生构造 `0x18164c970` 与 RTTI 已将 `40979312` 的 mode 0/1/2 分别确认绑定到 `CLKernelAdaptiveGGBuildCoeffs`／`CLKernelAdaptiveGGApply`／`CLKernelAdaptiveGGDarkOnly`；同构造另有 `AdaptiveGG`、`AdaptiveGGInit`、`AdaptiveGGChess`。证据为 `native-opencl-greengain-host.json` 和合并后的 `opencl-host-constructor-facts.json`。A7CR 默认启用 G1G2AdaptiveGainEnabled，但 flag 到实际相机调用仍未追完。
- 其中 `40979312` 的 mode 0 用 float CFA 对绿格和邻域统计两组 3 平面映射；mode 1 消费这些映射修正绿色采样，加入参考偏置并限至 0..65535；mode 2 以 ushort CFA 做暗部绿色的对角边缘权重平滑，保留同一横对中的 R/B 原值。mode 2 的暗部权重在扣偏置信号低于阈值时最大，到 4 倍阈值衰减为 0；阈值、bias、映射尺寸及模式的宿主真实取值还未确认。
- `41686560_zc20949a44d` 的 mode 0 将 RGB 编为 `L=R+2G+B+offset` 与 `(R-G)*32767/L`、`(B-G)*32767/L`；mode 2 重建色彩后按 0.299/0.587/0.114 亮度比缩放并限倍率 2。这说明有亮度／色度分离处理，但邻接的 PreColorNoise2012 不证明所有 mode 被当前相机选中。
- `41624656_zaf0647f3de`（LumaNoise2018 邻接）、`41413744`／`41419040`（ColorNoise2012 邻接）、`41888368`（SpikeNoiseReductionLuma 邻接）已提取完整源和条件签名。模式、参数绑定、噪声标定和实际顺序仍要继续追踪。

## 未恢复的关键链路

1. Sony ARW 压缩数据的实际入口、传感器解包、黑／白电平来源、坏点与线性化顺序。
2. A7CR 实际调用哪个 Bayer／GG／降噪分支，输入 CFA 相位、真实参数、ISO 插值及白平衡／曝光因子。
3. 分块 scheduler 的 padding、CFA 相位修正、边界扩展、global/local workgroup 以及缓存复用。
4. Bayer 后的颜色空间、ICC 输入 transfer domain、FCRV 组合顺序与最终输出变换。
5. 同一真实 A7CR RAW 在固定设置下的高位深 C1 输出和逐阶段数值对照。当前人工 GPU 算子试验不替代此证据。

## 重做命令

```powershell
.venv\Scripts\python.exe -X utf8 output/captureone-camera-profile/scripts/analyze_raw_resources.py
```

该命令只读安装文件，在研究目录生成有序相机参数和 OpenCL manifest／选中源；不会加载 C1 引擎或改动安装。ICC/FCRV 的独立分析见 `docs/captureone-a7cr-camera-profile-analysis.md`，两份报告互补，profile 不是 RAW 解码器。
