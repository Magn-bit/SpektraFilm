# 原版胶片能力补充建议

核查日期：2026-11-07。能力清单依据本项目实际携带的 `vendor/spektrafilm` 源码、参数定义和 profile 数据，以及本轮接入前的 Windows / Android 代码快照。GUI 另核对上游固定提交 `3bb2c2d2801ff68b92019cf1dbcbb133d60832bc`；下载证据保存在 `output/upstream-gui-review/`。按 research Skill 的方式追溯至一手源码；这份研究没有修改生产功能，后续开发状态需以实现与验证记录为准。

建议顺序是：**相纸/电影印片配对 → 模拟胶片画幅 → 少量暗房印放参数**。三项都扩展胶片显影本身，放在现有胶片工作流中，不重新引入 HSL、蒙版、校准或图库。

| 优先级 | 能力 | 现在已有 / 尚缺 | 实现复杂度 | 默认入口 |
| --- | --- | --- | --- | --- |
| 1 | 相纸与电影印片，并按胶片自动配对 | 核心、数据、光谱印相和中性滤色数据库已有；应用固定 Portra Endura，用户不能换，未读取胶片 `target_print` | 中：主要为跨端参数、配对、缓存和预览接入；不需要新物理模型 | 胶片名称下的一行「印相：自动」，点击后才展开；反转片直扫时隐藏印相选择 |
| 2 | 模拟胶片画幅 | 核心按物理长度计算颗粒和光晕尺度；桌面沿用 35mm 默认，Android 以 35mm 为固定基准按块换算，没有画幅选项 | 中：单个物理参数，但必须统一预览/原尺寸/分块和缓存；无需重采样或降像素 | 「颗粒」的高级项内一行「模拟画幅」，默认保持现有 35mm 基准 |
| 3 | 暗房印放曝光与 Y/M 滤色 | 光谱放大机与参数已有；应用仅接相机曝光，印放参数使用默认，未提供控制 | 中：三个标量、滤色 LUT 失效和中性基准验证；不新增空间卷积 | 与相纸共用默认折叠的「印相微调」；只在负片经印相输出时显示 |

## 1. 相纸与电影印片配对

本地 profile 共 28 个，其中 20 个 `stage=filming` 已包含在当前胶片列表，另外 8 个是 `stage=printing`：6 种相纸与 2 种电影印片。不要把印片型号伪装成拍摄胶片，也不需要用不存在的型号扩充列表。

已携带的印相材料为 Portra Endura、Supra Endura、Ultra Endura、Endura Premier、Ektacolor Edge、Fujifilm Crystal Archive Type II，以及 Kodak Vision 2383、Vision Premier 2393。

原版 `init_params(film_profile, print_profile)` 确实加载两个独立 profile；放大机阶段计算负片的光谱透射、滤光后的光源以及相纸感光响应，扫描阶段再读取相纸的染料和观察光源。这比在最后叠一个印片 LUT 更符合当前产品的完整光谱定位。

当前缺口：Windows `Settings.paper` 虽存在，但不在 `FILM_FIELDS` 中，用户状态不能保留所选相纸；Android `_make_params()` 直接固定 Portra Endura。Vision3 的上游 profile 明确推荐 2383，富士负片推荐 Crystal Archive Type II，现有应用没有自动采用这一元数据。建议默认「自动配对」，保持用户只选胶片就能工作的路径；手动材料选择收进该行菜单。自动推荐不等于限制用户进行其他组合。

本次对本地 JSON 进行的静态核对还确认：16 款负片的 `target_print` 配对，在 `TH-KG3` 光源下均有中性滤色数据库记录；另外 4 款反转片无 `target_print`。这为先做「自动配对」提供了已有数据基础，不等于实际样片效果或任意手动组合均已验证。

源码证据：

- [独立胶片/印相 profile 初始化](../vendor/spektrafilm/runtime/params_builder.py#L147)
- [按印相材料、光源、胶片读取中性滤色](../vendor/spektrafilm/runtime/params_builder.py#L45)
- [Vision3 500T 的 target_print 为 2383](../vendor/spektrafilm/data/profiles/kodak_vision3_500t.json#L18)
- [Pro 400H 的 target_print 为 Crystal Archive](../vendor/spektrafilm/data/profiles/fujifilm_pro_400h.json#L18)
- [2383 是 printing 阶段的 film 支持材料](../vendor/spektrafilm/data/profiles/kodak_2383.json#L15)
- [完整光谱印相计算](../vendor/spektrafilm/runtime/stages/printing.py#L75)
- [印相/胶片扫描使用不同光谱数据](../vendor/spektrafilm/runtime/stages/scanning.py#L50)
- [当前 Windows 仅允许的产品字段](../desktop/imaging.py#L70)、[固定 paper 默认值](../desktop/imaging.py#L101)
- [当前 Android 固定 Portra Endura](../android/app/src/main/python/studio_spectral.py#L22)

接入时需把材料 ID 纳入持久化、批量快照和缓存 key，检查中性滤色数据库是否覆盖组合；没有数据库项时不得把默认滤色冒充已校准。反转片目前走 `scan_film`，不应显示一个实际上不生效的相纸选择。

## 2. 模拟胶片画幅

上游 `CameraParams.film_format_mm` 已存在；`ResizingService` 用 **物理长边毫米数 ×1000 ÷ 图像长边像素数** 得到微米/像素。颗粒模型再用像素面积与颗粒面积计算每像素的粒子数，光晕等物理尺寸同样通过这个尺度换算。它与现有「颗粒大小」有不同职责：颗粒大小改变颗粒本身，画幅改变相同颗粒在整个画面中的相对尺度。

这项适合用户未来的中画幅需求，但它是**模拟胶片画幅**，不是输出尺寸、真实相机识别或画质升级。改变该项不得裁切、缩小或放大输出像素，也不应按照片像素多少自动决定它。UI 不应把“120”误当作 120mm 长边；中画幅具体预设需要按 6×4.5、6×6、6×7 等有效画幅校准，并保留与原版 35mm 默认兼容的基准。

源码证据：

- [相机物理画幅默认值](../vendor/spektrafilm/runtime/params_schema.py#L49)
- [长边到微米/像素的明确公式](../vendor/spektrafilm/runtime/services/resize.py#L17)
- [颗粒粒子数量使用像素物理面积](../vendor/spektrafilm/model/grain.py#L94)
- [曝光阶段按 pixel_size_um 应用柔化与光晕](../vendor/spektrafilm/runtime/stages/filming.py#L62)
- [当前 Android 的分块画幅比例换算](../android/app/src/main/python/studio_spectral.py#L23)

接入要求是统一桌面整帧、手机 tile 和预览的空间尺度，并做同一照片多分辨率、重叠块拼接与 100% 细节对照。当前 Android 的公式可作为分块接入起点；不能只把一个下拉框接到桌面参数就宣称双端一致。此处没有新增性能测量，复杂度判断来自代码结构。

## 3. 暗房印放曝光与 Y/M 滤色

上游已将拍摄曝光与印相曝光分开。`EnlargerParams.print_exposure` 控制印相时曝光，`y_filter_shift` / `m_filter_shift` 相对当前组合的中性滤色改变放大机光源，随后继续参与相纸的光谱曝光。建议首轮仅提供「印放曝光」与两个中性起点的滤色轴，其余如预闪、扩散、曲线形变继续隐藏，不把暗房工具铺满主面板。

这是印相材料前的光谱操作；它不等同当前已经删除的 RGB 后处理、HSL 或相机白平衡。印放曝光可以在 UI 使用 EV，但上游字段本身是线性倍率，调用时需要明确映射，例如 `2**EV`。滤色维度用原版 CC 语义和中性基准，不以“色温”冒名。反转片直扫时隐藏，避免无效控件。

源码证据：

- [印放曝光与 Y/M 滤色参数](../vendor/spektrafilm/runtime/params_schema.py#L61)
- [滤色偏移叠加到组合的中性滤色后生成光源](../vendor/spektrafilm/runtime/services/filter_enlarger_source.py#L15)
- [印放曝光作为线性倍率作用于原始相纸曝光](../vendor/spektrafilm/runtime/stages/printing.py#L54)
- [滤色光源实际进入相纸光谱曝光](../vendor/spektrafilm/runtime/stages/printing.py#L86)

这一项不增加新的空间卷积，但更改滤色会使光谱印放缓存失效，仍须测量首次与热路径，不能据此声称手机实时。继续复用现有交互代理与最终原尺寸显影的职责区分。

## 暂不优先增加

上游确实还实现了相机/放大机柔光滤镜（`black_pro_mist`、`glimmerglass`、`pro_mist`、`cinebloom`），以及扫描端锐化、白黑点、预闪等。柔光滤镜核由物理半径和像素尺寸构造，可能显著放大手机分块的重叠范围；现阶段用户优先性能，因此不列入前三。它们的参数族是上游建模，不应包装成与某款商业实体滤镜逐像素等价的认证效果。

依据：[柔光滤镜实现及核半径计算](../vendor/spektrafilm/model/diffusion.py#L585)、[扫描锐化](../vendor/spektrafilm/runtime/stages/scanning.py#L123)。现有 Portra 800 Push +1/+2 已在胶片列表，无需把“新增增感”当成尚不存在的功能再次交付。

这份文档仅为候选建议与代码核查，不代表上述三项已接入、已发布或已在 Android 真机验证。

## GUI 可借鉴结构

上游 GUI 使用 napari / Qt，主视图通过水平 splitter 分为单一图像区和参数区。参数区有 `MAIN`、`FILM`、`PRINT`、`ADVANCED`、`CONFIG` 五个标签，下面固定一条操作区。`MAIN` 本身仍包含导入、RAW、裁切、输入、相机、profile、曝光、放大机、扫描与输出等多组面板，因此适合作为参数语义的参考，不宜直接搬成当前产品的信息架构。

依据：[实际五个标签与固定操作区](https://github.com/andreavolpato/spektrafilm/blob/3bb2c2d2801ff68b92019cf1dbcbb133d60832bc/src/spektrafilm_gui/napari_layout.py#L398)、[图像/参数 splitter](https://github.com/andreavolpato/spektrafilm/blob/3bb2c2d2801ff68b92019cf1dbcbb133d60832bc/src/spektrafilm_gui/napari_layout.py#L470)。

### 两端的建议映射

| 上游已核实的做法 | 对当前产品的建议 | 边界 |
| --- | --- | --- |
| Film profile 与 Print profile 是两个独立字段 | 胶片为主选择；若接入印相材料，用下一行「印相：自动」承接 | 印相材料不混进胶片列表，不凭空增加胶片数量 |
| 多个物理阶段各用可折叠参数组 | 保持「胶片 → 曝光 → 颗粒 → 光晕 / 暗角」短路径；当前常用参数直接显示，未来印相参数按实际密度决定如何分组 | 折叠依据本产品的操作频率和视觉层级，不照搬五个技术标签；不恢复 HSL、蒙版、校准或图库 |
| 参数滚动区与底部操作区分开 | Windows 导出保持固定位置；Android 导出保持单一、可达且不挤压图片的入口 | 导出设置放弹层；不再同时出现多个同义主按钮 |
| 小图预览、全尺寸扫描、保存分别有明确语义 | 内部区分交互预览与最终原尺寸光谱显影；用户主路径合成一次「导出」 | 不要求用户依次点 Preview、Scan、Save；不把预览代理写成最终结果 |
| `scan_for_print` 会联动 scanner 白黑点与 glare，并恢复之前值 | 借鉴“状态联动及可恢复”原则：无效阶段的控件隐藏或明确不可用 | 上游这段联动不是“直扫自动隐藏相纸”的证据；隐藏相纸是本项目建议 |
| 一套参数 manifest 维护单位、步长、提示与分组 | 两端共用产品字段语义与默认值，显示单位、重置值和生效状态一致 | 不由 GUI 重写物理模型，不让界面文案成为导出参数的唯一依据 |

上游真实的 profile 控件是 `QComboBox` 子类；delegate 根据 profile 元数据在名称前绘制 `still /` 或 `cine /`。它没有在本次核查的控件内使用照片卡片或胶卷包装缩略图。可借鉴这种轻量用途标识，但用当前中文语义与 已认可的灰绿配色实现；无需增加装饰性图像。

依据：[独立 profile 字段](https://github.com/andreavolpato/spektrafilm/blob/3bb2c2d2801ff68b92019cf1dbcbb133d60832bc/src/spektrafilm_gui/param_manifest.py#L782)、[profile 用途文本和绘制](https://github.com/andreavolpato/spektrafilm/blob/3bb2c2d2801ff68b92019cf1dbcbb133d60832bc/src/spektrafilm_gui/widget_editors.py#L33)、[profile 下拉控件](https://github.com/andreavolpato/spektrafilm/blob/3bb2c2d2801ff68b92019cf1dbcbb133d60832bc/src/spektrafilm_gui/widget_editors.py#L103)。

### 折叠与预览的准确边界

`GroupManifest.collapsed_by_default` 默认为 true，`ParamsGroupSection` 使用该值构造 `CollapsibleSection`，这是可直接参考的渐进展开机制。`ParamSpec` 还标有 `tier="basic"` / 默认 `dev`；但当前读取到的 `ParamsGroupSection` 是逐个布局 `panel_fields` 或全部字段，**不能据此声称上游已经按 basic/dev 自动生成两级面板**。本项目若只露出少量高级项，应自行维护明确的产品白名单与布局，不照搬所有开发参数。

依据：[manifest 定义](https://github.com/andreavolpato/spektrafilm/blob/3bb2c2d2801ff68b92019cf1dbcbb133d60832bc/src/spektrafilm_gui/param_manifest.py#L47)、[实际字段布局和默认折叠](https://github.com/andreavolpato/spektrafilm/blob/3bb2c2d2801ff68b92019cf1dbcbb133d60832bc/src/spektrafilm_gui/widget_sections.py#L464)、[折叠组件](https://github.com/andreavolpato/spektrafilm/blob/3bb2c2d2801ff68b92019cf1dbcbb133d60832bc/src/spektrafilm_gui/widget_primitives.py#L27)。

上游按钮说明明确：`PREVIEW` 在小图上运行并停用颗粒、光晕、模糊、unsharp mask；`SCAN` 才运行原尺寸完整模拟；`SAVE` 保存当前输出层。本项目可以沿用分辨率分工，但用户已经要求“颗粒/光晕变化能看见”和原尺寸导出，不能照搬其删减预览内容的方式。需要把预览代理状态与真实细节验证区分清楚，并确保导出重新读取原图及完整参数。

依据：[三个按钮的真实语义](https://github.com/andreavolpato/spektrafilm/blob/3bb2c2d2801ff68b92019cf1dbcbb133d60832bc/src/spektrafilm_gui/widget_sections.py#L93)、[印刷扫描状态联动及恢复](https://github.com/andreavolpato/spektrafilm/blob/3bb2c2d2801ff68b92019cf1dbcbb133d60832bc/src/spektrafilm_gui/widget_sections.py#L802)。

### 保留与不采用

保留当前 Windows / Android 技术栈、已认可的布局和字体、已认可的灰绿配色；上游研究不构成换成 napari 或复制其皮肤的理由。优先改分组、字段职责、无效状态和预览/导出边界。参数区采用垂直滚动并在窄宽下正确收缩；上游同样禁用参数区水平滚动，但这本身不能解决内容最小宽度溢出，需要本项目实际检查。

上游虚拟相纸背面、Polaroid 显影动画、napari 图层配置、光谱调试与大量逐通道实验参数不纳入本次建议。上游 README 自述 GUI 有实验性质、部分参数说明有限；保留参数名字或控件外观不等于获得完整易用性。

另需独立验证色彩显示：上游 README 明确 napari 本身不做色彩管理，Windows 会尝试读取显示器 profile 并转换显示结果。这是显示链路的说明，不应被误读为“所有平台预览与导出天然色彩一致”。当前项目应分别核对屏幕显示转换与输出文件 ICC，而不是只对比 UI 截图。

依据：[单向依赖与 GUI/物理模型职责](https://github.com/andreavolpato/spektrafilm/blob/3bb2c2d2801ff68b92019cf1dbcbb133d60832bc/src/spektrafilm_gui/README.md#L5)、[滚动策略](https://github.com/andreavolpato/spektrafilm/blob/3bb2c2d2801ff68b92019cf1dbcbb133d60832bc/src/spektrafilm_gui/napari_layout.py#L183)、[显示色彩管理说明](https://github.com/andreavolpato/spektrafilm/blob/3bb2c2d2801ff68b92019cf1dbcbb133d60832bc/README.md#L339)、[GUI 实验性质说明](https://github.com/andreavolpato/spektrafilm/blob/3bb2c2d2801ff68b92019cf1dbcbb133d60832bc/README.md#L368)。
