# R1-USER-DEMO-HF-02-SSE

**实施状态：`ACCEPTANCE_CANDIDATE`**

## 前置核验

- Repo：`wgqa/OpsPilot`
- Base / 初始 HEAD：`6d36f06a0c9824764bdadfe390083e685d592231`
- 隔离分支：`codex/r1-user-demo-hf02-sse`
- 开工工作树干净；本报告在提交前记录实现 SHA，提交后以最终提交 SHA 为准。
- 远端 `main`：`60eee87bfe3cca522011316cb4cd2c0064ad291b`
- 远端 `codex/r1-user-demo-hf-01`：`6d36f06a0c9824764bdadfe390083e685d592231`
- `PROJECT_NORTH_STAR.md` Blob：`43dabda468506717c6956e676dfad4304c4f38e6`
- `AGENTS.md` Blob：`807b928686a4dd2cac7b15b3c354b9943c93c910`
- `.agents/skills/opspilot-slice-review/SKILL.md` Blob：`d405c8d413d633824b279202cc1503dab4cf0b03`
- 适用冻结合同：`EVENT_RECOVERY.md` Blob `9ae6c3f35b93c8c139d598c4dfde42447cf5d0cc`；`API_CONTRACT.md` Blob `eca9ec1650d3698363f88681713002ba6b6a37d7`；`STATE_TRANSITIONS.md` Blob `cb34e6402cf3ce795260414b9b652f31b49f4de1`。
- 本地依赖：Python 3.14.0、FastAPI 0.137.1、Starlette 1.8.0、Uvicorn 0.49.0、HTTPX 0.28.1。

## 结果与根因

**根因已确认。** 用户 Stop 脚本写入 `shutdown.request` 后，旧 `run_api.py` 只设置 `server.should_exit=True`。Uvicorn 随后先等待现有连接排空，才发送 ASGI lifespan shutdown；默认 `timeout_graceful_shutdown=None`，因此不会在 30 秒自行超时退出。SSE 生成器只轮询 `request.is_disconnected()`，服务停止信号没有传给生成器；仍连接的浏览器标签页会让 Uvicorn 等待，Stop 脚本的 30 秒期限到达后便留下 API 进程。

旧实现的 lifespan `finally` 才发出的通知也太晚：它在 Uvicorn 等连接结束之后执行，无法解除正在等待的 SSE。

## 修复

- `create_app()` 为应用创建线程安全的 `shutdown_requested` 事件；lifespan 启动时清除，退出时设置。
- SSE 循环在原有断开检查之外检查该事件，并沿用现有至多 250ms 的轮询周期退出。认证刷新、Session owner 校验、Outbox 投影、事件序列、`Last-Event-ID` 优先级、历史重放与客户端按 ID 去重语义未改。
- Windows Runner 的 Stop 文件观察器在设置 Uvicorn 退出标志前先设置该事件；`UserDemoServer.handle_exit()` 对控制台信号也先通知 SSE。
- 未缩短 Uvicorn graceful timeout；未改 Worker 取消、锁释放、Run 中断/恢复、Outbox 或业务写入代码。`Stop-UserDemo.ps1` 未变更，PID、可执行文件、命令标记和工作树身份校验保持原样。

## RED → GREEN 与适用回归

- RED：`RED-before-fix.txt`。在实际 Windows 子进程、随机 `127.0.0.1` 端口、独立 Domain/Checkpoint 下保持两条已认证 SSE 打开并写入同一停止哨兵；旧实现停止请求后 6.007 秒仍未退出，超过测试的 5 秒目标。测试失败而非将其记作通过。代码未设置较短的 Uvicorn timeout。
- GREEN：`GREEN-targeted.txt`，新增进程级回归 **2/2**。两条打开的 SSE 在停止信号后约 0.56 秒结束；无 SSE 时约 0.66 秒退出。测试还确认正常 Heartbeat 与提前断开、错误 Session owner 返回 404、重启后同一 Session/消息/Run 和 Event ID 保留、`Last-Event-ID` 优先于 `after` 并按原 ID 回放。
- 适用 Web/Event/Worker Recovery 最终回归：`FINAL_TEST_LOG.txt`，**17/17 通过**。范围为新 SSE 进程测试 2 项、M1 Web Events 3 项、Web API/权限 6 项、Worker recovery 6 项。
- 第一次未显式设置 Legacy Provider 测试前置开关的组合运行记录于 `REGRESSION-targeted.txt`：14/15；唯一失败为 `test_ops_02_expired_total_deadline_blocks_run_without_model_call` 在检查 deadline 前被既有 `LEGACY_PROVIDER_AUTHORIZATION_REQUIRED` 门禁挡住。按该测试合法前置条件重新运行时，Provider Key 是占位值，Base URL 指向本机关闭端口 `127.0.0.1:1`，该测试单独通过；最终 17 项组合回归也在此离线设置下通过。没有真实 Provider 请求。

完整命令、Windows 进程输出、耗时和退出码见同目录测试日志。全仓 pytest 未运行。

## 数据、安全与范围

- 所有进程使用新 worktree 下 pytest 专属临时 SQLite、Checkpoint、随机端口；测试将 Provider 明确关闭。除测试 HTTP 外没有出站网络。
- 首次登录和建 Session 使用测试专用的确定性密码；日志不包含密码或凭据。
- 重启检查使用同一临时 Domain 与 Checkpoint：Session 仍存在；测试创建的 CHAT_READONLY Message 和 QUEUED Run 保持原状态；Session 的两条事件仍以原 event_seq 回放。关闭过程本身不创建 Task、Approval、ActionIntent、Ledger 或业务写入。
- 正常服务仍在运行时，Heartbeats 可持续；主动关闭仅在服务关闭信号后结束流。多个 SSE 连接各自终止，不触及事件表或业务事实。
- 项目所有者工作树 `D:\学习\agent新项目\.worktrees\r1-user-demo-01` 的代码、`.env`、数据库、Checkpoint、Grant、Spend 和进程均未读取、修改或停止；测试未占用 8000/5173，也没有运行浏览器。
- 真实 Provider HTTP：0；外部业务写入：0；浏览器自动化：0；main 合并：0。

**证据限制：** 本轮实际验证了 Windows Python 子进程、正式 `create_app()`、生产 Runner 的停止哨兵观察器、Uvicorn 和 HTTP SSE；没有启动完整 Vite 页面，也没有执行 PowerShell `Stop-UserDemo.ps1` 本身。该脚本只负责写入已由集成测试覆盖的哨兵，且其安全进程身份检查未改；浏览器和脚本本身仍待项目所有者体验/主 Agent复核。

## 六维自检

1. **用户变化：** 浏览器保持 SSE 时也可请求正常服务退出，避免 Stop 到 30 秒后遗留 API。
2. **Agent 决策：** 不适用；不改变模型决策、工具选择或用户对话。
3. **观察驱动：** 服务继续运行时 Heartbeat 正常；进入 shutdown 后 SSE 结束；重启后同一事件按 cursor 回放。
4. **新增约束：** 仅服务生命周期信号结束事件流；鉴权、owner、cursor 和业务动作权限没有放宽。
5. **简化结果：** 复用现有 Uvicorn/ASGI 生命周期和 SSE 轮询；没有新任务取消系统、状态机或更短的硬超时。
6. **证据与停止线：** Windows 进程 RED/GREEN、权限与 Worker 定向回归已完成；真实浏览器、PowerShell Stop 脚本本体、活动业务 Run 中途关闭未直接执行，限制如上。满足本切片停止条件后交独立复核。
