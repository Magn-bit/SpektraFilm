# 相纸 `.cube` 导出

## 原版依据

对照最新 SpektraLab `2201f5fa4d256b0c742b46b8e31f8176a12ca6ea`：

- `desktop/src/export/ExportPage.tsx` 的导出方案菜单提供“将相纸导出为 .cube LUT”。
- `desktop/src/export/exporter.ts` → `engine/host/main.cpp::m_export_cube`；只传 `print_stock` 和保存位置，不传照片或当前调整。
- 数据直接取 `spk_print_lut_table`，`engine/host/output.cpp::cube_text` 将 native `[r,g,b,component]` 改排为 `.cube` 的红轴最快顺序。
- `engine/src/core/print_lut.{hpp,cpp}` 和 `include/spektrafilm/spk_engine.h` 说明这是预先烘焙的固定 print+scan 变换；依赖相纸及所配对负片的染料光谱，眩光等空间效果无法放入此表。

## 准确适用范围

输入是配套 LUT 负片密度轴归一化的 CMY 三通道，逐通道 `(density - low) / (high - low)`，域为 `0..1`。输出为 **Display P3，已进行 CCTF 编码**。不是普通照片的 RGB 输入，不能在普通照片上当胶片滤镜使用。

还须区分两类中间片：旧 `spk_export_di` 是归一化负片密度 tap，可与这类表配套；当前产品 `spk_render_digital_intermediate` 产生的是工作原色中的 Cineon log 编码，**不能直接套用这份表**。本功能没有恢复旧 DI tap 的主界面入口。

LUT 是资源中固定印相和扫描变换，不烘焙当前曝光、滤色、EDR、后期调色、颗粒、光晕、眩光、蒙版、几何或片边。与不同配对胶片混用的光谱误差没有在本节点量化，不承诺完整显影外观一致。

当前资源支持以下 8 种、均为 33³：

| 相纸或电影正片 | LUT 配对负片 | 上游明确配对 |
|---|---|---|
| Crystal Archive II | Fuji Pro 400H | 是 |
| Vision 2383 | Vision3 250D | 是 |
| Vision Premier 2393 | Vision3 250D | 否 |
| Ektacolor Edge | Portra 400 | 否 |
| Endura Premier | Portra 400 | 否 |
| Portra Endura | Portra 400 | 是 |
| Supra Endura | Portra 400 | 否 |
| Ultra Endura | Portra 400 | 否 |

Ilford Multigrade IV RC 没有配套表，界面禁用导出；不生成无依据的替代 LUT。这与 Ilford 完整光谱渲染是否可用是两回事。

## 实现与界面

`desktop/paper_lut.py` 读取缓存能力目录，在后台取得 native 表并立即复制 engine-owned 数据。导出 9 位有效数字，保留原始 float32 值，不裁剪输出；文件头注释携带输入域、输出空间、传递函数、配对负片与范围。按红轴最快的 `.cube` 标准排列，不修改数据含义。

印相分组增加“导出相纸 LUT…”；工具提示只在需要时说明适用输入。`Controller.paperLutInfo` 读取小目录，不启动 GPU；`exportPaperLut` 使用统一保存对话框，固定所选相纸快照。独立 QObject 接现有 `Job` 和 `export_pool`，完成回 GUI 线程更新状态与通知，不修改主 render 完成处理。避免重复任务，失败释放忙态；同目录临时写入后原子发布，不覆盖已存在文件，失败清理本任务临时文件。

## 关键节点

`scripts/verify_paper_lut.py` 一次聚合通过，耗时约 7.5 秒；证据 `output/paper-lut-review/report.json`：

- 8 个实际 native 表逐样本读回，`.cube` 红轴顺序正确，转回 float32 与 native 完全相同。
- 现有目标保留、无配套表不伪造输出、失败后无临时文件。
- 真实 Controller 入口与印相控件、中文路径、异步 Job、GUI 线程完成、重复防护和成功/失败恢复通过。
- 无配套纸材控件明确禁用，QML 错误 0；导出期间 GUI 定时器仍运行。
- 已查看 1366×768 逻辑窗口截图 `paper-lut-control-1366.png`，新增入口位于眩光后，未挤占固定底栏。

未做哈希测试、大 RAW 导出或未受影响模块回归。本说明属于对应源码交付内容，需随最终 Windows 源码包保留；源码节点不代替最终成品集成验收。
