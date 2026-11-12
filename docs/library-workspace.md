# 资料库与快速会话

`LibraryWorkspace` 是可选工作区，不改变直接拖入照片的快速会话。底层采用
MIT SpektraLab_library 0.3.1 的真实 C++ / SQLite SDK；42 个原生 API 的契约在
`native/library/API-SPEC.md`，来源和许可证在同目录保留。

## 接入

```python
workspace = LibraryWorkspace(thumbnail_provider=photo_provider)
workspace.flushCurrent.connect(controller.persist_current_synchronously)
workspace.openPhoto.connect(activate_library_photo)
controller.persisted.connect(workspace.saveEdit)
```

`openPhoto(path, record, metadata)` 的 record 是此前原样存入 SDK 的编辑对象，
metadata 含 library/image/variant/revision/kind/row。原生 edit 为 null 时传空字典。
激活期间应抑制旧照片的 persisted 回调，特别是同一个源文件的两个变体；先由
flushCurrent 保存旧项，再装入新项，避免把旧变体写入新变体。`saveEdit(path, record)`
消费当前已激活照片的同步持久化事件，不能给它传入过期的异步编辑事件。

QML `LibraryWorkspace.qml` 只需要 `workspace` 对象和 `closeRequested` 接线，沿用
已有 `Theme`、`StudioButton`、标题和字体。缩略图通过既有 `image://photos` provider
异步请求，只为当前最多 64 项页面登记；切换页面移除上一页登记和像素缓存。
库列表不加载 RAW 像素，导出继续由现有原尺寸渲染流程负责。

## 保存、切换、关闭

调整保存以 280 ms 归并，`edit.put(base_revision=...)` 顺序执行。切换变体、切换
资料库、切换快速会话或关闭窗口，都会先 flush 当前编辑器并等待旧记录提交。
发生 revision 冲突、超时或 helper 退出，不自动重放写入、不覆盖远端记录。
冲突可以显式“重新载入”，或保留当前记录“另存变体”。

窗口 `onClosing` 应阻止第一次关闭，调用 `prepareToClose()`，等 `closeReady`
发出后再实际关闭。不要等 `aboutToQuit` 才发起异步保存。确认 closeReady 后，
最后调用 `service.close()`；它发出 host.shutdown 并在 2 秒后兜底结束子进程，
不在界面线程执行 waitFor*。尚有冲突时不发 closeReady，编辑器保持打开。

快速会话切换完成前清空工作区的 active 变体与库 handle，再发出
quickSessionRequested，同路径的后续快速编辑不会回写旧资料库变体。

## 文件与数据边界

导入默认按引用登记，原照片不改写；只有显式 copy 或 session.move 才进行文件
操作，session.move 使用防覆盖原子移动。相册移除与“不留用”只调整库记录。
摄影师不需要常驻评级入口，界面仅提供留用/暂不留用。

监看文件夹使用 Qt 原生根目录变化通知，500 ms 合并后交由 helper 异步扫描；
30 秒的低频递归补扫覆盖深层子目录和离线后恢复，扫描只读文件系统元数据。
同时最多一个扫描，库切换后隔离旧结果，快速会话和退出时停止监看。

Capture One 链接、独立复制、同步和路径重定位通过真实 SDK 执行，源 C1 数据库
始终只读。导入目录、集合、变体和元数据不等于移植 C1 的私有显影算法。
当前 Windows 关键验收使用上游 16.8 schema fixture；真实来源兼容性仍由 probe
核对，不能把 fixture 验证泛化为所有 C1 版本均已实测。

## 已验证

- `output/library-bridge/verification.json`：42 API、Unicode/盘符重开、相册、变体、
  revision 冲突、会话独占、防覆盖移动还原、C1 只读快照、热 journal 拒绝、异步 bridge。
- `output/library-bridge/workspace-verification.json`：切换前保存、并发冲突保留与另存、
  相册增删成员、搜索、根目录真实通知；QML 消息为空。
- `output/library-bridge/library-workspace-1366x768.png`：保留现有字体和灰绿色系统的
  1366×768 逻辑像素布局截图。合成色块仅为测试照片，不作为产品示例图。
