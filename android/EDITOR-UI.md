# Android 编辑工作区

界面沿用 Kotlin / Android View，不引入新的 UI 框架。字体继续使用已认可的中文朱雀仿宋与英文、数字 Noto Serif 配对。

## 本轮实现

- 预览和参数分别占据有界空间，照片不再是参数长滚动页的一部分。竖屏为上方预览、下方参数，横屏为左图右栏；只有参数内容滚动。
- 点击照片可收起或显示参数；“收起 / 调整”保留明确入口。单击确认与双击缩放分开，对比拖动、双指缩放不会触发面板显隐。收起时不销毁控件，保留当前分组、参数值和滚动位置。
- 文件信息、照片列表、裁切和对比靠近预览；胶片/显影有明确选中底色。固定导出区域不覆盖参数，并继续处理系统栏和挖孔安全区。
- 裁切进入独立全屏工作区，可拖动框内移动位置、拖动四角或四边调整尺寸。支持原图、自由、1:1、3:2、4:3、16:9、XPan 65:24，以及标准比例横竖切换。取消不修改当前照片，应用后仅保存源坐标矩形。
- 裁切尺寸按完整、已校正方向的原始像素计算；预览快照不作为导出来源。裁切是主动改变取景范围，不执行额外缩小。
- 原有精确输入、长按微调和双击圆点复位保持可用。

## 单个验收节点

`EditorUiInstrumentation` 随 debug APK 构建，无须第二个测试 APK。它在真实 Android View 上聚合检查布局、交互和裁切，并输出 PNG 与 JSON。覆盖 360×800、393×852、412×915 dp，1 / 1.5 / 2 字体倍率及横屏；检查末组参数可见、导出不重叠、预览未坍缩、照片点击显隐和 XPan 源坐标移动/锁定比例缩放。它不重复历史 RAW 全图与光谱性能验收，也不做哈希测试。

```powershell
adb shell am instrument -w com.spektra.film/.EditorUiInstrumentation
```

可传 `-e photo_path /data/local/tmp/example.jpg` 使用真实 JPEG 预览素材。默认使用明确标记的 UI 测试图。产物位于应用私有目录 `files/editor-ui-check/`；运行是否通过以其中 `report.json` 为准。离屏测量与绘制不能替代手机上的手势触感、屏幕阅读器和帧率验收。

0.4.3 / versionCode 22 已完成 `assembleDebug lintDebug`（0 errors / 42 warnings），上述 runner 也已随 debug APK 编译通过。当前 ADB 无设备，runner、截图与真机手感尚未执行；详见 `android/BUILD-VERIFICATION.md`。
