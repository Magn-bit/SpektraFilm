# Windows 高位深图像流程

2026-11-07。本轮将相机 RAW 和 RGB16 源像素从显示图分离，保留浮点处理直到最终编码。

## 实现

- `read_photo` 继续返回兼容 Qt/Pillow 的 RGB 显示图。RAW 由 LibRaw 以 RGB16 处理，相机白平衡、sRGB传递、Blend和 histogram自动亮度保持原策略；高精度源像素附在图像上，显示图只取高字节。复制与代理缩放也保留独立精度数据。
- `render_pixels` 直接消费原始RGB16/float，完整光谱不再先转为RGB8。`render` 只在呈现时生成8位显示图；导出保留内部浮点结果。
- TIFF 使用16位RGB、sRGB ICC与Deflate level1无损压缩，按最多128行strip写入，避免再分配一整帧uint16编码副本。最多4个有序future，按48MiB编码窗口动态约束strip行数，不预提交全帧。预压缩bytes符合tifffile strip迭代器约定。JPEG最终编码时才量化为RGB8。JPG、TIFF有效画面像素尺寸均不变。
- 代理缩放逐通道转换，矩阵ICC逐128行转换，避免先将150MP RGB16全帧扩成1.8GB float临时数据。100%强度不建立无用的原图混合底；后处理复用独立float渲染结果，源float仍保持不可变。TIFF直接编码float结果，不先构造RGB8显示图；JPEG显示量化也按128行执行。
- 普通RGB16图片通过OpenImageIO读取；矩阵/TRC型RGB ICC在浮点进行PCS变换，覆盖常见sRGB、Adobe RGB和ProPhoto矩阵曲线表示。未实现的LUT/device-link型高位深ICC会明确报错，不经8位Pillow色管后冒充高精度。
- 原生完整光谱桥接接口为`desktop.native_spectral.render_spectral(encoded_srgb_float32,settings,preview=False,source_token=...)`。源token包含文件版本、代理尺寸和源白平衡参数，印相/胶片改变不改变源标识。没有原生后端时仍有CPU完整光谱兼容参考，不静默改为LUT。
- 新暗房参数进入设置验证、产品白名单、批量快照和所有预览缓存签名：相纸auto、片幅mm、眩光%、印相曝光EV、Y/M滤色shift。片幅传入`camera.film_format_mm`，CPU兼容路径也实际设置印相与眩光。
- Y/M滑块±100统一映射±60 CC；CPU直接用0.6倍CC，原生用0.01倍归一值再乘filter_shift_scale60。Windows与Android保留科学桥以非零印相/片幅/眩光设置核对，而不只验证全零默认。

## 验证

`tests/test_high_precision_pipeline.py`四项覆盖：真实CFA DNG的RGB16与LibRaw官方输出相同，并在原尺寸TIFF逐样本回读相同；16位渐变保留超过256阶；PIL复制/缩放精度来源正确；矩阵ICC浮点同配置变换误差小于2e-6；重复调整不改变float源像素。既有RAW偏暗回归两项仍通过。相关imaging 27项与HSL 9项已运行通过，旧TIFF断言改为读取16位像素核对，未用RGB8读取掩盖精度。

原生集成结果在`output/native-precision-acceptance.json`：合成CFA DNG → LibRaw RGB16 → 原生完整光谱float输入 → TIFF16，同为64×96，TIFF逐样本等于渲染结果的16位量化，含9294个不同数值，原片SHA不变。改变印相曝光复用底片（`negative_cached=true`）；小图热印相4.95ms、热整链导出17.85ms仅是接口验收，不代表大图性能；冷启动含引擎初始化1.79s。61MP/150MP真实文件的耗时与内存由统一发布验收单独记录，避免重复跑整套测试。

真实61MP Sony A7CR（9564×6376）由相同`verify_full_export.py`验收：初版无损TIFF整链20.695s，level1有界并发编码后13.027s（缩短37.1%），其中RAW解码2.189s、峰值工作集2869MiB。完整尺寸、TIFF16、ICC、原片SHA均通过；报告`output/full-export-0.4.0-fast61/report.json`。独立6.29MP编码helper对照从1.223s降到0.334s，不用于宣称整链时间。高像素峰值仍包含完整源和渲染帧，不宣称48MiB是整进程内存。

统一产品CPU回归共131项，首次有1项测试的8个跨平台子场景失败，原因为旧Android兼容桥默认glare仍开启；已修复并对同一项非零darkroom参数的8个场景定向复验通过。其余130项无需重跑。新增controller原生模式3项通过，覆盖640px交互与精细结果同模型、最新值/终值/撤销重做、迟到交互帧不得覆盖终值或撤销、暗房参数侧车持久化。未跑历史C1研究或撤下编辑器套件。日志`output/cpu-product-regression.log`保留首次失败证据，最终修复证据为`output/cpu-android-parity-regression.log`。

首次真实大图发现tifffile把ndarray iterator识别为整帧，已有不足128行夹具未覆盖多strip；改预压缩bytes后，精度梯度夹具扩为263行（三strip且末段7行）逐样本验证通过。编码优化后同一关键多strip定向检查通过，未重复整套RAW测试。

这不代表RAW headroom或完整C1显影算法已还原。当前LibRaw策略仍输出有界sRGB，不能保留矩阵变换后的所有负值/超白高光。高位深编码与完整原生光谱性能分别验收。

## 无裁切RAW高光余量的确切缺口

上游`raw_decoder.cpp`/`raw_headroom.cpp`在LibRaw子类的`convert_to_rgb_loop`截取实际白平衡`pre_mul`和相机到ProPhoto输出矩阵，在uint16裁切与输出曲线前生成线性float并恢复曝光尺度。rawpy公共API未提供这两个实际处理后的数据；`rgb_xyz_matrix`并非输出矩阵，不可直接套用。仅设置线性gamma/LinearResponse仍有LibRaw输出裁切，不能冒充该功能。本轮原生编译未引入LibRaw，因此默认自然显影RGB16保持不变。

后续应独立加入同版本LibRaw原生float解码ABI、支持机型/CFA检查、线性ProPhoto到工作空间且保留负值/超白的合同，再接源缓存key及显式模式。需要RAW对照样片和超白通道数值验收，不能以提高位深或曝光滑块代替。
