# Windows 功能复现清单

基准：SpektraLab 2.2.0，主源码 `2201f5fa4d256b0c742b46b8e31f8176a12ca6ea`（2026-11-08）；图库 SDK `f236e03b4c8eea622fd7360c4d6277ada48b180c`，MIT，ABI 1/schema 3。源码与官方旧版 Windows 便携包已下载到 `output/reference-spektralab-latest`。Mac 功能不等于官方 Windows 1.3.4-beta.2 已有功能。

本表记录 Windows **0.7.0** 的功能与验收边界，正式版本以 `release/manifest.json` 为准。确切候选 EXE、CLI 与 helper 已完成成品关键检查，记录在 `release/Evidence/Windows-0.7.0`；此前开发态证据按其原范围复用。当前认可字体保留。

| 功能 | 当前开发状态 | 实施与验收边界 |
| --- | --- | --- |
| 独立离线 RAW / 保留场景余量 | 已有实现和关键证据 | LibRaw 真实源、兼容 RGB16 与 Bayer headroom；不能称完整复制 C1 私有算法 |
| 81 波长胶片 / 相纸 / 黑白 / 反转扫描 | 已有实现 | 保留本项目扩展 5219 等材料、相纸兼容约束及直接扫描 |
| 原始尺寸大图、批量、失败恢复 | 已有实现 | 普通渲染具备有界 region 执行、串行编码、取消；不得以预览替代成品 |
| 前后分阶段基础 / 色阶 / 曲线 / HSL / 色轮 / 校准 | 已有实现 | 保留本项目蒙版、C1 式亮度及 RGB/luma 色阶优势 |
| 胶片曝光 / WB / 场景曲线 | 场景曲线已接并随当前工作区通过加载 | 曲线在 scene placement 后、进入胶片前；不能用成品曲线冒充 |
| 自动测光 / 配光 / scene placement | 已接 | 有界身份缓存、绝对曝光幂等、旧任务隔离；原生求解结果真正生效 |
| 宽容度图 / 拟合 / 应用 | 已接 | 真实原始与拟合分布、材料范围、超白、警告及过期状态 |
| 颗粒 / 光晕 / scatter / DIR / glare | 已接 | 依材料支持禁用不生效控制；四种颗粒与独立大小；普通控制和物理尺度区分 |
| headroom / boost 全图统计 | 新增验证通过 | `tests/test_native_optical_peaks.py`；不同 region core 与整图一致，默认值无额外扫描 |
| 相纸预闪 | 已接产品控制 | 0–0.03；是印放阶段曝光，与阴影数值提亮不同 |
| 完整光学 / minilab | Vulkan 与显式模式已接，native 小图通过 | 标定仅 Portra 400 → Portra Endura 两种输出空间；默认完整谱，不能将固定 LUT 说成全胶片新引擎 |
| 真实毫米画幅与自定义尺度 | 产品长短边 / 精确毫米已接 | 长/短边与像素裁切重映射；135/半格/XPan/645/6×6/7/8/9/12/17；不以裁切比例代替物理画幅 |
| 物理片边 | 原生与高层已接，真实源预览通过 | 原生 overscan、stock 边字、DX、格号、片门、strip/filed、底雾、漏光、carrier；不是完成图上画装饰 |
| 日期后背 | 原生与高层已接，独立孔日期通过 | EXIF 日期/数据行在底片曝光并进入颗粒和光晕；字体/画幅支持遵守真实模型 |
| 半格双图 | 已接并验证独立印放 | 18+1+18mm 线性 ProPhoto 源、各自 WB/曝光/印放/调整；原生 gate geometry，不是两张完成图拼接 |
| 全尺寸片边资源 | 61MP真实源扩展画布通过；最终91MP同shape完整光学2.019秒 | 真正heap准入使用整段GPU驻留；低显存/逐孔后期仍为精确行列执行。该时间不含RAW解码与编码；显式扩画布API与普通同尺寸输出分离 |
| 图库/显影/编辑共享浏览器 | 整合通过 | 虚拟化同源索引；保留无目录直接拖入工作流；不在主界面增加用户不需要的评级负担 |
| 图库 SDK / C1 只读镜像与复制 | Windows helper 与真实Controller变体验证通过 | Unicode、相册、变体、revision 冲突、session、防覆盖移动、C1 热 journal 与原库只读；`output/library-bridge/verification.json` |
| 看片台 | 已接并通过实际显影/摆放集成 | 毫米尺寸、自由摆放/旋转、按需显影、48 张有界代理、持久位置；不能用原片缩略图冒充冲洗结果 |
| 全窗导入 / 导出 / 设置工作流 | 全窗页面已接并通过1366/1440/1120逻辑尺寸检查 | 导入来源/递归/选择/取消、输出预览与配方、设置分组；原有直接拖入保留 |
| 分类参数剪贴板 / 同步 | 已有 GUI 与 sidecar 实现 | 默认保留裁切和蒙版，每张目标独立撤销；选择分类是可携带参数文档 |
| CLI / stdio MCP | 双入口成品与独立sidecar、同GUI通道通过 | 确切CLI实际HEIF→PNG原尺寸输出及12项MCP工具通过；同GUI显式开关/当前用户ACL/随机认证，异步导入导出任务 |
| sRGB / P3 / ProPhoto / Adobe RGB | 四空间关键色管/编码验证通过 | 真实矩阵、TRC 与 ICC，不能只改标签 |
| JPEG / HEIF / PNG / TIFF / DNG / RAW | HEIF8输出与HEIF10高位深输入通过 | HEIF8 明确质量、PNG/TIFF8/16、处理后 DNG 与原 RAW 复制区分 |
| 显示器 ICC / 软打样 | 已接并通过浮点LCMS对照 | 显示变换独立于成品；应从宽色域高精度结果变换，避免先裁为 sRGB |
| Cineon DI | 已接并通过真实Cineon TIFF16 + 两张显示LUT节点 | 密度 TIFF 和显示 LUT 配套；不可把普通 log 曲线改名 DI |
| 四语言 / 缩放 / 设置分类 | 四语言即时切换通过，设置已分类 | 831条精确文案、79动态模板；文件名与参数不变；当前字体保持 |
| 更新 / 诊断 / 内存和缓存预算 | 本地诊断/资源/上游参考更新已接 | 检查由用户触发，不上传诊断；本个人构建没有独立远程更新托管；不自动下载安装 |

上游目前禁用的 contrast mask（`FilmParams.swift` wire 恒 false）不算可用功能差距。所有新增能力需保留来源与许可证，不覆盖本项目的 RAW、大图、蒙版、几何和扩展材料。

确切0.7 EXE已通过完整谱/编辑/历史/TIFF16及全窗任务页、图库helper、HEIF/Adobe RGB、真Cineon DI、同GUI开关；CLI已通过独立会话原尺寸输出和stdio MCP。仅在关键节点检查，复用未受影响的有效证据；不做哈希测试，不重复历史普通61MP/150MP整链测速。最终9100万像素profile与首次真实RAW出片使用不同执行策略，报告明确分开。

2026-11-09整合证据：`output/parity-workspace/integrated-verification.json`：真实同路径变体设置/历史与SDK记录隔离、导入入口返回、看片台无model reset、全窗操作页、Cineon原尺寸16位/无RGB ICC、物理画布caller memmap。`output/localization/verification.json`：四语言实际运行切换；`widget-font-verification.json`：对话框字体诊断已修，0消息。

Windows 显示色管为SDR ICC，不冒称Apple的Metal/EDR平台特性；上游禁用的contrast-mask不计可用能力。物理片边最终输出扩展画布、取景按真实片门适配；这与普通照片导出不缩尺寸的契约分开。
