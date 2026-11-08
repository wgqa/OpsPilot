# OpsPilot R1 本地试用指南

## 唯一试用版本

- 工作树：D:\学习\agent新项目\.worktrees\r1-user-demo-01
- 分支：codex/r1-user-demo-01
- 起始候选：fe8b69d9e44ea6f9c585830ff14a66e64d9b1cab；最终 SHA 以本次候选提交为准。
- 业务库：.runtime/user-demo/domain.sqlite3
- Checkpoint：.runtime/user-demo/checkpoint.sqlite3
- 本地 API：127.0.0.1:8000；前端：127.0.0.1:5173。

这套试用数据与旧实验库、旧 Campaign Grant、Claim 和账本隔离。日常启动不会清空会话。浏览器由项目所有者自行打开；本任务没有执行浏览器自动化。

## 首次安装与初始化

在 PowerShell 中进入上面的工作树目录。需要 Python 3.11 或更高版本、Node.js 20.19 或更高版本和 npm。

    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
    .\scripts\user-demo\Initialize-UserDemo.ps1

初始化器只在 Domain 和 Checkpoint 文件均不存在时创建演示数据；已有库时会拒绝运行，不会自动重置。它会复制 .env.user-demo.example 为本工作树根目录下被 Git 忽略的 .env（若 .env 已存在则保留原文件），并建立 LangGraph Checkpoint schema。

用文本编辑器打开本地 .env，只填写本机登录密码：

- OPSPILOT_WEB_SUPPORT_PASSWORD：support-a 登录密码。
- OPSPILOT_WEB_APPROVER_PASSWORD：approver-a 登录密码。
- 可选的 OPSPILOT_WEB_SUPPORT_B_PASSWORD / OPSPILOT_WEB_APPROVER_B_PASSWORD 用于 tenant-b 的隔离演示。

启动脚本要求 tenant-a 的两个密码各至少 12 个字符。密码不会写进数据库模板、报告或启动日志。不要把 .env 发给他人，也不要在聊天中粘贴密码。

安装前端依赖。使用工作树自己的 npm 缓存，避免与其他项目的共享缓存争用：

    New-Item -ItemType Directory -Force .runtime\user-demo-tools | Out-Null
    npm --prefix frontend ci --ignore-scripts --no-audit --no-fund --cache .runtime\user-demo-tools\npm-cache

## 启动、登录与切换场景

日常启动：

    .\scripts\user-demo\Start-UserDemo.ps1 -Profile S1

在浏览器地址栏手动打开 http://127.0.0.1:5173/。使用 support-a 登录；需要查看审批状态时退出后以 approver-a 登录。登录密码取自你自己的本地 .env。

- S1 使用 orders-demo / integration-a，保留 API 凭据不匹配的本地 401 调查条件。
- S2 使用 orders-demo-s2 / integration-s2-a，保留凭据匹配但缺少 orders.read 的本地 403 条件。
- S3 的异步订单资源独立于 Profile：async-order 预置为 Delivery ACKNOWLEDGED、Receiver QUEUED；async-order-2 是未投递示例。

S1/S2 Profile 只决定新建同步调查绑定的可信 Demo 资源。切换前先停止服务，再用另一 Profile 启动；已有 Task 的绑定和历史不随 Profile 改写。S3 资源仍通过页面的订单选择入口绑定。

## 停止、重启与保留数据

    .\scripts\user-demo\Stop-UserDemo.ps1

停止脚本通过专用 shutdown.request 让 FastAPI/Uvicorn 执行正常 lifespan shutdown，再停止无状态的 Vite 进程。会话、消息、Domain、Checkpoint 和日志保留。再次执行 Start 命令会继续使用同一数据库。

初始化和日常启动是分开的。不要用旧 CLI 或实验 Runner 对试用库执行 reset。若确实要从空白重建，先停止服务，然后显式运行：

    .\scripts\user-demo\Reset-UserDemo.ps1 -ConfirmText "RESET USER DEMO DATA"

该命令会将整个 .runtime/user-demo 移到 .runtime/user-demo-backups 下带时间戳的目录，再创建新库；旧数据保留为备份。不要手动删除数据库文件来绕过备份保护。

## 真实可体验范围与限制

当前候选的实测状态：OFFLINE_DEMO_READY（API、单 Worker、前端 HTTP 和持久化底座通过本地检查；真实模型回答未启用）；REAL_PROVIDER_BLOCKED；BROWSER_NOT_VERIFIED。

重要：当前试用启动脚本刻意强制关闭 ASSISTANT_V1 Runtime Grant、普通 Provider 和 Legacy Provider，并清空该进程的模型 API Key。数据库不会创建 Runtime Grant、费用池、实验 Claim 或 Campaign。登录和页面可以使用，Domain 内有 S1/S2/S3 演示资源，但模型回答、由模型驱动的 S1/S2 调查与审批后修复闭环不能据此宣称可用。当前只有既有确定性测试证明这些本地 Domain 合同。

可以在页面探索协议/配置问题、普通会话、可信订单绑定、S1/S2/S3 的入口和已有结果投影；在本轮 Provider 被关闭的状态下，不能把程序的模型不可用提示当成 Agent 已完成调查。

若要亲自体验真实 DeepSeek，需另行批准 Provider、模型、一次性费用上限和停止条件，并由受信管理员在隔离数据库里单独配置持久 Runtime Grant。仅填写 API Key 不会启用调用；不要自行打开 Provider 开关或复用历史实验账本。此候选未创建 Grant，因此暂不设置未获批准的金额。首次收费授权前应复核当日官方价格和当前发送预留；例如若现行单次保守预留仍是 USD 0.645600，四次调用的应用侧最低池可按 USD 2.5824 评估，但这只是待复核的讨论值，不是本次授权或已配置额度。

## 故障排查

- 启动报告密码未设置：检查本地 .env 中的两个 tenant-a 密码变量；不要粘贴其值。
- 端口占用：脚本在启动前检查 8000/5173，关闭占用它们的本地程序后重试；脚本不会结束不认识的进程。
- API/Worker 未就绪：检查 .runtime/user-demo/logs/api.stderr.log 与 api.stdout.log。
- 前端未就绪：检查 web.stderr.log 与 web.stdout.log，再确认 Node/npm 依赖安装成功。
- Stop 报告 API 未退出：它不会强杀 API。保留进程清单和数据，查看日志并再次运行 Stop；不要直接删除 PID 清单。
- 找不到会话：确认仍在同一个试用工作树/Profile 的应用中。试用数据库只在该工作树的 .runtime/user-demo/ 下。

历史 smokes、旧 CLI 的 reset 命令和 AR-03/AR-04C/R1 Campaign Runner 不属于这套用户启动流程；部分旧 Runner 会清空其指定数据库或尝试真实 Provider 请求，不要把试用数据库路径传给它们。
