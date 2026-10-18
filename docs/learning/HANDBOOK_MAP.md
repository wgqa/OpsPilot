# 《AI Agent Handbook》—OpsPilot vNext M1-01 对照地图

本地图从 M1-01 任务卡指定的第 4–6 章学习主题出发，建立“原理—源码—实验—表达”链路。章节作为学习参考，不把本项目选择冒充为白皮书的唯一实现规定。

| 学习主题 | OpsPilot 实现位置 | 可复现实验 | 表达材料 |
|---|---|---|---|
| Task 与状态的权威来源 | `opspilot/domain/task_control.py`：TaskControl/TaskRun；`opspilot/domain/d3.py`：最终业务守卫 | N1-09/10/11，`docs/evidence/vnext/m1-01/logs/n1-domain-and-process-events.jsonl` | `docs/learning/M1-01/INTERVIEW_QA.md` 第 1、3 题 |
| 对话输入与持久化 | `opspilot/domain/database.py`：sessions/messages/commands/task_runs/outbox；`admit_task_message()` | N1-01/02 原子回滚和幂等重放 | 第 2、4 题 |
| 受控 Action 与人工批准 | `opspilot/domain/d3.py` 中 Plan/Approval/Intent/REPAIR/DELIVER 的事务入口 | N1-10 stale Plan 阻断、N1-11 repair 后 abort 阻断 delivery、真实 D3 smoke | 第 1、5 题 |
| 运行恢复与事实溯源 | `opspilot/investigator.py` run-specific checkpoint；`task_run_inputs` 中的 `USER_INPUT_UNTRUSTED` | 真实 M1 TaskRun smoke 与跨进程旧 checkpoint 恢复 | 第 3、4 题 |

**贯通证据：** [M1-01 报告](../evidence/vnext/m1-01/REPORT.md)、[状态转换](../baseline/STATE_TRANSITIONS.md)、[学习笔记](M1-01/STUDY_NOTES.md)、[面试卡](M1-01/INTERVIEW_QA.md)。

## M1-02：应用服务、Outbox 与事件流

| 学习主题 | OpsPilot 实现位置 | 可复现实验 | 表达材料 |
|---|---|---|---|
| HTTP 身份与授权 | `opspilot/web/auth.py`：`issue_session`/`authenticate_session`/`verify_csrf`；`opspilot/web/app.py` 路由依赖 | WEB-01/02/05：真实进程双 Cookie jar、伪造 Header、CSRF、跨租户读拒绝 | `M1-02/STUDY_NOTES.md` 1；`INTERVIEW_QA.md` 1/2 |
| HTTP 命令幂等 | `task_control.create_task_with_initial_run()`：单事务 Task/Message/Command/Run/Outbox | WEB-03/04：同 key 重放、同 key 异摘要、Trigger 注入回滚 | Study Notes 2；Q&A 3 |
| 单实例 Run 推进 | `opspilot/web/worker.py`：OS lock/owner epoch/恢复；`domain.execution_budget.py`：活跃总时限 | OPS-01/02：真实子进程退出、checkpoint 恢复、虚拟时钟 | Study Notes 3；Q&A 4/5 |
| Durable Event 与 SSE | `opspilot/domain/events.py`：`write_outbox_event`/`project_outbox`/`reconcile_legacy_action_events`；`web.app.event_stream` | N2-01/02/03/04/05：commit 后杀进程、cursor 重连、只补事件、越权拒绝 | Study Notes 4；Q&A 6/7 |
| 真实模型与工具 | `opspilot/investigator.py`：`run_investigation(run_id=...)`，既有 MCP stdio Client/Server | WEB-07：真实 Provider ID、Function Calling、4 次 MCP tools/call、等待审批和零未批写入 | Study Notes 5；Q&A 8 |

**贯通证据：** [M1-02 报告](../evidence/vnext/m1-02/REPORT.md)、[API 合同](../baseline/API_CONTRACT.md)、[事件恢复合同](../baseline/EVENT_RECOVERY.md)、[学习笔记](M1-02/STUDY_NOTES.md)、[面试卡](M1-02/INTERVIEW_QA.md)。
