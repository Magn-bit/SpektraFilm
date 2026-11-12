# Capture One RAW：函数体、公式与证据边界

本轮不是完整 RAW 引擎复原。已从本机原始安装字节恢复曝光统计、自动白平衡调度、曲线格式／插值与多个 OpenCL RAW stage 的宿主绑定；完整传感器解码、黑白电平、相机标定、实际 stage 选择和端到端同片一致性仍未建立。

## 1. 目标与方法

| 目标 | 身份 |
|---|---|
| `C:\Program Files\Capture One\Capture One\ImgCoreDll.dll` | AMD64；48,642,824 bytes；ImageBase `0x180000000`；SHA-256 `CA02B6AC2786E9A100F63221DF7340E5DF210416EB0BD53A4BB1BFC2306A44A4` |
| `P1.C1.ImageCoreWrapper.dll` | CIL / AnyCPU / .NETCoreApp v10.0；539,912 bytes；SHA-256 `5AAE6155242B996D23DA0DED07E777BF74F61D0C85A9979FBF26C64AB4D8380B`；MVID `a600cc41-cf07-45a1-b068-7c3a25575c1e` |

主证据目录为 `output/captureone-raw-algorithm/`。读取原始 PE、导出、导入、CIL 元数据和 Capstone 5.0.6 反汇编；未修改安装文件、目录或用户 catalog。父任务另在隔离进程中通过本机安装 DLL 的公开曲线导出做了 runtime oracle，见第 5 节。

REA 原生自动分析首次在 600,000 ms 启动 deadline 超时；根据恢复指引提高到 1,800,000 ms 后，第二次仅返回非 JSON 的 tool call error，未取得可用原生伪代码。没有继续重复相同启动。已有 16 条完整 Evidence 已导出为 `rea-evidence-bundle.json`，随后 `close_binary` 成功结束会话。公式依据可定位的原始机器码，不伪称由 Ghidra 完整反编译取得。

### 反汇编边界修正

- x64 `.pdata` 的 runtime-function entry 可能只是异常处理／分裂函数的一段，**不是完整语义函数边界**。例如 `0x181dc5940` 的首段在 `0x181dc5b51` 结束，实际分支继续到后续地址。
- `--length` 输出是显式线性切片，可能包含后续函数或填充；不能当作完整 CFG。
- 旧切片起点 `0x181dc57e0`、`0x181dc5fa0` 位于指令内部，其解码不用于任何语义结论。
- `pefile.get_offset_from_rva` 不证明地址有原始文件字节。旧 JSON 中 21 个引用／8 个地址落在未文件背书虚拟区；相应 `hex32/f32/f64` 无效。详见 `native-reference-backing-audit.json`。helper 已加入检查。本文使用的数学常量在有效 `.rdata` 中。

## 2. 已确认调用链与尚未恢复范围

| 功能 | 实际静态调用链 | 已恢复 | 未恢复 |
|---|---|---|---|
| Auto Exposure | `ICP_GetAutoExposure 0x18136d530 → 0x1814fa5d0 → 0x18185e820` | 加权 histogram、均值／高光公式、可选 LUT 逆查、范围 clamp | 当前运行策略选择、输入 tile 色彩空间与完整调用上下文 |
| Auto WB | `ICP_GetAutoWhiteBalance 0x18136d710 → 0x1814faab0 → 0x18185f7f0 → 0x1812f8f50` | 小图统计调度、估计器入口、失败返回值 | 估计器完整数学、光源／相机数据来源 |
| Auto Levels Float | `0x18136d130 → 0x1814f9cb0 → 0x181871a90 / 0x181874cb0` | 实际入口链 | 阈值、通道空间及最终映射 |
| 相机默认处理 | `IC_GetDefaultCameraProcessSettings 0x18135fea0 → 0x181552100` | 实际入口；资源任务恢复 defaults/profile 引用 | 默认参数到整条 RAW pipeline 的完整生效链 |
| FCRV | `POFilmCurveCreateFromFile 0x1818e7510 → 0x1818e3d30` | 格式字段、getter、点插入、导数 solve | FilmCurve 三向量在具体 RAW stage 中的完整组合与自动分支 |
| RAW Bayer OpenCL | 第 6 节宿主构造／RTTI → 原始明文 source | 多个 stage 的真实 source 绑定及宏 | A7CR 此次处理实际 dispatch、CPU 对应实现、标定参数值与端到端 parity |

Wrapper 有 417 条 P/Invoke 声明、449 个 native/runtime implementation 记录。`IC_ImageProcessSettings` 的 WB、exposure、gradation curves、recovery 等字段和 debug AHD/bilinear/quick/Engine2024 等枚举都只是声明证据，**不能据此声称算法已恢复或当前相机实际选用该算法**。

## 3. Auto Exposure：具体算式

证据：`native-raw-depth2-slices.json`、`native-ae-histogram-construction.json`、`native-math-import-thunks.json`。

### 3.1 策略选择

`0x18185e915` 读取全局 `0x182d19b2c`：0 进入 histogram 分支 `0x18185f023`，1 进入中心加权分支 `0x18185ea98`，2 进入中位数分支 `0x18185e93d`，其它值返回错误 4。全局位于 `.data` 的未文件背书部分，PE loader 的初始零值不是“当前运行默认值”的观测；静态初始化与设置写入尚未追完。

### 3.2 Histogram 的构造本身也有空间加权

`0x1812f6d70` 分配 256 个 float bins。对三分量 byte 像素 `C0,C1,C2`：

```text
bin = min(255, (306*C0 + 601*C1 + 117*C2) >> 10)
a_x = (1 + cos(2π*x/(width-1))) / 2
a_y = (1 + cos(2π*y/(height-1))) / 2
w = (1-a_x³) * (1-a_y³)
H[bin] += w
```

三分量按 3-byte stride 访问；系数来自实际整数乘法 `0x132/0x259/0x75`，总和 1024。2π 的 double 常量位于 `0x182a3d5b8`；`.5` 与 `1` 分别为 `0x182a3766c`、`0x182a37988`。因此后续 `N` 是空间权重总和，并非简单像素数。输入通道约定与 tile 色彩空间仍需从调用上下文验证；不把 byte 数组的命名推断当作已证实传感器色域。

### 3.3 均值与高光联合

非空／正常 histogram 上：

```text
N = Σ H[i]
μ = Σ (i*H[i]) / N
p = min(N-H[255], 0.99*N)
找到首个 i≥1，使 CDF[i]≥p
q = i-1 + (p-CDF[i-1]) / max(CDF[i]-CDF[i-1], 1)
Emean = log2(110 / μ)
Ehigh = log2(255*p / (N*q))
若 Ehigh 不在 [-7,7] 内：Ehigh = Emean
E = 0.5*Emean + 0.5*Ehigh
target = 28270 = 110*257
r = trunc(exp2(-E)*target)
```

CDF 分支未命中时 `q` 的初始 fallback 是 1。极端黑图、零尺寸、NaN/Inf 行为未做 runtime parity，不能用这些正常域公式替代整函数的错误处理。

随后，若无可选 LUT：`result = log2(target / uint16(r))`；若有 65,536-entry uint16 LUT，则分别从头线性 lower-bound 逆查 target 与 r，再计算 `log2(inv(target)/inv(r))`。未找到时使用 65535。末尾将 result 限制到 `[-4,+4]`。这意味着曲线逆映射和整数截断是算法的一部分，不能只保留 `log2(110/mean)`。

关键指令区间：histogram arithmetic `0x18185f0d0..0x18185f20a`；LUT 逆查 `0x18185f226..0x18185f28b`；最终 clamp 从 `0x18185f3ca` 后开始。`log2f` thunk `0x182072143`、`log2` thunk `0x1820721af`、`cosf` thunk `0x18207236f` 和 `exp2f` IAT `0x1820c60c8` 已由 import table 对应确认。

中位数策略也使用该 histogram；以半权重 CDF 对应 bin×257 作基准，再做相同可选 LUT 逆查与 log2 比值。中心加权策略另有 `0.299/0.587/0.114` float 亮度计算，但其迭代分支尚未整体重建。

## 4. Auto WB：已经恢复的是调度，不是整个白平衡算法

`0x18185f7f0` 要求对象 `this+0x58` 的 RAW representation 存在；从尺寸成员取得图像大小，重复减半直到相应维度不超过 `0x280=640`，再请求统计 tile。小图与 tile 条件不满足有独立错误路径。估计由 `0x1812f8f50` 完成，失败填三个 float `(1,1,1)`。

估计器约 6,970 bytes／1,546 instructions，包含相机 representation 的多次虚调用、候选数据和 log2 运算。当前已保存原始切片，但没有完整恢复统计选择、光源估计和相机标定，因此不能宣称“已复原 C1 自动白平衡”。

对 SpektraFilm 可直接采用的结构启发是：小尺寸统计与全尺寸像素处理分离；不要为了每次滑块移动扫描整张 61 MP 文件。这个建议来自实际调度，不代表照搬 C1 未恢复的色彩算式。

## 5. 曲线格式、自然样条与本机 runtime 验证

### 5.1 FCRV 字段与实际 getter

Parser `0x1818e3d30`：`II` / `MM` 决定端序；其后的 u32 是用于格式分支的 **Version**，不是插值类型。原生 `POFilmCurveGetVersion` 读取对象 +0x10 确认此命名。点向量读取函数 `0x1818e3950` 先读 count，再读 u32 pairs，以 `1/0xffffffff` 归一化。内部 pair 存储次序发生反转，不能不检查坐标语义便直接套资源 bytes。

首向量之后是 Factor、两个 counted strings、Flags、FlowAdjust、SensorType、ProductID；v5+ 还有一个 u32，由 `0x1818e439a` 读取并存对象 +0x14，原生 `POFilmCurveGetFileVersion` 确认其名为 **FileVersion**（具体业务语义未恢复）。例如 Standard 的 offset152=1、Linear 的 offset84=6 就是这个字段。随后 v6+ 继续第二和第三点向量，各自入口直接读取 count；v7 再读 Gain，v6 Gain 默认 1。不能漏掉该 FileVersion 字段，也不能将它称作第二插值类型。

| Export | 地址 | 实际对象字段 |
|---|---|---|
| POFilmCurveGetVersion | `0x1818e76c0` | u32 +0x10，首部格式 Version |
| POFilmCurveGetFileVersion | `0x1818e7700` | u32 +0x14，metadata 后 FileVersion |
| POFilmCurveGetCurve | `0x1818e7820` | pointer +0x58 |
| POFilmCurveGetCCDCurve | `0x1818e7830` | pointer +0x60 |
| POFilmCurveGetContrastCurve | `0x1818e7840` | pointer +0x68 |
| POFilmCurveGetFactor | `0x1818e7850` | u32 +0x70 |
| POFilmCurveGetFlags | `0x1818e76e0` | u32 +0x74 |
| POFilmCurveGetFlowAdjust | `0x1818e7860` | float32 +0x78 |
| POFilmCurveGetSensorType | `0x1818e7880` | u32 +0x7c |
| POFilmCurveGetProductID | `0x1818e78a0` | u32 +0x80 |
| POFilmCurveGetGain | `0x1818e78c0` | float32 +0x84 |
| POFilmCurveGetIsNoPreLinearize | `0x1818e78f0` | flags & 1 |
| POFilmCurveGetIsDefault | `0x1818e7900` | (flags >> 1) & 1 |

Auto 文件额外的 flag `0x20` 语义未恢复。资源文件 A7CR 与其它相机共享曲线／ICC bytes 不证明传感器解码相同。资源和 defaults 的独立记录见 `output/captureone-camera-profile/`。

### 5.2 从函数体恢复的导数求解

点插入 `0x181dc55f0` 以 x 排序，拒绝已有 x 间距 `<0.0001` 的插入；调用导数重算 `0x181dc5940`。点记录 48 bytes：x、y、derivative、lower、upper、rhs，均 double。

令 `h_i=x_(i+1)-x_i`、`s_i=(y_(i+1)-y_i)/h_i`。先构造 interior provisional derivative：

```text
d_i = (h_i*s_(i-1)+h_(i-1)*s_i)/(h_(i-1)+h_i)
d_last = 2*s_last - d_previous
d_first = 2*s_first - d_1
```

2 点退化为直线；3 点给出全局二次多项式导数。4 点及以上继续求三对角系统：

```text
lower_first = 0; upper_first = 0.5; rhs_first = 1.5*s_first
lower_last = 0.5; upper_last = 0; rhs_last = 1.5*s_last
interior lower_i = h_i / (2*(h_(i-1)+h_i))
interior upper_i = h_(i-1) / (2*(h_(i-1)+h_i))
interior rhs_i = 1.5*provisional_d_i
diagonal = 1
Thomas forward elimination / backward substitution → derivative_i
```

这等价于两端二阶导数为零的**自然三次样条**，不是此前早期推断的单调／斜率限制插值。没有证据证明额外 slope limiter。关键指令：初始 slopes `0x181dc5993..0x181dc5b2d`；边界与系数 `0x181dc5b63..0x181dc5d45`；Thomas solve `0x181dc5d60..0x181dc5f4c`；导数回填 `0x181dc5f60..0x181dc5f9b`。

### 5.3 ICGC 不是 FCRV 对象：ABI 与 oracle

`ICGC_GetValueForX 0x181379090` 调用 `0x181426ff0`，求值使用三次 Hermite：

```text
t=(x-x0)/h
y=y0+(3-2*t)*t²*(y1-y0)+h*t*(t-1)*((t-1)*d0+t*d1)
```

ICGC 用 32-byte 对象／24-byte 点记录，与 FCRV 的 40-byte 对象／48-byte 点记录不同，禁止将 `POFilmCurveGetCurve` 的返回值直接传 ICGC。

已由 wrapper 元数据与本机构建机器码确认：`ICGC_Create()->pointer`；`ICGC_Reset(pointer)->void`；`ICGC_Release(pointer)->void`；`ICGC_GetValueForX(pointer,float)->float`；`ICGC_SetCurve(pointer,ref IC_GradationCurve)`。SetCurve 结构为 inline 16 个 `(float x,float y)` 点、int32 count @0x80、StartPoint @0x84、EndPoint @0x8c，总 148 bytes；count 不含两端。native 先加入两端并排序，再构造曲线。AddPoint 此构建是拒绝／stub 跳转，不能作为有效插点 oracle。

父任务以隔离子进程正常加载本机安装 DLL、调用上述 exports，未 patch 或复制分发 DLL。见 `probe_native_curve.py`、`native-curve-runtime.json` 与对应 log：空／reset 曲线返回 identity；3 点在域内匹配二次插值，4 点以上匹配 natural cubic；域外是端点切线线性延伸。随后建立无 SciPy、无 C1 runtime 依赖的独立参考 `native/reference/captureone_curve.py`，限定 finite、有序、间距充分的输入点。44 组 2–18 点曲线（含随机、非单调和负 y）×121 个域内外采样，共 5,324 点，与本机 ICGC float32 输出逐值完全相同，最大误差 0。重复点排序／合并、FCRV 三曲线组合与 RAW 输入域不在该验证子集中。**此项验证覆盖明确子集的 ICGC 曲线行为，不是 RAW pipeline 的端到端 parity。**

## 6. RAW OpenCL：已证实宿主绑定的真实 stage

资源任务从同一个 ImgCoreDll 原始 `.rdata` 提取 119 个 NUL 终止源码、420 个 kernel declarations。绝大多数 kernel／变量名被混淆。不能只凭相邻文本给源码命名；本轮增加了源码地址 → RIP-relative LEA → 宿主构造 → MSVC x64 RTTI 的验证。

证据：`opencl-host-string-refs.json`（143 个 source-start refs 与 1 个 benchmark name ref），`opencl-host-constructor-facts.json`，`native-opencl-raw-host.json`，`native-opencl-bayer-stage-host.json`。source offsets 是 DLL **文件偏移**，函数地址是首选 image VA。

| source file offset | 宿主构造函数 | 已验证类／stage |
|---:|---|---|
| 40,790,064 | `0x18155e660` | `CLKernelBayerC1v2012_2_Standard` |
| 40,797,216 | `0x18155e660` | `CLKernelBayerC1v2012_2_ApplyCA` |
| 40,808,560 | `0x18155e340` | `CLKernelBayerC1v2012_2_ComputeCA` |
| 40,814,992 | `0x18155e9e0` | `CLKernelClippingRecovery` |
| 41,165,392 | `0x181684bc0` | `CLKernelBayerC1v2012_1_Apply` |
| 41,182,368 | `0x18168c470` | `CLKernelBayerC1v2012_1_SensorPlus`，四编译实例 |
| 41,208,528 | `0x181698680` | `CLKernelBayerC1v2012_3_EstimateRedFromBlue` |
| 41,214,464 | `0x181698680` | `CLKernelBayerC1v2012_3` |
| 40,993,680 | `0x18164c970` | `CLKernelAdaptiveGG`（同一构造另建立 Init 类） |
| 40,977,456 | `0x18164c970` | `CLKernelAdaptiveGGChess` |
| 40,979,312 | `0x18164c970` | `CLKernelAdaptiveGGBuildCoeffs` / `AdaptiveGGApply` / `AdaptiveGGDarkOnly` 三编译实例 |

例如 `0x18155e660` 同时建立 Standard、ComputeCA 和 ApplyCA 子对象；两个源码作为第 5 参传入共同程序对象构造 `0x181622c70`。其 `zbc6516e8d5` 编译宏由 context `+0xf70` 布尔选择 `"0" / "1"`，源码据此选择 local-memory 实现。SensorPlus 对 `z3dbd1ff682` 构建 `"0"/"1"/"2"/"3"` 实例；stage3 的该宏为 `"6"`；AdaptiveGG source 的该宏为 0/1/2，分别对应 build coefficients、apply、dark-only 类。资源文件 A7CR 的 G1G2AdaptiveGainEnabled=1 与此功能相关，但 flag 到实际执行的链尚未恢复。这些是实际 host instructions 证据，但尚不能称“某次 A7CR 曝光实际调用了此组合”。

父任务还将 4 个实际 Bayer 原 kernel 在本机 GPU 串联运行，constant RGB 三组、ramp／random 输入均得到有限值，检查了 CFA 原采样、各 stage 输入与 guards 未被改写，结果见 `output/captureone-bayer-runtime/report.json`。这是独立 kernel 运行与数据边界验证；尚无 C1 正常整图输出作对照，不能据此宣称端到端还原。

完整源码／kernel signature／宏依赖 manifest 在 `output/captureone-camera-profile/opencl-source-manifest.json`，选中的 source 在同目录 `opencl-selected/`。资源任务在另一份报告继续解释方向估计、色差与 tile halo，本文不重复把仍在分析的变量语义写成定论。

## 7. 对 SpektraFilm 的实施边界与优先级

1. **马上可用的结构经验**：预览统计用小图；RAW 解码／曝光／相机色彩与胶片显影分层缓存；只有真正依赖被改参数的 stage 失效。RAW 不能在滑块每一帧重新解码。
2. **已可独立重实现并做单元 parity 的部分**：加权曝光 histogram、曝光正常域公式、自然曲线及端点延伸。移入生产前仍应验证输入约定、错误域、性能与用户期望。
3. **需要继续证据的部分**：相机默认参数继承、黑电平／白电平和饱和修复、自动 WB 算法、Bayer stage 参数布局与实际 dispatch、相机 profile 的完整应用顺序。
4. **完整 RAW 复原的验收**：同一原始文件、同一处理选项和已知输出空间，取得正常 C1 处理结果；分别核对传感器解码值、线性 RGB、中间 stage 与最终输出。当前没有这种端到端参考输出，不能宣称已达到 C1 RAW 效果或速度。

若下一轮建立本机 processor runtime oracle，应先继续 wrapper 的以下确切入口，而不是根据名字猜 C ABI：`IC_LoadConfigFile` token `0x06000092`、`IC_GetDefaultProcessSettings` `0x06000095`、`ICP_Create` `0x060000d3`、`ICP_CreateFileProxy` `0x060000d4`、`ICP_CreateExternal` `0x060000d5`、`ICP_CreateDNG` `0x060000d9`、`ICP_ProcessToFile` `0x060000e9`、`ICP_ProcessToFiles` `0x060000ef`。这些入口返回／接收的 processor SafeHandle、process settings、file proxy、callbacks、文件输出参数布局尚未整体确认。本轮不尝试向未知原生结构填零后调用；这种崩溃不能产生有解释力的算法证据。

本轮没有向生产软件引入 C1 DLL、其源码或相机资源，没有创建“已还原 C1 引擎”的后备标签。保留的成果是可复核证据、独立公式及后续测试边界。
