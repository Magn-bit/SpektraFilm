# SpektraLab Android 引擎与性能分析

核查日期：2026-11-07。目标是从公开 Android 移植源码和同版本 APK 判断其 RAW、完整光谱、预览及导出链路，并据此评估 SpektraFilm 的性能改进方向。本报告没有修改生产代码，也没有 Android 真机或模拟器实测。

## 样本与证据范围

- Android 源码仓库：[`SAINTTaiYi/SpektraLab-Android`](https://github.com/SAINTTaiYi/SpektraLab-Android)，发布 `v1.5.0e`，固定 commit `9797ce9777210c8ff46d741e3d1731a0fd72db23`。
- APK：`output/spektralab-research/android/SpektraLab-1.5.0e-arm64-v8a.apk`，15,661,878 bytes，SHA-256 `e2d2babb2c8bb69c965f35ddf7bee219b8fd807060e38ebfc6ef66897dd4d0d1`。
- 已用 REA 静态检查 APK 包、`MainActivity`、导入 / 渲染 / 导出 Java 方法。相关 Evidence ID 为 `ev_86eae19d9a5588b00a9c73d38d354c414d9aa5312752d114d62a1e89e17f72c1`、`ev_2de9afc37da78a844ba5c6121f7039e0d47de6d9ce8161f5094f68b1a9adc303`、`ev_27405a9bfbba57ff69c66f4e5064f53bac1b9db839bce2b19404db0957caf6c1`、`ev_08f8f66f9f67c52319a97674d22747a7de74a87b003b9f0059a0a5a15edc2066`、`ev_885f079b50a4d9f6a8e7806b214f643de2a7b9c92a4b04a7a79c2e0fe3d0f349`。
- APK 仅静态分析，没有启动程序或读取运行时 GPU / RAW 数据。README 与 `docs/tiling.md` 中的秒数来自该仓库作者记录，不能当作本机或本项目实测。

## 它的渲染链路

| 阶段 | 核查结果 | 性能意义与边界 |
| --- | --- | --- |
| RAW 导入 | C++ JNI 调 LibRaw，把 RAW 解码成线性 RGB float，再送给 `spk_open`。`nativeRawDimensions` 只读头信息，先询问尺寸，不为弹窗提前解出整幅浮点图。见 [`spektralab_raw_jni.cpp`](../output/spektralab-research/android/source-release/app/src/main/cpp/spektralab_raw_jni.cpp)。 | 省掉 Java Bitmap 解码与重复全尺寸图像缓冲；仍然要为完整处理解码 RAW。默认导入会按内存 / 长边限制缩小，另有原始尺寸入口，故不能把该默认策略直接移植到要求保留像素的产品。 |
| 胶片计算 | 上游 C++ / Vulkan 光谱管线，APK 含 `libspektrafilm_engine.so` 和光谱、颗粒、扩散等 Vulkan SPIR-V shader。 | 计算在 GPU，而不是 Chaquopy Python + NumPy/SciPy 的 CPU 路径；这是架构差异的主要来源。它是 SpektraLab 自己的模型，不能视为 spektrafilm Python 模型可直接替换的后端。 |
| 参数求解 | RAW 会话打开后调用 `session.solve("both")`。 | 在进入预览前解一次流程参数；切胶片或改单一参数应复用会话与可缓存的阶段结果。 |
| 预览 | live tier 长边 2048；README 声称约 1 秒。Android UI 在后台线程调用 `spk_render(session, "live")`，再把 RGBA 结果转成 Bitmap。 | 区分低分辨率预览和完整导出是合理的；“约 1 秒”是作者描述，不是我们的测量。当前 release 源码还在每次预览后同步执行 JPEG 85 压缩和像素抽样 hash，再交给 UI 更新，属于可移除的诊断热路径开销。见 [`MainActivity.java`](../output/spektralab-research/android/source-release/app/src/main/java/app/spektralab/MainActivity.java) 的 `renderImage` 实现。 |
| 导出 | JNI 对完整会话调用 `spk_render(session, "full", ...)`，结果直接交给原生 JPEG / TIFF / DNG writer；JPEG 95、4:4:4，不经 Java Bitmap。 | 减少 Java 层整帧复制与再次编码。full 是“当前 session 的全分辨率 tier”，不是自动恢复已在导入时丢弃的像素；要保持像素，session 必须按原始尺寸打开且该设备确实有足够资源。 |
| 内存回收 | 导出前 `trimPool()`；必要时 suspend 预览 session，把持久平面临时写盘释放 GPU 副本，导出完成再恢复；不在预览与导出时同时长期占着两套工作集。 | 适合借鉴为会话生命周期 / 池管理策略，不能替代降低全管线峰值。 |

## 性能证据与参考限制

- README 对一个 SM8735 / Adreno 825、16.5 MP 样片报告 full render 8.2 秒、总计 8.4 秒。该数字限定于样片、设备与该版本，不等于 A7CR 61 MP，也不说明普通手机表现。
- Android 移植的 `docs/tiling.md` 记录：50 MP 导出结果从 103 秒降到 90 秒，主要通过映射 host-visible GPU 缓冲去掉一次整帧读回复制；RSS 仅从 792 降到 788 MiB。`striped` 计算从 95 秒降到 77 秒（约 19%），但峰值没有下降，因为输入、输出仍是整幅平面。
- 同一文档记录 50 MP 时同时存活约 7 个 12 B/px 平面，设备侧峰值约 4,005 MiB；估算 64 MP 约 5.1 GB、100 MP 约 8.4 GB。分带 dispatch 可以绕开 descriptor / 单次调度限制，但若仍保留整幅中间平面，就解决不了内存峰值。要稳定支持中画幅，需要源按带上传、整条阶段链按带执行、结果直接按带交给编码器的端到端流式架构。
- release 源码里 `IMPORT_LONG_EDGE = 8000`，并有设备预算与原尺寸导入选项；用户选择普通导入时可能发生降采样。导出调用的 `full` tier 基于 session 当前尺寸。这种明确告知并允许选择的预算机制值得参考，隐式缩小则不符合本项目“导入 / 导出分辨率不下降”的要求。
- 当前 APK 的诊断逻辑在每次预览中同步压 JPEG、hash，并把 JPEG 投递到本机 loopback `DebugSink`。这是对目标版本源码 / 静态 APK 的观察，不代表一定是它性能差的主因，但属于低风险可测的热路径清理项。

## 对 SpektraFilm 的性能判断

当前完整光谱计算确实有明显可优化空间，且主要瓶颈已由本项目基准定位，暂时不需要再凭感觉换另一套胶片模型：

- Windows 24 MP 完整光谱基准为 66.3 秒、峰值工作集约 5.84 GiB；stage profiler 中 `filming.develop` 约 29.5 秒，`scanning.scan_print` 约 20.0 秒，`filming.expose` 约 14.2 秒。见 [`docs/validation.md`](validation.md) 与 `output/spectral-components-24mp.json`。本机 A7CR 61 MP RAW 全链路 JPEG 为 164.269 秒、峰值约 14.3 GiB；它包括 RAW、渲染和编码，不应与 SpektraLab 的 GPU render 秒数直接相除。
- Android 随包使用的 `mobile_accel.py` 明确实现的是 NumPy / SciPy 兼容层，不包含 Numba / LLVM JIT；[`port-manifest.json`](../android/app/src/main/python/port-manifest.json) 也将 backend 标为 `NumPy/SciPy; no Numba/LLVM or desktop image I/O`。部分卷积和滤波会落在 SciPy 原生实现里，不能笼统说所有运算都是纯 Python，但颗粒采样、转换和大量数组中间操作仍由 CPU 数组路径承担。
- [`studio_spectral.py`](../android/app/src/main/python/studio_spectral.py) 将输入展开为 `float64` RGB，并在完整光谱阶段复制 `film_input`；上游 [`pipeline.py`](../android/app/src/main/python/spektrafilm/runtime/pipeline.py) 同样以 float64 进入流程。全帧 61 MP RGB 单个 float64 平面约 1.37 GiB，多个阶段缓冲叠加后，峰值内存和内存带宽成为实质瓶颈。
- Android 已用 [`FullResolutionPhoto.kt`](../android/app/src/main/java/com/spektra/film/FullResolutionPhoto.kt) 做有 halo 的原尺寸分块导出，并逐行送 JPEG / TIFF encoder；这是避免一次分配整张 Bitmap 的好基础。不过每个 tile 仍进入 Python/Chaquopy 光谱管线，重复分配数组和跨语言复制，会带来固定开销。`FilmEngine.kt` 还将 ARGB Bitmap 复制进 byte array，Python 返回后再建 Bitmap。
- Android 拖动参数时，当前代码调用 `renderInteractive()` 的 LUT 交互近似，停手后才调用完整光谱预览。UI 状态文案写了“交互近似 · 停下后光谱更新”。如果产品要求拖动时也只允许完整光谱，应改为在已缩小的预览源上节流运行完整光谱，而不是暗中将 LUT 当成完整结果；全尺寸导出仍继续从原片分块计算。

## 优化顺序

1. **先压低完整光谱工作集。** 延续 Android 现有 tile + halo 方案，继续把粒子采样、显影、打印 / 扫描阶段改成复用 scratch buffer 的分块处理；Windows 对大图也采用有界行带。不是只切输入和最终编码，避免每个 stage 又创建完整 float64 中间帧。
2. **把当前 profiler 热点下沉到 SIMD / C++ / 原生并行 kernel。** 优先 `filming.develop`（曲线、定向成色剂耦合、颗粒）与 `scanning.scan_print`（最终光谱转色），这是实测占时大头。先保持公式、随机种子与取样顺序一致，做每阶段误差和最终输出对照；不要用改 film profile 或换成近似 LUT 来伪装加速。
3. **缩小数据搬运与分配。** 避免 `Bitmap → byte[] → float64 RGB` 和返回时反向复制；为固定 tile 复用输入 / 输出 / 临时 buffer。以端到端的峰值 RSS / native heap / PSS 作为准入指标，而不是只看 Java heap。
4. **谨慎评估 float32。** float32 可把 RGB 工作数组带宽和体积减半，但属于数值变更。需用不同胶片、暗部、高饱和边缘与 61 MP RAW 样本比对 `DeltaE`、纹理、颗粒统计和最终 JPG/TIFF，设误差阈值后再决定；默认不牺牲数据精度。
5. **建立同一边界的端到端 benchmark。** RAW 解码、完整光谱、编码、落盘分阶段计时；记录输入哈希、输入 / 输出尺寸、CPU/GPU 型号、持续负载、热降频、峰值 PSS / native heap。预览、完整导出分别测，并在相同设备同一算法下比对。
6. **再做 GPU 后端可行性原型。** SpektraLab 的 Vulkan 证明“完整光谱放 GPU”有现实路径，但不能直接把它当作现有 SpektraFilm 引擎的即插即用优化。先选择一个当前热点阶段移植，复用同一 profile 数据和公式，在 Windows Vulkan 与 Android Vulkan 上做 bit / error 对照；评估 GPL-3.0 代码复用义务及 shader 维护成本后再决定是否扩展。

结论：引擎有实质优化空间。短期优先是端到端流式、热点阶段原生化和去掉数据复制；中期再比较 float32 与 Vulkan 原生后端。SpektraLab 最值得借鉴的是 Vulkan shader、阶段缓存 / 池管理、原生编码与分辨率选择机制；它的 GPU 模型不是本项目完整光谱数据的直接替身，默认缩图和每次预览的诊断压缩也不应照搬。
