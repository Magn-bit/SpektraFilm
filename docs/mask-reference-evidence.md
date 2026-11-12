# 蒙版、渐变、曲线及色轮的本机参考证据

日期：2026-11-06。工具：REA 6.8.0（静态 CLI/.NET 元数据与 CIL 解码），Ghidra 12.1.4；参考界面使用 Computer Use / CUA。用户授权对本机 Capture One、Lightroom 及所给风向袋样片研究。本轮没有修改应用代码，没有加载用户既有图库，没有复制商业代码到本项目实现。

## 本轮结论与强度

Capture One 的安装文件提供了**可审计的参数布局、托管包装方法体及原生边界**。它明确区分画笔大小、硬度、不透明度、流量；支持笔触开始/绘制/结束、线性/径向渐变、羽化、细化、复合与栅格化；全局和局部设置均有曲线与阴影/中间调/高光色彩平衡字段。

这些事实能支持独立实现的数据结构和交互分层。它们**不能证明**本项目与 C1 的插值、羽化、笔刷累积、明度分区、色域或混合算法等价。尚未取得商业软件导出的样片对照，不宣称重建其私有像素算法。

## 目标身份

所有 token 仅对记录的 SHA256 / MVID 有效，不是跨版本标识。

| 文件 | 版本/大小 | SHA256 / MVID |
| --- | --- | --- |
| `C:/Program Files/Capture One/Capture One/CaptureOne.dll` | 16.8.6.3784；20,982,784 B | SHA256 `add69b3dfead8c0ddc96ab8a9cfcb983bc3ff2d5fc5a84a1473cbf317a81d45c`；MVID `33acddc1-0848-4513-a6dc-e64ccbc56e45` |
| `C:/Program Files/Capture One/Capture One/P1.C1.ImageCoreWrapper.dll` | 539,912 B | SHA256 `5aae6155242b996d23da0ded07e777bf74f61d0c85a9979fbf26c64ab4d8380b`；MVID `a600cc41-cf07-45a1-b068-7c3a25575c1e` |
| `C:/Program Files/Capture One/Capture One/P1.C1.Core.dll` | 2,523,400 B | SHA256 `fc593d922ea76e976ea7e8f23811670288b409c56079f4e01e9172635d25e5b0`；MVID `d5fc4e94-8039-4f36-8772-78a193ac72a2` |
| `C:/Program Files/Capture One/Capture One/ImgCoreDll.dll` | 48,642,824 B；PE amd64 | SHA256 `ca02b6ac2786e9a100f63221df7340e5df210416eb0bd53a4bb1bfc2306a44a4` |
| `C:/Program Files/Adobe/Adobe Lightroom Classic/Lightroom.exe` | 已核对存在 | SHA256 `3921be3fb59fd28920015b9f95ade71c500ff34a44728d5bed8723b8cd7685cb` |
| `C:/Program Files/Adobe/Adobe Lightroom Classic/CameraRaw.dll` | 159,083,496 B | SHA256 `854f3275b64b8f3f47dc84ec0027f34662d39831c66f88ed17f86d54a9c822bf` |
| `C:/Program Files/Adobe/Adobe Lightroom Classic/Develop.lrmodule` | 26,892,264 B | SHA256 `62b28a8687b6b8fe5dcf35477735378526f99981f9d33773927e0b8b26983ee4` |

Lightroom 本轮只重新核对路径和文件 hash，没有新取得蒙版/曲线/色轮函数体或运行对照；之前 import 证据不能冒充其算法证据。未启动 Lightroom，也未访问其 catalog。

## 静态范围与原始证据

REA 对 `P1.C1.ImageCoreWrapper.dll` 返回完整静态覆盖：558 类型、2,854 字段、2,664 方法、1,031 MemberRef、7,034 call edges、2,999 字段访问、1,242 user strings，无解析 issue。过程没有加载 CLR 或执行目标程序集。

完整父 Evidence：`ev_bab9742e357da71af7482497dc16c5c25f1c27cf0c8c1cee398f99586abd13ac`。

| 用途 | Evidence ID |
| --- | --- |
| C1 主程序集身份 | `ev_34472e3285b7324aa8b7c644f49ff79bee9f7d4bb723f170d67531d55864be44` |
| Wrapper 类型视图 | `ev_e6bc0dd62a600fb760d63ddd8020c2bb71b14fc42dfacefea50fae486ac0f474` |
| Wrapper 全字段视图 | `ev_d5c6f6d72e411aeac48e241445ceaa5b0f6ef0993f2b8a02b9d5ce341672ee29` |
| Wrapper 笔触/渐变声明方法页 | `ev_8bcf0b7b470663cf2229532a37d4b43a85a9b54a12e874e2b53d373dec43f920` |
| Wrapper 曲线包装方法页 | `ev_6d019dab930d8cefbe3569bf6089980f6293b4f57043def569229504bc3d1b08` |
| Wrapper P/Invoke | `ev_64237885ac902e5705e1d6e57fb58e377f8cdafb7509f51b5ad9ea9249217f1c` |
| ImgCore 原生导出表 | `ev_bda6f20d074ece0a0c3caa4ef106c0d896830547b9d3dacbd31fae7c6e4a9a1b` |
| 指定蒙版导出地址视图 | `ev_f5400f1c3cf77d32abbf22aac7141500f0e534d5e7d25bf5b5d9cb352683dc07` |

完整导出 [rea-evidence.json](../output/mask-reference/rea-evidence.json)（45 records，41,839,064 B）。聚焦的身份、字段、方法、CIL anchors、P/Invoke 和失败摘要见 [summary.json](../output/mask-reference/summary.json)。页面分页只投影已保留 Evidence，没有重新运行分析。

## 画笔：可观察声明

`ImgCore.IC_Brush`（TypeDef `0x020000b2`）四字段均为 `r4` / float32：

| 字段 | Field token |
| --- | --- |
| size | `0x0400053f` |
| hardness | `0x04000540` |
| opacity | `0x04000541` |
| flow | `0x04000542` |

`ImgCore.IC_MaskDrawParameters.airbrushInterval` 为 int32（`0x04000543`）；另有 `coverArrowID`。`IC_BrushMode` 声明 draw、erase、auto draw/erase、fill、clone/heal 等不同模式。字段名说明这些概念分开保存，**不说明**数值范围、累积公式、采样间距或时间单位。

托管 P/Invoke 声明与当前 `ImgCoreDll.dll` 的实际导出名称相符，均为 cdecl；仅静态相符，不代表已运行调用：

| 托管方法 token | 原生方法 | PE 导出地址 |
| --- | --- | --- |
| `0x06000120` | IC_MaskBeginPath | `0x181380030` |
| `0x06000121` | IC_MaskDrawPath | `0x181380130` |
| `0x06000122` | IC_MaskEndPath | `0x181380250` |
| `0x06000123` | IC_MaskGetBrushShapeTransitional | `0x181380320` |
| `0x0600012b` | IC_MaskFeather | `0x181382960` |
| `0x0600012c` | IC_MaskRefine | `0x181381920` |
| `0x06000154` | IC_MaskRasterize | `0x18138c290` |

其中 `IC_MaskRefine` 的五参数托管重载 `0x0600012d` 是真实文件内 CIL：IL+6 压入 -1，IL+7 调用六参数 `0x0600012c`，共 8 条完整指令。原始 IL SHA256 `9b72efd50098ce9d51a1f024e053df4c1dc4b538c0eb2fe591f6c77fd0ed2b53`。这是包装层默认参数的代码证据，不是细化算法。

## 线性与径向渐变

- `IC_LinearGradientParameters`：start、stop 为 `IC_POINTF`（x/y float32），midpoint 为 float32，Field token 分别 `0x04000586`、`0x04000587`、`0x04000588`。
- `IC_RadialGradientParameters`：center、locus0、locus1、innerScale、fill（`0x04000589`–`0x0400058d`）。`IC_ParametricMaskFillOptions` 有 pmfFillIn / pmfFillOut。不能据名称推断两个 locus 的确切几何定义。
- 真实包装 API：`IC_MaskDrawGradient` `0x06000124`、带 midpoint 的 `IC_MaskDrawGradientQuickAndDirtyHackWithMidpoint` `0x06000125`、`IC_MaskDrawRadialGradient` `0x06000126`。
- 还存在 `IC_MaskCompositeBuild/Extract/Count` 方法声明和复合 blend-mode 类型，说明渐变形状与复合蒙版是可区分的概念。

可独立实施的设计：形状参数保留可编辑控制点；绘制空间统一到照片坐标；线性工具提供两端和中点、径向提供中心/旋转/轴长/软边；填内/填外与强度分开。以上是本项目的工程选择，需自行定义数学与测试，不将其称为 C1 同款公式。

## RGB 曲线：声明与实际包装代码

`IC_GradationCurves` 声明 curveX、curveR、curveG、curveB、curveL，Field token `0x0400035f`–`0x04000363`。`IC_GradationCurve` 包含 points、count、StartPoint、EndPoint；POINTF 的 x/y 为 float32。

`ImageCoreGradationCurve.SetCurve`（MethodDef `0x06000536`）有完整 230 B CIL，90/90 指令解码，无截断。可直接观察：

1. IL+10/12 创建长度 16 的内部 POINTF 数组。
2. 空输入分支把 count 置 0，StartPoint=(0,0)，EndPoint=(1,1)。
3. 非空输入把首尾端点分别写入 StartPoint / EndPoint，中间点写入 points，count 设为输入长度减 2。
4. IL+223 调用 `ICGC_SetCurve`（`0x06000114`）。该方法在本程序集只有 native 边界声明。

原始 IL SHA256 `2bcf10971edbebf19e35e5d5b3adc44bfeb5b85fd39d89993b218b1a9e32cfa1`。另一个集合重载 `0x06000537` 的行为结构相近。还存在 ICGC_Create / Release / Reset / AddPoint / GetValueForX 声明。

**限制：**16 是该包装方法的内部数组长度，不能推导整个软件最多允许的控制点数；代码中没有本次已取得的插值公式。端点默认单位是归一化 0–1，但不证明所有曲线 UI、处理空间或图像范围相同。

本项目可独立实现主 RGB + R/G/B 通道、稳定端点、点增删拖动、按通道重置；选择公开插值法并测试单调/过冲与中性默认值。不要因 API 名称相似便直接声称输出一致。

## 阴影、中间调、高光色轮

`IC_ImageProcessSettings` 和 `IC_LocalSettings` **分别**声明四组颜色字段：

| 角色 | 全局 Field token | 局部 Field token |
| --- | --- | --- |
| colorBalance | `0x04000473` | `0x040003ec` |
| colorBalanceShadow | `0x04000474` | `0x040003ed` |
| colorBalanceMidtone | `0x04000475` | `0x040003ee` |
| colorBalanceHighlight | `0x04000476` | `0x040003ef` |

每组引用 `IC_RGB32F`，其 r/g/b 为 float32（`0x040002f3`–`0x040002f5`）。两种设置也各自有 gradationCurves（全局 `0x04000486`，局部 `0x040003f9`）。这些是数据布局事实，不能据此确定 hue/saturation/luminance 的 UI 映射、权重边界或色彩空间。

运行界面读取到“色彩平衡 → 三向 → 阴影 / 中间调 / 高光”，每区有 HueSlider、SaturationSlider、LightnessSlider 入口；当时没有照片，控件均禁用。因此已观察的是入口和名称，没有验证这些控件的实际数值、效果或响应速度。

## 受控运行与失败边界

风向袋原样片为 81,102 B，只复制到 `output/mask-reference/source-windsock.jpg`。原片与副本的 SHA256 均为 `77dc014bf2a47f7ca96ee39fabe2e37e19fda615ff2b1df4abaf218a75398c57`，结束时复核相同。

C1 正常启动到此前已有的空临时会话 SpektraPortraitQA，显示“未选择图像”；未打开其照片或改动既有设置。尝试新建独立会话 SpektraMaskReference，名称写入成功，但地点字段输入未可靠生效：set_value 报 channel timeout，后续 accessibility tree 不可用；owned modal 高于主窗，点底部取消又报 outside window bounds。没有点击“好”，未创建会话，未导入样片，未导出商业软件结果。最后通过当前模态截图的标题栏关闭按钮退出，截图确认回到空会话。为避免影响实现，停止重试该路线。

原生 BrushShape 函数 dossier 的 Ghidra 路线在导入/分析 `ImgCoreDll.dll` 阶段触发 `provider_timeout`，启动预算 600,000 ms；profile digest `64922283ade10fadf28df5d1689f74f28ec027c5180b774a9d26635c0e69c554`。日志有大量 unresolved-constructor/pcode 提示，返回 output_incomplete=true，未确认 OOM。没有获得函数 dossier，不能把不完整日志描述成成功反编译。已关闭自己打开的 native session，没有修改 provider 配置或重跑长任务。

C1 主程序集和 P1.C1.Core 的 members 分析超出 REA 67,108,864 B 表示预算；主程序集即使选单一 LocalBrushSettingsModel 仍失败，只保留类型清单，fields/methods/calls 空集合不表示不存在。此后只使用完整成功的较小 wrapper 作为实质证据。

## 未知与后续验收

本轮未解决：C1 笔刷采样/叠加函数、软边公式、flow/opacity 量纲、梯度插值与 locus 语义、RGB/Luma 曲线插值、色轮分区/工作色彩空间、LR 对应算法、同图输出对照及交互时延。

项目应独立验证：中性参数像素不变；软边连续；填内/填外互补；渐变旋转与缩放一致；tile 与整幅一致；曲线端点/通道与中性默认；色轮的零饱和/零强度中性；拖动即刻反馈且松手只提交一次撤销；照片切换与异步旧结果隔离。截图、接口字段或构建通过均不能替代这些检查。
