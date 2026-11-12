# Capture One A7CR 相机配置与基础曲线的数值分析

日期：2026-11-07。安装目录：`C:\Program Files\Capture One\Capture One`，既有安装证据为 Capture One 16.8.6.3784。本报告的脚本只读其 ICC/FCRV 资源，不启动 GUI、不加载引擎、不修改生产代码，不将专有 profile 或完整 ICC 三维表加入应用／发布物。后续原生分析已核对 FCRV 版本及部分 metadata；RAW 和 OpenCL 的新证据另见 `docs/captureone-raw-resource-analysis.md`，本文的 profile 试验范围保持不变。

## 已恢复的内容与明确缺口

已恢复 A7CR 标准 ICC `mft2` 的输入曲线、矩阵、33³ 色彩表格式及可计算的局部变换；已解析五个 FCRV 的全部字节和三组坐标点。独立 ICC 插值实现经 LittleCMS 2.19 的 14 个合成 RGB 样本交叉验证，最大差约 0.502 Lab 单位，处于 LAB8 量化尺度。这是标准 profile 变换的验证，**不是 C1 对 RAW 成片的完整复现**。

本报告的 ICC/FCRV 文件本身不提供 Sony ARW 解压／解包、黑白电平、坏点、去马赛克、降噪、高光重建、白平衡及内部数据范围。后续已找到 Bayer 和高光 OpenCL 算子并做局部 GPU 试验，但 A7CR 全链调用、真实参数与曲线组合顺序仍未恢复。ICC 不包含这些完整算法，不能将 LibRaw 输出直接套该 ICC 就称为 C1 RAW 引擎。

官方《Base Characteristics panel overview》明确说 RAW 去马赛克后才选择推荐 ICC 并应用 tone curve。官方《Curve section》说明 Linear Response 仍有极端高亮 roll-off，而本机 FCRV 的三个存储点块都呈 identity；因此“坐标已读出”不能证明“完整曲线算子已还原”。

## 实际资源身份

| 文件／关系 | 可复核证据 |
|---|---|
| `Color Profiles/DSLR/SonyA7CR-Generic.icm` | 222184 字节；SHA-256 `d51fe19d17ff271b5aeb1d047ec37097250ace5873b732a9e8a216b6dde9247d` |
| `Color Profiles/DSLR/SonyA7CR-ProStandard.icm` | 222192 字节；SHA-256 `570e3a827d02dc18996d3391994c18d6cc6ae94a8021d7c77d411ba71f418f9f` |
| 与 A7R V 的关系 | 分别与 `SonyA7RM5-Generic.icm`／`SonyA7RM5-ProStandard.icm` 逐字节相同，内部 `desc` 也写 SonyA7RM5 |
| 与 A7R IV 的关系 | 对应 ICC 不同，不能泛化成所有 Sony 共用同一 profile |
| A7CR 的五个 FCRV | Auto、Film Standard、Film Extra Shadow、Film High Contrast、Linear Response，分别与 A7RM5 和 A7RM4 对应文件逐字节相同 |
| EComm 配置 | 另有 `SonyA7CR-EcommReference.icm`／`EcommStandard.icm`；含私有字段，不能视为默认相机解码矩阵 |

安装树另有 A7CR 命名的 Fuji 风格 `.icc`；仅凭在目录中存在不能认定为官方原生默认资源，本次不以它们解释 C1 默认 RAW。共享资源只证明颜色／基调文件相同，不能证明传感器解码分支或整张图输出相同。

## ICC 内部的真实数值函数

Generic／ProStandard 均为 ICC v2.1.0，类别 `scnr`、输入 `RGB `、PCS `Lab `、creator `POne`、header 日期 2022-11-17 17:13:22。`wtpt` 和 header illuminant 为 D50 近似：

```text
XYZ = (0.964202880859375, 1.0, 0.8249053955078125)
```

tag 为 `desc/cprt/wtpt/A2B0/tech`。`A2B0` 是 `mft2`（lut16Type）：3 输入／3 输出、每轴 33 格点、每输入通道 1025 项、每输出通道 512 项，内置 3×3 矩阵为单位矩阵。没有 `rXYZ/gXYZ/bXYZ` 与 `rTRC/gTRC/bTRC` 的矩阵型相机描述；颜色关系位于 33³ CLUT。不能把其中的单位矩阵当作相机到 XYZ 的已恢复矩阵。

标准格式的计算路径：

```text
ICC device RGB u∈[0,1]³
→ 三通道各自的 1025 项 input shaper（本文件三通道一致）
→ 33³ CLUT 插值
→ 512 项 output shaper（本文件全部精确 identity）
→ ICC v2 Lab16 解码
```

ICC v2 输出字值：`L*=word*100/65280`、`a*=word/256-128`、`b*=word/256-128`。研究脚本使用标准 tetrahedral 插值，**不是从 C1 二进制恢复的插值实现**。C1 前序步骤是否已应用黑电平、白平衡、缩放、曝光或 transfer function，不能由这个文件单独回答。

实际输入曲线采样如下，Generic 与 ProStandard 三通道完全相同：

| u | T(u) |
|---:|---:|
| 0 | 0 |
| 1/1024 | 0.0038910506 |
| 1/256 | 0.0156099794 |
| 0.01 | 0.0398864729 |
| 0.02 | 0.0791796750 |
| 0.05 | 0.1882749676 |
| 0.10 | 0.3250354772 |
| 0.18 | 0.4453614099 |
| 0.25 | 0.5066910811 |
| 0.50 | 0.6749370565 |
| 0.75 | 0.8374914168 |
| 1 | 1 |

它只能确认为 ICC 的 input shaper，不能直接命名为 sRGB gamma、曝光曲线或白平衡。

Generic 与 ProStandard 的 35937 个 CLUT 节点中有 9599 个变化。L* 逐节点完全一致；最大绝对 a* 差 5.91015625、b* 差 2.640625，平均绝对差约 0.418845／0.166818。输入／输出曲线相同。因此本机两个 profile 的差异集中于色彩轴映射，不是添加对比度或换 gamma。该节点差不能冒充真实照片最终色差。

合成 device RGB `(128,96,80)/255` 的函数验证：

| Profile | 独立实现 Lab | LittleCMS LAB8 解码 |
|---|---|---|
| Generic | (52.141072,19.618267,22.584035) | (52.156863,20,23) |
| ProStandard | (52.141072,19.456869,22.647169) | (52.156863,19,23) |
| EcommReference | (52.465075,16.469405,18.606546) | (52.549020,16,19) |
| EcommStandard | (52.141072,16.173534,18.425693) | (52.156863,16,18) |

这些是人工 profile 域样本，不是肤色真值、RAW 传感器码值或 GUI 默认渲染。LAB8 的 L 步长为 `100/255`，a/b 步长为 1，不能用它检验高精度全管线等价。脚本按 Pillow LAB 原始 array 的有符号 a/b 字节解码，避免把中性灰误读为 `(-128,-128)`。

## EComm 的私有矩阵候选

两个 EComm 文件的 `P1MX` 均为 48 字节：`data` 前缀、私有标志和可解释为 big-endian float32 的 9 个值：

```text
 1.2733807564  -0.2290428877  -0.0443378650
-0.0664795414   1.3947972059  -0.3283177018
 0.0642906725  -0.3845296800   1.3202389479
```

行和接近 1，但其用途、应用前后顺序和启用条件未知。DSLR Generic／ProStandard 没有该 tag，不能称为已确认的 A7CR sensor 矩阵。

## FCRV 全字节布局

这五个文件可按以下 little-endian 布局解析至文件末尾，没有忽略尾部：

```text
ASCII II
u32 format_version     // 原生 parser 已证实；本机均为 6
u32 n
n × (u32 x,u32 y)       // 第一坐标块，除以 0xffffffff
u32 Factor             // 原生 getter 已证实
u32 length + name bytes
u32 length + name bytes
u32 Flags
float32 FlowAdjust
u32 SensorType
u32 ProductID
u32 FileVersion        // 原生 getter 的字段名；与首部 Version 独立
u32 n2
n2 × (u32 x,u32 y)      // 第二坐标块
u32 n3
n3 × (u32 x,u32 y)      // 第三坐标块
```

Standard 共 284 字节：第一块从 offset10 开始，11 点；Factor 为 2；metadata offset136 为 `[Flags=3,FlowAdjust=1.0,SensorType=0x30000007,ProductID=0x30000007]`；FileVersion offset152 的值为 1、count offset156、点从 offset160 开始，11 点；末 count offset248、点从 offset252 开始，4 点。Auto 与 Standard 仅 byte136 的 `3→35` 不同，其他 283 字节相同。已确认 Flags 的 `0x01` 表示 NoPreLinearize、`0x02` 表示 IsDefault；两者在 Auto／Standard 相同，`0x20` 不能再解释为 IsDefault，其运行时含义与 Auto 选择规则仍未知。

主块部分实际点如下，完整 11 点和另外两块所有点均在 JSON：

| x | Standard / Auto | Extra Shadow | High Contrast |
|---:|---:|---:|---:|
| 0 | 0 | 0 | 0 |
| 0.048245614 | 0.097769507 | 0.110256818 | 0.090142235 |
| 0.096491228 | 0.248162347 | 0.248343797 | 0.247922072 |
| 0.168859649 | 0.453415803 | 0.451905263 | 0.480353726 |
| 0.250000000 | 0.623803538 | 0.626652888 | 0.665271847 |
| 0.502192982 | 0.877952321 | 0.878705828 | 0.899099385 |
| 1 | 1 | 1 | 1 |

Standard 第二块在 `x≈0.25` 为 `y≈0.585751979`，不等于第一块。第三块为 `(0,0)`、`(0.0942982454,0.0686015829)`、`(0.2499999998,0.2506596305)`、`(1,1)`。三块不同，不能只读取第一块就当作完整 tone operator，也不能未经追踪把三块顺次应用。

Linear Response 共 128 字节，三组存储点均只有 `(0,0)`／`(1,1)`，identity 检查已通过。Factor 为 1；metadata 为 `[Flags=1,FlowAdjust=1.0,SensorType=0x75000003,ProductID=0x75000003]`；FileVersion 为 6。官方却说明它有高亮 roll-off，故 identity 只验证坐标解码，不能证明其全部运行过程恒等。

原生 parser `0x1818e3d30` 对首 u32 按版本 2/5/6/7 分支，且 `POFilmCurveGetVersion @0x1818e76c0` 读取 object+0x10，证实首值 6 是用于解析分支的 Version；`POFilmCurveGetFileVersion @0x1818e7700` 读取 object+0x14，证实 metadata 后额外 u32 为独立 FileVersion，而非曲线插值类型或点 count。FileVersion 的具体业务含义仍未知。`POFilmCurveGetFactor` 读取 object+0x70；Flags+0x74、FlowAdjust+0x78、SensorType+0x7c、ProductID+0x80、Gain+0x84 的 getter 也已核对，Version 6 的 Gain 默认为 1。四点及以上的插值路径 `0x181dc5940` 解自然三次样条三对角系统，三点及以下另有导数构造，不能再把任意 slope limiter 当作已恢复原生插值。解析器仅记录该证据，不在本文件试验中冒充完整 C1 evaluator；输入域、边界、组合顺序仍需核查。静态字节证据保存于 `output/captureone-raw-algorithm/native-raw-depth1-slices.json` 至 `depth3`、`native-filmcurve-interpolation-slices.json` 及 `native-filmcurve-version-getters.json`。

## 后续复现必须补齐的证据

1. 明确 Sony ARW 输入归一化、去马赛克、白平衡、降噪、高光处理及内部 profile 输入域。LibRaw 的矩阵与解码结果不能替代这些证据。
2. 用同一 A7CR RAW 固定 C1 引擎版本、ICC、Film Curve、曝光、白平衡、全部默认调整和输出 ICC／尺寸，导出高位深无缩放基准。静态资源不代替真实运行结果。
3. 继续追踪 FCRV FileVersion 业务语义／flags、三块组合、输入域和 Linear Response 高亮保护。格式版本与部分 getter 虽已确认，也不能把任意 cubic 或线性插值近似称为完整原生算子。
4. 分阶段对比颜色渐变、边界、暗部与高光，区分“标准 ICC 局部变换可复现”和“完整 C1 默认图像等价”。

本次没有把 C1 模块或 profile 放进 Windows／Android；完整 RAW 还原仍有上述明确缺口。

## 复核材料

- `output/captureone-camera-profile/profile-evidence.json`：四个 ICC、五个 FCRV 的路径、SHA-256、tag 字节范围、所有坐标点、别名检查、函数样本与 LittleCMS 对照。
- `output/captureone-camera-profile/scripts/analyze_profiles.py`：只读研究解析器；命令 `.venv/Scripts/python.exe -X utf8 output/captureone-camera-profile/scripts/analyze_profiles.py`。只生成少量证据，不复制完整 ICC CLUT。
- 以下官方 article API 正文于 2026-11-07 读取并以 `official-<id>.txt` 保存在研究目录：
  - [Base Characteristics overview](https://support.captureone.com/hc/en-us/articles/360002588917-The-Base-Characteristics-panel-overview)：先去马赛克，后 ICC／tone curve。当前网页已描述 16.9 UI，不能当作本机 16.8.6 已升级的证据。
  - [Curve section](https://support.captureone.com/hc/en-us/articles/360002424317-What-is-the-Curve-section-of-the-Base-Characteristics-tool)：各基调曲线、Linear Response 高亮保护。
  - [Understanding ProStandard](https://support.captureone.com/hc/en-us/articles/27884003595421-Understanding-ProStandard-profiles)：色彩过渡和默认 profile 说明，实际 variant 仍需 GUI 核对。
  - [ProStandard camera profiles](https://support.captureone.com/hc/en-us/articles/360015331377-ProStandard-camera-profiles)。
- 标准格式参照 [ICC.1 lut16Type](https://www.color.org/specification/ICC1v43_2010-12.pdf)，Lab v2 解码公式也核对 [LittleCMS cmspcs.c](https://github.com/mm2/Little-CMS/blob/master/src/cmspcs.c)。这些标准函数不是闭源 C1 引擎调用。
