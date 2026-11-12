# SpektraLab 2.2 原生能力差距审计

审计版本：本地参考树 `output/reference-spektralab-latest/SpektraLab-2201f5fa4d256b0c742b46b8e31f8176a12ca6ea`。这是实际源码及 app wire 的对比，不等于对商用 LR／C1 私有算法的还原。Windows 是本轮交付目标。

## 结论与实施优先级

| 项目 | 上游真实状态 | 本地差距与处理 |
|---|---|---|
| Decode 场景曲线 | 实际 Swift 工具及 native 节点均存在 | 唯一新增 native schema；移植节点及 Vulkan kernel，保留本地显示曲线 |
| Minilab | 仅 Apple 启用，实际仅 Portra 400 → Portra Endura 一对已校准材料 | 为该真实 pair 移植 Vulkan；不冒称全材料可用，不替换默认完整光学路径 |
| 预闪 | native 已有；app 用 0…0.03、步长 .001 | 产品设置与参数桥未接通；无需重写底层模型 |
| 物理片幅 | native 表示画幅长边，4…200mm | 产品固定长边且限16…120；补片型／短长边语义与按照片比例换算 |
| 数字中间片 DI | native、schema、Vulkan 已有 | 产品缺开关与 Cineon 输出语义；不是场景 sRGB 直接输出 |
| Print Effects | app 闸门，关闭时保留设置但禁用 glare／preflash | 属产品状态接线 |
| Contrast Mask | schema 保留，但 app wire **固定 false** | 不作为当前2.2可用功能移植；本地独立 HDR 调整保留 |
| 原生片边及日期 | 本地已经移植 Vulkan 与字体栅格 | 不支持 striped，必须正确处理可变画布与全尺寸资源预算 |

本地额外参数（执行区域、全图曝光峰值、RAW基线曝光、颗粒形态和尺度、halation局部控制、独立中性配光等）均有实际用途，不能通过覆盖整套 upstream 来“升级”。

## Decode 曲线契约

- 证据：`app/SpektraLab/Sources/Model/FilmParams.swift:616`、`:779`；`Features/Develop/Edit/CurvePanel.swift:68`；`engine/src/pipeline/scene_latitude.cpp:77`；`pipeline.cpp:1963`。
- `scene_curve` 为逗号分隔的五行采样：RGB、Luma、R、G、B；每行至少2个数且各值在0…1。app 使用每行129个数（1/8EV间隔）、五位小数。
- 单位正方形映射到中灰周围 ±8EV。单位对角线是不改变画面；identity 发送空串、结构旁路。Shoot层参数更改使底片失效。
- 位置：自动测光／基线曝光、Scene Latitude之后，光谱上采样与Film Exposure之前。查表轴读 `log2(v / middle_gray) + filmExposureEV`，施加 `2^(f(E)-E)` 增益，使Film Exposure与曲线按上游定义组合。
- 处理顺序：先以Y计算Luma增益且保色相，再逐通道应用RGB总曲线，再分别应用R/G/B曲线。表外保持端点增益；负值／非正有限信号不丢失。
- 不得用现有输出编码域曲线代替它，也不得把它放进print LUT bake。

## Minilab真实覆盖与限制

证据：`engine/src/pipeline/pipeline.cpp:293`、`:1772`、`:2091`；`src/core/setup_cache.hpp:48`；`resources/minilab/index.json`和README。

上游只有在Apple、非DI、非scan-film、非反转片且非黑白时尝试加载已登记pair。`SPK_V2_REFERENCE_OPTICAL`环境变量可强制光学参考。实际catalog只有 `kodak_portra_400|kodak_portra_endura`，sRGB／ProPhoto各一张65³表，单张3,295,528字节；不能给其他材料伪造覆盖。

它保留真实胶片显影，通过底片光谱积分及中性反转恢复log-positive，查表得到**相纸CMY密度**，随后执行已有相纸扫描及输出变换。它不是普通显示RGB LUT，也不应该送给print LUT输出接口。其他pair应保留原光学路径；已登记但缺资源／资源失效必须报错。

资源头为28字节（uint32边长、float3低界、float3高界），随后65³×3 float32。上游检查payload及原始材料身份；这是标定正确性的运行时条件，不是本项目禁止的冗余发布哈希测试。

需要特别验证印相live controls：上游`node_minilab`的ep固定 `[1,1,1,0,0,0]`，且绕过enlarger曝光／曲线消费者。不能仅因wire里存在曝光、Y/M、预闪就认定这些控制在minilab上有效；本地接线必须明确适用范围，不能交付无效滑块。

## 预闪、印相方向与片幅

预闪证据：`FilmParams.swift:576`、`:751`，`DevelopPanels.swift:541`。其值是相纸基础光的线性倍数，**不是EV**；0.01已可明显改变画面，UI实用范围0…0.03。native schema是0…1，不能照搬为UI范围。

上游“Brightness”到`print_exposure`用 `2^-stops`（`FilmParams.swift:799`）。本地叫“印相曝光”，用`2^EV`，是相纸曝光的相反读法；若换标签必须同时处理方向与旧设置迁移，不能只改符号。

片幅证据：`FilmParams.swift:43`、`:109`。native `film_format_mm`是长边，以`long_mm*1000/max(width,height)`决定颗粒、halation和DIR的物理尺寸。短边模式应按照片长短边比例换算：135短边24mm在3:2是36，在4:3是32；120短边56mm在3:2是84，在正方形是56。批量应用要为每张照片重新计算，不能从第一张直接复制长边。

电影格式原始尺寸：Super8=4.01×5.79，16mm=7.49×10.26，Super16=7.41×12.52，Super35=14×24.89，65mm=23.01×52.63（mm）。静态规格110=13×17、APS=16.7×30.2、135=24×36、120按短边56、Custom。

## Overscan的尺寸及内存边界

证据：本地`src/pipeline/overscan.cpp:550`、`pipeline.cpp:2331`、`:2517`。

现有striped executor仍把完整平面保存在GPU，只分带执行局部节点；它不是磁盘／主机有界的全图执行器。overscan在whole stage改变宽高，但旧plan由原frame生成。只删除guard会使后续band的坐标与canvas不一致，不能这样“修复”。外部将同尺寸区域逐块当整张照片调用也会重复片边、日期、孔洞，并改变物理粒度。

现已新增独立 `spk_canvas_size` / `spk_render_canvas`：全源曝光checkpoint与峰值，全局canvas布局和随机坐标，delete-on-close磁盘光学平面、完整行/列高斯遍历，或当前device heap可容纳时逐个Gaussian整幅执行；不再截断IIR长尾，不需要关闭DIR或缩图。显式小预算仍保留精确全线执行。它与旧striped执行器不同，详见 `docs/native-bounded-film-canvas.md`。

## 验证范围

本审计使用源码、实际资源目录及app wire取证，没有新增全目录哈希、重复大RAW性能测试或声称完成私有算法还原。新增native实现须在一次集成构建后合并验证：identity bypass、scene曲线位置／色比、真实minilab pair与非pair回退、全尺寸片边尺寸及超预算失败。
