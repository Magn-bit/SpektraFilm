# Capture One 本机 RAW processor ABI 与受控输出

本轮已通过原版托管 wrapper 和本机正常安装的原生 DLL，在隔离 .NET 10 进程中打开 A7CR RAW、创建代理，并成功输出全尺寸 16 位 sRGB TIFF。它是后续独立实现的 **受控 native 参考样片**，不代表 SpektraFilm 已独立复原 C1，也不代表套用了 C1 GUI 的全部相机默认调整。

## 结果与证据

| 项目 | 实测 |
|---|---|
| 原始研究副本 | `output/captureone-raw-runtime/input/DSC06823.ARW`，原 M 盘文件未动 |
| 输出 | `output/captureone-processor-runtime/raw-render.tiff` |
| TIFF | 6336 × 9504；RGB 16/16/16 bits；Compression=1；Orientation=1；361,359,308 bytes |
| 输出 SHA-256 | `20d6ebf44528bac63367ccd6c53d3cb71ccc344766dc18c4752b01f784e1b8b6` |
| ICC | sRGB IEC61966-2.1；3144 bytes；与原安装 sRGB profile bytes 完全相同 |
| ICC SHA-256 | `2b3aa1645779a9e634744faf9b01e9102b0c9b88fd6deced7934df86b949af7e` |
| 原生输出返回值 | `resOK=0` |
| 最后一轮 ProcessToFile 耗时 | 2.3261458 s；仅该调用的单次本机耗时，不含前置初始化与完整冷启动，也不作 GPU 路径声明 |

验证脚本 `verify_output.py` 已实际通过，并生成 `oracle-output-validation.json`。预览 `raw-render-preview.jpg` 已目视确认：方向、场景和细节正常。它只是供检查的 JPEG，完整参考是 361 MB 的 16-bit TIFF。

## 身份与工具

- 安装位置：`C:\Program Files\Capture One\Capture One`。
- ImgCoreDll.dll SHA-256：`CA02B6AC2786E9A100F63221DF7340E5DF210416EB0BD53A4BB1BFC2306A44A4`。
- P1.C1.ImageCoreWrapper.dll SHA-256：`5AAE6155242B996D23DA0DED07E777BF74F61D0C85A9979FBF26C64AB4D8380B`；.NETCoreApp v10.0。
- 使用已有 .NET SDK 10.0.300／WindowsDesktop runtime 10.0.8。ILSpyCmd 9.1.0.7988 仅安装于 `output/captureone-processor-runtime/tools/`，没有改全局工具或 C1 安装。
- wrapper 的完整反编译材料在 `wrapper-project/`；单类型材料在 `decompiled/`。它们是研究证据，不进入生产或发布物。
- 未重复此前失败的 Ghidra 600／1800 秒全库启动；本轮依靠 ILSpy 的实际 CIL 声明、托管调用逻辑和成功执行结果。

## 确认的调用契约

原版 wrapper 的 `ImgCore.ImgCoreDll` 是公开类。harness 编译时引用本机 assembly，`Private=false`；运行通过 AssemblyLoadContext 与 NativeLibrary resolver 从原安装位置加载，**没有复制或打包 C1 DLL**。所有原生调用使用该 assembly 本身的 Cdecl P/Invoke，保留其 UTF-8 CustomMarshaler、SafeHandle 和 inline array 规则。

| 入口 | 已恢复签名／要求 |
|---|---|
| `IC_StaticInit(uint heapSize)` | 返回 `IC_Result`；本轮明确传 0；没有猜测无参 overload 的寄存器值 |
| `IC_LoadConfigFile(string pathName,bool allowPlainText)` | UTF-8 **目录路径**，须带末尾 `\`；wrapper 检查该目录存在 `coreConfig.cdx`；本轮传安装目录、true |
| `IC_SetResourcesPath(string path)` | 本轮安装目录带尾 `\` |
| `IC_GetDefaultProcessSettings(ref IC_ProcessSettings)` | 必须先用 `IC_ProcessSettings.CreateDefault()` 建立嵌套 Empty SafeHandles，随后 native 填默认值；verificationNumber 必须为 999444 |
| `ICIF_Create(string rawPath,string? proxyFileName)` | 返回 ImageCoreImageHandle；本轮 raw 为研究副本，proxy 参数 null，句柄有效 |
| `ICP_Create(string processorName)` | 返回 ImageCoreProcessorHandle；本轮有效 |
| `ICP_SetSource(processor,image,string proxyPath,int proxySize)` | 设置 RAW handle 与研究输出目录 `source.cop`，size=0；本轮返回 0。直接传 null proxyPath 返回 resInvalidParameter，不能假设 null 与不存在代理路径等价 |
| `ICP_CreateFileProxy(processor,string path,IC_CacheFlags,bool overwrite,bool cacheRawData,int size)` | 本轮 Preview=2，false，false，1024；返回0，生成 source.cop 与 source.cof；此1024只用于代理测试，不用于最终输出质量 |
| `ICP_SetStatusCallback(processor,ICPStatusCallback,nint context)` | Cdecl delegate `(IC_CallbackType,int,ref IC_CallbackReturnValue,nint)->void`；native 立即发 CallbackTest，本轮回调保活至输出后 |
| `ICP_ProcessToFile(processor,ref IC_ProcessSettings,IC_ProcessQuality,ref IC_FileDestination)` | 本轮质量 pqBest=0，16bit TIFF，返回0 |
| `IC_StaticShutdown()` | 所有 using SafeHandles 已离开其作用域后执行，返回0 |

`IC_LoadConfigFile` 的布尔开关只是原接口参数，本轮加载原有 cdx，没有替换配置、修改认证、挂接已有 GUI 或调用安全模块。

## 结构体的真实尺寸与封送

实际 `Marshal.SizeOf`／`Marshal.OffsetOf` 记录在 `managed-runtime-layout.json` 和每次运行 JSON 的 layout 项中：

| 类型 | native 封送尺寸 | 关键 offset |
|---|---:|---|
| IC_ProcessSettings | 80,272 bytes，Pack=8 | imageProcessSettings 64088；filmCurve 75080；colorFilmCurveRef 76104；colorProfileList 76112；cropScale80256；verificationNumber80264 |
| IC_ImageProcessSettings | 10,992 bytes，Pack=8 | rawWidth0、rawHeight4、rawPixelWidth8、rawPixelHeight12、cropRotation16 |
| IC_FileDestination | 7,912 bytes，Pack=8 | fileName0（1024 bytes）；fileType1024；bits1044；guides1084；xmpMetadata3648；ICC display name7764 |
| Utf8Marshaled_IC_MAX_PATH | 1,024 bytes | 固定 UTF-8 byte array |

不能用“分配约80KB并填几个 offset”的方法代替正确结构。多个固定数组和嵌套句柄需要原 wrapper 的 CreateDefault／PInvoke cleanup 逻辑；普通 `Marshal.StructureToPtr` 明确不允许这些 SafeHandle fields。

本轮保存了 `process-settings.bin`（80272B）和 `file-destination.bin`（7912B），通过声明相同 typed ref 参数的系统 `RtlMoveMemory` P/Invoke，捕获与最终原生调用一致的封送输入字节。这个复制函数只读本进程已知结构内存，不改目标代码。字节仅作本次过程证据，不能当作跨版本可移植 ABI。

`exact-settings.json` 保存公开托管字段，包括大部分可读值。C# InlineArray 的 JSON 呈现不能证明每个元素完整，所以完整输入以 native bytes、layout 与 harness 源码共同界定。

## 精确处理设置与默认值边界

本轮以 **IC_GetDefaultProcessSettings 的通用默认值** 为基础，然后依据该原始文件的 C1 InfoBlock 填入下列值：

- infbMetaData：RAW 9504 × 6336，pixel width／height 均3.75；captureX0/X1/Y0/Y1 均0。
- infbDefaults：cropRotation270°；shot WB `(2.512,1.000,1.676)`；默认 curve 文件名 SonyA7CR-Auto.fcrv、camera ICC SonyA7CR-ProStandard.icm。
- profile list：两个绝对路径，camera ProStandard → 安装目录 Common/sRGB Color Space Profile.icm；colorFilmCurveRef=0，用明确 filmCurve 路径。
- engine processingMethod1300；pqBest=0；cropIsRelative=true，center(.5,.5)，width=height=1，cropScale=cropScaleView=1；输出6336 ×9504来自90°方向转换，没有resize。
- file destination：TIFF=2，bits16，compression0枚举对应最终 TIFF Compression1，resolution300，无 XMP、无C2PA签名、无mask channels。

**没有把全部 infbDefaults 相机调整映射到 ProcessSettings。** 例如最终实际USMAmount=50、radius=.8、threshold1、noiseReductionAmount=0、CNRAmount=10；该照片的相机 InfoBlock 推荐USM180、NR50、CNR50。曝光／对比／饱和度／亮度均0，gain1。因此这是明确设置下可复现的native样片，不应写成“C1 GUI导入默认效果完全一致”。

全部四个 InfoBlock 保存在 `source-infbCommon.txt`、`source-infbRanges.txt`、`source-infbDefaults.txt`、`source-infbMetaData.txt`。这些文件来自原生 `IC_GetInfoBlockTransitional(image,1300,type)`，不是人工臆测。配置默认文件与样片元数据因此能关联起来。

## RAW 尺寸与日志限制

C1 报告的有效 RAW 区域为9504 ×6336，旋转后输出6336 ×9504。LibRaw 的同片可见区域9564 ×6376，多出边界。不能把两图直接拉伸到同尺寸，便声称算法逐像素一致；应先确认有效区坐标／裁边，再比较共同区域。

native-render.log 曾出现 proxy open error 和 missing XMP warning；已保留原始日志，没有把它抹掉。这没有阻止 pqBest 成功写出全尺寸16bit TIFF，返回值为0。尚需更深追踪该预览代理探测／回退分支；当前不据此声称“整个调用过程中没有任何后备路径”。本次没有调用 OpenCL 初始化接口，2.3秒也不作为GPU与CPU严格对比基准。

## 复现与下一轮插桩

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File D:\Project\SpektraFilm\output\captureone-processor-runtime\run_probe.ps1 -Stage render
D:\Project\SpektraFilm\.venv\Scripts\python.exe D:\Project\SpektraFilm\output\captureone-processor-runtime\verify_output.py
```

`run_probe.ps1` 可选择 layout/init/source/info/proxy/render。render 默认覆盖研究目录同名TIFF，做对照前应先保存有SHA的参考副本。

为了后续在新的受控进程中观测宿主参数：

```powershell
& 'C:\Program Files\dotnet\dotnet.exe' 'D:\Project\SpektraFilm\output\captureone-processor-runtime\harness\bin\Release\net10.0-windows\ProcessorProbe.dll' render 'D:\Project\SpektraFilm\output\captureone-raw-runtime\input\DSC06823.ARW' --pause
```

必须先清除旧 `resume-render.signal`；harness 在读取RAW、配置参数、绑定callback后写 `ready-to-render.json`（含PID），等待同目录新建 `resume-render.signal` 再执行，最多10分钟。这个钩子只为新的研究进程保留，不附加或修改用户现有C1进程。

下一步可以在这个已知成功链上，观察 RAW 缓冲区尺寸／偏移、Bayer stage 实际选择、black/gain/WB等参数和OpenCL dispatch；之后再给独立实现做同片中间结果与最终输出对照。成功调用本机引擎解决了参考样片问题，仍没有完成独立 RAW 引擎重建。
