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

## M1-03：Vue 对话工作台与持久只读聊天

| 学习主题 | OpsPilot 实现位置 | 可复现实验 | 表达材料 |
|---|---|---|---|
| 第 4 章：任务与异步推进 | `opspilot/domain/task_control.py` 的 Session/Task/Run 受理与恢复；`opspilot/web/worker.py` 的 Run 分派；`frontend/src/App.vue` 的 `watchRun()` | `CHAT-01/02`：无 Task 会话连续聊天；另一个 INVESTIGATE Run 等待审批时继续只读追问 | `M1-03/STUDY_NOTES.md` 1；`INTERVIEW_QA.md` 1/2 |
| 第 5 章：Context 来源与可复用资产 | `opspilot/domain/chat.py`：`prepare_chat_attempt()`、来源重核、`ContextManifest`；撤销 Memory / 失效回答不注入 | `CHAT-04`：来源逐项记录、历史记忆撤销后排除；`tests/test_m1_chat.py` | Study Notes 2；Q&A 3 |
| 第 6 章：受控动作与验证 | `opspilot/web/worker.py` 的 `CHAT_READONLY` 独立路径；`opspilot/domain/chat.py` 只写聊天记录；任务调查继续由既有 LangGraph/D2/D3 控制 | `CHAT-03`：真实聊天遇到“我批准了/立即修改”仍保持 WAITING_APPROVAL，动作表不变 | Study Notes 3；Q&A 4 |
| 第 8 章：事件、Checkpoint 与持久状态 | `opspilot/domain/database.py` v3 聊天 Attempt/Manifest/Chunk/Answer；`domain/events.py` 安全 SSE 投影；`chat_run_answers` 一 Run 一回执 | `CHAT-05/06`：幂等、Chunk 游标、增量期间刷新、服务重启后恢复；真实 Edge 截图与 `RESULTS.json` | Study Notes 4；Q&A 5/6 |
| 第 10 章：同步/异步边界 | FastAPI 只受理消息，单实例 Worker 调真实 Provider；前端 EventSource + Run/Chunk 恢复 | `UI-01/02`：浏览器交互、Origin/CSRF、角色和租户访问、SSE 重连与服务重启 | Study Notes 5；Q&A 2/6 |

**贯通证据：** [M1-03 报告](../evidence/vnext/m1-03/REPORT.md)、[机器结果](../evidence/vnext/m1-03/RESULTS.json)、[学习笔记](M1-03/STUDY_NOTES.md)、[面试卡](M1-03/INTERVIEW_QA.md)。本阶段采用的白皮书映射参考 [第 4 章](https://github.com/aliyun/ai-agent-handbook/blob/main/02-build/%E7%AC%AC%204%20%E7%AB%A0%20%E4%BB%BB%E5%8A%A1%EF%BC%9A%E7%BC%96%E6%8E%92%E3%80%81%E9%95%BF%E7%A8%8B%E6%8E%A8%E8%BF%9B%E4%B8%8E%E5%8D%8F%E4%BD%9C%E6%B5%81%E8%BD%AC.md)、[第 5 章](https://github.com/aliyun/ai-agent-handbook/blob/main/02-build/%E7%AC%AC%205%20%E7%AB%A0%20%E4%BF%A1%E6%81%AF%EF%BC%9A%E4%B8%8A%E4%B8%8B%E6%96%87%E3%80%81%E7%8A%B6%E6%80%81%E4%B8%8E%E5%8F%AF%E5%A4%8D%E7%94%A8%E8%83%BD%E5%8A%9B%E8%B5%84%E4%BA%A7.md)、[第 6 章](https://github.com/aliyun/ai-agent-handbook/blob/main/02-build/%E7%AC%AC%206%20%E7%AB%A0%20%E8%A1%8C%E5%8A%A8%EF%BC%9A%E5%8F%97%E6%8E%A7%E6%89%A7%E8%A1%8C%E3%80%81%E9%AA%8C%E8%AF%81%E5%8F%8D%E9%A6%88%E4%B8%8E%E4%BA%A4%E4%BB%98%E5%87%86%E5%A4%87.md)、[第 8 章](https://github.com/aliyun/ai-agent-handbook/blob/main/03-run/%E7%AC%AC%208%20%E7%AB%A0%20Agent%20%E7%8A%B6%E6%80%81%E5%AD%98%E5%82%A8%E4%B8%8E%E8%AF%AD%E4%B9%89%E8%B5%84%E4%BA%A7.md)和[第 10 章](https://github.com/aliyun/ai-agent-handbook/blob/main/03-run/%E7%AC%AC%2010%20%E7%AB%A0%20%20Agent%20%E5%BC%82%E6%AD%A5%E4%BB%BB%E5%8A%A1%E4%B8%8E%E8%87%AA%E5%8A%A8%E5%8C%96%E6%B5%81%E7%A8%8B.md)。
