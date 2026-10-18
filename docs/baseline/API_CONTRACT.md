# vNext API 合同（M1-01 Domain + M1-02 HTTP）

M1-01 提供 Python Domain 函数，尚未暴露 HTTP/FastAPI 路由。只有事务成功提交后，受理结果才是 `ACCEPTED`；本轮没有 HTTP `202` 响应语义。

## 已实现入口

| 入口 | 输入与职责 | 主要拒绝码 |
|---|---|---|
| `trusted_identity(path, actor_id)` | 从本地可信 registry 解析服务端身份；调用者构造的 tenant/role 会在事务中重新核验。 | `TRUSTED_IDENTITY_REQUIRED`, `TRUSTED_IDENTITY_MISMATCH` |
| `create_session(path, identity)` | 创建可信 owner 绑定的持久 Session。Task link 在 `create_task_binding(..., session_id=...)` 同事务建立。 | `TRUSTED_IDENTITY_*`, scope errors |
| `admit_task_message(...)` | 以 Session/Task/InputKind/body/idempotency key 原子写 Command、Message、Queued Run、outbox；关键纠错同步增加 revision、pending 高水位并失效旧授权。 | `IDEMPOTENCY_CONFLICT`, `SESSION_SCOPE_DENIED`, `TASK_ABORTED`, `TASK_ALREADY_TERMINAL`, `CORRECTION_REQUIRES_TASK` |
| `abort_task(...)` | Task owner 原子终止 Task；重复相同 key/digest 返回原结果，已完成任务产生拒绝审计结果。 | `TASK_OWNER_REQUIRED`, `TASK_ALREADY_TERMINAL` |
| `claim_task_run(...)` | Queued Run 原子变为 RUNNING，核对身份、revision、高水位和同 Task 活跃业务 Run。 | `TASK_RUN_NOT_QUEUED`, `TASK_RUN_BUSY`, `TASK_CONTROL_STALE`, `TASK_INPUT_PENDING` |
| `apply_pending_critical_inputs(...)` | 消费该 Run 可见的完整纠错序列，记录 digest/provenance，清 pending 并提升控制版本。 | `TASK_RUN_NOT_ACTIVE`, `TASK_INPUT_INCOMPLETE`, `TASK_CONTROL_STALE` |
| `resume_task_run(...)` | 仅从等待审批/可恢复状态重新 claim，并重查控制版本与消费高水位。 | `TASK_RUN_NOT_RESUMABLE`, `TASK_ABORTED`, `TASK_INPUT_PENDING`, `TASK_CONTROL_STALE` |
| `finish_task_run(...)` / `get_task_run(...)` | 写入 Run 结果，或按 tenant/session owner 读取。 | `TASK_RUN_NOT_ACTIVE`, `TASK_RUN_SCOPE_DENIED` |

## 幂等合同

本地唯一受理由可信 `tenant_id + actor_id + command_kind + target_ref + idempotency_key` 与 canonical request digest 判定。相同摘要返回原 `command_id/message_id/run_id`；同 key 下不同命令/目标/正文拒绝为 `IDEMPOTENCY_CONFLICT`，不增加 Message、Run、revision 或 outbox。

## 兼容与版本

不带 TaskRun token 的旧 Graph/CLI 入口仅可按 revision 0 兼容；必须满足 Task 仍 ACTIVE、无 pending critical input 且资源权限有效。新版 Plan 绑定控制版本及已消费的纠错高水位。M1-01 当时未暴露 HTTP；当前 M1-02 HTTP 合同见下节。客户端仍不得自报 actor/tenant/role。

## M1-02 FastAPI 应用服务合同

Web 路由只映射到既有 Domain 命令和查询；`task_control.py`、`d3.py` 与同一 SQLite 仍是唯一业务权威。服务只绑定 `127.0.0.1`，单 Uvicorn worker；Worker 使用 OS 文件锁与持久 owner epoch，禁止多进程并发推进。

| 方法与路径 | 权限/行为 | 受理状态 |
|---|---|---|
| `POST /api/auth/login` | Origin 校验；以本地未入库的角色密码验证并签发随机 HttpOnly、SameSite=Strict 会话 Cookie；数据库只保存令牌摘要与 CSRF 摘要。 | 200；错密码 401、Origin 不符 403 |
| `GET /api/auth/me`, `POST /api/auth/logout` | 从服务端 registry 恢复 actor/tenant/role；注销是受 CSRF/Origin 保护的写命令。 | 200；无效/过期/注销会话 401 |
| `POST /api/sessions`, `GET /api/sessions[/{sid}]` | 当前登录 SUPPORT owner 创建并读取自己的 Session；列表使用稳定顺序与分页。 | 201 / 200；跨 owner 或 tenant 404 |
| `POST /api/sessions/{sid}/tasks` | 在一次 Domain `BEGIN IMMEDIATE` 中创建可信 S1 binding、首条 Message、Command、QUEUED INVESTIGATE Run、预算与 Outbox；资源来自固定服务端 Demo 配置。 | 首次 202；同 key/同 digest 200 重放原 IDs；同 key/异 digest 409 |
| `POST /api/sessions/{sid}/messages` | 复用 M1-01 `admit_task_message`；CHAT_READONLY 可排队但无模型回答执行器时显示 `QUEUED/NOT_IMPLEMENTED`；纠错返回 `RECEIVED_NOT_APPLIED`。 | 202；Domain 冲突/拒绝映射结构化 `code` |
| `GET /api/sessions/{sid}/messages`, `/api/tasks/{tid}`, `/api/tasks/{tid}/runs`, `/api/runs/{rid}` | 按可信登录身份与 Domain Session/Task binding 授权；APPROVER 只在活动待审批范围内读取，不具备 abort/纠错权限。 | 200；无授权资源 404 |
| `POST /api/tasks/{tid}/abort` | 仅 Task SUPPORT owner；调用 Domain `abort_task`；写入口均验证 Origin 与 CSRF。 | 202；审批者 403 |
| `GET /api/sessions/{sid}/events/history`, `GET /api/sessions/{sid}/events` | 事件历史与 SSE 读取均只对 Session owner 开放；`Last-Event-ID` 优先于 `after`；SSE `id` 是持久 event_seq，重放可至少一次，客户端按 ID 去重。 | 200；游标错误 400；未登录 401；越权 404 |

所有 DTO 禁止额外 actor/tenant/role/executor 字段；伪造身份 Header 不改变认证身份，额外 JSON 身份字段被拒绝。API 不返回原始模型 Prompt、登录 token、凭据或 Authorization。首条用户问题持久保存，但在 M1-04 动态对话接通前不声称其自由文本已进入调查上下文。
