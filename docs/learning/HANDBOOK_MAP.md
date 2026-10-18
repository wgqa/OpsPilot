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


## M1-04：自然语言驱动调查与关键纠错

| 学习主题 | OpsPilot 实现位置 | 可复现实验 | 表达材料 |
|---|---|---|---|
| 第 4 章：Task、Run 与图的边界 | `domain/task_control.py` 持久化初始 Message、`source_message_id` 与 `TaskRun`；`domain/investigation_context.py` 按可信绑定选择初始描述和已应用更正；`investigator.py` 在图 intake 处理明确的 S1 范围请求 | NL-01/03/04：真实 Edge 输入、403 Scope 请求安全等待、正式更正消费到新 Run | `M1-04/STUDY_NOTES.md` 1、2；`INTERVIEW_QA.md` 1、2、4 |
| 第 5 章：Prompt Context 与来源 Provenance | `investigator._prompt_messages()` 将用户输入标为 `USER_INPUT_UNTRUSTED`，记录 Message/Run/控制高水位、Prompt digest 与 Context Provenance；更正 Run 只复用 `domain.chat._current_evidence()` 验过版本的同 Task MCP Evidence | NL-A/NL-B 有不同 Prompt digest 和真实 MCP 工具顺序；NL-C 同时携带初始描述和更正，控制 revision=2 | Study Notes 2、3；Q&A 1、2、5 |
| 第 6 章：Evidence Gate 与受控动作 | `domain.d2.evaluate_evidence_gate()` 仍是唯一 Gate；`domain.d3.save_local_report(run_id=...)` 对新控制版本下的非 READY 结果作 Run 级守卫；UI 的普通聊天没有审批或动作入口 | NL-03/06：403/Scope 输入无模型与 Evidence；只读威胁输入后 Task/Plan/控制版本/动作计数不变。NL-05 复跑 N1-10/11 | Study Notes 3、4；Q&A 3、4、6 |

**贯通证据：** [M1-04 报告](../evidence/vnext/m1-04/REPORT.md)、[机器结果](../evidence/vnext/m1-04/RESULTS.json)、[案例集](../evidence/vnext/m1-04/CASES.md)、[学习笔记](M1-04/STUDY_NOTES.md)和[面试卡](M1-04/INTERVIEW_QA.md)。白皮书第 4–6 章参考链接见上方 M1-03 部分；章节作为对照阅读，不取代本仓库冻结合同。

## M1-05：Web 双角色审批与原调查图恢复

| 学习主题 | OpsPilot 实现位置 | 可复现实验 | 表达材料 |
|---|---|---|---|
| 第 4 章：Task、Run 与长程推进 | `domain/task_control.py::submit_web_plan_approval()` 在单事务中接受审批命令、唯一 `APPROVAL_RESUME` Run、可信恢复映射和 Outbox；`web/worker.py` 释放旧 Run 后只认领新 Run | APR-02/07：Trigger 注入验证全回滚；真实 API 在审批提交后退出，新进程恢复唯一队列 Run | `M1-05/STUDY_NOTES.md` 1、3；`INTERVIEW_QA.md` 2、4 |
| 第 5 章：状态与来源边界 | `get_approval_resume_link()` 在读取 checkpoint 前验证租户、Task、Plan、审批、控制 revision、原 Run 与 checkpoint thread；`investigator.run_investigation()` 用新 Run 身份恢复原 thread | APR-03/07：旧调查 Run 保持 `WAITING_APPROVAL`；同一 checkpoint 沿原 Plan 继续；提交后的进程退出后仍只有一个 REPAIR Ledger | Study Notes 1、2；Q&A 1、3 |
| 第 6 章：HITL、受控行动与交付 | `d3._submit_plan_approval_in_transaction()` 复用原 D3 授权规则；`get_task_outcome()` 从 Approval、Ledger、在线验证、冻结报告、DeliveryRecord 投影结果；Outbox 投影供 SSE 补发 | APR-03/04/09：独立 APPROVER 实际核对证据并拒绝/批准；S1 真实 HTTP 401→200；REJECTED 时无 ActionIntent/工单 | Study Notes 3、4；Q&A 2、4、5 |

**贯通证据：** [M1-05 报告](../evidence/vnext/m1-05/REPORT.md)、[机器结果](../evidence/vnext/m1-05/RESULTS.json)、[失败与修复记录](../evidence/vnext/m1-05/ATTEMPTS.md)、[学习笔记](M1-05/STUDY_NOTES.md)和[面试卡](M1-05/INTERVIEW_QA.md)。白皮书第 4–6 章参考链接见上方 M1-03 部分；章节只作分析框架，项目的事务与权限合同以仓库冻结规格为准。

## M1-06：首切片整体验收与交付冻结

| 白皮书章节 | 阅读问题 | OpsPilot 源码与实验 | M1-06 新鲜证据 |
|---|---|---|---|
| 第 4 章：任务、长程推进与完成证据 | 用户输入如何变为一个有来源、可中止、可恢复的 TaskRun？审批以后如何恢复原工作？ | `domain/task_control.py::create_task_with_initial_run()`、`submit_web_plan_approval()`、`get_approval_resume_link()`；`investigator.run_investigation()`；`web/worker.py::_process_run()` | M1FIN-02/03/05；N1-09/10/11；[M1-05 Edge Trace](../evidence/vnext/m1-06/runs/20261018T115200Z/m1-05/runs/20261018T115934Z/RESULTS.json) |
| 第 5 章：信息、状态与复用资产 | 哪些内容是用户线索，哪些是可引用的 Evidence？撤销或版本变化后如何排除派生上下文？ | `investigation_context.py`、`investigator._prompt_messages()`、`domain/chat.py::_current_evidence()`、ContextManifest 来源校验 | M1FIN-02/09；来源撤销与 v7 证据失效的 fresh pytest；NL-A/B 不同 Prompt digest 和相同可信绑定 |
| 第 6 章：受控行动与验证 | 模型建议何时可以转为有副作用的业务动作？怎样形成业务完成证据？ | `domain/d2.py::evaluate_evidence_gate()`；`domain/d3.py::execute_repair()`、`execute_deliver()`、`get_task_outcome()`；审批和 Intent 的事务守卫 | M1FIN-03/04/07；Config v7→v8、真实 HTTP 401→200、订单 `demo-order/CONFIRMED` 与单份 Delivery/Ticket 回执 |
| 第 8 章：状态存储与事件 | Graph 执行位置和业务事实为何要分开存？事件重放能否重做副作用？ | LangGraph SQLite Checkpoint、Domain SQLite `approval_resume_links`/ActionLedger；`domain/events.py` Outbox 投影 | M1FIN-03/07/08；响应丢失后的新 PID 恢复；849 个唯一 event_seq 及 N2-01 replay 回归 |
| 第 10 章：异步任务与自动化流程 | HTTP 受理、Worker 推进、浏览器刷新和 SSE 重连怎样闭合？ | `web/app.py` Session/Run/API 与 `event_stream()`；`web/worker.py::SingleInstanceWorker`；Vue `watchRun()` | M1FIN-01/08；真实 Edge refresh/restart；M1-04 两个 Worker PID，M1-05 四个 crash/recovery PID |
| 第 13 章：Agent 可观测性 | 怎样把一个用户结果追到模型、工具、业务提交、错误和成本？ | Provider trace 的 response ID、Prompt digest/usage；MCP Observation 与 Evidence ID；TaskRun/Plan/Checkpoint、ActionLedger、Verification、Outbox event_seq | M1FIN-02/03/07/08/11；`docs/evidence/vnext/m1-06/RUN_MANIFEST.json`、`RESULTS.json` 与原始 logs |
| 第 14 章：Agent 安全 | 如何防止 Prompt Injection、伪造角色、跨租户读取或状态竞争变成越权动作？ | `web/auth.py` trusted session / CSRF；`task_control.py` control revision；`d3.py` transactional authorization；`chat.py` source/ContextManifest validation | M1FIN-04/05/06/09；APR04 rejection、N1-09/10/11、cross-tenant 404、unlisted-Origin 403、只读威胁不写入 |

**贯通证据：** [M1-06 报告](../evidence/vnext/m1-06/REPORT.md)、[机器结果矩阵](../evidence/vnext/m1-06/RESULTS.json)、[原始证据索引](../evidence/vnext/m1-06/EVIDENCE_INDEX.md)、[源码学习笔记](M1-06/STUDY_NOTES.md)、[面试追问](M1-06/INTERVIEW_QA.md)。

白皮书对照章节：第 4 章[任务](https://github.com/aliyun/ai-agent-handbook/blob/main/02-build/%E7%AC%AC%204%20%E7%AB%A0%20%E4%BB%BB%E5%8A%A1%EF%BC%9A%E7%BC%96%E6%8E%92%E3%80%81%E9%95%BF%E7%A8%8B%E6%8E%A8%E8%BF%9B%E4%B8%8E%E5%8D%8F%E4%BD%9C%E6%B5%81%E8%BD%AC.md)、第 5 章[信息](https://github.com/aliyun/ai-agent-handbook/blob/main/02-build/%E7%AC%AC%205%20%E7%AB%A0%E4%BF%A1%E6%81%AF%EF%BC%9A%E4%B8%8A%E4%B8%8B%E6%96%87%E3%80%81%E7%8A%B6%E6%80%81%E4%B8%8E%E5%8F%AF%E5%A4%8D%E7%94%A8%E8%83%BD%E5%8A%9B%E8%B5%84%E4%BA%A7.md)、第 6 章[行动](https://github.com/aliyun/ai-agent-handbook/blob/main/02-build/%E7%AC%AC%206%20%E7%AB%A0%20%E8%A1%8C%E5%8A%A8%EF%BC%9A%E5%8F%97%E6%8E%A7%E6%89%A7%E8%A1%8C%E3%80%81%E9%AA%8C%E8%AF%81%E5%8F%8D%E9%A6%88%E4%B8%8E%E4%BA%A4%E4%BB%98%E5%87%86%E5%A4%87.md)、第 8 章[状态存储](https://github.com/aliyun/ai-agent-handbook/blob/main/03-run/%E7%AC%AC%208%20%E7%AB%A0%20Agent%20状态存储与语义资产.md)、第 10 章[异步任务](https://github.com/aliyun/ai-agent-handbook/blob/main/03-run/%E7%AC%AC%2010%20章%20%20Agent%20异步任务与自动化流程.md)、第 13 章[可观测性](https://github.com/aliyun/ai-agent-handbook/blob/main/04-governance/%E7%AC%AC%2013%20章%E3%80%80Agent%20的可观测性.md)和第 14 章[安全](https://github.com/aliyun/ai-agent-handbook/blob/main/04-governance/%E7%AC%AC%2014%20章%20Agent%20安全.md)。这些章节是阅读对照，不取代 OpsPilot v0.3 合同与冻结实施基线。
