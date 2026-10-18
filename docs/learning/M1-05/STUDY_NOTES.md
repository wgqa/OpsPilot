# M1-05 源码学习笔记

本阶段把《AI Agent Handbook》第 4–6 章用于检查长程任务、状态来源和人工受控行动。白皮书提供概念框架；审批资格、TaskControl、业务动作和当前安全边界仍由仓库合同与 Domain 代码定义。

## 1. 一个审批是一次原子受理，不是一个按钮事件

`POST /api/tasks/{task_id}/plans/{plan_hash}/approval` 先经过服务端 Cookie 身份、Origin、CSRF 和 APPROVER 角色校验。`task_control.submit_web_plan_approval()` 随后在一个 `BEGIN IMMEDIATE` 事务中重新验证 TaskControl revision、来源调查 Run、Plan 资格和当前资源版本，并写入 Approval、幂等 Command、唯一 `APPROVAL_RESUME` Run、恢复映射与两个 Outbox 事件。事务中的 SQLite Trigger 故障测试证明，任何一个后续插入失败都会一并回滚批准和入队。

源码入口：`opspilot/web/app.py::post_plan_approval`、`opspilot/domain/task_control.py::submit_web_plan_approval`、`opspilot/domain/d3.py::_submit_plan_approval_in_transaction`。定向证据见 [`pytest-approval-directed.txt`](../../evidence/vnext/m1-05/pytest-approval-directed.txt) 中的 APR-02 测试。

## 2. 新 Run 身份与旧 Graph checkpoint 是两种不同身份

原调查 Run 在 `WAITING_APPROVAL` 结束执行占用。审批事务创建的新 Run 以自己的 Run ID 接受 Worker fence、控制 revision 和重试状态；`approval_resume_links` 才能把它映射到可信绑定的原 checkpoint thread。恢复前，Domain 会检查来源 Run、Plan、审批决定、控制版本、Tenant 和 Task；随后 Investigator 确认 checkpoint 中的 Plan hash、stage 和 interrupt 与数据库一致。它不会重新调查或生成第二个 Plan。

恢复时把审批标记同时写入 LangGraph `Command.update` 和被中断节点的返回值，曾触发同一 state channel 的重复写入错误。真实崩溃恢复尝试在 [`runs/20261018T095638Z/RESULTS.json`](../../evidence/vnext/m1-05/runs/20261018T095638Z/RESULTS.json) 留有失败快照；修复后 [`runs/20261018T100615Z/RESULTS.json`](../../evidence/vnext/m1-05/runs/20261018T100615Z/RESULTS.json) 记录原 Run、新 Run、checkpoint thread、唯一 REPAIR/DELIVER 回执和最终交付。入口见 `opspilot/domain/task_control.py::get_approval_resume_link` 与 `opspilot/investigator.py::run_investigation`。

## 3. Commit 后进程退出时，Ledger 与 checkpoint 的先后差异必须可恢复

真实 Edge smoke 在审批事务 COMMIT 后、HTTP 响应前退出 API 进程，子进程退出码为 86；数据库仍只有一条 Approval、一条恢复链接，没有 ActionIntent。随后 Worker 在 REPAIR COMMIT 后、checkpoint 更新前退出，退出码为 87；中间快照显示配置 CAS 已从 v7 到 v8，只有一条 REPAIR Ledger，没有 Verification、Report 或 Delivery。新 Worker 使用相同 ActionIntent 读取已提交回执并继续验证、冻结报告和交付，最终计数仍为 REPAIR=1、DELIVER=1、工单=1。

证据见 [`REPORT.md`](../../evidence/vnext/m1-05/REPORT.md) 的 APR-07，原始 API/浏览器日志在 `docs/evidence/vnext/m1-05/runs/20261018T100615Z/logs/`。这说明 Graph checkpoint 记录执行进度，Domain 回执裁决副作用是否已发生。

## 4. 用户结果由回执构成，Outbox 只负责可靠呈现

`get_task_outcome()` 的 `DELIVERED` 来自持久 DeliveryRecord；Task 的 `COMPLETED` 状态本身不会证明业务 API 已恢复或工单已交付。只有相同 service、integration、principal 与固定 route 的在线 HTTP 200，以及 `order_id=demo-order`、`status=CONFIRMED` 进入 VerificationReceipt 后，才可冻结恢复报告并执行独立 DELIVER。SSE 从同事务写入的 Outbox 投影；重连补事件不会再次执行业务动作。

失败测试 [pytest-full-attempt-01-temp-acl.txt](../../evidence/vnext/m1-05/pytest-full-attempt-01-temp-acl.txt) 不是业务断言失败，而是 Windows Temp 权限问题；最后的全量结果使用仓库 `.runtime` 临时目录，详见 [`REPORT.md`](../../evidence/vnext/m1-05/REPORT.md)。本 Demo 使用单实例 Worker 和本地 SQLite，不能据此宣称多进程分布式执行或生产级 IAM。
