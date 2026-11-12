# 完整胶片显影 CPU 热点

2026-11-07，在当前 Windows 开发机以用户真实 Sony α7CR RAW `M:/2026/2026-06 #北京/DSC06823.ARW` 取最长边 2048 的样片。原始朝向后尺寸 6376×9564，样片 1365×2048，SHA-256 为 `c0d80fc67e79e84ee5c4d6ba71c11c8407af13356f47ac2fec53176b73cae56e`。只解码读取，没有修改原片。

采用完整显影参数而不是 `preview_mode`，并保留原片物理像素间距 3.6596 µm，使颗粒粒子大小、DIR 空间半径走原尺寸导出的分支。计时从已完成曝光的 `log_e_film` 到 `cmy_film`，不含 RAW 解码、曝光、相纸、扫描、编码和 UI；三次测量。详细结果见 [profile-develop-components.json](../output/profile-develop-components.json)，复现脚本是 `scripts/profile_develop_components.py`。

| 组件 | 三次中位耗时 | 范围 |
| --- | ---: | --- |
| `filming.develop` 总计 | 3.038 s | 完整底片显影 |
| 初始密度曲线插值 | 0.020 s | 一次 RGB 曲线 |
| DIR 总计 | 0.689 s | 含空间、矩阵及第二次曲线 |
| DIR 指数尾滤波 | 0.461 s | 三个 Gaussian 近似，默认权重 0.06 |
| DIR Gaussian | 0.135 s | 单次 RGB 滤波 |
| 颗粒总计 | 2.319 s | 九层转换、采样、云与最终滤波 |
| SciPy Poisson 采样 | 1.214 s | 九次采样 |
| 颗粒层曲线 `np.interp` | 0.420 s | 九次插值 |
| 粒子函数其余自身工作 | 约 0.498 s | 概率、饱和度与数组计算，扣除已单列子调用 |
| 颗粒 Gaussian 总计 | 0.081 s | 九层云滤波及一次 RGB 最终滤波 |
| 微结构 | 约 8 µs | 此物理间距未满足 sigma > 0.05，未采样 |

表中父子项重叠，不能直接相加。JSON 同时记录每项 inclusive 与 exclusive 时间及调用次数。该输入的显影大头是颗粒，不是已经有 Numba 的三通道曲线插值；单独把密度曲线上 GPU 无法直接解决它。缩小样片不应按像素倍数推算整幅导出承诺。

已实现两项保持公式的短路：

1. DIR 混合权重为 0 时不计算指数尾，权重为 1 时不计算 Gaussian。非有限诊断输入继续执行旧表达式，以保持 NaN/Inf 传播。默认 Portra 权重为 0.06，因此这项不能算入默认速度收益。旧表达式零权重实验为 0.680 s，对照省略尾滤波为 0.239 s，输出逐值一致；此实验在短路实现前完成，实际生产短路另增加有限输入检查，不能把该原型时间当最终成品时间。
2. 小 sigma 的有限长度 FIR 当 `int(truncate*sigma+0.5)==0` 时已恰好只有权重 1；直接返回独立像素副本，省掉两个全帧 pass 及并行调度。本例九个粒子云里五个属于此分支。独立实验输出逐值一致，但完整显影采样抖动明显，不能据此保证 10% 成品提升。

`tests/test_exact_filter_shortcuts.py` 五项测试覆盖随机、1×1、非连续输入、radius 临界值、权重 0/1 及紧邻边界、正片/负片、曝光 shift、非有限输入和输出所有权；全部通过，日志为 `output/exact-filter-shortcuts-tests.log`。

后续更值得测量的方向是保留 NumPy 同一 RandomState 和分布，比较 `scipy.stats.poisson.rvs(rate)` 与更薄的 `np.random.poisson(rate)` 入口，检查是否能去掉重复 broadcast/合法性数组开销；以及九层 `np.interp` 的查找和转换合并。这两项尚未实现或测量，不能列为已完成收益。微结构在本次根本未执行，优化它不会改善这张照片。
