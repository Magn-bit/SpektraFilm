# Android RAW 亮度修复与验证（2026-11-07）

修复了 RAW 显影偏暗的两个具体原因，使用 LibRaw 自身的解码和输出规则，没有引入 C1／Adobe 私有算法。

`RawDecoder.cpp` 原来设为 `highlight=5`（ReconstructDefault）。LibRaw 0.22.3 的 `src/postprocessing/mem_image.cpp:201` 只有在 `!((highlight & ~2) || no_auto_bright)` 时才计算直方图自动提亮；因此即使 `no_auto_bright=0`，重建模式也会跳过该分支。现改为 `highlight=2`（Blend），保留相机白平衡、sRGB、16-bit、AHD 与 0.01 自动提亮分位。

另一个独立问题是逐行写出前的 `RowRaw::prepareOutputCurve()` 把 gamma white 固定为 65536。只修改高光模式仍不能修复此处。现在直接遵循 `LibRaw::copy_mem_image` 的直方图、未旋转宽高、Fuji 计数修正、各通道 `t_white` 和 `bright` 规则；直方图不存在时也与官方实现相同，保留已有曲线。生产路径继续逐行写 RGB16LE，不创建 `dcraw_make_mem_image` 的整图 RGB 副本，不缩小或裁切原图。

`RawPhotoCache.kt` 缓存命名空间更新为 `raw-develop-v2-blend-auto-white`，旧版本像素不会复用。源 RAW 不写入；缓存仍为私有临时文件。

## 实际验证

在 WSL 主机编译和运行了 Android 使用的同源 C++ 核心。测试 oracle 是相同参数的官方 LibRaw `dcraw_make_mem_image`；整图内存副本只在验证程序中使用。以下均为输出逐字节一致：

- CFA DNG 的 8 种方向，完整 96×64 或 64×96；另含半尺寸路径。
- 新增 1/16 曝光合成 DNG，完整和半尺寸路径。旧重建模式归一化 RGB 均值 0.128553，修复后 0.503557，验证阈值可捕获任一旧错误。
- Pixel 4 XL 真 DNG：3700×2774，61,582,800 字节，均值 0.498762。
- 用户授权读取的 Sony A7CR `DSC06823.ARW`：6376×9564，365,880,384 字节，均值 0.532608。

取消清理、保留旧完整目标文件的原子取消、不支持文件、截断 RAW 的回归也通过。测试程序总耗时 19.90 秒、峰值 RSS 1,494,472 KiB，包含两次全尺寸 RAW 显影、全图 oracle 及其他用例；这是主机测试，不能当作手机显影速度或手机峰值内存。未执行 Gradle 构建或真机测试，由发布流程统一完成。

原片 SHA256 与验证前记录一致：`c0d80fc67e79e84ee5c4d6ba71c11c8407af13356f47ac2fec53176b73cae56e`。全尺寸 RGB16LE 输出 SHA256：`81b3ce00b787fe84564b414af0f0e8c0cfd6b79c8d980753079a344462db1c7c`。

日志：`output/native-raw-brightness-fixed.log`、`output/native-raw-brightness-fixed-a7cr.log`。用例源码：`android/app/src/main/cpp/tests/RawDecoderValidation.cpp`。

```powershell
wsl.exe -d Ubuntu-24.04 -- cmake --build /var/tmp/spektra-raw-host --target spektra_raw_validation spektra_raw_probe --parallel 2
wsl.exe -d Ubuntu-24.04 -- /var/tmp/spektra-raw-host/spektra_raw_validation /mnt/d/Project/SpektraFilm/output/native-raw-brightness-fixed /mnt/d/Project/SpektraFilm/output/offline-engine/pixel4xl-raw-pixls-3502.dng
wsl.exe -d Ubuntu-24.04 -- /var/tmp/spektra-raw-host/spektra_raw_validation /mnt/d/Project/SpektraFilm/output/native-raw-brightness-fixed-a7cr "/mnt/m/2026/2026-06 #北京/DSC06823.ARW"
```

自动提亮会随照片直方图改变输出亮度；它不保证与相机 JPEG 或商业软件的色调、色彩配置和高光效果完全相同。本轮验证的是正确应用约定参数及完整像素输出。

## Windows 实际解码回归

新增 `tests/test_raw_brightness.py`，在系统临时目录独立生成真 CFA DNG，不依赖 `output/` 样片或 mock。实际经过 `desktop.imaging.read_photo`，验证未旋转／旋转照片的完整尺寸、预览尺寸及 `source_size`；完整和半尺寸预览均与单独调用官方 rawpy Blend 的像素完全一致，同时比较旧重建模式及明确关闭自动提亮的输出。全尺寸 96×64／64×96，预览 32×21／21×32，原文件哈希不变。

Windows rawpy 0.26.1 / LibRaw 0.22.0 下，2 项测试（各含 2 种方向）通过，运行 0.086 秒。执行：`.venv/Scripts/python.exe -m unittest discover -s tests -p test_raw_brightness.py -v`。该测试不启动完整胶片显影，也不是大 RAW 性能测量。
