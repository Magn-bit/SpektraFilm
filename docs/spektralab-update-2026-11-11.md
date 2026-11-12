# SpektraLab 2.3.2 更新核对与移植

本轮核对日期：2026-11-11。以官方 GitHub API、确切提交的完整源码和本机 Windows 原生小样本为证据；未运行最新 macOS 应用，不把 Swift/Metal 静态分析称为 Mac 界面或显示器实测。

后续集成已完成：Windows 0.8.0 于本日正式发布。下表保留各增量调查阶段的责任与范围；确切成品13项精修和输出检查见 [成品验收记录](windows-0.8-release-verification.md)，不是新增大 RAW 性能或 macOS 运行结论。

## 版本与来源

- 主项目：`https://github.com/JamesQiu2005/SpektraLab`。
- 原基线：`2201f5fa4d256b0c742b46b8e31f8176a12ca6ea`，2.2.0。
- 本轮基线：`1952c63537ec576d24422f1065b12495631346a5`，2.3.2，提交时间 2026-11-10T11:49:21Z；官方发行 2026-11-10T11:50:09Z。
- 比较结果：13 个提交、149 个文件。官方 Windows 发行仍为 1.3.4-beta.2，不能称其 Windows 已有 Mac 2.3.2 全部功能。
- 图库 SDK 的 `f236e03b4c8eea622fd7360c4d6277ada48b180c` 未变化。
- API 原件、完整新源码与差分：`output/reference-spektralab-update-20261111/`，不覆盖原 2.2.0 证据。源代码沿用原 GPL-3.0 及材料的各自许可，新增 README 商标说明不构成额外影像功能；不使用其名称宣称官方版本。

## 用户可见增量与真实消费者

表中 `N` 是新基线根目录，`H=N/app/SpektraLab/Sources`，`E=N/engine`。实现状态只表示列出的范围，最终 Windows 成品节点由发布记录单列。

| 增量 | 原版入口 → 处理 → 结果 | SpektraFilm 对应范围 / 当前状态 |
| --- | --- | --- |
| 数字中间片作为相纸条带末卡 | `StockPreviewPanel` / `StockPreviewRules` → `FilmParams.digitalIntermediate` → `Pipeline::di_active_` 输出 Cineon/ProPhoto 代码 → `CineonView` 用 `DIView-Cineon-to-ProPhoto.cube` 做 float32 三线性显示变换 | 原有 DI 输出配方保留；条带入口与普通图像显影的 DI view 由主线程接通。它与 No Print Profile 扫描模式不同，DI 导出原始 log code 不应重复套 view。 |
| 画布色域 | `CanvasGamut` / Mac 菜单 → `GamutProof` → `OutputTransform`，按 Display P3→目标空间的 CAM16-UCS 压缩与真实传递函数显示 | 主线程接画布与细节瓦片；新增 `color_transform.cpp` 与 `spk_color_transform_rgb` 真 GPU 浮点转换薄桥已构建。不能以普通矩阵/ICC重标记替代色域压缩。 |
| 导出预览跟随配方色域 | `MacExportPage` → `gamutProof(recipe.colour)` → 同显示变换 | 本项目实际编码回读打样已接；新画布变换进一步统一普通预览。 |
| GUI 会话 CLI / MCP | `AgentServer/AgentTools/AgentExecutor` → MacDriver 当前窗口的同一模型 | 本轮原有同 GUI 19 项工具已实现并有独立证据；不另开假会话或恢复用户不需要的评级。 |
| 检查更新 | `MacSettingsGeneral/UpdateCheck/UpdateAnnounce` → 构建指定的 release URL，设置可控制启动检查 | 本项目原有显式参考版本查询可复用；不把上游 Mac 自动下载/安装功能暗示为本项目升级服务。 |
| 真 HDR 与峰值亮度 | `HighDynamicRangeGroup` → `HDRSessionCurve` / `HDRGain` → `HDRRendition` / `HDRGainMap` / `ExportWriter` | 不是现有“高光/阴影”调整。native 每介质 gain 曲线与正片独立光谱扫描已移植并构建；HDR 文件模块由独立任务集成。显示器链与最终封装需另验，不以本机 SDR 预览冒称 HDR 显示通过。 |
| 放大机四项回归 | `EnlargerGroup` → 亮度 / Y / M / 预闪 → `Pipeline::minilab_enlarger` → `spk_minilab` 的每通道 `a*gain+offset` | 已移植光学常量规则，保留 neutral 状态；Portra400/Endura 的校准路线现在四项都有实际变化。主线程移除之前因非零控制自动退回光学路线的旧限制，并接预闪新显示范围。 |
| Decode 曲线后的直方图 | `CurvePanel` / `HistogramPlot` → `spk_scene_latitude` 的 `curved_fractions` 与 RGB rows | native 已使用真实 node_scene_latitude→node_scene_curve→像素回读统计；独立 UI 任务接实际最新场景。不能将旧 histogram bins 简单横移冒称曲线后结果。 |
| 更清晰的紧裁切预览 | `FullDetail` / Scheduler，按裁切后的显示尺寸处理 | 本地已有原尺寸细节瓦片 / 自然对比链，可复用；须保持裁切、显示坐标和最终原源输出分开。 |
| 拖放修复 | 2.3.0 `MacDropOffer` 判定可导入文件、结束清理；2.3.1 修复 Finder 文件/文件夹未进入导入页 | Windows 既有文件管理器拖放不依赖 Finder，保留可导入文件判定和清理；不照搬 Apple API。 |
| Intel Mac 启动修复 | 2.3.2 `spk_metal_math_probe` 避免依赖该 GPU 的不融合行为，仍检测 fast-math/reassociation | 仅 Metal 启动数学自检变化，本项目 Windows Vulkan 有独立既有自检，无需用此改写 Vulkan 数学策略。 |

## 放大机精确规则

`EnlargerGroup.swift` 中预闪显示 0…1，实际 wire 为 0…0.2（原最大 0.03）；旧保存数值仍是物理曝光值，不得批量乘除破坏历史。印相亮度使用 −3…+3 stops；Y/M 过滤为 −1…+1。

旧本地 `node_minilab` 对这四项非零直接报 neutral-only；上游旧版则固定 epilogue 为 `{1,1,1,0,0,0}`。新函数比较当前设置与 rest 的 `print_constants`，用实际负片中灰谱、印相灯/滤片和相纸感光度计算三通道比率，预闪以 rest 中灰曝光归一化后加到表格的中灰域。相纸表仍来自校准材料，未以改名 LUT 或经验 RGB 偏移替代。

## 曲线后统计与轴

native `Pipeline::scene_latitude_sample` 复用真实几何、输入传递函数与测光 gain；若存在场景宽容度或 Decode 曲线，则在同一代理上执行真实 GPU 节点并重新读像素。JSON `scene.histogram` 保留 `lo_ev=-16`、`hi_ev=16`、128 个 `fractions`；新增 `fractions_r/g/b` 和有实际变换才存在的 `curved_fractions[_r/_g/_b]`。`exposure_ev` 将统计的 before-film 轴移动到 Decode 曲线轴。`placed_fractions` 是建议拟合值的示意，不能当已提交曲线后的真实统计。

同时修正介质探针：清除当前 Decode 曲线，按印相曝光补偿策略固定探针轴；最终 reply 把 medium 移回场景轴，防止改变曝光或当前曲线后把材料本身的肩部/纬度误量为变化。

## HDR 像素和封装契约

### 负片 / 相纸

新增 C ABI `spk_session_hdr_curve(session,request_json,out_json)`，调用者以 `spk_string_free` 释放。请求仅允许 `headroom`（1.0001…16，默认4）、可选 `clip_ev`（−24…24）和 `include_ramp`。同一介质复用 1024×8 实际光谱探针，在自己的轴上生成 family-A 肩部延伸；返回 256 点 `log2_gain`、平滑 `ks`、原始斜率 `rho`、`domain_log2_y=[-12,0]`、`top=log2H`、`kappa=1`、`rho_max=2`、`detail_clamp=.10` 以及诊断。无适用中灰/肩部、DI log code 和开启印相 EDR 的会话明确拒绝，不能返回随意的通用提亮表。

显影后的 16-bit Display P3 SDR 像素不改动，单独求全尺寸灰度增益图。用线性 P3 的 Y 系数 `.2289746,.6917385,.0792869` 得到 `own=log2Y`，局部 Gaussian tone 为 L，`L'=own-clamp(own-L,−.10,.10)`；`gain=clamp(Ks(L')+κ·clamp(ρ(L'),0,2)·(own−L'),0,top)`。输出代码 `round(gain/top*255)`。Gaussian σ=2×实际颗粒宽度，分条计算并保留 halo；不能把缩略图放大做最终图。屏幕仅按当前 headroom 权重显示该图，与文件是否保存增益图分开。

### 正片

正片是三层染料密度的 HDR 扫描，不是负片印相 gain 表。新增参数 `scan_hdr_headroom`、`scan_hdr_stretch`、`scan_hdr_output_scale`、`grain_seed`，缺省保持原扫描。`scan_hdr.cpp` 在真实染料谱积分下解三层中性灯亮度，移动各层肩部并在显影密度范围中压缩、于光谱扫描前展开，保留层间光谱串扰。SDR rendition 用 stretch 将透明片基放到0.98；HDR rendition 用 H 和 gamut 后1/H缩放，导出图按两次实际 rendition 亮度比生成。两次必须共享 grain seed。本地自定义 texture 路线也接显式 seed，缺省仍保留原 tile seed，避免无关旧图随机外观改变。

### 文件与显示边界

原版公开 2.3.0–2.3.2 发行说明明确称其当前文件仍仅 Apple gain-map，LR/ACR 读其 SDR 图。新源码 `HDRContainer/HDRUltraHDR` 同时存在 ISO/Apple/Adobe 声明代码与研究注释；这些定义不等于已发布文件可被所有读者读取，须核对调用和真实封装，不能直接引用注释声称兼容。JPEG/HEIF gain map 与 PNG/TIFF 无 gain map 的策略不同；显示 HDR 需要系统与屏幕链单独支持。

## 材料、许可与构建修正

13 个新增提交没有增加胶片或相纸数据目录，本轮不以新增空名称充当更多材料。现有30胶片/9纸材的前轮数据与来源继续保留。

构建节点发现原 `build-windows.sh` 在 stage 时用旧 Python vendor profiles 覆盖 native profiles，导致8纸材各自已追加的 EDR 标定丢失；canonical 源码标定没有丢。已修为覆盖后逐纸材合入该 canonical `edr_tone_map`，不改谱/密度数组，不借用别的相纸，重复构建仍保留。

## 本机关键验证

`scripts/verify_lab_232_native.py` 与 `output/lab-232-native-review/report.json` 记录 Windows Vulkan 上 96×64 彩色线性 ramp 的聚合节点：四个放大机控制、精确恢复、真实 Decode 后统计、HDR 表/拒绝条件、正片独立扫描与 seed、8纸材 stage 数据。它不是大 RAW 导出耗时，也不是 Mac/显示器兼容验收。最终 UI、编码器和确切发布包的节点由主线程追加。

`scripts/verify_lab_232_desktop.py` 的320×213真实夕阳照片节点另记录画布与DI：4空间CAM16及关闭压缩皆有限，关闭压缩对独立colour-science CAT02/CCTF参考最大误差≤5.61e-6，源像素未改写。首轮发现Adobe关闭压缩时，色域矩阵微负通道经过普通gamma出现7个NaN；已给独立转换ABI新增signed gamma mode6，旧光谱pipeline mode2语义不改。Adobe负值输入解码补查误差6.30e-8。同空间ProPhoto使用发布的近似矩阵，有约4.35e-5自身roundtrip残差（独立参考也同样存在），不是错误要求零差异的快捷旁路。

DI节点实际验证65³表轴序、raw Cineon→专用view→post→geometry顺序与普通图像DI消费者逐像素相同；相纸与DI输出均有真实外观差异。JPEG/TIFF配方共用viewed像素且各自带RGB ICC，TIFF16回读精确量化；专用DI配方保留Cineon原始代码，无RGB ICC，不混入显示调节，显式裁切仍精确。证据与已目视检查的4图对照位于`output/lab-232-desktop-review/`。聚合5.484秒仅小图功能节点，不作为RAW处理性能或显示器色准声明。
