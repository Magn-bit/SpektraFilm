# RAW 原片质量与中画幅验证

2026-11-07。当前优先级：正确解包、相机白平衡、黑白电平、清晰度和高光，其后才是胶片显影与交互速度。正式生产使用 LibRaw；Capture One 独立重建仍处于[局部验证阶段](captureone-raw-reconstruction.md)。

## 本轮实现

- Windows 的文件选择、拖入/粘贴、元数据、解码和 RAW 原片另存统一使用 `shared/photo_formats.py`，补齐 IIQ、3FR、FFF、MOS、NRW 等路由。Android 使用同样的26种后缀，测试检查两端清单一致。
- Android 导入改为 `developPreview`，从 RAW 像素显影生成半尺寸代理，再按编辑预算缩放；不用内嵌 JPEG 冒充显影。代理保存完整原片尺寸，源 URI 和文件保持不变。
- 预览和完整 RGB16 缓存使用不同键。完整导出仅访问 full 缓存，缺失时从原 URI 重新读取并执行 `halfSize=false`。解码尺寸和字节数必须与原片完整有效区一致，否则失败，不能降尺寸完成导出。
- 预览仍需完整 RAW 解包；保留按完整传感器面积计算的保守内存准入，不能把所有开销当成四分之一。后续只有实测证明峰值降低后才调整这个预算。

## 真实样片验证

`scripts/verify_camera_raw.py --download-medium-format --full` 下载公开 CC0 样片，按保存的 raw.pixls.us 数据集 SHA-256 校验。已有 M 盘原片只读。报告和图像在 `output/camera-raw-validation/`，不混入应用资源。

| 样片 | 完整显影尺寸（朝向后） | 测试编码 |
| --- | --- | --- |
| Sony A7CR | 6376 × 9564 | 用户提供 ARW |
| Canon CR2 | 4020 × 6024 | 用户提供 CR2 |
| 手机 DNG | 4000 × 3000 | 用户提供整数 CFA DNG |
| Fujifilm GFX 100 | 11662 × 8746 | 16位压缩 RAF |
| Hasselblad X2D 100C | 11664 × 8750 | 16位 3FR |
| Phase One IQ4 150MP | 14204 × 10652 | IIQ L |

Windows 六张均实际完成预览与完整解码，尺寸和输入 SHA-256 检查通过。尺寸是解码器完整有效画面，不是含黑边的传感器面积，也未额外套用厂商 DefaultCrop。不能用不同软件的默认裁边尺寸相互拉伸来伪造一致。

新打包的 Windows EXE 也实际通过微型 CFA DNG（改为 IIQ 后缀以检查路由）的导入、预览、完整光谱 JPEG 导出、64×96原尺寸、ICC和源文件完整性检查；它不是实际 IIQ 编码或1.5亿像素完整光谱导出验收。证据为 `output/raw-compatibility-candidate/windows-raw-smoke.json`。

Android 原生解码代码的主机测试，对全尺寸与半尺寸分别与官方 LibRaw `dcraw_make_mem_image` 输出逐字节比较；三个中画幅的结果记录在 `output/native-medium-format-*.log`。这验证解码代码，不等于手机端运行或完成了胶片导出。测试 APK 增加了真实微型 CFA DNG 的“预览→完整缓存→原尺寸 JPEG”集成检查，未连接设备时仅完成编译，不能称实机通过。

## 验收边界

- 后缀路由不等于支持每款相机、每种压缩或多帧格式。当前 Windows rawpy 0.26.1 / LibRaw 0.22.0；Android LibRaw 0.22.3。新机型需按实际文件确认支持。
- 输出尺寸保留不代表全程16位：Windows现有图像接口为 RGB8，Android磁盘解码缓存为 RGB16，但现有 Bitmap 胶片管线也会转成8位输入。不能将本轮改动宣传为16位端到端显影或无损颜色管线。
- 官方解码器对照是实现一致性检查，不能证明色彩已经达到物理标定准确度或完全复现 Capture One。白平衡、肤色、高光与噪声仍需分场景的质量对照。
- Android当前单源临时文件上限512 MiB、单完整像素缓存1 GiB；高像素原片还受设备可用内存、存储与完整光谱计算约束。超出资源条件明确失败，不能用缩略图作为成功结果。
- 本轮生成 Windows/Android 开发候选，正式 `release/` 未更新。没有把局部 C1 研究或主机检查写成正式手机验收。
