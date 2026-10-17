# M1-01 学习笔记：TaskControl 的原子裁决

## 1. Graph checkpoint 不是 Task 的事实来源

checkpoint 说明某个 Run 执行到哪里；abort、纠错受理、Plan 授权和 Action COMMIT 都必须回到 Domain SQLite 决定。否则旧 checkpoint 恢复时会把已终止任务误当成仍可写。M1-01 在 `run_investigation()` 恢复前校验 TaskControl/Run，且 D3 的 Plan、Approval、Intent、REPAIR、DELIVER 仍在各自写事务内检查。checkpoint 只是执行续点，持久 Ledger 才证明业务动作。

**源码/实验：** `opspilot/investigator.py` 的 `run_investigation()`、`opspilot/domain/d3.py` 的 `execute_repair()` / `execute_deliver()`；N1-09 与 N1-11 的真实子进程事件在 `docs/evidence/vnext/m1-01/logs/n1-domain-and-process-events.jsonl`。

## 2. 输入受理和业务提交需要同一条数据库排序

`BEGIN IMMEDIATE` 是这份单 SQLite Domain 中的线性化边界。关键纠错在受理事务就提高 revision、登记 pending 高水位、取消当前 Plan 资格并阻断旧业务 Run；不能等旧模型响应后再处理。REPAIR/DELIVER 的最终事务再核对 TaskControl 和 Plan 绑定。若两个事务竞争，持有写锁并先提交的一方决定后续资格。

这证明的是同一 SQLite 文件内的事务先后，不是跨主机分布式锁，也没有声称跨进程 worker lease 已交付。

**源码/实验：** `opspilot/domain/task_control.py` 的 `admit_task_message()` / `abort_task()`；`opspilot/domain/d3.py` 的 `_assert_plan_control()`；N1-01、N1-10、N1-11。

## 3. 用户纠错是调查线索，不是可信 Evidence

更正内容必须原样持久化以保证可追溯，但其 provenance 为 `USER_INPUT_UNTRUSTED`。受信 Run 消费完整高水位时才清 pending、增加 applied revision；模型 Prompt 明确将这些内容单独标记为 `untrusted_user_corrections`。Gate 仍只由当前 TaskScope 下的 MCP Evidence 确定，不能从一句用户描述直接产生 Plan。

**源码/实验：** `apply_pending_critical_inputs()`、`_prompt_messages()`；真实模型 smoke 的 token/Function Calling/MCP 日志在 `docs/evidence/vnext/m1-01/logs/real-model-task-run.jsonl`。N1-10 还验证旧 Plan 的 revision 0 被拒，新 Plan 绑定 revision 2 与消息高水位。

## 4. 幂等身份和 outbox 解决受理响应丢失

调用者超时后无法知道本地事务是否已提交。持久 Command 保存 canonical digest 与原 `message_id/run_id`，同请求重试返回同一身份；不同正文复用 key 时明确冲突。outbox 事件与受理事实同事务写入，后续 projector 可重放而不靠内存通知。

**源码/实验：** `commands`、`domain_outbox` schema 与 `_find_idempotent_command()`；N1-01 用数据库 trigger 在写 Run 时注入 abort 证明回滚，N1-02 验证重放三 ID 和 `IDEMPOTENCY_CONFLICT`。

## 5. 迁移不能为“让旧数据通过”重算历史身份

旧 Task 只在新控制表没有 Message/Run 历史时安全回填为 revision 0；未知历史不升级为当前 revision，而是缺少控制记录并 fail closed。新的 Plan control 关系独立于冻结 Plan JSON，保持原 Plan hash、Intent digest、Ledger 事实。

**源码/实验：** `database.initialize()` 的 user_version 迁移；迁移测试重放两次并断言原 Plan hash 不变。兼容边界见 `docs/baseline/API_CONTRACT.md`。

## 方法参考与项目判断

《AI Agent Handbook》第 4–6 章是 Task/state、交互与持久化、受控 Action 的学习参照。这里选择 SQLite `BEGIN IMMEDIATE`、独立 control revision 与旧 Plan 绑定是对现有单体 Domain 的实现判断；章节本身不替代 S1 合同、安全评审或这些真实测试。
