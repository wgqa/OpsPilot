# OpsPilot R1 本地试用指南

## 唯一试用版本

- 工作树：D:\学习\agent新项目\.worktrees\r1-user-demo-01
- 分支：codex/r1-user-demo-live-01
- 起始试用基线：4113fa25a0a46ca3c3fd15dfd0bf06697889fc7f；最终 SHA 以本次候选提交为准。
- 业务库：.runtime/user-demo/domain.sqlite3
- Checkpoint：.runtime/user-demo/checkpoint.sqlite3
- 本地 API：127.0.0.1:8000；前端：127.0.0.1:5173。

这套试用数据与旧实验库、旧 Campaign Grant、Claim 和账本隔离。日常启动不会清空会话。浏览器由项目所有者自行打开；本任务没有执行浏览器自动化。

## 首次安装与初始化

在 PowerShell 中进入上面的工作树目录。需要 Python 3.11 或更高版本、Node.js 20.19 或更高版本和 npm。

    Set-Location 'D:\学习\agent新项目\.worktrees\r1-user-demo-01'

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

默认模式是 `Offline`，启动命令等同于 `-Mode Offline`，会强制关闭所有 Provider 路径并清空子进程 API Key。它保留登录、演示资源和已有离线能力。

## 真实 Provider Live 模式（本地可选）

当前源码只支持 DeepSeek `deepseek-flash`。本候选没有 API Key、Runtime Grant 或费用池，也没有发送真实 Provider 请求。只有在你另行核对模型和官方当前价格、选定愿意承担的费用总额，并明确授权真实调用后，才按以下步骤自行启用：

1. 在 `.env` 中填写 `OPSPILOT_MODEL_API_KEY`。不要在聊天、命令行参数或日志中粘贴 Key。确认 `OPSPILOT_MODEL_NAME` 与 `OPSPILOT_MODEL_BASE_URL` 使用当前受支持的模型和官方端点；填写你核对过的 `OPSPILOT_MODEL_CONFIG_VERSION`、`OPSPILOT_MODEL_PRICE_VERSION`、输入/输出 `...RATE_MICRO_PER_MILLION` 和 `OPSPILOT_ASSISTANT_SERVICE_IDENTITY`。费率单位是每百万 Token 的微美元（USD × 1,000,000），不会自动从供应商读取。
2. 停止服务后运行 `.\scripts\user-demo\Configure-UserDemoLive.ps1`。它会显示非密钥配置，让你输入自己选择的总额度和 Grant 到期时间，再要求键入包含该额度的确切授权句。该操作会在本地试用 Domain 中创建一次持久共享 Runtime Grant/费用池，但不会发送 Provider 请求。它只对空费用账本生效，已创建后不会再新建或重置费用池；所以先确定额度。不要在没有独立收费授权时运行此配置。
3. 启动正式普通 Assistant：

       .\scripts\user-demo\Start-UserDemo.ps1 -Profile S1 -Mode Live

   脚本会在启动服务前检查 API Key 是否存在、模型/价格配置是否与当前 Grant 一致、Grant 是否有效、共享池是否 ACTIVE、余额是否足以覆盖一次最大请求预留，以及数据库是否混入实验 Campaign。它不发送连通性探针；Key 是否有效、网络是否可用，只会在你之后真实提交消息时知道。启动失败会报告原因并且不回退到旧 Provider 路径。

4. 多 Session 共用同一数据库中的费用池。查看费用：

       .\scripts\user-demo\Show-UserDemoSpend.ps1

   输出包含 Usage 结算估算、未决/UNKNOWN 预留、已占用总额、剩余额度和暂停状态。它不是供应商账单。余额不足或 Grant/价格状态失效时不会自动重置数据库、替换费用池或重发 UNKNOWN 请求。

切回 Offline 前先运行 Stop，再以 `-Mode Offline` 启动。Offline 会在该服务进程中禁用普通与 Legacy Provider；本地 Runtime Grant 和账本会保留。

## 停止、重启与保留数据

    .\scripts\user-demo\Stop-UserDemo.ps1

停止脚本通过专用 shutdown.request 让 FastAPI/Uvicorn 执行正常 lifespan shutdown，再停止无状态的 Vite 进程。会话、消息、Domain、Checkpoint 和日志保留。再次执行 Start 命令会继续使用同一数据库。

初始化和日常启动是分开的。不要用旧 CLI 或实验 Runner 对试用库执行 reset。若确实要从空白重建，先停止服务，然后显式运行：

    .\scripts\user-demo\Reset-UserDemo.ps1 -ConfirmText "RESET USER DEMO DATA"

该命令会将整个 .runtime/user-demo 移到 .runtime/user-demo-backups 下带时间戳的目录，再创建新库；旧数据保留为备份。不要手动删除数据库文件来绕过备份保护。

## 真实可体验范围与限制

当前候选的实测状态：OFFLINE_DEMO_READY（API、单 Worker、前端 HTTP、登录和持久化底座通过本地检查；真实模型回答未启用）；REAL_PROVIDER_BLOCKED（本地没有有效 Key/Grant，Live 未启用）；BROWSER_NOT_VERIFIED。

重要：默认 Offline 启动脚本会关闭 ASSISTANT_V1 Runtime、普通 Provider 和 Legacy Provider，并清空该进程的模型 API Key。首次初始化不会创建 Runtime Grant、费用池、实验 Claim 或 Campaign。登录和页面可以使用，Domain 内有 S1/S2/S3 演示资源，但在你单独配置 Live Grant 前，模型回答、由模型驱动的 S1/S2 调查与审批后修复闭环不能据此宣称可用。当前只有既有确定性测试证明这些本地 Domain 合同。

可以在页面探索协议/配置问题、普通会话、可信订单绑定、S1/S2/S3 的入口和已有结果投影；在本轮 Provider 被关闭的状态下，不能把程序的模型不可用提示当成 Agent 已完成调查。

仅填写 API Key 不会启用调用；Live 启动还要求当前隔离数据库中的持久 Grant。不要复制实验账本或历史 Grant。本候选没有代你设置预算金额、创建 Grant 或发送 Provider 请求。应用费用池按你亲自核对的价格和配置估算，并不等于供应商账单。

## 故障排查

- 启动报告密码未设置：检查本地 .env 中的两个 tenant-a 密码变量；不要粘贴其值。
- 端口占用：脚本在启动前检查 8000/5173，关闭占用它们的本地程序后重试；脚本不会结束不认识的进程。
- API/Worker 未就绪：检查 .runtime/user-demo/logs/api.stderr.log 与 api.stdout.log。
- 前端未就绪：检查 web.stderr.log 与 web.stdout.log，再确认 Node/npm 依赖安装成功。
- Stop 报告 API 未退出：它不会强杀 API。保留进程清单和数据，查看日志并再次运行 Stop；不要直接删除 PID 清单。
- 找不到会话：确认仍在同一个试用工作树/Profile 的应用中。试用数据库只在该工作树的 .runtime/user-demo/ 下。

历史 smokes、旧 CLI 的 reset 命令和 AR-03/AR-04C/R1 Campaign Runner 不属于这套用户启动流程；部分旧 Runner 会清空其指定数据库或尝试真实 Provider 请求，不要把试用数据库路径传给它们。
