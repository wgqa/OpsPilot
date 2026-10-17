# vNext M1-01 状态转换

本文件只冻结 M1-01 的可观察 Domain 语义；不是对未实现 UI、HTTP API 或后续阶段的实现声明。

| 实体 | 转换 | 原子条件与效果 |
|---|---|---|
| TaskControl | `ACTIVE(rev=n) → ABORTED(rev=n+1)` | Task 所属的可信 SUPPORT owner 发出 `abort_task`；同一事务取消活动 Plan、撤销未消费权限、阻断活动业务 Run、记录 Command 与 outbox。无 Plan 时也生效。 |
| TaskControl | `ACTIVE(rev=n) → ACTIVE(rev=n+1, pending=seq)` | `CORRECT_TASK_INPUT` 受理时，同事务写 Message、Command、Queued Run、outbox；使旧 Run/Plan/permission 失效。业务写事务此后被 pending 高水位挡住。 |
| TaskControl | `ACTIVE(rev=n, pending=seq) → ACTIVE(rev=n+1, pending=NULL, applied=seq)` | 当前可信 Run 以 `USER_INPUT_UNTRUSTED` 逐条持久消费完整纠错高水位后才能清 pending。它们进入模型上下文只作调查线索，不进入 Evidence。 |
| TaskRun | `QUEUED → RUNNING → WAITING_APPROVAL / WAITING_INPUT / SUCCEEDED / FAILED / BLOCKED / INTERRUPTED_RECOVERABLE` | claim 使用 SQLite 写事务；同 Task 至多一个 RUNNING 的业务 Run。Correction/abort 可以在同事务将旧 QUEUED/RUNNING 业务 Run 标为 BLOCKED。 |
| TaskRun | `WAITING_APPROVAL / INTERRUPTED_RECOVERABLE → RUNNING` | owner 恢复前重新核对 TaskControl revision、pending 和已消费消息高水位；失配则拒绝。跨进程 worker lease 和自动接管留给后续任务。 |
| Plan | 新建后不可变 | `d3_plan_control_bindings` 记录 revision、consumed message sequence、Run ID；Plan canonical JSON 与 hash 不塞入新控制字段，不重算历史 hash。 |
| Action | `REPAIR/DELIVER` 新提交 | 同一 Domain 写事务检查 TaskControl、Plan binding、PlanAuthorization、Approval、分开的 permission、Intent 身份和现有版本。检查失败时不产生新的业务写入。 |
| Action history | `COMMITTED` 回查 | 相同受信 scope、Intent、幂等身份与 digest 下允许读回既有 Ledger。abort/correction 不抹去配置事实或已提交 Ledger。 |

## 线性化顺序

`BEGIN IMMEDIATE` 获取同一 SQLite 写锁，串行化 TaskControl 命令和 D3 提交。若 abort/correction 先提交，旧提交会看到 ABORTED/pending/stale revision 而失败；若 REPAIR 先提交，配置变化与 Ledger 保留，后续 abort 可阻断未提交 DELIVER；DELIVER 完成后 abort 返回 `TASK_ALREADY_TERMINAL`，不能覆盖完成事实。

`cancel_plan` 是原计划授权历史的取消，`abort_task` 是 Task 级终止，`CORRECT_TASK_INPUT` 是会创建新 Run 的关键输入，三者语义不互换。
