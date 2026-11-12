# Windows 完整细节与三类磁盘缓存

## 参考证据与取舍

SpektraLab 2.2.0 `2201f5fa4d256b0c742b46b8e31f8176a12ca6ea`：

- `Services/WorkingCopies.swift`：源的可重建工作副本/RAW代理、使用中pin、LRU与原子到达；唯一原片不是可清理对象。
- `Services/AppSettings.swift:48`：工作/预览/完整渲染默认预算分别5/10/8 GiB。
- `Engine/FullRender.swift`：完整渲染256像素tile与半尺寸层，工作空间16位结果，跨交付容器复用。
- `Engine/FullDetail.swift`：只读屏幕可见范围、编辑后撤下过期细节、一个完整任务被多个视口请求复用。

本项目使用lossless NumPy float32/uint16磁盘映射并按行/列裁出视口，避免重新量化成16位。缓存保存完整settings后的最终图（包含geometry），不是上游的pre-Layer2检查点。仅显式放大/导出触发完整渲染，不预先全解码整批照片。

当前引擎直接sRGB和ProPhoto链路使用不同目标CAM16压缩。为了旧输出保真，输出空间/DI域是缓存身份的一部分；同空间的JPEG、PNG、TIFF、HEIF、位深、品质和尺寸配方共享原像素float32结果。不同目标色域依照原有原生链各建一份，并共享工作副本。没有以ProPhoto矩阵转换/clip冒充原链逐像素等价。

## 缓存与生命周期

- working：完整源的精确解码像素与原色域/线性/基准曝光信息；默认5GiB。
- preview：显式边长的高精度解码代理，原尺寸与采样边长不同身份；默认10GiB。
- full：指定最终颜色域的全分辨率float32处理结果；默认8GiB。
- identity：规范源路径、源size/mtime_ns/ctime_ns、完整settings、计算模式、输出域、算法版本。文件名散列只编码身份，不做原片内容哈希或哈希验收。
- 每类独立LRU，使用中映射/写入pin，临时文件无manifest不能读。清理只删除本缓存根目录中生成的平面文件对，不递归删除、不接触原片/导出/导入保留物。
- 预算0或单项超过预算时不持久保留；近满磁盘保留64MiB余量，缓存失败不能破坏正常处理。
- 全尺寸图不进QImage；界面只保留上限约4MP的视口patch。连续平移只保留最新ask，同settings完整任务继续，过期patch不发布。编辑使旧细节立即失效，导出与退出会收束任务。

## 状态

- 实现：`desktop/disk_cache.py`、`desktop/full_detail.py`。
- 已接：`Controller._source`精确代理/工作副本；`setActualSize`独立detail；完整输出在resize/encode之前复用。
- UI设置/视口覆盖由主线程接入；`rect`与`request`的坐标为含裁切/几何后的整幅图归一化范围，纹理尺寸为物理屏幕像素。`request(x,y,w,h,pixelWidth,pixelHeight,comparing=false)`兼容六参数；对比时额外发布`originalSource`，使用同一几何/光学准备的自然原片。
- 已通过6项核心缓存/实际Vulkan同空间输出验收（0.430s），覆盖原尺寸131×97不变、float32逐像素一致、JPEG/TIFF/尺寸配方复用一次渲染、参数变更失效、取消、独立预算/pin/LRU/清理安全、代理与完整源隔离。
- 新增异步生命周期与真实1:1区域两项关键检查通过（0.175s）：平移不取消当前完整生产者、只发布最新视口、原图对比、工作线程暂停无Qt计时器跨线程警告、导出结束自动恢复、同路径原片stat变更及参数变更隔离。默认用户目录Controller启动/关闭通过；修复Windows包目录首次创建后路径重定向。
- 收尾两项定向检查通过（0.232s）：生产中收到清理请求会保留deferred-clear标记，直到返回的只读映射释放后删除；Controller测光结果应用前再次核实源stat，同路径原片改写也不会应用旧建议。
- 没有重复历史61MP导出、HDR性能或基础CLI测试。尚需主线程完成实际QML覆盖/缓存设置界面的聚合视觉检查。
- 跨进程缓存写入锁未实现；同进程请求会合并，不能把该实现描述为多进程缓存仲裁。源身份使用文件stat，不读取原片内容做哈希。
