# vNext M1-01 事件与恢复合同

## 同事务受理

`commands`、`messages`、`task_runs`、`task_controls`、D3 Plan/permission 失效和 `domain_outbox` 共用现有 Domain SQLite。命令入口使用 `BEGIN IMMEDIATE`；失败回滚时不能留下 Message、Command、Run、控制 revision 或受理事件的孤儿。`domain_outbox` 以 `(source_kind, source_id, event_kind)` 唯一键防止同一来源事件重复。

M1-01 只负责事件记录，不消费 outbox，不实现 projector、HTTP API 或 SSE。UI 上 `202 Accepted` 的实现应等 outbox/Command/Run 提交后才由后续 API 返回。

## 进程与 checkpoint

- Domain 数据库是 Task、Command、Message、Run、Plan control、Approval、Intent、Ledger 和业务事实的权威来源。
- LangGraph checkpoint 是 Run 内执行续点，不是审批或业务回执。带 `run_id` 的新 Run 使用独立 checkpoint thread key，避免读取旧 Run 的 checkpoint。
- `run_investigation(..., resume=True)` 在恢复前先核对可信 owner、TaskControl 和持久 Run 状态；abort/correction 后旧 checkpoint 在 graph state access 前阻断。
- REPAIR/DELIVER 最后仍须在同一 Domain 写事务内核对 TaskControl 和 Plan binding；早期 Graph 检查只是节省工作，不替代最终授权。

## 交付限制

当前 SQLite 只证明本地单数据库事务顺序。M1-01 不实现跨主机 worker lease、分布式 exactly-once、outbox 消费重试、SSE Last-Event-ID 或自动认领崩溃遗留 RUNNING Run；这些接口必须在后续任务重新审查和验证。
