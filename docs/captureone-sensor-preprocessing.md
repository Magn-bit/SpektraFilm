# Capture One A7CR 传感器预处理：宿主绑定与真实运行证据

日期：2026-11-07。目标为已安装的 Capture One `ImgCoreDll.dll`，AMD64，首选 ImageBase `0x180000000`，SHA-256 `ca02b6ac2786e9a100f63221df7340e5df210416eb0bd53a4bb1bfc2306a44a4`。文中的地址均为这个首选基址下的 VA，运行时必须按 RVA 重定位。本次只写研究报告及 `output/captureone-sensor-preprocessing/`，没有更改生产引擎或将 C1 数据打包进发布物。

## 本次确定了什么

不再只有 OpenCL 源码：已将真实 Bayer/G1G2 setter、内核参数上传、相机 ISO 选择、A7CR 内置噪声标定表连起来。另一次正常原引擎运行保留了 32 次 Bayer 与 32 次 GG setter 的观测，和静态恢复的噪声系数及阈值逐浮点相符。尚未恢复 A7CR 黑电平读取与全部 RAW 解包归一化代码；也没有证明完整颜色输出与 C1 完全一致。

相关既有材料：`captureone-raw-algorithm-analysis.md`、`captureone-raw-resource-analysis.md`、`captureone-a7cr-camera-profile-analysis.md`。这些旧文档关于“尚无实际 A7CR 参数”的描述应以本文及后续运行证据补充。

## 1. 正常 A7CR 运行得到的内部值

原始运行证据：`output/captureone-sensor-runtime/setter-observation.json`，REA Evidence `ev_6339f59dd4c37df450627d0ecd7e4284ce12289ab0e984148e51b2d309197aee`。目标为隔离的 `dotnet.exe` 受控 harness，加载正常安装的 ImgCoreDll；Frida 只观察，没有改返回值、参数或认证逻辑。每个 setter 最多保留 32 次，不能把这个上限解释成整张照片只调用 32 次。

| 对象／偏移 | 实际观测 | 对应关系 |
|---|---:|---|
| context `+0x8a8/+0x8ac/+0x8b0` | 2.51200008 / 1 / 1.676 | RGB 白平衡；与正常源信息 WB 一致 |
| context `+0x11000` | 1300 | 处理版本分支；源默认 `IB_I_PROCESSINGMETHOD_DEFAULT=1300` |
| context `+0x11020` | 1 | GG setter 使用的模式数值 |
| context `+0x11038` | 3.90454006195 | 下文 `a`，噪声 floor 系数 |
| context `+0x1103c` | 1.57550001144 | 下文 `b`，Poisson 系数 |
| context `+0x1104c` | 0 | GG 阈值中的附加控制量，语义未命名 |
| context `+0x11060` | 2048 | 此阶段使用的黑偏置整数 |
| Bayer `+0x78/+0x7c/+0x80` | 2.51200008 / 1 / 1.676 | R/G、1、B/G |
| Bayer `+0x84/+0x88` | 166.69566345 / 2048 | regularizer / reference bias |
| GG `+0x7c/+0x80/+0x84` | 639.73236084 / 639.73236084 / 63.97323608 | 两个阈值槽及 0.1 倍阈值 |
| GG `+0x88/+0x8c/+0x90/+0x94` | 2048 / 0.1 / 0.25 / 0 | bias 与其他算法参数 |

`source-infbMetaData.txt` 正常返回 RAW 9504×6336，pixel width/height 均 3.75，RAW uncompressed。它们在 `output/captureone-processor-runtime/`。此前 LibRaw unpack 样本 black=512，而 C1 setter bias=2048，**数值上符合 14-bit → 16-bit 的 ×4 关系**；这尚不能单独证明每个 Bayer 输入样本都等于 LibRaw 原值乘 4，仍须抓实际输入块逐样本比较。C1 白电平值和饱和映射也尚未由这一观测确定。

## 2. A7CR 内置 ISO 噪声表是真实参数来源

已验证 RTTI：`CSonyA7CRImageRep` vtable `0x182917d10`。其 vslot `+0x310` → `0x181adb1f0`，通过逐条 `mov/movss` 将 **34 个 16-byte 记录**写入栈，再传给 `0x1818e8d80` 构造映射。每个记录是 `uint32 ISO; float floorPerISO; float poissonPerISO; uint32 padding`。不是从邻近字符串推测。

完整标定表在 `sony-a7cr-noise-table.json`；重现脚本为 `extract_sony_noise_table.py`。脚本只模拟静态常量搬运，不执行 C1。代表节点如下：

| ISO | floor / ISO | Poisson / ISO |
|---:|---:|---:|
| 50 | 0.0708153993 | 0.0325619988 |
| 100 | 0.0390454009 | 0.0157549996 |
| 200 | 0.0420458987 | 0.0170013998 |
| 320 | 0.0170501992 | 0.0167864002 |
| 800 | 0.0183227994 | 0.0177168008 |
| 3200 | 0.0179159995 | 0.0179775003 |
| 12800 | 0.0168949999 | 0.0182163008 |
| 16000 | 0.0134798000 | 0.0109759998 |
| 102400 | 0.0110087004 | 0.0106811998 |

真实系数解析器 `0x18154e580`：原始 `.pdata` 第一片只到 `0x18154e590`，必须继续读至实际 `ret 0x18154e8dc`。`noise-resolution-linear.json` 保存完整线性片，后面包含下一函数，不能把全部 2048 bytes 都当作这一函数。

解析顺序：

1. 调用 ImageRep `+0x668` 取 ISO，失败回 100；`+0x2f8` 可提供替代 ISO。
2. 调用 `+0x310` 取得相机噪声表；非空时查找不高于当前 ISO 的节点，低于最小节点时保留第一节点。这段没有相邻节点混合算式。
3. 表空时，使用配置 `+0xb4/+0xb8`（`noiseFloorCoeff_ISO` / `noisePoissonCoeff_ISO`）。
4. 两个系数有任一不大于 0 时，改用 `+0xbc/+0xc0` 的 normalisedISO 系数，除以 pixelWidth×pixelHeight。`+0x848` 获取尺寸，失败回 5×5。A7CR getter `0x181adb7f0` 固定返回 3.75×3.75，与正常元数据一致。
5. 乘有效 ISO；其中 `+0x2e8` 可以修正有效 ISO。A7CR 的 `0x181ac1d10` 在 ISO<100 返回 0.5，否则 1；低于 2 的这一分支不形成额外整档除法。
6. 调用相机 `+0x318`（A7CR 跳到 `0x1818d86e0`）进一步修正；可选 `+0x300` 返回估计值时还可能调整 floor。A7CR `+0x300` 明确返回 false。
7. 输出两 float 和一个有效标志，调用方再写入渲染上下文。尚未定位这一最终 context copy 的全部宿主路径。

ISO100 节点乘 100，float32 结果恰为 **3.90454006195 / 1.57550001144**，与正常 C1 hook 的 64 条 setter context 完全一致，最大绝对差 0。`verify_sensor_formulas.py` 与 `formula-cross-check.json` 保存数值交叉验证。

A7CR 另有 vslot `+0x320` → `0x181ac1ef0`：实际 ISO>12800 时，传入两 float 均乘 `exp2f(0.5)`，即 √2，否则返回 false。`0x1818350f0` 的 EnhancedDenoiseBayerToBayer 路径在估计噪声之后实际调用这个 slot。**尚未证明默认非 AI 显影路径也一定调用它**，不能将 √2 无条件套到所有 A7CR RAW。

因此，BASEDEFAULT 中的 `-1/-1/8/0.8` 不能直接作为 A7CR 默认算法参数。它们是有明确 fallback 规则的配置值。

## 3. 配置继承与 ISO 选择：没有发现插值

`0x1818dacb0` 包含 `CCameraConfig::LoadFile` / `parseData` 实际文件读取、XML 遍历及错误消息。它要求 ISO 有序且有 ISO0；相机/ISO 节点继承前一节点的整个参数块，再覆盖显式字段。`0x181dca440` 是数值配置读取器：

| 字段名 | 读取后参数块偏移 |
|---|---|
| noiseFloorCoeff_ISO | `+0xb4` |
| noisePoissonCoeff_ISO | `+0xb8` |
| noiseFloorCoeff_normalisedISO | `+0xbc` |
| noisePoissonCoeff_normalisedISO | `+0xc0` |

`0x1818dc540` → `0x181dcb970` 从尾部向前扫描 ISO 节点，找到第一个 `node.ISO <= image.ISO` 后复制 `node+4` 的 0xdc bytes。另一个 `0x1818dbff0` 同样反向选择，复制 `node+0xe0` 的 0xec bytes。均为阶梯选择；不能称为已经恢复“ISO 插值”。相机噪声表还有上节的独立查表流程，两者不要混淆。

`0x1812fe080` 与 `0x1812fdfd0` 已核实只是 std::string 构造辅助函数；`0x181dc9740` 是 XML 字符串转 float。先前把这些辅助地址当作 ISO 查表候选的猜测不成立。

## 4. Bayer stage 1 的真实宿主公式与上传

`CImgOpBayerC1v2012_1` vtable `0x182747790`，参数 setter slot6 → `0x181681560`。RCX 为 operation，RDX 为渲染 context；它保存 context 到 operation `+0x90`。

```text
op[0x78] = context.R / context.G
op[0x7c] = 1
op[0x80] = context.B / context.G
a = context.float[0x11038]
b = context.float[0x1103c]
op[0x84] = min(65536, 50 * (sqrt(4*a*a/100 + b*b) + b))
op[0x88] = predicate_1818115f0(context) ? 0 : float(context.uint32[0x11060])
```

`exp2f(16)` 是真实 import 调用，所以上限是 65536。正常运行 32 条 Bayer setter 的 regularizer 按 float32 重算，最大误差 0。

GPU 对应链：`CLKernelBayerC1v2012_1` 参数方法 `0x181681480` 将 op `+0x78/+0x80/+0x84/+0x88` 搬到 Apply 子对象 `+0x188/+0x18c/+0x190/+0x194`。`0x181684950` 实际上传：arg5 为 float2(R/G,B/G)，arg6 为 regularizer，arg7 为 reference bias；arg8/9 为辅助图与布局；arg10 的 local memory 取决于 context。它们与已提取 stage1 OpenCL 签名一致。

CPU process slot11 → `0x181683970`，入口 RCX=operation、RDX=source bitmap rep、R8=destination rep、R9=辅助集合。source `+0x40` 为数据指针、`+0x38` 为 byte stride、`+0x1c..0x28` 为 ROI int4、`+0x2c` 为 pixel format。开头直接把 source byte stride 右移 1 作 ushort stride。函数包括 AVX 和普通分支；不能将采到这一入口的 CFA 当作刚从文件解包、完全未校正的 CFA。

第二次正常运行的 `buffer-observation-metadata.json`（Evidence `ev_3481b6d6f0b095fd2750671abbc886c99a822154ec1433d6208ccec7438e9593`）实测 source format1、destination format4，每个 ROI64×64，首块偏移(18,18)，另一块(850,82)，source byte stride2336、destination13856。`+0x1c/+0x20` 是 data 所指 buffer 内的 ROI 偏移，读样本必须额外加 `y*stride+x*pixelSize`；不能把 data 当作该 ROI 的第一像素。该次采样因旧脚本维度断言跳过了像素，证据只证明 metadata。

**CPU 第一步输出是 packed float3 的稀疏 RGB，不是已完成四步的 RGB。** 末端按能力/宽度分派 `0x181686c40`（16px）、`0x181687520`（8px）、`0x181683550`（scalar）。已读完整 scalar 到 `ret 0x181683962`：`0x1816837ea/7f1/7f8` 写 G/B 并将 R 设0；另一相位 `0x1816838ee/8f4/8fb` 写 R/G 并将 B 设0；原始 G 采样点保留 G 并使 R/B 为0。像素步长以 `3*x` 索引。它与 OpenCL stage1 的 float4 接口存在打包差异；不能仅按数组形状直接逐字节比较，需先对应三颜色分量和 CFA 相位。证据在 `bayer-scalar-full.json`。AVX 内部 helper `0x181685930/0x181686760` 的逐像素等价性仍须验证。

GPU wrapper dispatcher `0x181684e40` 的 `.pdata` 第一片极短，完整控制流继续到后面。`bayer-dispatch-full.json` 保存显式线性范围；该文件不以片段结束误判语义函数结束。

## 5. G1/G2 阈值、参数向量与黑偏置条件

`CImgOpAdaptiveGG` vtable `0x18271a328`，setter `0x181647db0`，CPU process `0x181648110`。令 `a/b` 同上，`q=context.int[0x484]+context.float[0x1104c]`：

```text
u = max((100-q)*0.2, 1)
v = u*u
T = min(65535, 0.5*v*(sqrt(4*a*a/(v+1e-6)+b*b)+b))
op[0x7c] = T
op[0x80] = T
op[0x84] = 0.1*T
op[0x88] = predicate_1818115f0(context) ? 0 : context.bias
op[0x8c] = 0.1
op[0x90] = 0.25
op[0x94] = 0
```

中间除法有 double 精度再转回 float，脚本保留这一细节。另有模式/诊断覆盖分支：例如 mode2 或一个全局诊断模式把 `+0x8c` 改为 8，将原 0.1 放到 `+0x94`；不能把默认向量推广到所有模式。

实际 GPU host `0x18164de40`（普通 build/apply）和 `0x18164ebf0`（dark-only）都先建立并调用同一 GG setter，再打包 float8：

```text
( op[0x80], op[0x84], op[0x90], op[0x8c], 110000, op[0x88], 0, 0 )
```

这补上原 GG kernel 中 s0/s1/s2/s3/s4/s5 的来源。主 build/apply 路径还会在 bias>0 时先通过另一个 kernel 做负 bias 加法，再将 bias 传给后续恢复流程；调用顺序不能省掉。具体指令在 `gg-and-default-params.json`。这并不证明默认 A7CR 某次运行走了 OpenCL：上述真实 native hook 用的是正常 CPU 处理。

首次 hook 未读取 `context+0x484`；第二次正常 CPU buffer 观测明确读到 0。用该实际值代入，32 次 GG 的 T 都逐 float32 相符（最大差0）。尚未命名此字段对应的 UI 语义。两次运行使用同一受控 harness/settings；不是把第二次的值伪装成首次逐事件读取。

黑偏置 predicate `0x1818115f0`：bias=0 或 context `+0xb0` 为 7/8 时为 false；否则旧处理版本 `<1300` 为 true；新版本由 `0x1818128e0` 的第一半径是否>0决定。后者还要求 ImageRep vslot `+0x330` 为 true。A7CR 该 slot 指向 `0x1814261b0`，真实字节 `xor al,al; ret`，因此新版本 A7CR 这一路返回零半径，predicate=false，stage1/GG 保留 bias2048。这是静态与实际 setter 观测一致的分支证据。

## 6. 仍须补齐的边界

- A7CR 黑电平从 ARW metadata／解包结果进入 context `+0x11060` 的全部调用链；白电平及高光饱和映射。
- 同一个 ROI 的 GG 前后与 LibRaw unpack 全通道逐像素对照。附录已补受控 CPU Bayer stage1 的输入/输出与隔离 scalar 对照；现有4个 OpenCL内核运行验证仍不替代完整默认CPU管线对照。
- `context+0x484` 的 UI 语义；完整 context 初始化和噪声结果写回点。
- RAW 码值、噪声表单位、WB、相机矩阵、ICC/FCRV、高光重建、输出编码的全链一致性。此次还不足以宣称已复制完整 C1 RAW 引擎。

对自主引擎最直接的启发是：明确传感器码值域与偏置；用相机/ISO标定而不是固定噪声系数；G1/G2与去马赛克共享同一噪声模型；保留halo与ROI约定；分清CPU/OpenCL路径。实现应使用自有或可合法分发的标定数据，研究得到的 C1 表和资源不应直接进入发布包。

## 7. CPU／OpenCL stage1 差异附录：单块真实 A7CR 输入的闭合验证

此次额外验证的对象是正常 C1 CPU 运行捕获的 **64×64** Bayer stage1 ROI，而不是合成平场。捕获证据为 `output/captureone-sensor-runtime/bayer-buffer-samples.json`，Evidence `ev_0e78d7c94aa111e4acb93978d7ebf9d4927639a4a8337ba954cf99aa253738fe`。原始源样本为96×96 ushort，ROI位于(16,16)，上下文参数仍是 R/G=2.5120000839、B/G=1.6759999990、regularizer=166.69566345、bias=2048。捕获外缘16px不应全当已加载传感器数据；本stage1使用的6px halo位于实际所需区域内。

相同输入送入已提取的原始 OpenCL global/no-aux 分支，GPU与独立参考最大差0.0078125；但 GPU 与正常 CPU 输出最大差 **230.080078125**，超过1传感器单位的通道有313个。这个差异保留在 `captured-stage-comparison.json`，不能用宽容差抹掉，也不能据此把 CPU 输出当作完整四步 demosaic。

### 7.0 真实传感器域对照：4倍码值、镜像边界与已改变的绿色

`output/captureone-sensor-runtime/sensor-domain-comparison.json` 将该ROI与同一 ARW 的文件解包结果精确定位。**这不是简单正向矩形拷贝**：ROI第一点对应物理传感器 `(x=8458,y=60)`，本块局部行 `y` 对应 `sensorY=20+abs(40-y)`；在物理第20行发生镜像。若直接正向增加传感器行索引，会得到假差异。这里只测到一处顶边镜像，不推断所有边角填充规则。

| 通道 | 样本数 | 不等于4倍文件解包码值 | 最大绝对差 |
|---|---:|---:|---:|
| R | 1024 | 0 | 0 |
| B | 1024 | 0 | 0 |
| G1/G2合计 | 2048 | 2026 | 116 |

文件metadata black=512，实际Bayer setter bias=2048，R/B逐样本恰等于原始码值×4。这证明这块输入的R/B尚未减去该黑电平，不能把bias2048当成已归零后的再次偏置。绿色已被前处理改变，平均绝对差28.1430664，但此对照本身没有恢复GG全部公式，因此不把全部绿色差异自动归因于某个尚未闭合的GG函数。ARW文件前后SHA256一致。白点15360、其他ISO、坏点或相机的映射仍未因此被恢复。

### 7.1 隔离原生 math worker 与正常 CPU 输出完全相符

完整 scalar loop 表明以下两个函数可独立完成每个 R/B 位点的分类与绿色插值。两者反汇编中均无外部调用。`probe_scalar_bayer.py` 在单独 Python 子进程中正常加载本机已安装 DLL，只给它传入自己分配的 operation、样本和偏移表；没有改写正在运行的 C1、安装文件或配置。

```text
0x1816816d0:
  ushort classify(op*, ushort* pixel, int64 ushortStride,
                  float channelGain, float auxiliaryDifference,
                  int32* spatialOffsets)
0x181682d90:
  float interpolate(op*, ushort* pixel, ushort direction,
                    float channelGain, int32* spatialOffsets)
```

operation `+0x78/+0x7c/+0x80/+0x84/+0x88` 按真实 setter 值填充。空间偏移表是宿主 `0x1816839dd..0x181683b67` 构造的40个 int32；单位为ushort样本数。捕获样本在隔离进程重排为96列后，必须重建stride=96的表，不能继续传正常运行的1168样本stride。此次 `auxiliaryDifference` 显式置零。

结果：隔离 scalar 输出的 **64×64×3 全部 float32 与正常捕获输出逐值完全相符，最大／平均误差均0**。原始 CFA 色通道也完全保持。于是无需假设未知 auxiliary map 或 AVX 舍入误差，便能解释这一ROI的正常 CPU 输出。这个结果只证明这块捕获的数据；没有证明所有 CPU SIMD 分支或非零 auxiliary 条件与scalar相同。

### 7.2 差异来自三项明确算术规则

| 项目 | 原始 OpenCL global 分支 | 原生 scalar CPU 分支 |
|---|---|---|
| 分类中心缩放 | `floor(float(center)*gain)+offset` | `(center*floor(gain*1024)>>10)+offset` |
| 相邻同色样本中点 | `floor((center+neighbor+1)/2)` | `floor((center+neighbor)/2)` |
| 水平分支 east 权重 | `(eastVariation+abs(east2-center))*gain` | `eastVariation+abs(east2-center)*gain` |

其中 `offset=trunc(bias-bias*gain)`。CPU分类中心的固定点规则可直接见 `0x1816816fe..0x1816817a0`；插值中点的 `lea`／`shr 1` 未先加1；水平分支 `0x1816833ed..0x18168348f` 只把同色差乘gain后加到eastVariation上。GPU分支把整个eastVariation也乘gain，不能共享一套未区分算术语义的输出公式。

`compare_scalar_variants.py` 在独立研究进程里做逐项消融，保留原始 GPU 参考结果；未改生产实现：

| 独立参考变体 | 2048个R/B位点方向不符数 | 与原生 CPU 输出最大差 | 平均差 |
|---|---:|---:|---:|
| 原始 GPU 规则 | 7 | 230.078125 | 0.88234138 |
| 仅改CPU固定点中心 | 0 | 154.12890625 | 0.84421206 |
| 再改CPU中点取整 | 0 | 154.12890625 | 0.84421206 |
| 再改对称east权重 | 0 | **0** | **0** |

此真实ROI的样本中点本来都是偶数，所以中点规则变化不影响这块数据；需要奇数合成样本才能单独覆盖这一分支。组合CPU规则后，除了最终所选结果，**每个色点分别强制方向1／2／3的6144个绿色候选值也与隔离原生 worker 完全一致**。这排除了只让当前分类碰巧选对一个候选的解释。

后续独立交叉验证已覆盖28项：9种合成输入×3套显式参数，再加这一真实A7CR捕获；包括奇数、全黑／饱和、方向边缘和噪声。`output/captureone-bayer-cpu-reference/report.json` 保存全部数值：CPU参考分类、三种强制候选与最终输出均逐float零误差，方向错配0。此扩展结果补足奇数中点覆盖，但仍限定于已检查的scalar worker与auxiliaryDifference=0，并未扩大到完整RAW处理链。

最大原始差异位于ROI `(y=33,x=31)`，蓝色原始样本14492、gain≈1.676。GPU缩放中心22904，CPU固定点中心22901：GPU选方向2、绿色19867.455078125，CPU选方向1、绿色19637.375；隔离 scalar 强制方向2时绿色19867.453125，与独立 GPU 参考一致。这是离散分类翻转，不能当成简单浮点尾数误差。

### 7.3 证据边界与可用启发

`isolated-scalar-comparison.json` 保存原生与正常运行的零误差结果；`scalar-variant-comparison.json` 保存逐项消融，包括原先失败数字与所有七个方向差异坐标；`ablation-reference-source.py` 和manifest保存用于复核的独立参考代数及校验和；所有 `.npy` 输出位于本节同名研究目录。该记录不包含可分发的 C1 DLL或原始私有kernel。

本附录闭合的是 **一个真实输入ROI、auxiliaryDifference=0、stage1绿色恢复**。CPU的其他位深／布局、非零辅助图、SIMD跨版本、其他去马赛克stage、GG预处理、相机色彩和输出链仍需分别验证。不能据此宣称已完整复制 C1 Bayer 或 RAW 引擎。

对自主引擎的直接价值是建立稳定、显式的数值合同：不要把“CPU/GPU差异”全部归因于浮点；方向分类必须固定整数化顺序；精确局部候选可以预先缓存；性能优化时分别验证分类图、全部候选和最终像素，防止只看一张结果图漏掉边界翻转。

## 8. 后续 CPU stage 的真实入口，供独立运行采样

以下由已安装DLL的MSVC RTTI→CompleteObjectLocator→vtable关联验证；未将同名factory creator误认为operation。slot6是context setter、slot11是Run，与stage1一致：

| RTTI类 | vtable | setter slot6 | Run slot11 |
|---|---|---|---|
| `CImgOpBayerC1v2012_2` | `0x18274dcb8` | `0x18168cb30` | `0x181690bf0` |
| `CImgOpBayerC1v2012_3` | `0x182753300` | `0x1816930b0` | `0x1816972e0` |
| `CImgOpBayerCollapseRGB32F` | `0x182758880` | `0x1816a1c20` | `0x1816a1dc0` |

Run prologue确认RCX=operation、RDX=source bitmap rep、R8=destination、R9=auxiliary集合。stage2的setter短函数在`0x18168cb75` ret：context保存在op+0x88，R/G、1、B/G存于+0x78/+0x7c/+0x80。stage3的setter保存context于op+0xa0，并另有噪声／能力分支；这里尚未将这些字段命名为已验证的完整宿主公式。

stage3 Run在`0x18169732a..343`先把source ROI的x/y各减6、w/h各加12，并继续可能扩张；采样必须保留入口与出口的ROI metadata，不能把入口ROI指针与后续改变后的坐标混用。此节只是定位下一轮正常运行采样的入口，不宣称已验证CPU stage2/3的完整逐像素等价。

## 证据索引及复核

所有新增静态材料在 `output/captureone-sensor-preprocessing/`：

- `analyze_sensor_host.py`：只读 backed PE；RTTI/vtable、指令、直接调用及 RIP 关联。
- `bayer-operation-setter.json`、`bayer-kernel-bindings.json`、`operation-vtables.json`：Bayer/GG 宿主公式和绑定。
- `camera-config-load.json`、`config-field-reader.json`、`iso-runtime-query.json`、`iso-interpolation.json`、`noise-default-resolution.json`：配置读取及阶梯选择。`iso-interpolation` 仅为早期文件名，其内容证实的是阶梯选择。
- `a7cr-noise-virtuals.json`、`full-sony-noise-table.json`、`sony-a7cr-noise-table.json`：相机表与虚函数。
- `noise-resolution-linear.json`、`sensor-noise-builder.json`：噪声解析与 EnhancedDenoise 调用。
- `verify_sensor_formulas.py`、`formula-cross-check.json`：正常 native hook 的独立数值交叉验证。
- `bayer-single-pixel-workers.json`、`bayer-ratio-full.json`：完整 scalar分类／插值worker（后者显式线性范围到ret）。
- `probe_scalar_bayer.py`、`isolated-scalar-comparison.json`、`isolated-native-*.npy`：隔离原生单像素oracle对正常CPU捕获。
- `compare_scalar_variants.py`、`scalar-variant-comparison.json`、`ablation-reference-manifest.json`：CPU/GPU算术规则消融；保留原始失败差异。
- `bayer-followup-types.json`、`bayer-followup-vtables.json`、`bayer-followup-setters.json`、`bayer-followup-run-prologues.json`：后续CPU stage的真实RTTI/vtable/Run入口。

`field-xrefs.json`、`virtual-call-xrefs.json` 是候选定位辅助；**相同位移不意味着同一种对象或同一字段**。栈位移、其他类虚表的同号 slot 不用于证明相机语义。默认 `.pdata` 长度仅是运行时 unwind fragment；只有经后续控制流检查的范围才用于本报告公式。未重复失败的 Ghidra 冷启动。
