# M1-01 面试卡：TaskControl 原子裁决

## 1. 为什么不只在 LangGraph 入口检查 abort？

**30 秒：** 入口检查到动作提交之间，用户仍可能终止 Task；checkpoint 也可能在另一个进程恢复。因此我把 TaskControl revision/pending/terminal 校验放进 Plan、Approval、ActionIntent、REPAIR 和 DELIVER 的 Domain 写事务。旧 checkpoint 只负责续点，不决定有没有写权限。

**2 分钟：** 外层检查只能省掉无效模型调用，无法裁决它与 REPAIR/DELIVER 谁先提交。我为 Task 建了权威 control 行，abort 或关键纠错通过 `BEGIN IMMEDIATE` 与 D3 写路径在同一 SQLite 文件内排序。Plan 绑定控制 revision；新业务提交在事务内核对当前 Task 状态和 Plan 绑定。若 abort/纠错先提交，旧 Plan 被取消、旧 Run 被阻断，动作返回 `TASK_ABORTED`、`TASK_INPUT_PENDING` 或 `TASK_CONTROL_STALE`。若 REPAIR 先提交，Ledger 和版本变化保留，之后的 DELIVER 可被拒绝。真实 N1-09/11 子进程恢复在读旧 checkpoint 前被拒绝，N1-10 则先后覆盖 pending 与 stale 两个窗口。

**索引：** `task_control.py`、`d3.py`；[N1 事件](../../evidence/vnext/m1-01/logs/n1-domain-and-process-events.jsonl)。

## 2. 怎么证明 Message、Command 和 Run 没有受理孤儿？

**30 秒：** 三者和 outbox 在同一个 `BEGIN IMMEDIATE` 里写。测试通过数据库 trigger 在 Message/Command 插入后、Run 插入时强制 SQL abort，再检查所有表都没有已提交孤儿；去掉 trigger 后同一 key 可以重试成功。

**2 分钟：** 我没有靠 mock 让 API 返回成功，而是从真实 SQLite 事务边界注入失败。连接上下文回滚控制 revision、Command、Message、Queued Run 和 outbox。随后相同 canonical digest 重试，系统回传原 `command_id/message_id/run_id`，revision 只增长一次。正文变化复用 key 则返回 `IDEMPOTENCY_CONFLICT`。本轮没有 HTTP endpoint，所以只能说 Domain 受理在提交后返回 ACCEPTED；HTTP 202 仍是后续工作。

**索引：** `database.py`、`task_control.py`；N1-01/02 事件及 `test_n1_01_02_admission_is_atomic_and_idempotent`。

## 3. correction 如何阻止旧调查并让新调查继续？

**30 秒：** correction 的接受当刻提高 control revision、设置 pending message sequence 并取消旧授权；旧 Run 不能再提交。新 owner Run 消费整段 correction 后才能清 pending。内容以 `USER_INPUT_UNTRUSTED` 进入新 Prompt，不能直接当 Evidence。

**2 分钟：** 新 message 不是“等模型有空再看”的提示。它先被 Command/Message/Queued Run 原子持久化，TaskControl 同事务记录高水位。当前有效 Plan 和未消费 permission 失效，旧业务 Run 标 BLOCKED。消费阶段检查 pending sequence 与 source message，逐条登记 digest/provenance，再将 applied high-water 和 revision 一起更新。模型看到明确标记的用户纠错，但 Gate 仍依赖当前 MCP Evidence；新 Plan 在独立 control 关系中绑定 Run ID、revision 和已消费序号。N1-10 证明旧 Intent 在消费前得到 `TASK_INPUT_PENDING`，之后得到 `TASK_CONTROL_STALE`；新鲜证据、新审批才完成一次 REPAIR。

**索引：** `task_control.py`、`investigator.py::_prompt_messages()`、`d3.py::create_plan_from_gate()`；[真实 model/MCP Run smoke](../../evidence/vnext/m1-01/logs/real-model-task-run.jsonl)。

## 4. SQLite 如何实现竞态裁决？边界是什么？

**30 秒：** `BEGIN IMMEDIATE` 获取 Domain 写锁，把 abort/correction 与最终业务 COMMIT 排序。两个事务哪个先提交，后来的动作就按持久 revision 再检查。本轮证明同一 SQLite 文件内语义，不声称分布式 exactly-once。

**2 分钟：** Message 受理、TaskControl 更新、Plan 授权变化和 D3 最终 REPAIR/DELIVER COMMIT 都使用相同 Domain 文件的写事务。SQLITE 写锁是本地线性化点，而 partial unique index 限制一个 Task 同时只有一个 RUNNING business Run。N1-05 用独立线程/连接同时 claim 同一 Run，至多一个成功。N1-09/11 则是独立 OS 进程恢复旧 checkpoint。生产级身份、跨主机 worker lease、outbox projector、消息队列和分布式 exactly-once 不在 M1-01 交付范围。

**索引：** `database.py`、`task_control.py`；N1-05/09/11 事件；`docs/baseline/EVENT_RECOVERY.md`。

## 5. 如何保护已提交 REPAIR 和已完成业务事实？

**30 秒：** abort 不回滚已经 COMMITTED 的 REPAIR。它只阻止之后的新动作；历史 Ledger 仍可由受信 executor 按原 Intent 身份回查。若 DELIVER 尚未提交，工单不写；如果 DELIVER 已经完成，abort 返回 `TASK_ALREADY_TERMINAL`。

**2 分钟：** N1-11 先通过旧 Plan 的 REPAIR 事务把 config 从 v7 更新到 v8，并写入一条 COMMITTED Ledger；随后 abort 增加 control revision，撤销未消费 DELIVER permission。另一 OS 进程尝试恢复原 checkpoint，在 checkpoint state read 前被 `TASK_ABORTED` 拒绝。直接调用原 DELIVER Intent 的 Domain 入口也失败，工单 entry/DELIVER ledger 为零。REPAIR 仍可重放为同一个历史 Ledger。另一个真实 D3 closure 测试确保交付已完成后 abort 被明确拒绝。

**索引：** `task_control.py::abort_task()`、`d3.py::execute_repair/execute_deliver()`；`N1-11` 和 `test_abort_after_real_delivery_cannot_overwrite_completed_business_task`。
