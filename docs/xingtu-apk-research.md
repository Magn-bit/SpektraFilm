# 醒图 APK 静态研究记录

日期：2026-11-08  
目标：`D:/Data/xwechat_files/wxid_37xfbg94l8p322_5a8c/msg/file/2026-11/base.apk(1).1`  
副本：`output/rea/xingtu-reference.apk`  
SHA-256：`84bb5e6851eaf2a3c8743187b9eaceaf8f1bf7be32e1ede1e44dbe2a18b6d2b5`

## 已观察到的包结构

REA 的 APK 压缩包库存完整覆盖 90,512 个条目：

- 37 个 DEX 文件。
- 157 个 arm64-v8a 原生库。
- 3,672 个 `assets` 条目和 28,067 个 `res` 条目。
- 原生库中出现 `liblens.so`、`libpainter.so`、`libretouch_business.so`、`libretouch_sdk.so`、`libnative-filters.so`、`libskity.so`、`libimagepipeline.so` 等。
- 资源中出现 `xt_business_jigsaw_ic_frame_*`、`xt_home_jigsaw`、`xt_ic_batch_edit`、`xt_ic_business_edit_free`、`xt_ic_business_edit_mirror`、`xt_ic_business_edit_left/right`、`xt_ic_business_edit_grain`、`xt_ic_business_edit_color_tone`、`xt_ic_business_edit_curve` 等名称。
- `assets` 中出现 `color_curve.zip`、`black_white_level.zip`、`detail_level.zip`、`localMask.zip`、`filter/00origin_pic.zip`、`custom_layout.json`、`drag_layout.json`、`local_beauty_all.json` 及多种画笔、橡皮、贴纸和人像资源。

## 对 SpektraFilm 可采用的内容

只吸收工作流和交互组织，不复制其私有算法、模型、原生库或美术资源：

1. 拼图入口应从主工作区进入独立画布，画幅选择用可见图标表达 1:1、3:4、4:3、3:2、9:16、16:9；每个格子可以独立拖动取景和缩放。
2. 批量编辑应是显式的“选择照片 → 选择编辑类别 → 应用”，与单张历史隔离；默认不复制构图和蒙版，避免破坏不同照片的取景。
3. 裁切工具应在原照片位置直接出现裁切框，支持自由、预置比例、旋转、水平/垂直镜像；输出尺寸只由用户明确裁切或输出长边决定。
4. 色阶、曲线、颗粒和色彩调整应作为同一编辑任务下的清晰分组，保持照片预览和参数同时可见。
5. 排版与装饰应使用少量有职责的原创样式：留白、片边、日期/相机信息、接触印样和网格；不把贴纸/人像美化功能带入胶片暗房主流程。

## 未确认与限制

- 该 APK 过大，JADX 在 REA 默认 1 GiB Java heap 上加载失败；因此没有把类、方法或算法语义写成已确认事实。
- 原生导出表可观察到模块边界，但导出符号不等于运行时调用链，也不能证明 RAW 解码、滤镜或拼图算法的具体实现。
- 资源文件名只证明资源存在，不证明某个功能在当前版本可见、默认开启或适合直接移植。
- 研究结论只用于 SpektraFilm 的独立离线实现和 UI/UX 取舍；不拷贝第三方 APK 中的代码、模型、素材或私有算法。

