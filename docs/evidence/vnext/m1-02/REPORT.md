# OpsPilot vNext M1-02 实施与运行报告

## 交付状态

M1-02 的 FastAPI 本地应用服务、可信身份、Domain 原子受理、单实例 Worker、持久 Outbox 与 SSE 已实现并完成本轮新鲜测试。代码范围仅包含 M1-02 以及为跨进程恢复所需的 revision=0 最小修正；M1-03、Web 审批、真实只读聊天回答和其他后续阶段未开始。最终由 `main` 提交交付，实施提交 SHA 在提交后回填。

## 起点、环境与复现

- 起点：`main@9658aa3a02513a41cfd40ce1e5974d49ec9fe9ed`。开工前本地 HEAD、分支和 `origin/main` 均与该 SHA 一致；工作树仅有 `开发目录/` 用户提供的未跟踪任务卡/历史合同，本轮始终未将其暂存或改动。
- 运行环境：Windows 11、Python 3.14.0。精确依赖见 [`logs/environment.txt`](logs/environment.txt)，`pip check` 结果为通过，见 [`logs/pip-check.txt`](logs/pip-check.txt)。本轮新增并锁定 FastAPI 0.137.1、Uvicorn 0.49.0、HTTPX 0.28.1。
- 定向复现命令：`.venv\Scripts\python.exe -m pytest -q -s tests\test_m1_web_api.py tests\test_m1_web_events.py tests\test_m1_worker_recovery.py tests\test_m1_event_process_recovery.py tests\test_m1_task_control.py --basetemp=.runtime\m102-targeted-final-final`，结果 27 passed、0 failed，原始输出 [`logs/pytest-m1-02.txt`](logs/pytest-m1-02.txt)。
- 全量复现命令：`.venv\Scripts\python.exe -m pytest -q -s --basetemp=.runtime\m102-full-final-final`，结果 91 passed、0 failed，退出码 0，原始输出 [`logs/pytest-full.txt`](logs/pytest-full.txt)。
- 独立服务 smoke：`.venv\Scripts\python.exe -X utf8 -m opspilot.smokes.m1_web --evidence-dir docs\evidence\vnext\m1-02 --restart-window-seconds 60 --completion-timeout-seconds 180`。它启动真实 loopback Uvicorn、使用独立 Cookie jar 登录并通过实际 HTTP/SSE 建立 Task；随后强制结束服务进程并启动新进程恢复同一 Run。原始 HTTP、SSE、服务日志、模型/MCP 轨迹分别见 `logs/http-two-roles.jsonl`、`logs/sse-reconnect.jsonl`、`logs/web-server.log`、`logs/real-model-taskrun.jsonl` 与 `logs/worker-restart.jsonl`。

## 实现范围

- `opspilot/web/app.py` 提供 health、login/me/logout、Session、Message、Task、Run、abort、事件历史及 SSE 路由。`auth.py` 从服务端 registry 得到 actor/tenant/role；服务端仅持久化随机 cookie token 摘要，写请求检查 Origin 与 CSRF，资源 GET/SSE 按受信 owner/tenant 授权。入口只允许 loopback 和单 worker。
- `task_control.create_task_with_initial_run()` 在 Domain 事务中创建 TaskBinding、首条 Message、Command、queued INVESTIGATE Run、持久预算及 Outbox 事实；相同幂等键/正文返回相同 IDs，异正文冲突。API 不直接更改 Task 的业务状态。
- `opspilot/web/worker.py` 使用单实例 OS 锁、owner fencing、Domain 队列和已有 Investigator/LangGraph 推进 S1；WAITING_APPROVAL 释放执行占用、不自动批准。恢复只认 Domain Run 与可信 Checkpoint；持久 C1 活跃时限不计入审批等待，D2 的模型/MCP 尝试预算保留。
- `domain/events.py` 将 Domain 事务写入的 Outbox 幂等投影为按数据库 event_seq 排序的 Session Event。SSE 的 `Last-Event-ID` 优先于 `after`；重放允许至少一次，由稳定 ID 去重。已提交历史 Ledger 的缺事件修复只投影事件，不执行业务写入。
- 为恢复真实跨进程 Workflow，`d3.authorize_workflow_resume()` 显式区分 `expected_control_revision is None` 与合法整数 `0`。这一最小修正附有 revision=0 授权回归测试，不改变冻结审批或执行合同。
- 只读聊天在本卡仅受理与回读，保持 `QUEUED/NOT_IMPLEMENTED`；首条自由文本被持久保存，但当前固定 S1 Prompt 未声称使用它。D1/D2 的固定调查路径仍通过本轮真实 Provider 与 MCP。

## 用例结果与运行证据

| 用例 | 结果 | 证据与边界 |
|---|---|---|
| WEB-01 | PASS | 真实 HTTP 未登录返回 401；身份伪造 Header 不改变可信主体。错密码及伪造 body 字段由 API 测试覆盖。见 `logs/http-two-roles.jsonl`、`tests/test_m1_web_api.py`。 |
| WEB-02 | PASS | SUPPORT、APPROVER、另一个租户主体独立登录；跨 tenant Session/Task 为 404；Approver abort 为 403；授权待审 Task 读取为 200。见 HTTP/SSE 日志。 |
| WEB-03 | PASS | HTTP 创建返回 202；相同幂等 key 重放返回 200 且 IDs 相同；变更摘要为 409 `IDEMPOTENCY_CONFLICT`。事务断言仅创建一组 Task/Message/Command/Run。 |
| WEB-04 | PASS | 注入 Task/Run 与关键纠错插入失败，事务回滚且无孤儿记录；重试后 revision 和业务命令只提交一次。见 `test_web_04_*`。 |
| WEB-05 | PASS | 真实 HTTP 缺 CSRF、错误 Origin 均 403；测试覆盖注销、过期和注销后读写关闭。 |
| WEB-06 | PASS | 争用 Run claim 只有一个 RUNNING owner；进入 WAITING_APPROVAL 后不占执行者；CHAT_READONLY 仍 QUEUED，结束只读 Run 不会完成业务 Task。 |
| WEB-07 | PASS | 真实 loopback Uvicorn + 两个角色的 Cookie jar + 真实模型/MCP S1。客户端断开后 Worker 继续，重连读取持久事件；Task/Run 最终 WAITING_APPROVAL，审批前六类 D3 业务写记录均为 0。见后三个 smoke 日志。 |
| N2-01 | PASS | 子进程在真实 Domain REPAIR commit 后立即退出；新 FastAPI 进程回放一个持久事件。Intent=1、Ledger=1、REPAIR event=1、config version=8。该测试使用本地可信程序化 D3 审批构造恢复窗口，不代表 Web 审批功能。见 `logs/n2-01-repair-event-recovery.jsonl`。 |
| N2-02 | PASS | SSE 客户端收首帧后断开并以 Last-Event-ID 重连；持久 seq 连续，重复投递可按 ID 去重，`Last-Event-ID` 优先于 `after`。见 `logs/sse-reconnect.jsonl`。 |
| N2-03 | PASS | 使用合成历史 COMMITTED Ledger 夹具验证 reconciler 只补一条缺失事件，Intent/Ledger/config 均不变；这是事件投影测试，不宣称为新鲜线上业务动作。 |
| N2-04 | PASS | 无 Task Session 可持久化/回放 CHAT_READONLY 消息；没有真实回答时回答保持 NOT_IMPLEMENTED、Run 保持 QUEUED。见 SSE 日志。 |
| N2-05 | PASS | 未授权主体访问未知 Session 事件流/历史被拒绝，不返回 payload。见 `test_n2_05_*`。 |
| OPS-01 | PASS | Uvicorn 进程在模型 attempt 与 Checkpoint 持久后被强制结束；新 PID 确认旧 owner 已停止，复用同一 Run ID 和 Checkpoint，最终 WAITING_APPROVAL。见 `logs/worker-restart.jsonl`。 |
| OPS-02 | PASS | 注入时钟验证活跃期限跨等待/恢复持久且不累计观察到的停机时间；过期预算令调查 INCONCLUSIVE 且不发起新模型调用。见 `test_ops_02_*`。 |

### 真实模型与 MCP 轨迹

最新独立 HTTP smoke 的 Task/Run 为 `task-c1366d9b-9074-4d9a-b016-916f1bac30a1` / `run-f32589dc-c47b-4a2b-9a32-33a61fae9b3c`。模型 Provider ID 为 `deepseek-flash`：5 次已完成响应，保留 5 个 provider response ID；累计 input/output/total tokens 为 11,764 / 864 / 12,628。进程终止时另有 1 个持久 MODEL `RESERVED` attempt、无响应 ID/Token usage，因此不计为成功；供应商是否已完成该请求未知。

MCP 实际调用 4 次：`get_integration_config`、`get_principal_status`、`get_auth_policy`、`probe_endpoint`，均有持久证据。Endpoint `/api/orders/demo-order` 首次真实状态是 HTTP 401、credential_ref=`cred-v1`；Policy 接受 `cred-v2`，Principal 为 ENABLED。重启后同一调查恢复并形成 Plan，Task/Run 停在 WAITING_APPROVAL。当前没有 Approval、ActionIntent、ActionLedger、VerificationReceipt、ReportArtifact 或 DeliveryRecord；配置及工单写入为零。该 smoke 证明的是模型/MCP 调查与 Run/Checkpoint 恢复，不是修复业务完成。

## 首次失败、已知限制与风险

首次失败与修复均保留在 [`logs/attempts.md`](logs/attempts.md)：smoke 首次因日志目录缺失未启动；Windows 强杀后的 OS byte-range lock 有释放延迟，加入最多 1 秒有界获取重试并保持 fail closed；一次真实模型重启因 revision 0 被旧 `or -1` 表达式拒绝，已显式区分 None/0 并通过真实恢复复验；第一次定向测试仍期望 schema version 1，修正为当前迁移后的 version 2。历史 D6 首次 D3 smoke 的 `FAIL` 仍在全量日志中保留，测试会断言该历史事实；本轮 pytest 的实际结果为 91/91 通过。

本地账号密码来自未入 Git 的环境配置；SQLite 和 OS 锁仅用于单机 Demo，不构成生产 IAM、跨机器租约或分布式 exactly-once。N2-03 依赖合成历史 Ledger 夹具。CHAT_READONLY 模型回答、Web 审批/拒绝、多 worker/分布式调度、首条自由文本进入动态 Prompt 均未实现。被终止的 MODEL attempt 结果未知，但它只对应只读模型请求；不会重放未知业务副作用。当前调查停在审批边界，六类业务写入为零。

## Git 与交接

- 主分支起点为 `9658aa3a02513a41cfd40ce1e5974d49ec9fe9ed`；实施结束 SHA 将在提交后填入本报告。最终推送后会复核 `origin/main` 与本地 `main` 完全一致。
- M1-02 提交后立即停止实施；M1-03 尚未开始。交由主 Agent 按源代码、91 项全量回归、27 项 M1 定向回归、HTTP/SSE 事件、worker 重启与真实模型/MCP 轨迹进行独立审查。
