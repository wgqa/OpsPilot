# vNext M1-01 状态转换

本文件保留 M1-01 的 Domain 状态合同，并记录 M1-02 的服务层投影；不代表 UI 或后续阶段已实现。

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

## M1-02 HTTP 与 Worker 扩展

| 实体 | 转换 | 条件与权威来源 |
|---|---|---|
| Web Session | 未登录 → authenticated | 本地密码验证后由服务端 registry 解析身份；数据库保存 token/CSRF digest、expiry 和 revoke；所有资源 GET 均按 owner/tenant 复验。 |
| Session/Task 接受 | command 未存在 → `ACCEPTED` + `QUEUED INVESTIGATE` | 一次 Domain `BEGIN IMMEDIATE` 写 Session link、TaskBinding/TaskControl、首 Message、Command、Run、deadline budget 与 Outbox；相同 key/digest 重放原 ID，不同摘要拒绝。 |
| Business Run | `QUEUED → RUNNING` | 单实例 Worker 持有 OS 文件锁并注册递增 epoch；TaskControl 的 revision/pending 输入及唯一 active Run 守卫仍由 TaskControl 校验。 |
| Business Run | `RUNNING → WAITING_APPROVAL / WAITING_INPUT` | Investigator 依据真实 MCP Evidence/Graph 结果结束当前 Run；等待状态释放 worker 推进占用，业务 Task 状态仍来自 Domain。 |
| Process restart | 旧 `RUNNING → INTERRUPTED_RECOVERABLE → RUNNING` | 只有新进程获得排他 OS 锁后可恢复；持久 Run、Task owner、TaskControl、D3 authorization 和同 Run checkpoint 复核；非法/未知结果保留为可恢复或不确定，不从 SSE 事件重放业务动作。 |
| Business Run | 活跃总时限耗尽 → `BLOCKED/INCONCLUSIVE` | 持久 Task budget 只累计活跃区间，等待审批/输入不计时；跨恢复不重置总预算。 |
| CHAT_READONLY Run | `QUEUED → QUEUED`（未实现应答） | 当前无只读回答执行器；不消耗 Worker、不写 Graph checkpoint、不改变业务 Task 状态、不返回合成回答。 |
| Domain Outbox | 已提交事实 → `session_events` | 同事务先记录 Outbox 与持久 Event；对账器依赖 ActionLedger 补旧事件，SSE 只传输事件，不授予或重复业务动作。 |

M1-02 修正了 D3 `authorize_workflow_resume()` 中 `expected_control_revision=0` 被 `or -1` 误作缺失值的边界；`None` 才代表缺失，零仍是有效 revision。该补正保留原 TaskControl 合同，并由跨进程 Run 恢复和 revision-zero 定向测试覆盖。
