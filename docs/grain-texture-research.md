# 0.4.3 颗粒结构与 LR / Capture One 参考

当前四个选项的问题是只改变同一种颗粒的面积、模糊和强度，经典、粗粝和团簇的空间结构没有真正区分。本次保留已保存的四个 ID，改为独立的密度纹理形态；没有把新的名称当作新的算法。

## 商业软件中实际确认的内容

- Capture One 本机 `P1.C1.ImageCoreWrapper.dll` 的 `ImgCore.IC_FilmGrains` 结构声明四个字段：`amount`、`density`、`granularity`、`filmType`。前三个为 float，最后一个指向 `IC_FilmTypes`。REA Evidence：`ev_e3b2cc6a7f069d3596814b31cc690ed209c806669253c6b88908b8251c0ac52c`。
- `ImgCore.IC_FilmTypes` 枚举实际包含 `filmFineGrain`、`filmSilverRich`、`filmSoft`、`filmCubicGrain`、`filmTabularGrain`、`filmHarsh` 六个名称。REA Evidence：`ev_c9cce5fe4c348bb2b0893f57d34c18123d12b9549b102f7e439969d0f49bcfb2`。这是已安装程序的静态声明证据，不能据此宣称完整恢复了这些模式的内部数学。
- 本机 C1 随附 `Styles/Film & Cine Looks/Cinema Warm.costyle` 独立保存 `FilmGrainAmount`、`FilmGrainDensity`、`FilmGrainGranularity`、`FilmGrainType`，佐证类型、数量和尺寸在实际样式格式里是不同控制量。
- 本机 LR Classic `Resources/zh_cn/TranslatedStrings.txt` 的设置映射明确分开 `GrainAmount`、`GrainSize`、`GrainRoughness`；局部颗粒说明还明确大小和粗糙度跨颗粒工具共享。LR 的粗糙度与 C1 的多种类型不是同一个界面概念。

以上没有运行或改写商业程序，也没有复制它们的 DLL、纹理资源或 shader。历史 C1 原生深度分析的 provider 超时边界仍然存在，本轮未把参数声明冒充私有颗粒算法的完整逆向结果。

## 采用的产品设计

| 保存 ID | 显示名称 | 实际结构 |
|---|---|---|
| fine | 细腻 | 高频、密集、低振幅的连续细纹理 |
| classic | 经典 | 混合两种细粒尺度的柔性随机纹理 |
| coarse | 粗粝 | 抖动位置和半径的圆形柔边颗粒云；较稀疏、重尾分布 |
| clustered | 团簇 | 连续的低频团簇，叠加团簇内部的细颗粒 |

- 在胶片密度域生成一个通道共享的随机场，再进入原本的光谱印相、相纸及扫描链路；避免独立 RGB 随机数造成的彩噪。
- 颗粒方差随负片密度和物理像素间距变化。强度通过 `grain_amount` 缩放密度偏差；粒径通过微米尺度改变边界，两者独立。
- 新的 `grain_texture=1..4` 为原创产品纹理算子；`0` 完整保留原来的 Poisson 子层颗粒支路。没有宣称新算子是 LR/C1 的逐像素复刻，也没有用 LUT 替换主光谱计算。
- 原图全画幅坐标和确定性种子决定粒子位置，区域导出不会从每个 tile 的左上角重启。相同图片调强度时不会把颗粒重新随机洗牌。
- Vulkan 单个计算 kernel 完成新纹理，避免为类型切换增加多次高斯模糊。Metal 代码同步实现，尚无 Mac 构建验证；Windows 显式 CPU 兼容路径有同结构、有界 NumPy 实现。

## 验证

运行 `native/engine/verify_grain_textures.py`，在 RTX 3070 Ti Laptop GPU 上对 9504×6336 虚拟原片中的 480×320 原像素区域、35mm 片幅、35% 颗粒、1× 粒径使用相同种子进行检查。输出为 `output/grain-refinement/metrics.json` 和 `grain-types-1to1.png`。

四型的亮度标准差分别约 .0121 / .0200 / .0336 / .0194；相邻像素相关系数约 -.101 / .061 / .589 / .656。粗粝的峭度约 3.84，经典约 2.36，证明差异包括分布尾部和空间相关性。通道差残差的标准差低于亮度残差的 6%；平均亮度变化低于 .00036。

独立区域保留 16px 扫描滤镜邻域后，同一原图坐标的渲染误差为 0；CPU 密度强度翻倍的最大误差约 6e-8。该小区域验证不是整张 61MP 导出测速，也不是 Android 真机结果。
