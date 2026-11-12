# 单实例照片打开 · 2026-11-09

`desktop/main.py` 现在接受位置文件路径及已有 `--open`。普通启动在字体和编辑器初始化前建立当前用户的单实例入口；再次启动只发送照片路径、收到接受回执后退出，不再建立另一个编辑器。

`desktop/single_instance.py` 采用 `QLockFile` 选主和 `QLocalServer.UserAccessOption` 当前用户本地管道。Windows 名称包含当前 SID，未开放网络、脚本或任意属性调用，与默认关闭的 CLI/MCP 自动化无关。握手提供主进程PID，使启动方可授予该进程前台激活权限；最小化窗口恢复时保留系统原来的窗口状态。

主窗口尚未绑定或正在导出时，收到的照片进入有界队列。绑定后/导出结束，每轮最多128条交给原有 `controller.add_paths`，再由既有16文件分批导入。重复路径合并，原有照片会由控制器选中，不另建重复记录。原片不改写。

Qt `FileOpen` 事件也走同一边界。`--smoke-test`、`--capture-state` 或 `--screenshot` 的运行不建立/转交用户窗口，保持验收隔离。未自动修改用户系统文件关联；由“打开方式”指定exe传文件即可，不强占照片默认应用。

关键节点 `scripts/verify_single_instance.py` 使用真实两个进程及两个96×64 PNG，真实Controller：第二进程收到确认即退出，导出忙状态前导入数为0，结束后同一主窗口出现2张，最小化恢复、重复FileOpen事件不多出照片，GUI自动化仍关闭。结果 `output/single-instance/verification.json`。未重复大RAW或做哈希检查；最终候选exe入口仍交发布节点验证。
