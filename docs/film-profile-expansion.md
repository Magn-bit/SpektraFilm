# 胶片数据扩展：来源、转换与边界

核查日期：2026-11-07。完成了三个新增彩色胶片候选：**Fujifilm Velvia 50、Agfa Vista 100、Fujifilm Natura 1600**。三者来自各自独立的数值资料，没有复制现有胶片曲线再改名，也没有从输出 LUT 反推光谱。原始数值、转换程序、哈希与验证结果都已保留。

这些是**基于公开数字化资料与明确假设的光谱模型配置**，不是本项目新做的实测标定。菜单可以采用胶片通用名称；关于数据来源、插值、分层推导、颗粒与光晕标定程度的说明应保留在本文和资源许可中。

## 现有引擎与上游的实际范围

2026-11-07 查询 GitHub，Spektrafilm 当前 HEAD 仍为 [`3bb2c2d2801ff68b92019cf1dbcbb133d60832bc`](https://github.com/andreavolpato/spektrafilm/tree/3bb2c2d2801ff68b92019cf1dbcbb133d60832bc)，与本项目原固定版本相同。其 [profiles 目录](https://github.com/andreavolpato/spektrafilm/tree/3bb2c2d2801ff68b92019cf1dbcbb133d60832bc/src/spektrafilm/data/profiles)依然有 28 个 JSON：16 个拍摄负片配置（含 Portra 800 的两个增感变体）、4 个拍摄反转片、8 个印相材料。它们全部是 `channel_model=color`。

`andreavolpato/agx-emulsion` 的 GitHub API 请求重定向到 `andreavolpato/spektrafilm`，不是另一份新增片库。上游 GUI 的 [stock enum](https://github.com/andreavolpato/spektrafilm/blob/3bb2c2d2801ff68b92019cf1dbcbb133d60832bc/src/spektrafilm/model/stocks.py)也只列出上述 20 个拍摄配置。仅扩展原 GUI 的下拉列表不能得到新数据。

本地完整字段、形状、缺值数量和各配置 SHA-256 见 `output/film-profile-research/local-profile-inventory.json`。主要结构如下：

| 字段 | 本地形状 / 意义 | 新增材料必须提供或明确建模的内容 |
| --- | --- | --- |
| `wavelengths` | 81，380–780 nm，5 nm 间隔 | 原资料实际覆盖范围及带外假设 |
| `log_sensitivity` | 81×3，RGB 感光层对入射光的 log10 响应 | 谱形、相对速度与参考光源归一化 |
| `channel_density` | 81×3，CMY 染料单位密度谱 | 独立染料资料或有标记的分离模型 |
| `base_density` | 81，片基 / 最低谱密度 | 数据来源、密度标尺与底雾处理 |
| `midscale_neutral_density` | 81，中灰后的总谱密度 | 应由本胶片的模型计算 |
| `log_exposure` / `density_curves` | 256 / 256×3 | 曝光轴单位、H-D 曲线、插值和端点处理 |
| `density_curves_layers` | 256×3×3 | 三个数值子层，不等于已测量三层乳剂 |
| `density_curves_model` | 三通道各三个 normal-CDF 参数组 | 拟合方式与误差 |
| Hanatos 适配字段 | 四参数窗口，3×15 多项式 | 未标定时采用恒等变换，不能复制别的片种适配面 |

`profiles/io.py` 接受 `channel_model=bw`，但 `_validate_profile` 仍要求三个感光 / 染料 / 密度通道；曝光、DIR、颗粒、扫描路径也固定三通道。运行时没有真正采用 `is_bw` 的银盐支路。`ColorReferenceService` 中的 `black_white` 指扫描黑白端点校正，不代表黑白胶片支持。

用户原参考 [trouble123456/Film-Simulation](https://github.com/trouble123456/Film-Simulation/tree/dc715d94efe75ce88df2e8b411d0c2f1b4479083)的当前 HEAD 也没有变化。仓库顶层未公开独立胶片文件，源码在 25,136,857 字节的 `Film-Simulation-src.zip` 内；本轮下载在 18.5 MB 时中断，未完成 ZIP 内配置的新增审计，不能据此断言包内没有别的胶片。也未把 darktable / RawTherapee 的胶片 Hald / LUT 当作缺失的光谱响应资料。

## 六个实际候选

以下 Jan Lohse 链接统一固定在 [`bcbcfc6861f49cc706dc5d00ea048e4853060aab`](https://github.com/JanLohse/spectral_film_lut/tree/bcbcfc6861f49cc706dc5d00ea048e4853060aab)。其 [README](https://github.com/JanLohse/spectral_film_lut/blob/bcbcfc6861f49cc706dc5d00ea048e4853060aab/README.md)说明数值由 datasheet 数字化，也明确承认旧片资料精度、层间作用等限制。本轮核查了数值文件和处理代码；没有把尚未独立取得的原厂家 PDF 宣称为已验证。资料源名称虽包含 LUT，本次采用的是 `FilmData` 中的数值字典，不是其导出的 LUT。

| 候选 | 已确认存在的资料 | 波段 / 缺失与假设 | 当前结论 |
| --- | --- | --- | --- |
| [Fujifilm Velvia 50，2007](https://github.com/JanLohse/spectral_film_lut/blob/bcbcfc6861f49cc706dc5d00ea048e4853060aab/src/spectral_film_lut/reversal_film/fuji_velvia_50.py) | ISO 50、Status A 三条 H-D、三条 `log_sensitivity`、三条 `spectral_density`、MTF/RMS 数值 | R 579–691、G 486–592、B 387–494 nm；染料谱有不同终点；最低谱由 Status A 最低密度解出。缺真实子层、独立粒子 / DIR 标定 | 已转换、通过实际引擎；三者中分色谱证据最完整 |
| [Agfa Vista 100，2001](https://github.com/JanLohse/spectral_film_lut/blob/bcbcfc6861f49cc706dc5d00ea048e4853060aab/src/spectral_film_lut/negative_film/agfa_vista_100.py) | ISO 100、Status M 三条 H-D、RGB 感光谱、`d_ref_sd` 与 `d_min_sd` 总谱 | R 395–673、G 381–594、B 379–526 nm；**无独立三染料谱**，按总谱峰谷切分再平滑。它是资料中标记的 2001 Agfa Vista，不等于后来品牌下所有 Vista / Vista Plus 批次 | 已转换、数值求得指定相纸中性滤色 |
| [Fujifilm Natura 1600，2003](https://github.com/JanLohse/spectral_film_lut/blob/bcbcfc6861f49cc706dc5d00ea048e4853060aab/src/spectral_film_lut/negative_film/fuji_natura_1600.py) | ISO 1600、Status M 三条 H-D、RGB 感光谱、参考 / 最低总谱 | R 559–677、G 471–614、B 387–504 nm；染料同样由总谱推导，不能称三染料实测 | 已转换、数值求得指定相纸中性滤色 |
| [Kodak Tri-X 400](https://github.com/JanLohse/spectral_film_lut/blob/bcbcfc6861f49cc706dc5d00ea048e4853060aab/src/spectral_film_lut/bw_negative_film/kodak_trix_400.py) | 单感光谱 31 点、单 H-D 多组、MTF / RMS 数值；ISO 400 | 感光资料 300.1–668.3 nm，现引擎仅 380–780 nm；无实测银密度吸收谱、格式与工艺限定底雾。数值显影标签 6/7/9/11 缺匹配厂家文档的工艺确认 | 已隔离为单通道原始数据，待银盐支路 |
| [Kodak Double-X 5222](https://github.com/JanLohse/spectral_film_lut/blob/bcbcfc6861f49cc706dc5d00ea048e4853060aab/src/spectral_film_lut/bw_negative_film/kodak_5222.py) | 单感光谱 29 点、单 H-D 多组、RMS；来源设 ISO 250 | 400.5–669.8 nm；无银吸收实测谱；显影标签 4/5/6/9/12 的显影液、温度、搅动条件尚须核对 | 已隔离为单通道原始数据，待银盐支路 |
| [Ilford HP5 Plus 厂家技术资料](https://www.ilfordphoto.com/amfile/file/download/file/1903/product/695/) | 2018-11、6 页官方 PDF；ISO 400、材料 / 格式、显影时间、特性曲线、2850 K wedge spectrogram | 第 1 页是楔形光谱图，不是可直接当作定量 log 响应的 XY 数表；第 5 页曲线注明 ILFOTEC HC(1+31)、20°C、6½ min、间歇搅动 | 更适合按已注明的工艺条件单独数字化；厂家 PDF 未发现开放再分发许可，不能直接随发行包分发 |

HP5 PDF 本地研究副本 SHA-256：`f06f383d714bc9d13033f9e30a6aedf29d9b9f4d25c4a353d69e6526cb2f037f`。文本摘取在 `evidence/manufacturers/ilford_hp5_pdf.txt`。本轮尝试的旧 Kodak / Fuji 官方链接返回 404，失败记录保存在 `evidence/manufacturers/manifest.json`；这些链接不作为已取得的资料证据。

## 三款彩色配置的转换

转换入口：`scripts/import_additional_profiles.py`。使用现有 `.venv` 的 NumPy、SciPy、colour-science 和 vendor 引擎，不安装整套第三方 GUI。脚本只写 `output/film-profile-research/` 子目录；缺失的源文件从固定 commit 获取并校验 SHA-256。通过 AST 读取数值，**不执行下载的 Python 模块**。

```powershell
.venv/Scripts/python.exe -X utf8 scripts/import_additional_profiles.py --verify
```

生成结果在 `output/film-profile-research/candidates/`：每片 `.json`、`.provenance.json`、`.runtime.json`、数值诊断 `.npz`，以及总表 `summary.json`、MIT 全文和变更说明。JSON 中 metadata 记录了来源与假设。该目录的 `diagnostic-preview.png` 是色卡 / 灰阶预览图；显示用 PNG 将域外值截到显示范围，原始数值测试没有截断。

转换采用以下明确条件：

1. 输出统一为 380–780 nm、5 nm。感光度沿用来源的 log 域插值和线性带外延拓，延拓值先限于 `[-12,12]`；染料、片基采用来源的 Gaussian 尾部策略。源波段之外不是已测量数据，也没有近红外准确性主张。
2. Velvia 采用独立三条谱。Agfa / Natura 从 `d_ref_sd-d_min_sd` 得到参考谱，用蓝 / 绿 / 红峰间谷值划区，25 nm sigma 平滑权重，得到**推导染料基底**；各片的谷值写入 provenance。这一步不是新增三染料测量。
3. 谱基底按来源的 Status A / M 权重归一化。正片用 Status A 逆矩阵；负片采用来源 APD / CDD-to-CID 逆矩阵处理 H-D。这是来源代码的近似密度解混，不是完整层间化学测量。
4. 曝光轴用 `log10(12.5/ISO)` 重锚；D55 18.4% 灰使用引擎实际 Hanatos 重建的入射谱进行灵敏度归一化。Velvia 另在 D50 观察光下数值求解透射谱中灰，使线性 sRGB 中灰达到 `[0.184]*3`。三个曝光修正约为 **+0.465 / +0.232 / +0.202 stop**，属于模型的中性 / 速度校准，不是新增 ISO 测量。
5. 负片高曝光端使用来源的 logistic 肩部延拓；准备后曝光域之外钳到端点，不让多项式外插无限增长。密度解混后做非负 / 单调投影；这部分的最大修正单独记录，未隐含在拟合误差中。
6. 每通道拟合三个 normal-CDF 数值分量，排序后生成子层张量。层和与最终曲线完全一致；这三个分量仅让引擎拥有自洽的数值模型，不宣称物理乳剂层数或颗粒分布已被测出。
7. Hanatos 窗口为恒等、适配面为零，不复制现有片种的拟合面。`antihalation=weak`、`log_sensitivity_density_over_min=0.2` 是 schema 的保底描述；没有实测含义。D50 是选定的观察条件。发行整合应按 runtime sidecar 关闭新片未经标定的 DIR 耦合；普通颗粒与光晕参数可作为通用模型开放，但不可描述成这些片种的实测参数。

### 数值校准与验收记录

| 材料 | 3-CDF 各通道最大 RMSE / 最大绝对误差 | 单调投影最大修正 | 底谱非负钳位最大修正 |
| --- | --- | --- | --- |
| Velvia 50 | 0.002654 / 0.010002 D | 0.011476 D | 0 |
| Agfa Vista 100 | 0.003489 / 0.010838 D | 0.006652 D | 0 |
| Natura 1600 | 0.002627 / 0.008718 D | 0.000037 D | 0.007348 D |

误差针对**经上述插值、解混与投影之后的目标曲线采样点**。它不是原厂图的读取误差、拍摄测量误差或成片颜色 ΔE。

负片的中性滤色不是沿用默认 55Y / 65M；在 `TH-KG3` 放大光源、`fujifilm_crystal_archive_typeii`、当前直接光谱印相 / 扫描路径上，以 D55 场景的线性 18.4% 灰，数值求解 C/M/Y（至少一色为零）：

| 胶片 | C | M | Y | 灰阶输出，线性 sRGB |
| --- | ---: | ---: | ---: | --- |
| Agfa Vista 100 | 0 | 42.6722501 | 23.0968810 | 约 `[0.1816261]*3` |
| Natura 1600 | 0 | 46.4963012 | 50.7296610 | 约 `[0.1817883]*3` |

求解关闭了 DIR、颗粒、空间作用和扫描黑白端点修正。中灰的 log RGB 比值残差约 `5.1e-11` / `4.3e-11`。这是模型中性校准，**仅针对该相纸与光源组合**；更换相纸 / 光源、开启 DIR 或改变扫描条件时不能继续宣称同等中性。完整条件和值在 runtime / provenance sidecar。正片直接扫描，不套负片相纸路径。

已经运行的检查：

- 调用 vendor 的 `profile_from_dict` 与 `_validate_profile`；另外检查全部光谱 / 曲线数组有限、曝光轴严格递增、曲线单调、子层和精确等于曲线。
- 实际 `Simulator` 的 Hanatos 曝光 → 显影 → 光谱印相（负片）→ 扫描；10 级灰阶覆盖场景线性 0–2，24 个 ColorChecker 2005 色块。全部输出有限，灰阶单调。
- 诊断时关闭输出 gamut 压缩，因此有少量 sRGB 域外负通道。这不是 NaN，也不表示数据加载失败；发行路径保持已有的输出 gamut 处理。不能以诊断 PNG 截断后的外观代替数值结果。
- 64×64 阶梯输入开启子层颗粒，在通用 host 粒子参数下三者均输出有限。记录见 `sublayer-grain-smoke.json`，它验证算法兼容性，不验证各片的颗粒尺寸或 RMS 准确性。
- 编码与线性输入对等：同一场景线性 `sRGB=0.184` 对应编码 `sRGB≈0.4661065746`。前者 `input_cctf_decoding=False`，后者 `True`，三款输出最大差均 `<1e-14`；完整色卡的对等检查也内置于 `--verify`。**编码值 0.184 不能当作线性 18.4% 灰。**

### 产品入口的实际完整尺寸导出

2026-11-07 用 `output/mask-reference/source-windsock.jpg` 验证了已经安装的三款数据。入口是产品的 `film_settings` 和 `export_photo`，不是单独调用研究脚本的 Simulator；没有改动生产参数或测试。使用标准胶片设置：曝光 0、颗粒 18 / classic / size 1、光晕 12、强度 100%，原有后处理保持产品 canonical 状态。产品的光谱印相 / 扫描采用现有 LUT 加速，实际文件输出保持源尺寸，未采用 preview / 缩小导出。

可重跑脚本是 `scripts/verify_additional_films.py`；默认输出目录必须尚未存在，避免覆盖已有导出。结果及完整设置记录在 `output/film-profile-research/exports-final/report.json`，`comparison.png` 只是 760×1252 的缩略对照图。

| 实际导出 | 尺寸 | 色彩 / 位深 |
| --- | --- | --- |
| Velvia 50 JPG、Vista 100 JPG、Natura 1600 JPG | 各 1280×1920，与源图一致 | RGB，产品 sRGB ICC，quality 100 |
| Velvia 50 TIFF | 1280×1920，与源图一致 | RGB，8 bits/channel，LZW，产品 sRGB ICC |

四个文件均重新打开核对格式、尺寸、ICC 与可解码性。TIFF 是当前产品实际导出能力的 8 位 TIFF，不能将其描述为 16 位输出。三个 JPG 的 SHA-256 均不同，解码后两两平均绝对 RGB 差分别约 **5.153、6.429、4.890 / 255**；这些数值证明输出不同，不是胶片真实性或审美评价。缩略对比图已经目视检查，可辨认同一风向袋、天空和云层，没有构图改变或明显破损。

源图导出前后的 SHA-256 均为 `77dc014bf2a47f7ca96ee39fabe2e37e19fda615ff2b1df4abaf218a75398c57`。本次结果仅覆盖当前 Windows 代码、这一张样片及上述设置，不扩展为其他场景、Android 设备或厂家实拍的等价验证。

## 黑白的下一阶段实现边界

Tri-X / 5222 的原数值已另存到 `output/film-profile-research/bw-source-only/`，保留单通道和多组显影曲线，不伪装成彩色配置。它们不是现引擎可直接加载的 profile。数值显影标签暂时保留上游原始整数，不在缺少工艺文档时擅自给出显影液、温度或“几分钟标准显影”的准确含义。

可实施的支路应使用 `H(x,y)=Σλ L(x,y,λ)·S(λ)` 单一曝光，经过一条 H-D 曲线得到银密度，再通过 `D(λ)=D_base(λ)+a_silver(λ)·D_silver` 形成透射谱。若首版暂设 `a_silver(λ)=1`，应明确这是中性银吸收近似，和 Jan Lohse `FilmSpectral` 的黑白分支相同，**不是实测银谱**。之后可走黑白相纸单通道印相或明确的负片反相扫描；不能未经定义把银密度塞进三条 CMY 染料通道再称为完整光谱标定。

黑白支路还需给出：格式和工艺限定的片基 / 底雾、密度标尺、参考光源下的速度归一化、实测或有声明的颗粒参数，以及真实的单通道 / 相关颗粒（避免独立 RGB 颗粒造成彩色噪声）。Tri-X 的 300–380 nm 与两片 670–780 nm 不完整区间应按引擎支持范围裁切 / 低响应外推并记录；不能用无资料的红外响应模拟特殊红外片。

## 分发与来源

- Jan Lohse 的代码与所附数值文件在该固定版本的 [MIT LICENSE](https://github.com/JanLohse/spectral_film_lut/blob/bcbcfc6861f49cc706dc5d00ea048e4853060aab/LICENSE) 下公开，版权为 `Copyright (c) 2026 Jan Lohse`。保留完整 MIT 许可及作者署名，标明本项目转换 / 拟合 / 推导。候选目录提供 `LICENSE-data-MIT.txt`，metadata / provenance 也保留出处。
- 原厂家 PDF 的公开下载与开放许可是两件事。厂家商标、图像和文档原件不因项目采用 MIT 而自动归本项目；本次未把厂家 PDF 加入发行资源。所采用的可分发数值来源是明确带 MIT 的代码资料，而不是“网上能找到 PDF”这一理由。
- 现有 Spektrafilm 源码仍遵循 GPLv3，原 28 个 profile、相纸与相关资源保留 Andrea Volpato 的 CC BY-SA 4.0 署名 / 许可。新增数据没有替换这些原许可。中性滤色由现有相纸数据计算，发行时继续随包保留相纸许可和作者署名。
- 所有抓取证据位于 `output/film-profile-research/evidence/`：上游 HEAD / tree API 原件、MIT 文件、固定版数值源码、下载 URL 与 SHA-256。每片 provenance 还包含源文件哈希、转换后 profile 哈希、数据支持区间、假设与验证结果，可重跑对照。

这轮验证覆盖数据兼容性和数值稳定性。尚未完成的质量步骤是：对照原厂家曲线复核数字化误差、与受控光源下的实拍 / 扫描色卡比较、标定各片的颗粒 / 光晕 / DIR 参数，以及给缺少独立染料谱的两款负片补充更直接的测量来源。
