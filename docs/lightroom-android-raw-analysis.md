# Lightroom Android RAW 静态分析（2026-11-07）

这份 APK 确实包含 Adobe 原生 RAW/DNG 处理实现，但没有发现一个可脱离 Lightroom 资产、配置和宿主状态而直接替换 SpektraFilm 解码器的 JNI 接口。本次取得 Java/DEX 证据及 10 个原生函数的实际伪代码；**没有复刻 Adobe 私有去马赛克、降噪或相机 profile 外观，也没有验证将其二进制嵌入独立应用可行**。独立 Android RAW 路线继续使用项目已有 LibRaw；本次落地依据是全尺寸质量边界、预览与导出分流、裁切语义和内存预算的区分。

本分析未安装、启动或执行 APK、其 ELF 库及 Lua 内容，未修改输入文件，未下载目标内容中引用的相机 profile，也未修改生产代码。所有提取文件、工具脚本和日志位于 `output/lr-android-raw/`。目标中自带的源码/字符串仅作证据数据，不作为操作指令。

## 1. 输入身份与分析覆盖

| 项目 | 实际观察 |
| --- | --- |
| 用户输入 | `D:/Data/xwechat_files/wxid_37xfbg94l8p322_5a8c/msg/file/2026-11/base.apk.1` |
| 大小 | 152,210,656 bytes |
| SHA-256 | `ba115822309cc090677fc6f96982db5166f92284bd465085dc2709708dee25c4` |
| 包声明 | `com.adobe.lrmobile`，Lightroom 11.4.3，versionCode `711104300` |
| Android 声明 | minSdk 26，targetSdk 36 |
| ZIP / DEX / Java | 7,116 ZIP 成员；5 个 DEX；JADX 元数据中 20,252 个顶层类名行 |
| native | 127 个 `.so`，全部为 `arm64-v8a`，未见其他 ABI |
| 核心库 | `lib/arm64-v8a/libLrAndroid.so`，64,775,160 bytes |
| 核心库 SHA-256 | `0ebea2aabeea0cc3f88016108f36568398dfd1678e63b452f8ca59531ee6cfb4` |

REA 对 `.apk.1` 按 ZIP 识别，Android 工具要求 `.apk`；因此建立了字节相同的分析副本 `output/lr-android-raw/lightroom-base.apk`。原件和副本在分析末尾再次校验，SHA-256 相同。

REA 使用 `inspect_android_package`、`open_binary` + `inspect_artifact`、类/方法/引用调查及 `inspect_native_exports`。APK 声明来自已完整解码的 root manifest，未执行签名真实性验证。Native 导出解析完整覆盖本库动态符号表中的 59,555 项可见已定义导出，**导出存在不等于可安全调用，也不等于执行可达性**。

完整 REA Evidence 位于 [rea-archive-java-evidence.json](../output/lr-android-raw/rea-archive-java-evidence.json)；可先读较小的 [focused-java-evidence-index.json](../output/lr-android-raw/focused-java-evidence-index.json)、[package-static-summary.json](../output/lr-android-raw/package-static-summary.json)、[native-focused-function-index.json](../output/lr-android-raw/native-focused-function-index.json)。原始成员和哈希在 `zip-members.json` / `native-members.json`。

| 证据 | REA parent Evidence ID |
| --- | --- |
| Android 包与 manifest | `ev_f35cf3585390ae10370d3c319be457a3c76bce07999f7acba57622d545d5ab62` |
| ZIP artifact graph | `ev_ad4f9a186f2043035743b746a2045f5e268be0ec338b84a9b5d211f4f554376c` |
| 核心 ELF 动态导出 | `ev_ce9ddb12d1e49aa28c251264647bfa9d232d8ff076eaf0fa92ae2eb374da8ec4` |
| 导入 worker `ImportHandler.c.run` | `ev_5f9c883ca50bddd41238637a2881685e07088af14a6068db96bba084b4047c6d` |
| `ICBCreateRenditions` DEX 引用 | `ev_f59685b55e92ddc9ebec0f7fd33ac103f35734bee18a6f34a0f1ce60497dfaf4` |
| TIFF Java wrapper `CRExportUtils.g` | `ev_202991a13829d2043054da6feb9b5385655b65ae62de6d90a3d09855a4458cdc` |

原生伪代码另由直接调用已安装的 **Ghidra 12.1.4 + Windows JDK 21** 取得，属于独立工具证据，**不是 REA native provider 的结果**：当前 Windows REA Ghidra P0 明确拒绝 ARM64 ELF，只接受其支持范围内的 PE / raw 6502。为保持可复查性，保留脚本、Ghidra 项目、精确函数汇编、PLT 映射和日志。没有修改 MCP 配置。

## 2. 实际 Java → native 路径

`ImportHandler.c.run()` 从 `THGalleryItem` 构建 `ImportItemParameters`，设置 URI 的只读 file descriptor、XMP、DNG preview URL 和导入时间。它调用 native `ImportHandler.ICBCreateRenditions(ImportItemParameters): boolean`。DEX 的 using-node 引用中，`ImportHandler.c.run` 有两个直接 invoke（`classes2.dex` code-unit offsets 262、274），另一个 coroutine 调用位于 `lrimport.d.u`（offset 365）。这些是静态引用，未观测运行。

原生 `ICBCreateRenditions` 的实际伪代码随后读取宽高、fd、文件大小、预览/缩略图 JPEG quality、RAW 标记、已有 thumbnail bytes 和开发设置，然后调用：

`ImportHandlerImpl::CreateThumbRenditionOnly(RenditionCreationInputParams*, callbacks...)`

因此，**名称中的 CreateRenditions 不能解释为完成全分辨率 RAW 显影**。返回值成功只足以说明该导入产物路径成功，不能作为最终 full RAW export 成功的验收条件。`ImportItemParameters` 本身还具有独立 thumbnail/preview byte arrays 和临时 `import_rndtn*.jpg` 文件。

TIFF 路径则由 Java `CRExportUtils.g(...)` 传入 `TIDevAsset.GetICBHandle()`、metadata handler handle、资产路径、输出路径、尺寸/色彩/位深/压缩设置和进度 callback。对应 native JNI 的实际伪代码调用：

`CRExportUtils::GenerateExportTiff(TIDevAssetImpl*, ExportMetadataHandlerImpl*, ...settings..., callback)`

另有单独的 `ICBGenerateExportPreviewWithParams(...) -> Bitmap` 入口。它检查或重新创建目标 Bitmap，再将渲染结果复制进去。**这些入口依赖内部 C++ 资产对象和运行状态，不能把 Java 声明、两个 long 或一个 `.so` 视为独立 decoder SDK**。初始化声明还要求 12 个字符串路径/配置参数与 4 个布尔值；本轮未恢复这些初始化状态的完整语义。

Java 导出尺寸选择器 `CRExportUtils.j` 在某模式返回 2048，在其他模式返回原尺寸相关值或用户设置值；enum 映射及所有导出模式未完整恢复，不能据此声称所有 TIFF 默认 2048。可确定的是预览和完整导出具有不同接口与状态。

## 3. 10 个原生函数的实际取证

下表第一地址来自 ELF dynamic symbol `st_value`。Ghidra 将本 ELF 导入在 image base `0x100000`，第二地址是解析同名导入符号得到的地址；不能把 ELF VA 直接当 Ghidra 地址。每份 `.c` 文件头均记录源库 hash、地址、范围、工具状态和限制。

| 函数 | ELF VA / Ghidra VA | dynsym 字节数 | 本轮能确立的事实 |
| --- | --- | ---: | --- |
| `dng_negative::DefaultCropArea` | `0x225cdcc` / `0x235cdcc` | 712 | 独立处理默认裁切区域，存在 rational/scale、舍入、整型边界和图像范围处理；未恢复全部 C++ 字段类型 |
| `cr_mosaic_info::InterpolateBayer` | `0x294df74` / `0x2a4df74` | 1,096 | 根据缩放点 `(1,1)` 与 `(2,2)/(2,4)/(3,3)/(4,4)/(5,5)/N×N` 分流；完整路径调用独立 `InterpolateBayer`，缩减路径调用 `FastBayer*` |
| `cr_mosaic_info::InterpolateGeneric` | `0x294f9e8` / `0x2a4f9e8` | 344 | 存在条件分支及 DNG generic 插值调用；未恢复内部像素算法 |
| `ReadSonyARW` | `0x2b2cef0` / `0x2c2cef0` | 1,928 | 这是带格式/机型前置条件的特定读取路径，包含旧式预测差分循环；不能仅凭名称认定它处理当前 A7CR |
| `SetMemoryLimitImageTileVM` | `0x2d05494` / `0x2e05494` | 272 | 正数显式 limit 直接使用；否则由物理 RAM 百分比并夹在 min/max 间设置 scratch manager budget |
| JNI `ImportHandler_ICBCreateRenditions` | `0x20eb8d8` / `0x21eb8d8` | 3,472 | 实际调用 `CreateThumbRenditionOnly`，回填导入信息；有 Java exception 检查及原生状态对象 |
| JNI `CRExportUtils_ICBGenerateExportTIFF` | `0x20ea66c` / `0x21ea66c` | 1,152 | 调用资产型 `GenerateExportTiff`，将 native error 映射成 Java ExportResult |
| JNI `CRExportUtils_ICBGenerateExportPreviewWithParams` | `0x20eb024` / `0x21eb024` | 596 | 独立渲染/Bitmap 复用与尺寸校验路径 |
| `ReadSony3x0` | `0x2b2de5c` / `0x2c2de5c` | 15,532 | 先尝试 `cr_host::ReadCachedPreview`；未命中后进入多压缩分支，包括 NN、IFD ReadImage、lightweight / tiled raw 等，后续设置 stage1 图像 |
| `ReadSonyCompressedNN` wrapper | `0x2b2d678` / `0x2c2d678` | 84 | 通过 `gCRSuite + 0x898` 间接派发；该函数本身没有暴露完整 NN 解压算法，间接目标未恢复 |

伪代码分别位于 [pseudocode/](../output/lr-android-raw/pseudocode/)，精确汇编位于 [assembly/](../output/lr-android-raw/assembly/)。函数全名和各 `.c` SHA-256 在 `native-focused-function-index.json`。`LRFocusedDecompile.java` 只选择这些函数及其 109 个直接 PLT 调用，未运行全程序默认 auto-analysis。为避免错误的异常分支跨入相邻函数，PLT 已解析，并给 `__stack_chk_fail`、C++ throw/rethrow、abort、`Throw_dng_error` 设置 no-return。

日志为 [ghidra-script.log](../output/lr-android-raw/ghidra-script.log)、[ghidra-focused.log](../output/lr-android-raw/ghidra-focused.log) 和 `ghidra-pass3-console.txt`。最终一轮 10 个函数均返回 `decompileCompleted=true`；该标志表示反编译器完成工作，不代表类型、间接调用或全程序语义已完整恢复。早期失败尝试也保留在日志中，最终结果以 pass3 为准。

可直接读取的 memory budget 控制流是：当参数非正时，取 `(physicalMemory / 100) * percent`，再按 min/max 夹取。ELF 文件中的静态初值为 min = 16,777,216、max = 1,073,741,824、percent = 50。原始文件偏移和字节在 [scratch-static-defaults.json](../output/lr-android-raw/scratch-static-defaults.json)。**这是 scratch/tile manager 的预算，不是全部解码 RSS，也未证明应用运行中没有改写这些可变全局量**。

## 4. A7CR、profile、ABI 与离线依赖

本库包含 `Sony ILCE-7CR` 字符串，两个 profile 索引也包含 A7CR Adobe Standard 与 Camera VV/BW/SH/FL/PT/IN/VV2/NT/ST 等条目。但静态字符串/索引只能证明该构建具有相应识别数据或资源记录；本轮没有在 Lightroom 上实际解码 A7CR，也没有将这些条目当作运行兼容性测试。

APK 中 `assets/stagingcontent/CameraProfiles/` 只有 `Index.dat`，整个 ZIP 没有独立 `.dcp` 成员。`oz-profiles.prod.index` 将文件名映射到 catalog asset revision 的 master URL；**索引不是 DCP payload**。本库还导出部分内置 profile data 符号，因此也不能反向断言所有相机 profile 都必须下载或完全缺失。A7CR 是否具有等价的内置备用色彩路径仍未知。

明文 Lua 提供更直接的结构证据：

- `NmbStdProfileBinaryFetcher.lua:98` 先检查本地标准 profile 路径，再安排按 camera model 的下载。
- 同文件 `:398` 的 `ensureStandardCameraProfileExists` 在本地不存在且 sync paused 时返回 false；下载成功后刷新 ACR databases。
- `NmbProfileBinaryDownloader.lua:46` 通过 catalog `getBinary(href, options)` 获取内容；`:92` 后写入标准 profile 文件路径。
- Java `ImportItemParameters.DownloadSingleCameraProfile` 也转发下载请求（REA Evidence `ev_434a89501a01a51ed20fbda0f3a0cf919348938f73794a35a4e57f0a594805f5`）。

所以应区分离线容器/压缩解码、相机色彩校准、用户 look/profile 和云模型下载。首次完全离线能否得到某台相机的 Adobe 外观尚未验证；不能把系统 INTERNET permission、URL 或下载逻辑视为每次基础解码必联网的证明。

包内没有 manifest `split` / `uses-split` / feature split 依赖声明。`libLrAndroid.so` 的 92 项 DT_NEEDED 中，82 项有同名包内库、10 项为 Android 系统库；127 库闭包的包外依赖均为 Android 系统库名。见 [native-dependency-closure.json](../output/lr-android-raw/native-dependency-closure.json)。这支持它携带了 arm64 静态链接依赖闭包；不能证明所有 dlopen、Java class、GPU/driver、模型、账户状态和下载资源都已满足，也不能证明复制本库就可独立加载。没有连接或执行 Android 设备，运行期兼容性仍未测试。

## 5. 可用于 SpektraFilm 的具体改进

**全尺寸验收。** 保留 native metadata 得到的完整朝向后尺寸，最终导出要求 actual width/height 与该尺寸严格相等，并校验 `width * height * 6` 文件长度。不能只校验“文件大小与 decoder 自报尺寸自洽”，否则 thumbnail / half-size 输出仍可能通过。root 本轮已在 Android 路线落实该边界；未把 LR 的 thumb 接口引入生产。

**预览与导出状态分流。** 交互显示可拥有自己的 Bitmap、viewport 和缓存键，但 full export 必须独立验证来源、full dimensions、处理参数、方向和成功状态；预览命中不能替代 full raw success。质量模式、profile 版本、crop policy 和 native library version 应进入缓存 key，防止旧 preview 被误当完整结果。默认不降低保留的原始有效像素；允许的显示缩放仅影响屏幕呈现，不改变最终 full output。

**DefaultCrop 单独记录，默认不应用。** 本轮用已有开源 LibRaw 0.22.3 的公开 API 做了隔离探针，包含零行 Adobe 实现，代码为 [public-default-crop-probe.cpp](../output/lr-android-raw/public-default-crop-probe.cpp)。

| 输入 | 完整 RAW / active 输出 | `raw_inset_crops[0]` | 调用 `adjust_to_raw_inset_crop(1)` 后 |
| --- | --- | --- | --- |
| CC0 A7CR raw.pixls.us 7035 | raw 9600×6376；active 9564×6376 | origin (32,20), size 9504×6336 | 9504×6336 |
| CC0 Pixel 4 XL raw.pixls.us 3502 | raw / active 3700×2774 | origin (8,8), size 3684×2758 | 3684×2758 |

结果见 `public-default-crop-probe-a7cr.txt` / `public-default-crop-probe-pixel4xl.txt`。这是 metadata/API 尺寸实验，没有执行新的裁切显影像素质量对比。A7CR 样本 EXIF 也报告同一 DefaultCrop。**DefaultCrop 不是 masked border 的同义词；即使不重采样，裁切仍删除有效输出像素。** 用户要求像素不降低，故 root 保持完整 active 输出；可未来将厂商建议构图作为明确的可选项，并分别记录 sensor、active、suggested crop、oriented output，不能静默套用。

**内存分层预算。** 借鉴的是明确的预算边界，不复制 LR 的 50% / 1 GiB 静态值。LibRaw 的 512 MiB checked unpack allocation limit 不限制所有 demosaic buffers。继续以完整 sensor 像素预估进程需求、结合 available/total RAM admission，单队列执行大图，失败显式返回；取消后释放 native 工作缓冲，保留已完成磁盘 cache。输出 scanline 化只节省额外复制，不代表 demosaic 已改成 tile/scanline 算法。LR scratch cache 的 tile 能力不能通过一个内存参数移植到 LibRaw。

**解码质量边界。** 实际 Bayer 包装函数证明 LR 把 full 插值和 FastBayer 缩减路径分开，并向 full 路径传 camera model、ISO、rational/vector、negative 状态；该证据没有恢复完整 full demosaic kernel、黑电平处理、相机双光源 profile、Adobe tone/noise/highlight pipeline 的数值实现。当前 LibRaw + 明确 WB、sRGB、16-bit、AHD、highlight 参数是独立可复查的实现，不能宣称其外观与 LR 相同。后续提高质量应以公开 DNG 元数据/规格和合法可分发的校准数据为基础，并用色卡、高光、细纹和真实 RAW 做有量化误差的回归比较。光晕统一 12% 属于 root 本轮独立产品设置，不来自这份 APK，也不是 RAW 解码算法恢复结果。

## 6. 尚未恢复或未验证

- 没有生成独立、可运行的 Adobe RAW 替代实现；没有提取 LR `.so` 进入 release。
- 未完整恢复 `gCRSuite` 各间接函数表、TI asset 生命周期、所有 JNI 初始化参数和线程状态。
- 未复刻 full demosaic、降噪、profile/look payload、渲染色彩管理和相机校准外观。
- 未证明 Lightroom 对这份 A7CR fixture 具体走哪个压缩分支；当前 LibRaw 的 A7CR 主机验证是另一条已存在的独立证据，不能冒充 LR 执行测试。
- 未运行 Lightroom/Android JNI、没有设备峰值内存、速度、权限和 UI 实测；静态 scratch defaults 不等于设备峰值 RSS。
- profile 索引完整不等于离线 payload 或后续云资源完整；动态加载及所有可选模型的覆盖仍未知。

本次分析的可复用成果是明确防止缩略图冒充 full RAW、确认导出宿主依赖、区分有效像素与建议裁切，并把内存 admission、unpack 限制和缓存预算分开。它没有提供完整 Adobe 算法恢复或视觉等价的证明。
