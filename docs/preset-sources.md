# 预设来源、授权与兼容性核查

核查日期：2026-11-06。当前范围按用户最新反馈收敛为**人像、风光日常用途**；已有完整光谱模型，不再用胶片型号预设重复填充，也不将强绿、夜调、漂白等实验 CLUT 作为默认合集。保留尼康 Links 原版核查及其他来源研究作为背景。只访问匿名公开的一手网页、作者仓库与公开 API；未登录尼康账号、未获取付费内容、未上传用户照片。

0.3.1 更新：已接入八色混合器及 XMP 24 项 HSL 字段，默认原创风格增加针对肤色/黄绿/蓝青的独立色带设置。6 款真实作者 XMP 已用新解析器验证 HSL 起效、展示名不受嵌套 Look 污染；仍保留“部分转换”与 Adobe Color 依赖警告。HSL 算法由本项目实现，Adobe 处理版本、外部 DCP/Look、清晰度/去朦胧等不能因字段被解析而宣称原版还原；这六款不作为原版内置。

## 结论

- 本版交付 **18 款 SpektraFilm 原创实用参数风格：8 人像 + 10 风光，列表首项为“无预设”**。全部为本项目直接实现的基础色彩参数，用户无需将常规人像或风光与电影胶片乳剂重复命名；不调用外部 Hald、不宣称对应作者或平台热门排名。
- Links 的配方已由尼康一手资料准确核实：**Nature by Links**，优化校准名 **Nature_Links**，使用 **FLEXIBLE_COLOR**。它不是我们现有的某条曲线，也没有被核实为 `.cube` 或 XMP。[N1][N2]
- 人像新增：窗边自然光、清透人像、克制人像、逆光人像；风光新增：建筑中性、山野层次、阴天柔光、春日自然。新增项采用保守的曝光外色彩参数、HSL与曲线，分别聚焦光线、肤色、植被、天空与建筑材质。
- 当前未取得 Links 配方文件的第三方再分发授权，也未取得足够的完整渲染数据，不能内置一个自创风格并标成“Links 原版”。本轮可提供官方入口与准确说明。[N2][N4]
- 找到用途明确且 MIT 可分发的 **6 款 peva3 作者 XMP 候选**：Natural Skin、Bright & Airy Wedding、Golden Hour Selfie、Epic Landscape、Grass Natural Exterior、Byron Bay Surf。库有 **138 stars**，没有单款热门排名证据。文件仅保留在 `output/preset-research/practical-xmp-source/` 用于研究，不打包发布；**当前部分 XMP 导入不能忠实保留这些预设的核心 HSL / Adobe 渲染效果，不作为完整原版内置**。[E1–E3]
- 真正写明人像/风光用途的 HALO + TERRA 与 Lunchuan 原创库明确禁止二次分发，不能因文件在公开 GitHub 上就打包进本软件。[E4][E5]
- t3mujinpack 胶片 Hald 与 CreativePack / PictureFX 的许可和格式核查仍有研究价值，但不满足本轮默认风格定位。不能把实验风格换一个日常人像名称来绕过用途不符。

## 1. Nikon / Links：已证实的原版身份

| 项目 | 已核实内容 |
| --- | --- |
| 作者 | 官方创作者列表为 **Links**；职务为“摄影师/自媒体创作者”。本人一手账号标题为 Links TV。 |
| 官方配方名 | **Nature by Links** |
| Picture Control 名 | **Nature_Links** |
| 配方 ID | `01JAYCCCHHNG6AWXA2MF43C9ZF` |
| 创作者 ID | `01M3NKKKY7R7VB22G3H9DESZER` |
| 官方描述 | 适合自然光下的日常生活、绿草、蓝天、木头等；控制饱和度和对比度，获得柔和、自然的感觉。这是创作者说明，不是本项目实测结论。 |
| 类型 | 官方配方 JSON 中 `pictureControl.settingName = FLEXIBLE_COLOR`。 |
| 公开查看 | 官方创作者与该配方的文字信息可匿名 GET。官方帮助描述的使用路径是保存到云创、注册照相机并无线传送；没有发现该配方的匿名原始文件下载入口，未登录核验账号操作。 |
| 文件格式 | 云创官方帮助明确：创建色彩方案可上传优化校准 **`.np3`**，不支持 **`.ncp` / `.np2`**；NX Studio 本身支持 NCP/NP2/NP3 家族。这些证明云创与 NP3 的关系，但本次没有取得 Nature by Links 的原始文件，不把它宣称为已下载、已解析的 NP3。 |
| `.cube` / XMP | 未找到尼康或 Links 发布的该配方原版 `.cube` / XMP，不能声称已支持。 |
| 热度 | 公开详情响应返回 `likeCount: 0`，无法据此证实“人气非常高”；匿名 API 字段也不构成真实全网热度评估。 |

来源：[N1][N2][N3][N5][N7][N8]。正确的中文官网域名为 `imagingcloud.nikon.com.cn`；直达配方页面需使用带尾斜线的路由：[Nature by Links 官方页](https://imagingcloud.nikon.com.cn/recipe/release/detail/?id=01JAYCCCHHNG6AWXA2MF43C9ZF)。不把全球站的 `/sorry` 页面当成正确详情页。

### 为何公开文字不足以真实套用

该公开响应给出了 sharpening、clarity、saturation 等摘要，但 contrast、highlight、shadow、whiteLevel、blackLevel 的值是字符串 `gamma`，没有完整曲线、八色混合或所有色彩分级数据。NX Studio 官方文档也确认 Flexible Color 包括自定义曲线、Color Blender 和 Color Grading。[N2][N6]

因此，照着 `saturation: +18` 和若干锐化值重建，无法证明获得 Nature by Links 原版结果；跨引擎使用相同数值也不保证像素一致。现有完整光谱显影器、Adobe Camera Raw、Nikon Flexible Color 是不同处理系统。

### 授权边界

尼康云创中国使用条款第六条第 5 项 l 禁止将尼康或第三方提供的相关信息、内容或软件用于尼康云创之外的其他目的；第八条第 2 项保留内容及程序相关知识产权，未许可给会员。本次未核得允许第三方软件重新打包、转换并分发 Links 配方的单独授权。[N4]

这份核查不把条款附件的“相机更新程序”许可误套到摄影配方；也不把“免费使用”“公开可查看”解释成允许再分发。建议只保留官方入口，待用户合法取得文件并确认用途许可后，再评估本地导入及真实转换。不能把普通网络第三方声称的“Links 同款”当成作者原版。

## 2. 实用人像 / 风光作者 XMP 候选

来源：`peva3/EmulsionPresets`。虽然该库主体包括胶片模拟，但以下六款来自其 Mobile / Genre / Geographic 类别，本次没有选胶片型号。作者 README 明确每款 `.xmp` 按 MIT 发布；固定 commit 为 `0cdb71c60603867a046bc92c63617feec7894dd1`，核查时仓库 138 stars。用途描述是作者 catalog 的一手声明，不是本项目已经用人像或风光样片验证的保证。[E1–E3]

| 作者实际预设名 | 作者说明的用途 | 本文件中的核心参数与当前兼容问题 |
| --- | --- | --- |
| Natural Skin | 自然肤色、克制处理。 | 橙/红色提亮与降饱和是关键；当前导入器未转换这些 HSL 字段。 |
| Bright & Airy Wedding | 柔亮婚礼、干净白色和浅色调。 | 曝光 +0.50、清晰度 -10、纹理 -5 及分色相调节；当前只保留部分色调，不能声称完整柔光。 |
| Golden Hour Selfie | 金色时段暖人像。 | 橙/红色明度、曝光、去雾和柔化参数；当前无法完整保留。 |
| Epic Landscape | 金色时段风光、深色天空、前景细节。 | 清晰度 +15、去雾 +10 及蓝/绿 HSL；未转换细节和 HSL 就不是原作者效果。 |
| Grass Natural Exterior | 自然草地绿色、平衡天空。 | 绿/黄色相与饱和度是核心；当前导入器未转换。 |
| Byron Bay Surf | 海岸金光、海水青蓝、浅色沙滩。 | 水色/橙色 HSL、曝光 +0.60、去雾 -8；当前不能完整还原。 |

原 XMP、MIT 许可、作者 README 及逐款固定 URL、SHA256、参数与部分转换警告已保存：`output/preset-research/practical-xmp-source/manifest.json`。本轮没有为了显示“已接入”而去掉这些警告，也没有把类似的本项目参数套上作者原名。

六个文件均指定 Adobe **ProcessVersion 15.4**，包含 **Adobe Color Look**。这些是对 Adobe 引擎的引用，不会随 XMP 获得 Adobe 渲染器。当前 `import_style_json` 可读取基础对比、高低光、饱和度/鲜艳度、RGB 点曲线及部分色轮，但不转换分色相 HSL、纹理、清晰度、去雾、完整白黑场/曝光策略、Adobe Look/profile 等；各像素算法也不同。故“能解析 XML / 部分映射成功”不等于“原版风格完整支持”。

在本轮限定时间内，未找到同时具有**高人气可核证、日常人像/风光用途明确、允许再分发、可由现引擎忠实读取**的六款预设合集。不能把库级 stars 充作单款热门证据。可用本项目明确署名的原创人像/风光风格服务真实任务，并保留外部 XMP 的部分转换入口，后续再按真实文件扩展兼容。

排除记录：

- `thead4md/halo-terra-presets`：0 stars；人像 HALO 与风光 TERRA 用途清楚，但 LICENSE 明确“Redistribution or resale ... is not permitted without written permission”。不下载或打包预设文件。[E4]
- `lunchuan-cmd/lunchuan-presets`：1 star；Portrait Skin、会议及活动用途明确，但 README 明确“禁止转售、二次分发、打包进其他预设合集出售”。个人/商业照片可用不代表可内置软件。不下载或打包预设文件。[E5]
- `Questtion/Lightroom-Presets`：2 stars，MIT；作者自述业余，内容主要为活动、运动、蒙版及编号预设，没有足够一手信息将其列为成熟日常人像/风光热门合集。不硬凑六款。[E6]
- `9bic/lrpresets`：3 stars，MIT；仅 9bichrome / mecabify 两款，无足够一手用途描述或热度证据，不将其泛称人像/风光常用预设。[E7]

## 3. 历史候选：t3mujinpack（胶片型号，不作本轮默认集）

作者：João Almeida。仓库现地址为 `t3mujinpack/t3mujinpack`，旧 `t3mujin/t3mujinpack` 已跳转。作者 README 明确说明它是用于 darktable 的胶片模拟集合，主要依靠 Lab Tone Curves，黑白风格也使用 Channel Mixer。[T1]

| 项目 | 核查结果 |
| --- | --- |
| 原始格式 | `.dtstyle`，另有作者仓库提供的 `haldcluts/*.png`。 |
| 当前 master 内容 | 53 个 `.dtstyle`、51 个 HaldCLUT PNG，数量不同；不能声称每个 style 都有对应 Hald。 |
| 可下载 | GitHub 作者仓库及 Releases 匿名公开下载，无账号或付费要求。 |
| 授权 | 根目录 `LICENSE.txt` 为 MIT，Copyright © 2017 João Almeida；分发时附版权和许可声明。 |
| 热度证据 | 1,082 stars；v0.6.0 `flat.zip` 10,174 次、`one-level.zip` 9,933 次下载，最终 API 快照时间为 2026-11-06 18:25:39（UTC+8）。 |
| 固定版本 | 本轮仓库 commit：`0b421f3e25209ed78253d1724a29cc6255c5e7fe`。 |
| 直接验证 | 已下载下列 8 张作者 Hald，全部 1728×1728、RGB、内嵌 sRGB ICC，共 9,283,490 bytes；保留原文件与 MIT 许可。未把照片上传到任何服务。 |

该样本 SHA256：`73dbff69fd948b0a268e660c4582f78d0b7da67f0c672d49f67acfc92cc38809`。

此前研究过以下 **作者提供的 Hald 文件**；用户已明确不需要重复胶片型号，本表只保留来源核查记录：

| 作者文件名中的名称 | 精选理由与核验边界 |
| --- | --- |
| Fuji Velvia 50 | 作者 README 明确举例其鲜明色彩；适合与柔和路线区分。[T1] |
| Kodak Kodakchrome 64 | 源文件确实拼作 `Kodakchrome`；保留 source name，展示名修正常见拼写时注明。作者 README 用 Kodachrome 作为较克制色彩的例子。[T1][T3] |
| Fuji Fortia SP 50 | 与常见 Portra 不同的反转片候选；README 的 v0.6.0 新增项目，有实际 style 与 Hald 文件。具体效果仍需实片评估。[T1][T3] |
| Ilford Delta 3200 | 补充黑白方向；Hald 只能携带逐像素色彩变换，不含胶片颗粒的空间结构。[T1][T3] |

MIT 授权允许保留来源后分发这些文件；本轮已对这 8 个 Hald 作离线适配，保留原始样本与来源。不能将 Hald 结果描述成对 darktable 所有模块或真实胶片物理过程的完整复现。作者仓库有 CineStill 800T `.dtstyle`，但当前 `haldcluts` 未发现其对应 PNG，不能为了补名字自行生成并冒称作者 Hald。[T3]

### 本轮实际下载的 8 款

源文件保留在 `output/preset-research/hald-source/`，并包含 `LICENSE.txt` 与 `manifest.json`。清单逐个记录作者实际文件名、固定 commit、`source_path`、`source_url`、PNG SHA256、字节数、sRGB ICC 信息及 MIT 许可。目录中另有可复现下载脚本 `output/preset-research/download_hald_sources.py`。

1. Fuji Velvia 50 — Color Slide。
2. Kodak Kodakchrome 64 — Color Slide；按源文件保留拼写。
3. Fuji Fortia SP 50 — Color Slide。
4. Ilford Delta 3200 — Black and White。
5. Kodak Gold 200 — Color Negative。
6. Kodak Ektar 100 — Color Negative。
7. Fuji Pro 400H — Color Negative。
8. Kodak Tri-X 400 — Black and White。

这是涵盖反转片、负片及黑白方向的**编辑精选**，没有捏造单款热度排行榜或作者未提供的调色。PNG 为 Hald level 12，即每色轴 144 个采样点；后续适配应保留其采样密度，而非缩到既有低维 LUT 后仍声称原样加载。

## 4. 历史候选：RawTherapee Film Simulation / CreativePack

该集合的目录 README 标注版本 **2015-09-20**、**CC BY-SA 4.0**，作者/贡献者为 Pat David、Pavlov Dmitry、Michael Ezra；注明除文件名另有说明外，为 sRGB、8-bit/channel、PNG HaldCLUT。Pat David 本人的文章确认了 RawTherapee 中使用这些胶片模拟及官方共享下载入口。[R1][R2]

本次读取的可公开访问镜像 `cedeber/hald-clut` 含此集合 **293 张 PNG**，其中包括推拉和衰退变体，不等于 293 种独立胶片。镜像仓库当日 **332 stars**，该数字只是镜像关注度，不能用作每个 LUT 的人气。[R3][R4]

`CreativePack-1` 的 BleachBypass、Moonlight、TensionGreen 等不对应具体胶片型号，但用户已进一步明确需要日常人像与风光，它们也不应替换默认集。初筛实片发现 BleachBypass1 在高亮云层会大片截白，进一步说明“名称有特点”不能代替实际用途筛选。不能改名成自然肤色、通透风光后声称适配成功。[R3]

分发或改制时提供作者署名、来源链接、CC BY-SA 4.0 链接，并标记变更；衍生 LUT 按相同许可提供。不能只保留根目录 GPL 文件而漏掉素材级 CC BY-SA。不要将此集合中的商标名称解释成对应胶片厂商官方认可。[R1]

访问限制：Pat David 文章指向的 RawTherapee `shared/HaldCLUT.zip` 在本次请求返回 HTTP 466，旧 RawPedia Film Simulation URL 返回 404。因此，本轮实际确认可下载的是 GitHub 镜像具体文件，**没有宣称官方整包下载已测试成功**。镜像固定 commit：`3b3180f82d4dcea1e6e8c5648473539a910d7f49`。[R2–R4]

## 5. 历史候选：PictureFX

Marc Roovers 的 PictureFX 是另一组作品。上述镜像 `HaldCLUT/PictureFX/README.txt` 单独明确 **CC BY-SA 4.0**，注明由 Marc Roovers 开发；当前目录有 **19 个 PNG**。作者本人站点说明许多作品有 `.cube`，同时可有不同分辨率 PNG 和其他 LUT 格式；该说明不能替代逐个文件核验，也不能默认不同年份作品沿用同一许可。[P1][P2][R3]

旧集合中的 `GoldFX-Spring-Breeze` / `GoldFX-Perfect-Sunset-05min` 本轮检查时既没有 ICC，也没有 PNG sRGB/gamma 元数据；其独立 README 未像 RawTherapee 集合那样明确工作空间，故没有直接假定 sRGB 并接入。也没有它们单独下载量或日常人像适用证据。不能把 FreshLUTs 上“免费下载”自动等同于可随应用分发；新作品必须逐项核实作者与许可。[P1][P2]

## 6. 与当前项目的真实兼容性

下表区分格式能力与产品默认内容。共享 Hald 读取曾完成，但胶片型号/实验风格已被用户否定为本轮默认选项；当前默认目录已收敛为上述 10 款原创实用风格。历史 t3mujinpack、CreativePack 和 PictureFX 文件仅作本机研究留档，本版不交付这些风格。不能把旧目录计数当最终交付内容，也不把源码运行验证等同于已发布 EXE/APK 或 Android 真机验证。

| 格式 | 当前源码能力 | 后续真实接入要求 |
| --- | --- | --- |
| 项目内部 float32 `.bin` LUT | `desktop/imaging.py::load_lut` 从内部 manifest 按 `<f4`、`n×n×n×3` 读入。 | 不能把外部文件改扩展名后套入。 |
| `.sfpreset` / 预设 JSON | `shared/style_presets.py` 已有参数文档读取与归一化。 | 仅本项目约定参数，不是其他引擎兼容声明。 |
| Adobe XMP | 新增 `import_style_json` 只做基础色调、部分 RGB 点曲线、色轮字段转换，并返回未转换警告。 | 不包含 Adobe profile、处理版本、校准或全部 HSL 等价；不声称 Adobe 视觉一致。 |
| 经离线适配的作者 Hald | **读取核心已实现**：RGB8 保存原 PNG 的完整样本，三线性插值、分块处理、有界缓存。是否保留某个具体风格由最新产品用途决定。 | 原阶、颜色空间、hash、许可需逐项核验；不能因技术可读而把不实用的实验/胶片型号设为默认。 |
| 用户任意 HaldCLUT PNG | **尚无通用外部 Hald 导入器**。 | 内置离线适配不意味着能任意导入；其他阶数、颜色空间、编码和来源仍需独立解析与验证。 |
| `.cube` | 当前没有通用 `.cube` 导入器。 | 需解析大小、DOMAIN、数据顺序与插值。 |
| darktable `.dtstyle` | 当前不直接支持。 | 不将 Lab 曲线数值直接当 RGB 曲线；优先使用作者已经公开的 Hald 版本。 |
| Nikon NCP / NP2 / NP3 / Cloud Picture Control | 当前不支持。 | 完整文件解析、许可与 Nikon 对应渲染机制均未解决，不能仅根据公开参数摘要标记为已接入。 |

推荐产品组织：把“胶片/相纸科学模型”和“创作者/色彩风格”分为不同概念；预设保留作者、版本、source URL、license、hash、转换方式。默认只陈列少量差异明确的风格，原版、作者导出的 Hald、部分转换与本项目原创必须准确标记。外部格式不支持时明确说明，不能静默套用近似风格。

### 实片证据边界

当前 10 款原创风格已通过 `scripts/verify_practical_styles.py` 调用实际 catalog、`apply_style` 与 `render()` 验证，输出位于 `output/practical-style-sample/`。其中 `landscape-comparison.png` 展示原片与 6 款风光，`portrait-comparison.png` 展示原片与 4 款人像；图片文字、布局和实际可见变化均已人工看图核对。对比图为完整构图缩略图，没有生成照片或重绘原片。

所有风光 TIFF 保留 1280×1920，人像 TIFF 保留 512×512；本次均为 **RGB 8-bit、内嵌 sRGB**，回读与渲染结果逐像素一致。报告记录每款设置、源/结果 SHA256、尺寸、差异及单次耗时；中性基线逐像素等于解码原片，源文件与 catalog hash 未变。报告不把 RGB 差异作为审美评分，也不把此次 RGB8 证据泛化为 16-bit 输出验证。

风光源为现有用户风向袋照片，仅有蓝天、云和红白主体，不存在森林、海水、城市或夜景，故只能确认六款参数真实起效与输出完整，不能据此验收所有对应场景。人像源为本机 `skimage.data.astronaut()` 的 NASA Eileen Collins 公开领域照片（其文档标注无已知版权限制，出处 https://flic.kr/p/r9qvLn），仅用于本地研发验证，未放入产品 assets 或发布包。单人样片**不代表专业肤色多样性验收**，也不包含脸部识别、皮肤局部蒙版或磨皮；柔光表示全局明暗过渡调整。

单次渲染计时来自本机内存中已解码的照片，不含解码、输入/显示、TIFF 写盘或 Android 运行，不能视为统计 benchmark、实时预览延迟或 60fps 证据。此前胶片/实验 Hald 的样片也仅作研发留档，不作为本版默认风格交付证明。

## 一手来源

- [N1] [Nikon 中国公开创作者 API](https://api.user.ir.imagingcloud.nikon.com.cn/info/creator)，匿名 GET，`Accept-Language: zh-cn`；创作者字段及配方 path。
- [N2] [Nature by Links 官方公开详情 API](https://api.user.ir.imagingcloud.nikon.com.cn/publicrecipe/0000000000000001/01JAYCCCHHNG6AWXA2MF43C9ZF?sortType=0&isPagenation=false)，匿名 GET；原版名称、Picture Control 与摘要。取证 JSON 位于 `output/preset-research/nikon-links-recipe.json`；临时 CDN 签名参数已移除，不下载或分发样片。
- [N3] [NX Studio：Importing/Exporting Custom Picture Control Files](https://nikonimglib.com/nxstdo/onlinehelp/en/copy_custom_picture_controls_50.html)，NCP/NP2/NP3 格式与兼容性。
- [N4] [尼康云创中国使用条款](https://accounts.cld.nikon.com.cn/termsofuse?serviceId=NIC&country_code=CN)，页面修订日期 2024-07-25；第六、八条。
- [N5] [Links 本人 YouTube 账号](https://www.youtube.com/@linksphotograph/about)，页面标题 Links TV；不是配方文件下载或授权来源。
- [N6] [NX Studio：The Picture Control (Flexible Color) Tool](https://nikonimglib.com/nxstdo/onlinehelp/en/the_picture_controls_flexible_color_23.html)。
- [N7] [尼康云创官方帮助：色彩方案](https://imagingcloud.nikon.com.cn/html/faq/overview_recipe/zh-cn-prc.html)，明确 `.np3` 支持及 `.ncp` / `.np2` 不支持；[通过您的图像创建并保存色彩方案](https://imagingcloud.nikon.com.cn/html/faq/saved_recipe/zh-cn-prc.html)。
- [N8] [官方帮助：传送优化校准至照相机](https://imagingcloud.nikon.com.cn/html/faq/sync_picture_control/zh-cn-prc.html)，[在照相机上使用](https://imagingcloud.nikon.com.cn/html/faq/use_picture_control/zh-cn-prc.html)。
- [T1] [t3mujinpack 作者 README](https://github.com/t3mujinpack/t3mujinpack/blob/0b421f3e25209ed78253d1724a29cc6255c5e7fe/README.md)。
- [T2] [t3mujinpack MIT 许可](https://github.com/t3mujinpack/t3mujinpack/blob/0b421f3e25209ed78253d1724a29cc6255c5e7fe/LICENSE.txt)。
- [T3] [t3mujinpack 作者 HaldCLUT 目录](https://github.com/t3mujinpack/t3mujinpack/tree/0b421f3e25209ed78253d1724a29cc6255c5e7fe/haldcluts)，[固定版本树 API](https://api.github.com/repos/t3mujinpack/t3mujinpack/git/trees/0b421f3e25209ed78253d1724a29cc6255c5e7fe?recursive=1)。
- [T4] [作者 v0.6.0 Releases](https://github.com/t3mujinpack/t3mujinpack/releases/tag/v0.6.0)，[下载计数 API](https://api.github.com/repos/t3mujinpack/t3mujinpack/releases/latest)，[stars API](https://api.github.com/repos/t3mujinpack/t3mujinpack)。
- [R1] [RawTherapee Film Simulation 素材 README 及 CC BY-SA](https://github.com/cedeber/hald-clut/blob/3b3180f82d4dcea1e6e8c5648473539a910d7f49/HaldCLUT/Film%20Simulation/README.txt)。
- [R2] [Pat David 本人：Film Emulation in RawTherapee](https://patdavid.net/2015/03/film-emulation-in-rawtherapee/)。
- [R3] [HaldCLUT 镜像的固定版本树 API](https://api.github.com/repos/cedeber/hald-clut/git/trees/3b3180f82d4dcea1e6e8c5648473539a910d7f49?recursive=1)。
- [R4] [HaldCLUT 镜像仓库 API](https://api.github.com/repos/cedeber/hald-clut)。
- [P1] [PictureFX 素材目录的独立许可与作者说明](https://github.com/cedeber/hald-clut/blob/3b3180f82d4dcea1e6e8c5648473539a910d7f49/HaldCLUT/PictureFX/README.txt)。
- [P2] [Marc Roovers 本人 PictureFX 页面](https://marcrphoto.wordpress.com/picturefx/)。
- [E1] [peva3 作者 README](https://github.com/peva3/EmulsionPresets/blob/0cdb71c60603867a046bc92c63617feec7894dd1/README.md)、[MIT LICENSE](https://github.com/peva3/EmulsionPresets/blob/0cdb71c60603867a046bc92c63617feec7894dd1/LICENSE)。
- [E2] [作者逐款 catalog](https://github.com/peva3/EmulsionPresets/blob/0cdb71c60603867a046bc92c63617feec7894dd1/presets.json)，六款原始固定 URL 见本地 practical-xmp-source/manifest.json。
- [E3] [peva3 仓库统计 API](https://api.github.com/repos/peva3/EmulsionPresets)，2026-11-06 138 stars，库级指标。
- [E4] [HALO + TERRA 作者许可](https://github.com/thead4md/halo-terra-presets/blob/main/LICENSE)、[README](https://github.com/thead4md/halo-terra-presets)。
- [E5] [Lunchuan 作者 README 授权说明](https://github.com/lunchuan-cmd/lunchuan-presets)。
- [E6] [Questtion 作者 README](https://github.com/Questtion/Lightroom-Presets)、[MIT 许可](https://github.com/Questtion/Lightroom-Presets/blob/main/LICENSE)。
- [E7] [9bic 作者 README](https://github.com/9bic/lrpresets)、[MIT 许可](https://github.com/9bic/lrpresets/blob/master/LICENSE)。

开放许可正文：[MIT](https://opensource.org/license/mit)、[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)。Stars、发布下载计数与在线内容会变化，以上指标只代表本次核查时点。
