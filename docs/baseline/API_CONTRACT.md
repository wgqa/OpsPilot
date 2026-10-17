# vNext M1-01 内部 Domain API 合同

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

不带 TaskRun token 的旧 Graph/CLI 入口仅可按 revision 0 兼容；必须满足 Task 仍 ACTIVE、无 pending critical input 且资源权限有效。新版 Plan 绑定控制版本及已消费的纠错高水位。跨 HTTP 认证、浏览器 Session/API DTO 与 SSE 留待后续卡片，不由客户端自报 actor/tenant/role。
