# 隔离本地 Demo 启动说明

本说明仅用于 Windows 单机 Demo。实际验收时不能把 API health、TestClient 或构建通过冒充浏览器体验。

## 实际验证过的入口

本轮环境：Windows、Python 3.14.0、Node v24.16.0、npm 11.13.0；Python 包以 requirements.lock.txt 为准。当前全局 pip check 有 OpenTelemetry 版本冲突，详见 INTEGRATION_REPORT.md。

### 创建新的本地 Demo 数据库

在仓库根目录 PowerShell：

    New-Item -ItemType Directory -Path .runtime -Force | Out-Null
    $id = Get-Date -Format 'yyyyMMdd-HHmmss'
    $db = ".runtime/r1-demo-$id.sqlite3"
    .\.venv\Scripts\python.exe -m opspilot.cli reset --scenario S1_POS --db $db

本轮已在独立 Windows 临时目录运行相同 reset 命令，场景 S1_POS，退出码 0。每次使用新文件名；reset 会初始化指定 DB，不要指向已有数据库或历史实验账本。

### 启动 API 与单一 Worker

为确保应用读写刚才创建的同一个隔离数据库，并使用独立 Checkpoint：

    $env:OPSPILOT_DB_PATH = (Resolve-Path $db).Path
    $env:OPSPILOT_CHECKPOINT_DB_PATH = (Join-Path (Resolve-Path .runtime).Path "r1-demo-$id-checkpoints.sqlite3")
    $env:OPSPILOT_ASSISTANT_PROVIDER_ENABLED = '0'
    .\.venv\Scripts\python.exe -m opspilot.web.server --host 127.0.0.1 --port 8000 --workers 1

服务只监听 loopback，单 Worker 是应用约束。开另一个 PowerShell 检查：

    Invoke-RestMethod http://127.0.0.1:8000/api/health

本轮以新临时 DB、独立 Checkpoint、Provider 开关为 0、没有 Provider 凭据的子进程实际调用 health，得到 HTTP 200，body 中 status=ok 且 worker.ready=true。程序日志记录 Application shutdown complete。控制信号导致 Windows 子进程退出码 3，因此本报告只把 health 与 Worker ready 记为通过，不把该退出码描述为成功退出码。

前端已有运行方式：新终端进入 frontend，执行 npm ci，设置 OPSPILOT_API_ORIGIN=http://127.0.0.1:8000，然后 npm run dev -- --host 127.0.0.1 --port 5173。打开 http://127.0.0.1:5173 属于浏览器体验；本轮未执行。

## Provider 与凭据边界

- 不需要 Provider Key 的工作：数据库 reset、离线确定性回归、health、前端 typecheck/build、页面开发服务器启动。
- Assistant Provider 默认关闭。create_assistant_model 首先要求 OPSPILOT_ASSISTANT_PROVIDER_ENABLED=1；仅有 API Key 不会自动授权或触发调用。
- 本项目 Provider 工厂目前还要求支持的实验 ID、模型名/端点配置以及对应实验授权/一次性 Claim。真实收费行为不能用本地 runbook 自行启用；需使用独立正式授权。
- 本轮没有向服务子进程传递 OPSPILOT_MODEL_API_KEY、端点或模型配置；外部 Provider 请求为 0。
- 本地 Demo 数据仅为隔离 fixture，非生产身份或生产 IAM。

## 首查日志

- Python Web 服务：运行终端的 Uvicorn、lifespan 和 Worker 输出。
- 定向测试：本地私有证据目录中的 Python pytest logs。
- 前端：Vite 终端与浏览器 Console/Network（仅在有浏览器授权时）。
- Provider 实验：仅检查该实验自己隔离账本、dispatch 与私有 Trace；不可把历史 Claim/账本重置后复用。

完整前端命令、结果和日志哈希见 EVIDENCE_INDEX.md。
