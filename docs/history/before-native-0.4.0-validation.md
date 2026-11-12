# SpektraFilm 0.3.3 验证记录

本轮仅回退外观：Windows和Android恢复此前冷白、深灰、灰绿配色，桌面正文恢复14px；背景、菜单、滑杆、焦点、阴影、文件弹窗及Android系统主题同步。布局、字体家族、23款胶片、完整光谱引擎、RAW与原尺寸导出逻辑保持本轮之前的实现。

本轮构建与相关UI回归日志：output/windows-build-0.3.3-style-rollback.log、output/android-build-0.3.3-style-rollback.log、output/python-0.3.3-style-rollback.log。最终成品证据目录为 output/release-0.3.3-style-rollback，实际发布状态以 release/manifest.json 为准。Android没有连接设备，不能将构建/资源校验称为真机视觉验收。

本轮已发布0.3.3：16项相关UI/发布回归通过；实际Windows EXE的JPG/TIFF、旧状态中性化、五个界面状态检查通过；Android主/测试APK编译及资源、签名核对通过，lint零错误/38警告。发布文件4848个SHA256全部匹配。Android真机验收仍未进行。

下面是0.3.2功能基线、数据来源及测量，不能当作本轮重新测量结果。

---

# SpektraFilm 0.3.2 验证记录

开发与发布环境：Windows。实际发布版本与哈希以 release/manifest.json 和 release/SHA256SUMS.txt 为准。本轮最终成品验收记录在 output/release-0.3.2-claude-final；两端0.3.2已发布，4848个发布文件SHA256全部匹配。Windows实际EXE完成Portra JPG与Vista100 TIFF原尺寸输出，纯胶片策略与五个界面状态检查通过。

## 产品范围与界面

产品入口固定为完整胶片光谱显影：23款胶片、曝光、颗粒及大小/类型、光晕、暗角、强度。旧记录中的基础修图、曲线、色轮、HSL、蒙版、几何、外部风格与关闭胶片状态被中性化，预览、批量和导出共用同一白名单。历史工具模块保留供研究，不能被产品旧接口重新启用。

保留字体与工作台布局，更新 Claude 暖白/陶土配色；颗粒横排按钮改成紧凑菜单。参数通过间距和分隔建立层级，未照搬上游折叠面板；胶片档案分类栏采用内容宽度与换行，防止挤出右内边距。主界面不显示推导标签，来源元数据和说明文档完整保留。

新增三款胶片为 Velvia 50、Vista 100、Natura 1600。数值来源、模型拟合、固定版本与许可证详见 film-profile-expansion.md；并非实拍逐像素匹配证明。交互LUT由同一模型生成，最终输出仍走完整光谱，不把LUT等同光谱计算。

Python/Qt 最终全量运行209项，其中202项通过、7项归档旧编辑UI跳过，无失败。结果见 output/python-regression-0.3.2-final.log，覆盖纯胶片迁移、独立逐张状态、异步预览、菜单鼠标/键盘、撤销/重做及滚动保持、新profile实际Simulator与跨端参数一致性。归档编辑UI测试有明确skip，底层数学回归仍执行。

## RAW 与尺寸

Windows 使用 rawpy/LibRaw，Android 使用 LibRaw 0.22.3 JNI。Android 解码结果必须与RAW元数据的完整朝向后尺寸逐项一致，并校验 width×height×6 字节；拒绝缩略图、半尺寸、隐式默认裁切及错误朝向。完整RGB16LE私有缓存供预览和原尺寸区域导出，缓存有租约、磁盘/内存准入、取消与回收。

RAW 原片另存与输入字节相同，不包含显影效果。JPG质量100/4:4:4或分享质量85，两者均保持像素尺寸；TIFF为RGB8/sRGB/LZW，无16-bit输出。内部RGB16缓存不等于全链路16-bit。内存不足明确失败，不静默缩小输出。

同源Android native核心在WSL主机完成8方向、半尺寸、真实DNG与LibRaw输出逐字节对照，以及取消、原子发布、损坏/不支持检查：output/native-raw-validation/validation.log。Pixel4XL DNG实际完整尺寸为3700×2774；A7CR为9564×6376、365880384 RGB16LE字节。未套减少像素的建议默认裁切。这些为主机验证，不是Android设备结果。

用户提供的 Lightroom 11.4.3 APK 静态分析见 lightroom-android-raw-analysis.md。已查明其thumb-only rendition与完整导出依赖链，未恢复完整Adobe算法，也没有将私有库或相机配置打入APK。两端独立离线，不依赖LR/C1宿主或电脑代处理。

## 实片、性能与限制

本轮 Windows 当前源码实际将公开A7CR ARW以完整光谱导出为9564×6376 JPG，嵌入sRGB、源hash不变。总耗时164.269秒（含读RAW、完整谱及编码），进程峰值14624.9MiB，JPG为84747180字节；RAW另存hash一致。报告 output/raw-film-0.3.2-a7cr/report.json。这不是实际成品EXE或Android测速，不能据此称手机大图已通过。

历史24MP完整光谱渲染基准为6000×4000、66.3秒、峰值约5.84GiB，仅含渲染，不含RAW读取、编码与写盘，且不是本轮0.3.2测量。完整光谱为CPU科学计算，61–150MP仍有明显时间和内存成本。Android按原图区域分块并逐行编码，但native科学计算峰值无法仅从Java heap准确预测。

用户授权样片副本 output/mask-reference/source-windsock.jpg 为1280×1920，SHA256 77dc014bf2a47f7ca96ee39fabe2e37e19fda615ff2b1df4abaf218a75398c57。新增三片实片完整光谱JPG/TIFF、ICC、尺寸、差异与源完整性记录在 output/film-profile-research/exports-final/report.json；缩小对比图仅供视觉检查，不是导出来源。

## 构建与成品

Windows 由PyInstaller生成便携目录。scripts/verify_packaged_release.py对实际EXE执行完整光谱JPG/TIFF、遗留记录中性化、异步导入、预览、撤销/重做、ICC和源完整性；包含新胶片路径、胶片/导出/颗粒菜单截图及当前资源哈希检查。发布脚本只接受成功验收的同一候选。

Android已执行 assembleDebug、assembleDebugAndroidTest、lintDebug，日志 output/android-build-0.3.2-claude-final.log；0错误、38警告。APK逐文件核对303光谱源文件、23款胶片、许可、字体与sRGB，报告 output/android-verification-0.3.2-claude.json。最终成品验收另核调试签名。测试APK已编译，未执行设备instrumentation。

本机无连接Android真机或模拟器，因此手机触控、SAF、字体缩放、安全区、实际大RAW导出和速度尚未真机验收。Windows源码/同源native主机/包资源检查不能代替这些结果。当前Android尚未具有与Windows相同的普通图片ICC转换，不声称完整Adobe DCP/Look或商业软件等价。

macOS/iOS按用户决定暂停。旧版0.3.1及更早研究证据保存在output，不能当作当前产品功能或本轮性能结论。Windows/Android正式发布目录已替换为当前版本，原生组件对应源码随APK提供。旧临时候选目录 release/.windows-candidate 的删除被自动审批以 blocked by policy 拒绝，仍保留，未再次尝试绕过。
