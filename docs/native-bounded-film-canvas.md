# 原始像素密度的物理胶片画布

`spk_canvas_size` 只计算原生画布及片门几何；`spk_render_canvas` 将完整尺寸的 RGBA16 写入调用者提供的存储（可为磁盘映射）。普通照片渲染仍严格保持原图尺寸；只有显式物理片边会扩展画布，片门选框产生的真实裁切独立记录，不能偷偷降低像素密度。

## 执行与资源

源先按完整宽度的短行带完成输入解码、固定自动测光、场景宽容度/曲线、光谱上采样和胶片曝光。float32 曝光保存在 delete-on-close 临时文件，全源峰值在所有行带上归约一次；高光 boost 和 headroom 随后共用这一精确峰值。片边、日期、漏光、片门和背光在全画布坐标中生成。

每个中间光学平面使用临时磁盘映射。GPU 每次仅持有有限的行带、列带或局部源矩形；完整源输入仍需要一次 GPU 上传并保留，不宣称整个进程只有行带内存。映射的脏页与页缓存受操作系统管理，进程实际峰值随物理内存、文件系统和其他程序变化。

最终版优先让单张、无逐孔后期的整条原生图留在GPU：在实际device heap能容纳最坏五个float平面、额外暂存和安全余量时，直接使用原有`run_film`/`run_print`，避免反复落盘和重新上传。该内部准入不跳过光学或换成LUT；overscan只有在这项全图准入成功时才按自身即时输出需求分配。预算不足、显式小预算或独立逐孔后期进入下述精确磁盘执行。

高斯模糊复用原来的 Vulkan 内核与系数：

- FIR 保留先纵向后横向、真实 reflect 边界及最后一次融合累加。
- IIR 保留先横向后纵向、YvV 双浮点递归与最后一次融合累加。每次 GPU 调用包含完整的真实横行或纵列；递归不会在照片内部重置。
- 混合通道仍先 FIR 再 IIR；指数/多次反射混合按原组件顺序累加。

因此 DIR 长尾、透镜模糊、halation/scatter、颗粒染料云、微结构、glare、扫描模糊与锐化不需要截断 IIR 半径。第一版 12σ halo 已被移除，`finite_iir_context=false`，`exact_iir_sweeps=true`。完整高斯图若能通过实际 Vulkan device heap admission（留出其他程序和安全余量），在单个阶段内直接整幅计算，减少CPU/GPU传输；各阶段仍在磁盘平面处分开，避免把DIR保留的log与光学中间帧都累积在显存中。预算不足或显式指定的小预算使用精确全线遍历，每pipeline最多16项系数缓存减少行组等待，且线组独立按较轻的模糊图预算扩展。两者不改变算法和分辨率，代价仍包含临时存储及IO。

逐孔印相从同一磁盘底片重印，独立滤色/曝光/预闪及后期参数保留；暗角和随机场使用全图坐标。Cineon DI 保留自己的编码契约，不走 sRGB 编码。几何须由调用者提前准备，未实现的全底片 contrast mask 明确拒绝，不能悄悄忽略。

取消在带、GPU 节点与写入之间检查；失败输出必须丢弃，所有映射和临时文件通过 RAII 清理。报告包括真实输出尺寸、最大局部源/工作块、完整行列 pass 数、pointwise pass 数及临时 checkpoint 峰值。`region_edge` 只改变几何区域计划，`budget_bytes` 限制后续 GPU 中间块，不能改变最终分辨率或物理参数。

## 定向验证

`tests/test_native_canvas.py` 在当前 Windows Vulkan runtime 上 5 项通过（2026-11-09，自适应版3.669 秒）：横竖 135/date-only 与不同区域计划、完整光学/全局随机场、独立半格/暗角、取消/单调进度/临时清理、16MiB 请求预算下原始颗粒染料云及 IIR。与 native 整幅输出最大允许差为 2–3 RGBA16 LSB；这些小中型夹具只证明组合语义与分带边界，不证明 61MP 性能。

实际 A7CR 61MP 的唯一代表导出使用 `scripts/verify_native_canvas_full.py`，报告写入 `output/native-canvas-61mp/report.json`。脚本从真实 ARW 解码、保留原像素密度生成135物理片边并编码 TIFF16/ICC，记录尺寸、时间、CPU/GPU采样以及源大小/mtime；不执行哈希测试。性能结果需以该实际报告为准。

该次精确磁盘版成功从9564×6376 RAW产生9924×9184物理135画布，TIFF16/ICC为413,704,132字节；源大小/mtime不变。原解码3.373秒，准备/显影147.775秒，编码4.408秒，总155.724秒；进程峰7,897.67MiB，GPU全进程采样峰2,561MiB，临时checkpoint峰5,468,520,960字节。此结果揭示原小线组GPU占用和IO瓶颈，不能称性能达标。随后添加了上述整幅Gaussian admission与更宽线组，不重复解RAW/编码；同shape合成光学性能单独记录 `output/native-canvas-adaptive-profile/report.json`，不能将合成时间冒称真实成品全链时间。

最终同shape合成输入保留9512×6376 gate源、9924×9184（91,142,016像素）画布、默认Portra400/Endura、颗粒/halation/scatter/DIR及日期曝光，完整resident图的native耗时 **2.0189秒**（film1.1486、print0.1782、pack/read0.3532；其余为准入/调度），spk_open另0.809秒。完整行列pass24、Gaussian12、checkpoint0；pool实际峰4,423,445,444B、源/常量749,039,096B，GPU staging另计。准入额 **5,602,738,688B**，实际RTX3070Ti Laptop为8192MiB。最终DLL为5,649,870B、mtime_ns=1794160663640496900，报告包含相同标识；没有哈希测试。该profile跳过RAW解码和TIFF编码，**不是2秒完整出片的承诺**。

最终resident与整幅native的参数/光学节点相同；小图全幅对照在已有2–3 RGBA16 LSB范围内。新增resident后首次定向检查只有“完整line计数”遗漏FIR报告，实际像素对照已通过；补齐真实FIR launch记录后，相关完整光学与16MiB强制分带两项通过（`output/native-canvas-resident-final-verification.log`）。不重复未受影响的取消、逐孔、HDR、scene曲线和历史大RAW验收。
