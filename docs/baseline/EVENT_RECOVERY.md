# vNext M1-01 事件与恢复合同

## 同事务受理

`commands`、`messages`、`task_runs`、`task_controls`、D3 Plan/permission 失效和 `domain_outbox` 共用现有 Domain SQLite。命令入口使用 `BEGIN IMMEDIATE`；失败回滚时不能留下 Message、Command、Run、控制 revision 或受理事件的孤儿。`domain_outbox` 以 `(source_kind, source_id, event_kind)` 唯一键防止同一来源事件重复。

M1-01 当时只负责事件记录；M1-02 已加入幂等 projector、HTTP API 与 SSE。UI 上 `202 Accepted` 只在 outbox/Command/Run 提交后返回。

## 进程与 checkpoint

- Domain 数据库是 Task、Command、Message、Run、Plan control、Approval、Intent、Ledger 和业务事实的权威来源。
- LangGraph checkpoint 是 Run 内执行续点，不是审批或业务回执。带 `run_id` 的新 Run 使用独立 checkpoint thread key，避免读取旧 Run 的 checkpoint。
- `run_investigation(..., resume=True)` 在恢复前先核对可信 owner、TaskControl 和持久 Run 状态；abort/correction 后旧 checkpoint 在 graph state access 前阻断。
- REPAIR/DELIVER 最后仍须在同一 Domain 写事务内核对 TaskControl 和 Plan binding；早期 Graph 检查只是节省工作，不替代最终授权。

## 交付限制

当前 SQLite 只证明本地单数据库事务顺序。M1-02 单实例 Worker 由本机 OS 文件锁排他，owner epoch 用于写入 fencing；进程取得锁后将遗留业务 Run 标记 `INTERRUPTED_RECOVERABLE`，并沿既有 run-specific LangGraph checkpoint 与 D3 Intent/Ledger 语义恢复。单机 Demo 不提供跨主机 lease 或分布式 exactly-once。

## M1-02 Outbox 与 Session Event 投影

- 新增应用命令、Run 转换和 D3 关键事务在业务事务中调用 `write_outbox_event()`；Outbox 与 `session_events` 同事务写入。`(source_kind, source_id, event_kind)` 唯一键保证同一事实只有一条事件。
- Projector 对旧 Outbox 幂等补投影；Action reconciler 只依据已提交的 ActionLedger 补事件，不创建 Intent、不调用 REPAIR/DELIVER。N2-01 真实子进程在 REPAIR commit 后立即退出，新 API 进程只查询回放，配置版本与 Ledger 均仍为一次。
- SSE 的 `id:` 是 SQLite `event_seq`；客户端断开只终止当前传输。重连时 `Last-Event-ID` 优先于 `after`，事件可至少一次重送，客户端按 ID 去重。Heartbeat 只发送注释帧，不进入 Event 表。
- Event payload 按键白名单构造，不包含消息正文、Prompt、登录 token、凭据值或 Authorization。Session owner 和 tenant 是历史查询及 SSE 的共同授权边界；猜测 event ID 不能绕过来源资源授权。
- HTTP 响应丢失后的命令重放通过 M1-01 的 canonical digest 返回原始 ID；事件回放不重新运行 Investigator 或业务动作。未知动作结果仍由 D3 Ledger/Receipt 判定，不从事件内容推导。
