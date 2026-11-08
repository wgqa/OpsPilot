# OpsPilot R1 用户试用环境图

## 版本与隔离路径

- 试用源码根：D:\学习\agent新项目\.worktrees\r1-user-demo-01
- 分支：codex/r1-user-demo-01；基于 r1-engine-final-closeout-02 的 fe8b69d9e44ea6f9c585830ff14a66e64d9b1cab。
- 本轮专属运行目录：.runtime/user-demo/。
- Domain SQLite：.runtime/user-demo/domain.sqlite3。
- LangGraph Checkpoint SQLite：.runtime/user-demo/checkpoint.sqlite3。
- 试用日志：.runtime/user-demo/logs/。
- 前端 npm 缓存：.runtime/user-demo-tools/npm-cache/。

这些路径均位于试用工作树。启动脚本不会解析或复制历史实验 DB、Checkpoint、Campaign、Runtime Grant、Claim 或费用账本。外部数据库路径由启动脚本设置成专用绝对路径。

## 配置优先级

应用从当前试用源码根目录读取 .env。opspilot.config.load_local_environment() 使用 os.environ.setdefault：已经存在的 PowerShell/进程环境变量优先，.env 只填补进程环境中不存在的变量。它不会自动读取其他工作树的 .env。历史 m4_continuous smoke 有单独写死的原仓库 .env 路径，不是正式 Web 启动路径，本试用脚本不运行该 smoke。

Start-UserDemo.ps1 为新子进程显式设置本试用 DB/Checkpoint 路径、Web/API 地址、所选 Profile，并强制设置 Runtime、普通 Provider、Legacy Provider 为关闭、Experiment ID 为空、模型 Key 为空。该约束优先于本机 .env 或继承环境。脚本不会打印环境值。

## 当前变量来源与状态

下表写变量名、来源和职责，不含凭据内容。状态是本轮整理时的工作树状态；用户日后可在本地 .env 中自行配置登录密码。

| 变量 | 来源/状态 | 用途 |
| --- | --- | --- |
| OPSPILOT_DB_PATH | Start 脚本强制为 .runtime/user-demo/domain.sqlite3 | Domain/会话/业务事实 |
| OPSPILOT_CHECKPOINT_DB_PATH | Start 脚本强制为 .runtime/user-demo/checkpoint.sqlite3 | Graph 执行 Checkpoint |
| OPSPILOT_WEB_ORIGIN | Start 脚本强制为 127.0.0.1:8000 | Web CSRF/Origin 校验 |
| OPSPILOT_API_ORIGIN | Start 脚本强制为 127.0.0.1:8000 | Vite API 代理目标 |
| OPSPILOT_DEMO_SERVICE_ID / OPSPILOT_DEMO_INTEGRATION_ID | Start 脚本按 S1/S2 Profile 设置 | 新同步调查资源；S3 使用独立 async 资源 |
| OPSPILOT_WEB_SUPPORT_PASSWORD | .env 模板有占位值；所有者必须填写 | support-a 本地登录 |
| OPSPILOT_WEB_APPROVER_PASSWORD | .env 模板有占位值；所有者必须填写 | approver-a 本地登录 |
| OPSPILOT_WEB_SUPPORT_B_PASSWORD / OPSPILOT_WEB_APPROVER_B_PASSWORD | 模板为空、可选填写 | tenant-b 隔离演示账号 |
| OPSPILOT_ASSISTANT_RUNTIME_ENABLED | 启动子进程强制为 0 | 普通 Assistant Runtime 的产品开关 |
| OPSPILOT_ASSISTANT_PROVIDER_ENABLED | 启动子进程强制为 0 | 普通 Provider 出站开关 |
| OPSPILOT_LEGACY_PROVIDER_ENABLED | 启动子进程强制为 0 | 旧 Chat/Investigator 出站开关 |
| OPSPILOT_ASSISTANT_EXPERIMENT_ID | 启动子进程强制为空 | 防止进入实验专属 Runner |
| OPSPILOT_MODEL_API_KEY | 启动子进程强制为空；未读取或显示本机值 | Provider 凭据；本试用不需要也不使用 |
| OPSPILOT_MODEL_BASE_URL / OPSPILOT_MODEL_NAME | 本轮未配置；Provider 关闭 | 供应商地址和模型，仅未来单独授权时使用 |
| OPSPILOT_MODEL_CONFIG_VERSION / OPSPILOT_MODEL_PRICE_VERSION / OPSPILOT_ASSISTANT_SERVICE_IDENTITY | 本轮未配置；Provider 关闭 | 持久 Runtime Grant 绑定字段 |
| OPSPILOT_WEB_SESSION_TTL_SECONDS | .env 未提供时应用默认 3600 秒 | 本地登录 Session 时长 |
| OPSPILOT_EXECUTOR_ID | .env 未提供时应用默认 executor-a | Demo Task 的本地 Executor 身份 |

初始检查未发现本工作树 .env，也未发现 PowerShell 进程中 Provider/Proxy 环境变量；初始化器只会从模板生成被忽略的 .env。无 API Key、无模型授权、无 Runtime Grant。不要把本地 .env 或命令行环境转发到公开日志。

## 数据初始化、重置与保护

Initialize-UserDemo.ps1 只调用隔离初始化器；初始化器使用现有 reset_fixture(S1_POS)，但在 Domain/Checkpoint 文件已经存在或初始化锁已被占用时拒绝继续。随后只在新库追加一个 S2 403 资源、将 S3 async-order 的本地观察设为 ACKNOWLEDGED/QUEUED，并调用 AsyncSqliteSaver.setup() 创建 Checkpoint schema。初始化不建 Runtime Authority、Pool、Default Grant、Spend 或 Campaign。

正常 Start 不运行 reset_fixture，不删除会话。Stop 先让 FastAPI 正常结束 lifespan，记录和数据保留。显式 Reset 要求确认短语，将整个 user-demo 目录移入带时间戳的 user-demo-backups，再重建；它不覆盖旧备份。

旧实验/Smoke 的 .runtime 均留在各自历史工作树。盘点看到根工作树含大量 m1/m2/m4 和 pytest-* 目录；codex/ar02-live-01 含 ar02-* Campaign；ar03-material-live-01-post-live-closeout 含 RESUME-01/02 与 closeout 目录；ar03-real-llm-01-live 含 AR-02 REAL-JOURNEY-02/03 目录；antigravity/ar03-protocol-compare 含历史材料/测试目录。另有多个 worktree 各自的 pytest 临时目录。根工作树 .runtime 顶层有 199 个历史文件。这里只盘点目录/文件名、大小和时间，没有读取旧数据库内容；本任务未修改这些目录。

历史 Runner 可能有清空目标 DB、固定输出目录、一次性 Claim 或真实 Provider 出站能力。不得从该试用工作树调用它们，也不得指向 .runtime/user-demo/。

## 本地端口和进程

- API + 单一 Worker：127.0.0.1:8000，来源 opspilot.web.server / scripts/user-demo/run_api.py。
- Vue/Vite：127.0.0.1:5173，来源 frontend/vite.config.ts。
- 后端检查：GET /api/health，要求 status=ok 且 worker.ready=true。
- 前端检查：GET /，要求 HTTP 200；该检查不执行 JavaScript，也不属于浏览器验收。
- 进程 PID/命令身份：.runtime/user-demo/processes.json；日志在同目录 logs/。Stop 只操作清单内且可核对可执行文件及命令行标记的进程。

## 试用状态

- OFFLINE_DEMO_READY：本地 Web/API/Worker/持久化启动验证通过；不代表模型回答能力通过。
- REAL_PROVIDER_READY：本轮未达到。
- REAL_PROVIDER_BLOCKED：Provider 开关关闭、Key 未注入、Runtime Grant 未创建；需另行授权与受信配置。
- BROWSER_NOT_VERIFIED：页面仅通过 HTTP 状态检查，所有者仍需亲自用浏览器体验。

## 本候选的本地验证记录

- `python -m venv .venv` 与 `.venv\\Scripts\\python.exe -m pip install -e ".[dev]"`：通过。为支持干净隔离安装，候选只增加了 `pyproject.toml` 的 setuptools 包发现范围。
- `.venv\\Scripts\\python.exe -m pytest -q --basetemp .runtime/user-demo-validation/pytest-user-demo-final-3 tests/test_user_demo_setup.py tests/test_product_01_runtime_grant_01.py tests/test_product_01_runtime_grant_01_hf01.py`：33/33 通过。
- `npm --prefix frontend run build`：通过；本轮没有改前端源码。
- 四个 PowerShell 试用脚本解析：通过。启动脚本拒绝示例密码；用仅存在于测试进程环境的临时密码启动后，API Health 为 `ok`、Worker `ready=true`、前端根路径 HTTP 200，正式 `/api/auth/login` 返回成功；随后通过脚本正常停止。
- 使用本地登录接口建立的一个 Session，在停止并重启服务后仍可读回。当前隔离 Domain 有 1 个演示 Session、0 条聊天消息、0 个 Task；Runtime Grant、费用池、Grant Spend、Campaign 均为 0。Checkpoint 数据库已有 `checkpoints` 与 `writes` 表。
- 验证调用计数：真实 Provider HTTP 0、MCP `tools/call` 0、浏览器自动化 0、外部业务写入 0。初始化演示资源时使用的回调仅访问本机隔离 Demo 服务。

这些结果证明隔离启动、登录会话持久化及基础服务可用；不证明页面浏览器体验、真实模型回答或真实 Assistant 调查。项目所有者需先在本地 `.env` 替换两个必填密码，再按用户指南自行打开浏览器。
