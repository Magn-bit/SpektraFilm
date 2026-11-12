# 本机镜头配置与导入处理

日期：2026-11-05。实现位于 desktop/lens.py，回归位于 tests/test_lens.py。

## 数据来源与使用范围

本机已发现 C:/ProgramData/Adobe/CameraRaw/LensProfiles，共 3602 个 .lcp。
这些是用户已安装软件留下的可读 XML 配置。应用仅在当前机器只读读取，
不修改 Lightroom、Camera Raw、Capture One，不复制、打包或重新发布 Adobe 配置。
既然已有可读校准，不需要反编译这些程序。没有逆向其二进制代码或提取私有数据库。

可选路径：SPEKTRAFILM_LCP_PATH（多个目录使用平台路径分隔符，Windows 为分号）。
未配置时检查 ProgramData 及 AppData 的 Adobe/CameraRaw/LensProfiles。
不带 LCP 的机器仍能使用独立的保守去紫边，几何保持原样。
新增/移除配置后重启应用刷新目录与身份索引。

元数据首先使用 Pillow EXIF；信息不足时调用本机已有 exiftool。
本机验证可执行文件 D:/Tool/reaConverterPro/App/reaConverter/utl/exiftool.exe，版本 11.91；
另一个已知候选 D:/Tool/TimelapseToolbox/resources/extraResources/exiftool.exe。
可用 SPEKTRAFILM_EXIFTOOL 明确指定工具，也支持 PATH 中的 exiftool。
外部工具没有被复制或打包。调用不经过 shell，超时 8 秒、Windows 不弹控制台。
只请求 Make、Model、LensModel/Lens、焦距、35mm 等效焦距、光圈、对焦距离和方向，
不请求 GPS，也不把整份 EXIF 写入日志或导出记录。

## 集成接口

inspect_photo(path: str) -> dict

prepare_photo(image: PIL.Image.Image, source_path: str, *, correction=True, defringe=True)
    -> tuple[PIL.Image.Image, dict]

输入应为 read_photo 已按 EXIF 方向摆正的 RGB 8bit 图像。
模块先按 EXIF 2–8 的逆变换回到传感器坐标进行校准，再恢复显示方向。
方向 2/4/5/7 的镜像同样处理；不能对尚未摆正的原始像素直接调用该接口。
输出尺寸保持不变，必要时通过自动裁切缩放收紧视场。

适合后台导入解码后调用一次，并按源文件/预览尺寸/两个开关缓存结果；
滑块调色重复使用已准备的图像。全尺寸 JPG/TIFF 导出应在全尺寸解码后再调用一次。
RAW 原片另存必须继续逐字节复制原文件，不经过此模块，也不能声称包含显影效果。
图像及元数据源文件均不会被本模块修改。

状态为可 JSON 序列化字典：

| 字段 | 含义 |
| --- | --- |
| matched、profile、profile_path、reason | 是否找到唯一配置、配置名称/位置、未应用原因 |
| make、model、lens | 识别的相机与镜头，不猜测缺失镜头 |
| focal_length、focal_35mm、aperture、focus_distance、orientation、raw、metadata_source | 处理所需元数据 |
| distortion | 本次是否实际进行了透视镜头重映射；matched 不等于已处理 |
| chromatic_aberration | 是否具备完整 R/G/B 校准并实际应用通道对齐 |
| defringe、defringe_pixels | 是否开启保守去紫边及检测到的处理像素数；开启不保证检测到紫边 |
| crop_scale、focal_samples | 自动裁切倍率及实际使用的焦距样本 |
| warnings、summary | 失败回退说明与简短中文状态 |

reason 典型值：metadata_missing、profiles_unavailable、unmatched、ambiguous_profile、
focal_length_missing、focal_outside_calibration、unsafe_or_excessive_geometry、disabled。

## 匹配与实现

- 相机厂商、镜头名称和 RAW/JPEG 类型必须精确归一化匹配；只去掉大小写与标点差异，
  不通过相似名称猜测光学系数。指定相机型号的配置必须匹配该型号。
- 相机专用配置优先于通用配置；仍有多个同等候选时返回歧义，不任意选择。
- 只读取小段 XML 身份头建立索引，遇到第一个 PerspectiveModel 即停止；
  只有真实候选才完整解析系数，避免每张图完整解析 3602 份校准。
- 普通透视 PerspectiveModel Version 1/2：三项径向系数及两项切向系数。
  同时支持 XML 属性、元素文本以及嵌套 rdf:Description。
- 焦距在采样之间按对数焦距线性插值，焦点样本优先选择最接近已知对焦距离的记录，
  没有距离时选低残差记录。没有有效焦距或超出标定范围时不外推；端点保留 2% 元数据舍入容差。
  不实现完整的多维光圈/对焦距离插值。
- 归一化焦距以图像最长边为基准，主点分别按宽高归一化。
  缺少显式 FocalLengthX/Y 时使用 35mm 等效焦距或实焦距 × SensorFormatFactor 推导。
- 主几何使用径向/切向多项式，ScaleFactor 不作为第二次主几何缩放；
  它用于红/绿与蓝/绿的相对通道模型。这与所核验的 RawTherapee 普通透视映射约定一致。
- 自动裁切检查各通道 41×41 采样网格和映射单调性，通过二分寻找无越界的最小倍率。
  超过 1.8 倍仍不安全时放弃校准并回退原图；不是对任意畸变的数学完备证明。
- 通道对齐需要完整 ChromaticRedGreenModel、ChromaticGreenModel、ChromaticBlueGreenModel。
  缺一项即跳过校准式色差处理。基础几何与通道偏移合并在一次分块双线性采样中。
- 不带配置的去紫边仅在高对比、近中性邻域、狭窄紫色带同时成立时降低色度。
  保留亮度并限制幅度；没有对整张图片的紫色统一去色。真正的细紫色物体仍可能被误判，
  应保留独立开关，不能描述为自动辨别所有真实物体与光学紫边。
- NumPy/SciPy 计算按 96/128 行分块，减少 24MP 浮点临时数组峰值。
  没有新增 Python 大型依赖，没有使用 OpenCV、lensfunpy 或逆向得到的二进制组件。

数学约定核验自 RawTherapee 官方源码：
https://github.com/Beep6581/RawTherapee/blob/dev/rtengine/lcp.cc
具体函数 LCPModelCommon::prepareParams、LCPProfile::calcParams、
LCPMapper::correctDistortion、LCPMapper::correctCA。实现和测试是本项目代码；
本说明不意味着与 Adobe 或 RawTherapee 输出逐像素一致。

## 本机验证

完整解析调查 3602 份本机 LCP，耗时 15.869 秒，仅用于调查，不是导入时的实现：
3157 份可以解析，2772 份含有效焦距样本，791 份具备完整三色模型。
63 份传感器倍率无效，382 份没有当前支持的透视模型。
这些是结构性调查数量，不是 2772 款镜头的成像质量认证。

普通 Sony FE 24–70mm F2.8 GM II RAW 配置完成解析与实际映射烟测。
测试所用该份配置没有完整三色模型，因此不能报告其校准式色差矫正已启用。
独立保守去紫边仍可用。

本机单次测量，缓存前后分开报告；不是跨设备性能承诺：

| 场景 | 实测 |
| --- | --- |
| 首次扫描并建立 3602 份身份头索引、匹配 Sony GM II | 1290.10 ms |
| 完全相同的已缓存镜头匹配 | 0.0015 ms |
| 索引已热，同镜头另一机型首次匹配 | 0.1319 ms |
| 索引已热，不存在镜头首次匹配 | 0.0026 ms |
| 首次通过现有 exiftool 提取无 EXIF 小 JPG | 322.49 ms |
| 相同文件元数据缓存命中，含路径/stat 开销 | 0.9008 ms |
| Pillow EXIF 提取 + 已热配置匹配 | 1.027 ms |
| 1440×960 普通几何 / 去紫边 | 155 / 161 ms |
| 6000×4000 普通几何 / 去紫边 | 3050 / 2957 ms |

性能输入是中性合成校准图；完整解码、复杂场景、色差模型及 UI/显影不计入上述处理时间。
EXIF 性能使用小 JPG 和写有 EXIF 的 JPEG 字节测试夹具；后者使用 .arw 后缀仅测试输入类型匹配，
不是相机 RAW 解码性能或真实 RAW 元数据覆盖验证。没有用用户原片进行破坏性测试。

20 项回归覆盖：精确匹配、RAW/JPEG 隔离、相机限制、歧义、坏 XML/非有限系数、
无元数据、关闭处理、恒等逐像素、无黑边裁切、EXIF 全部旋转镜像、
已知弯曲校准线恢复为直线、完整/缺失色差模型、对数焦距插值、越界焦距拒绝、
细紫边削弱、大片紫色保护、嵌套 RDF 和本机 Sony 配置。
运行：.venv/Scripts/python.exe -X utf8 -m unittest discover -s tests -p test_lens.py -v

尚未支持：鱼眼、相机内置嵌入式畸变参数、光学暗角补偿、复杂已裁剪 JPEG 的传感器裁切恢复、
自动识别第三方软件已做过的镜头校正、Capture One 私有数据库、全部 LCP 方言。
几何校准不是透视扶正、水平矫正或任意自由变换。Android 端没有接入本机 Adobe LCP。
没有与 LR/Capture One 的实拍标定或逐像素对照，因此不声称效果等价。
