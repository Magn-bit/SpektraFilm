"""Write release notes only after verified candidates have been published."""
from pathlib import Path
from datetime import datetime
import json,re,hashlib
root=Path(__file__).resolve().parents[1]
read=lambda p:json.loads((root/p).read_text(encoding='utf-8'))
manifest=read('release/manifest.json');assert manifest['version']=='0.2.1'
proof=read('output/release-verification.json');assert proof['ok']
parity=read('output/android/spectral-parity/report.json');assert parity['ok']
interface=read('output/interface-refinement/report.json');assert interface['ok']
log=(root/'output/test-final.log').read_text(encoding='utf-8');assert '\nOK' in log
count=int(re.search(r'Ran (\d+) tests',log).group(1))
for product,key in [('windows','executable'),('android','apk')]:
    assert hashlib.sha256((root/'release'/manifest[product][key]).read_bytes()).hexdigest()==manifest[product]['sha256']
stamp=datetime.now().astimezone().isoformat(timespec='seconds')
content=f'''# SpektraFilm 0.2.1 · 验证记录

更新：{stamp}。本地交付以 release/manifest.json 与 SHA256SUMS.txt 为准。

## 成品

- Windows：release/Windows/SpektraFilm/SpektraFilm.exe，保留整个目录与 _internal。便携开发版，未正式代码签名。
- Android：release/Android/SpektraFilm-0.2.1-debug.apk，versionCode 3、arm64-v8a、API 26+，调试签名。
- 设备测试 APK：output/android/SpektraFilm-0.2.1-tests.apk，已编译，未执行。
- 上一版保存在 release/history，未删除。

## 本轮界面

实际内置汇文明朝体，中文/Latin 字形来源均已验证，Noto Serif SC 仅作为缺字回退。删除 Windows 顶部中央文案与编辑区宣传短句，保留窗口拖动区和右上角圆点。参数数值、当前照片与多选状态、搜索空反馈已精修。

统一导出、关于、胶片库与应用文件窗口的字体、表面、圆角与按钮。文件窗口保留真实 QFileDialog 文件模型及键盘行为，覆盖已有文件时在应用内提示并阻止覆盖。Android 应用内弹窗保持相同风格，系统文件/目录授权保留平台界面。

Android 重置按钮独立留白并按文字实际宽度布局；所有参数滑块两端按 thumb 半径留出空间，避免最右端半圆裁切。设备测试包含实际 Activity 滑块端点几何检查，尚未运行，不能当作真机截图验收。

## 回归与实际 Windows 窗口

{count} 项 Python 测试通过（output/test-final.log），涵盖文件/图片导入、剪贴板、批量、独立历史、缓存和队列竞态、镜头模块、EXIF、导出、字体实际字形、文件对话框与只允许完整模式。状态/队列测试用轻量替身隔离科学计算，真实完整管线由实际 EXE 与科学对照验证，未将模拟测试称为真实光谱运行。

7 组真实窗口流程通过：Unicode WM_DROPFILES、Ctrl+V 文件、Ctrl+V 位图、全选/批量胶片、三张实际 JPG/ICC、图外对比与最小窗口导出。证据 output/workflow-verification/report.json。界面字体、搜索、最小窗口弹窗与三类文件窗口检查通过，见 output/interface-refinement/report.json。

52 个 Qt DPI/尺寸/页签组合通过，轨道与数值间距至少 8px。离屏缩放只验证布局几何，不等于跨物理显示器 DPI 测试；另含原生 Windows 截图，证据 output/scrollbar-verification。已有窗口位置/大小/最大化记忆验证见 output/window-runtime.json。

## 实际 EXE 与发布副本

在只含 Windows 系统目录的 PATH 下，实际 EXE 完成完整光谱 JPG 与 TIFF 的导入、预览、分组撤销/重做、原尺寸导出、sRGB ICC 与原图 hash 保护，两个报告 settings.spectral 均为 true，字体均为 Huiwen-mincho。证据 {proof['evidence']}。empty/export/library 截图也来自实际 EXE。

全部 QML、字体、Qt 中文翻译与许可和源码逐字节匹配。release 暂存副本完成独立启动/完整预览检查后才替换当前交付；旧版保留。逐文件 SHA256 清单覆盖两端成品、README 与 manifest。

## Android 完整光谱

Chaquopy 16.1.0 / Python 3.10 嵌入原版曝光、胶片、相纸、扫描管线。停止调节及 JPG/TIFF 导出使用完整内核，没有轻量模式开关；交互时明确标注近似。快速、完整与文件工作各用独立执行通道，各任务独立拥有 Bitmap；完整预览/导出串行进入科学内核，过期结果丢弃。

移植不修改桌面 vendor。scripts/prepare_android_spectral.py 可复现副本，port-manifest.json 记录差异和原始源码 hash。Numba/LLVM 替换为 NumPy/SciPy 数组内核，NumPy FFT 替代 pyFFTW，文件读写交给 Android；保留原数学管线与数据。随机模型使用 NumPy 分布，随机序列与原 Numba 近似采样不同。

主机数值对照覆盖 PCHIP、2D/3D Mitchell、四种 Gaussian sigma、密度曲线、负片/反转片及开/关光晕。关闭胶片颗粒与随机相纸眩光后，最大绝对误差 {max(parity['max_absolute_errors'].values()):.3g}（阈值 1e-8）。另检查 Android 桥接 ARGB 输出尺寸和物理颗粒生效。证据 output/android/spectral-parity/report.json。这是主机数学对照，不是 Android 运行时测试。

assembleDebug、assembleDebugAndroidTest、lintDebug 成功，Lint 0 errors、16 warnings（output/android/build-0.2.1.log）。APK 内完整源码/数据与当前生成文件逐字节核对，包含 arm64 CPython、NumPy/SciPy/scikit-image 原生依赖、20 胶片交互 LUT、字体、许可、ICC，未内置样片。apksigner 校验通过；证据 output/android/verification.json、signature-final.log。55 个初始 Python 模块通过 3.10 语法检查；资源包初始化模块随 APK 一并编译/打包。

本机没有连接真机或模拟器，未执行设备测试、Android 截图、低内存、权限、显示色彩及帧率验收。完整预览最长边 960px、交互 640px，均受保守内存预算进一步限制；JPG/TIFF 从来源重新解码，但不保证原尺寸。首次初始化较慢，完整任务不支持内核级即时取消。RAW 只复制原字节，不含完整 RAW 解码；Android 没有桌面 LCP、项目存档或撤销。

## 性能与其他边界

独立交互队列、最新请求合并、质量优先与缓存失效已有回归。历史 output/preview-benchmark.json 中的 LUT/交互性能仅对应当时测量范围，不能当作本轮完整光谱或 Android 性能。未宣称 60fps。

桌面镜头校正仅只读本机可靠匹配且支持的 LCP，缺数据不猜参数，不分发 Adobe 数据。桌面尚无裁剪、16 bit 输出或显示器 ICC 软打样。四项导出仍为高品质 JPG、分享 JPG、TIFF、RAW 原片。

通用“前端设计” Skill 已更新，安装位置与 D:/Tool/Skills/software-frontend-craft 备份一致；与本产品绑定的字体/品牌不写成通用强制规定。
'''
(root/'docs/validation.md').write_text(content,encoding='utf-8')
plan=root/'task_plan.md';text=plan.read_text(encoding='utf-8')
start=text.index('## 本轮界面精修');end=text.index('## 上轮目标',start)
text=text[:start]+'''## 本轮界面精修
1. [completed] 检查实际界面，保留认可方向。
2. [completed] 去文案、真实明朝字体、统一弹窗、数值与照片选择层级。
3. [completed] 75 项回归、7 组原生流程、52 个 DPI/布局组合与界面截图检查。
4. [completed] 两端只保留完整光谱；Android 原版模型移植并完成主机数学对照、APK 源码与依赖检查。
5. [completed] Android 重置宽度与滑块端点修复；测试 APK 已编译，真机验收仍待设备。
6. [completed] 0.2.1 两端构建、签名/成品验证及本地发布，旧版保留；通用 Skill 与备份一致。

'''+text[end:]
plan.write_text(text,encoding='utf-8')
for name in ['progress.md','findings.md']:
    path=root/name;old=path.read_text(encoding='utf-8');marker='\n## 0.2.1 完整光谱与界面发布\n'
    if marker in old:old=old.split(marker)[0]
    path.write_text(old+marker+f'\n{stamp}：两端完整光谱、真实汇文明朝体、统一弹窗、安卓重置与滑块端点修复。{count} 项回归、7 组原生流程、52 个布局组合、实际 EXE 光谱 JPG/TIFF、Android 构建/Lint/源码/依赖/签名检查及主机数学对照通过。0.2.1 发布至 release，旧版进入 history；Android 无设备运行，内存/触控/权限仍需真机验收。见 docs/validation.md。\n',encoding='utf-8')
print(json.dumps(dict(ok=True,version='0.2.1',tests=count),ensure_ascii=False))
