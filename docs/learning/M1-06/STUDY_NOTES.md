# M1-06 源码学习笔记：从输入到有回执的受控完成

## 先看合同，再追代码

M1-06 冻结的用例与 PASS 标准在 `docs/evidence/vnext/m1-06/ACCEPTANCE_PLAN.md`。总体数据和权限合同以仓库 `docs/handoff/vnext/OpsPilot-vNext-v0.3-product-architecture-contract.md`、`docs/baseline/` 中的 API、状态、事件和授权文件为准。M1-06 是一次首切片整体验收；它没有增加新的运行时或业务能力。

建议按下面顺序阅读源码：

1. **消息怎么变成受控工作：** `opspilot/domain/task_control.py::create_task_with_initial_run()` 将可信身份、Task 绑定、初始 Message、Run、命令与事件放进 Domain；`claim_task_run()` 和 `apply_pending_critical_inputs()` 决定 Run 是否仍有资格推进。`opspilot/domain/investigation_context.py` 从持久 Message 与控制 revision 装配调查线索。
2. **模型看到什么：** `opspilot/investigator.py::_prompt_messages()` 将用户消息、来源 ID/digest 和可信事实分层；`run_investigation()` 运行 LangGraph 并把实际调用写入 Domain trace。`opspilot/domain/chat.py::_current_evidence()` 每次为聊天重验当前版本 Evidence 和历史回答来源。用户文本可以提示调查方向，但不设置 tenant、actor、route、权限或 Gate。
3. **只读工具与证据：** MCP Client 调用 scoped MCP Server；Server 从 TaskBinding 读取对象范围，Domain 再核验资源归属。`opspilot/domain/d2.py::evaluate_evidence_gate()` 从 Evidence 返回确定性 Gate。Chat 的 `CHAT_READONLY` 是另一条 Run，不消费业务 Task 的 Plan/审批/动作资格。
4. **计划、审批和提交：** `opspilot/domain/d3.py::execute_repair()` 与 `execute_deliver()` 只接受已持久化 Intent ID，并在 SQLite 事务中重核资格和动作身份；REPAIR 改配置后还要同身份在线验证。验证收据与报告冻结后，独立 DELIVER 写入 TicketEntry。
5. **Web 恢复与事件：** `opspilot/domain/task_control.py::submit_web_plan_approval()` 原子写 Approval、一个 `APPROVAL_RESUME` Run、原 checkpoint 映射和 Outbox。`get_approval_resume_link()` 在恢复 checkpoint 前重核 Domain 权限与来源。`opspilot/web/worker.py` 使用单实例进程锁恢复队列；`opspilot/web/app.py::event_stream()` 与 `opspilot/domain/events.py` 提供稳定序号事件重放。
6. **预算和故障边界：** `opspilot/domain/execution_budget.py` 计 active interval，审批等待不计时；`tests/test_d4_recovery.py` 保证无 Domain 回执的终端 checkpoint 不冒充外部动作成功。

## 一条新鲜完整 Trace

选读证据：`docs/evidence/vnext/m1-06/runs/20261018T115200Z/m1-05/runs/20261018T115934Z/RESULTS.json`。

1. `support-a` 的浏览器输入“昨晚凭证轮换后，订单接口开始返回 HTTP 401……”生成 Task `task-97c83c8d-703f-4a94-aff1-31e95b98604a`。可信绑定固定为 `orders-demo / integration-a / principal-a / /api/orders/demo-order`。
2. LangGraph 的来源 Run `run-47da6233-ae63-4f7f-80a9-bc0b4554b124` 使用真实 Provider `deepseek-flash` 五次。每次均有响应 ID和真实 usage。MCP 返回 Config v7/cred-v1、Policy v3 接受 cred-v2、Principal ENABLED v2、Probe HTTP 401；Gate 由这些类型化 Evidence 得出 READY。
3. Domain 生成 Plan hash `43de79c0ec15b573bd5621a8b73d2a583392802503e7310ebbd3c1eb170b6aa2`。Graph checkpoint 停在审批；此时业务写入计数为 0。独立 `approver-a` 在浏览器审查同一 Plan 并提交 Approval `approval-79835a87-6aa6-44ab-9e83-32b6b8502827`。
4. Domain 同一提交事务产生 `APPROVAL_RESUME` Run `run-c4f81a6e-3a01-47e7-9eb2-7b1cfbc36d3e`，并引用原 checkpoint thread `opspilot-b3459a89-2aaf-4ef7-935c-d6e609c88056::run-47da6233-ae63-4f7f-80a9-bc0b4554b124`。恢复依据是 Domain link，而不是另造 Plan。
5. 审批 HTTP 响应丢失时 API PID 32416 以预设故障码 86 退出。新进程重读已提交 Approval 和唯一 Resume Run。随后 REPAIR ActionIntent / Ledger 提交，Config CAS 从 v7 到 v8、cred-v1 到 cred-v2。REPAIR HTTP 响应丢失时 PID 14648 以故障码 87 退出；PID 17240 的新进程从权威 Domain Ledger 继续。
6. 同 service/integration/principal/route 的实际业务 HTTP 返回 200；响应包含 `order_id=demo-order` 与 `status=CONFIRMED`。Domain 写入 VerificationReceipt `verification-85cda665-d221-4c28-a770-e4524b4df292`，随后冻结 Report `report-5491fc72-4a74-461d-a9b6-d0d79c144e0f`，再用独立 DELIVER Intent/Ledger 写入 DeliveryRecord `delivery-afd9e019-791c-4d4d-89cb-221ee4f8dedd` 和 `INC-A-001` TicketEntry `ticket-entry-a410366e-c1e2-465a-99c3-489d1dad0745`。
7. 最终 Domain 计数：两条 Intent/ActionLedger（REPAIR 与 DELIVER 各一）、两条独立 Permission、一条验证、一份冻结报告、一条交付记录和一条工单回执。Task 事件投影有 849 条、`event_seq` 唯一且递增（2–851）；只读对账发现 846 有一个游标间隙，同时 850 条匹配 Outbox 事实全部有投影，因此没有声称序号无间隙或遗漏已提交事件。详情见 `docs/evidence/vnext/m1-06/runs/20261018T115200Z/logs/sse-projection-audit.json`.

上述是有限的 loopback Demo S1 闭环，不代表面向生产的 IAM、外部工单系统或分布式 exactly-once。

## 这轮证据支持什么

- Edge 的三轮聊天有五次真实 Provider response；刷新并重启 API 后，`BLUE-ORBIT` 和历史消息仍可恢复。
- NL-A / NL-B 使用同一可信绑定、不同初始消息和 Prompt digest。自然语言的“怀疑主体禁用”仍是未信任线索；当前 MCP Evidence 显示主体 ENABLED、接口 401。
- 正式 `CORRECT_TASK_INPUT` 提升控制 revision 并让旧 Plan CANCELLED；新 Run 要重新取得当前证据。超出 S1 的 403/Scope 请求在模型、MCP、Evidence 之前安全停止。
- 审批期间聊天与 TaskControl、Plan、审批或 ActionIntent 分离。实际 M1-05 记录的活跃预算从 7,877 ms 到 7,877 ms，deadline 600,000 ms。
- 首次真实 M1-04 浏览器失败来自 E2E 页面 selector 过时；修复发生在测试 helper。失败日志保留，成功结果在新 DB 中生成。没有产品 runtime 修复。
- M1-06 对 Memory 只核对 D5 的来源撤销与版本失效；D5 固定通用 Memory 的适用性问题仍在。D6 E10 仍 PARTIAL，D7 首次 E01 失败与 61/64 记录仍保留。

## 已交付与未交付边界

**本切片已实现并在本轮复验：** S1 固定订单路由的真实 Provider/MCP 只读调查；带消息来源和可信绑定的持久 Task/Run；确定性 Evidence Gate；双角色 Web 审批和原 LangGraph checkpoint 恢复；有独立 Intent/Ledger 的 REPAIR/DELIVER；同身份在线 HTTP 验证、冻结报告、工单回执；单实例 Worker、SQLite Domain/Outbox、SSE history/replay；Task 终止/关键纠错、来源撤销和版本失效防线。

**本切片没有交付：** M2 的 S2 场景；M3 的长期 Context 压缩与 Memory 效果验证；M4 的独立 P0 整体验收；生产级 IAM；分布式 Worker/队列和分布式 exactly-once；多模型 Gateway、多 Agent 或通用 Agent 平台。Demo 只验证 loopback 本地 S1，不代表接入真实生产业务 API。D5 Memory 固定且通用，D6 E10 仍 PARTIAL，均作为已知限制保留。

## 白皮书对照阅读

仓库的 [HANDBOOK_MAP.md](../HANDBOOK_MAP.md) 已将第 4、5、6、8、10、13、14 章映射到源码与新鲜实验。重点可读：

- 第 4 章“任务”：查看 Task/Run、LangGraph interrupt、独立 resume Run 与业务完成回执。 [原文](https://github.com/aliyun/ai-agent-handbook/blob/main/02-build/%E7%AC%AC%204%20%E7%AB%A0%20%E4%BB%BB%E5%8A%A1%EF%BC%9A%E7%BC%96%E6%8E%92%E3%80%81%E9%95%BF%E7%A8%8B%E6%8E%A8%E8%BF%9B%E4%B8%8E%E5%8D%8F%E4%BD%9C%E6%B5%81%E8%BD%AC.md)
- 第 5 章“信息”：阅读 Prompt 来源、Session/Task State、ContextManifest 和 Memory 失效机制。 [原文](https://github.com/aliyun/ai-agent-handbook/blob/main/02-build/%E7%AC%AC%205%20%E7%AB%A0%E4%BF%A1%E6%81%AF%EF%BC%9A%E4%B8%8A%E4%B8%8B%E6%96%87%E3%80%81%E7%8A%B6%E6%80%81%E4%B8%8E%E5%8F%AF%E5%A4%8D%E7%94%A8%E8%83%BD%E5%8A%9B%E8%B5%84%E4%BA%A7.md)
- 第 6 章“行动”：对照模型建议、确定性 Gate、审批、Intent、在线验证和独立交付。 [原文](https://github.com/aliyun/ai-agent-handbook/blob/main/02-build/%E7%AC%AC%206%20%E7%AB%A0%20%E8%A1%8C%E5%8A%A8%EF%BC%9A%E5%8F%97%E6%8E%A7%E6%89%A7%E8%A1%8C%E3%80%81%E9%AA%8C%E8%AF%81%E5%8F%8D%E9%A6%88%E4%B8%8E%E4%BA%A4%E4%BB%98%E5%87%86%E5%A4%87.md)
- 第 8 章“状态存储”：对照 LangGraph Checkpoint 与 Domain SQLite 的职责。 [原文](https://github.com/aliyun/ai-agent-handbook/blob/main/03-run/%E7%AC%AC%208%20%E7%AB%A0%20Agent%20%E7%8A%B6%E6%80%81%E5%AD%98%E5%82%A8%E4%B8%8E%E8%AF%AD%E4%B9%89%E8%B5%84%E4%BA%A7.md)
- 第 10 章“异步任务”：查看 FastAPI 受理、单实例 Worker、SSE history/replay。 [原文](https://github.com/aliyun/ai-agent-handbook/blob/main/03-run/%E7%AC%AC%2010%20章%20%20Agent%20异步任务与自动化流程.md)
- 第 13 章“可观测性”：用 Provider response ID、Prompt digest、MCP observation、event_seq 和 Domain 回执串出可核对 Trace。 [原文](https://github.com/aliyun/ai-agent-handbook/blob/main/04-governance/%E7%AC%AC%2013%20章%E3%80%80Agent%20的可观测性.md)
- 第 14 章“安全”：检查可信身份、来源分级、权限逐次校验、跨租户边界和 Prompt Injection 防护。 [原文](https://github.com/aliyun/ai-agent-handbook/blob/main/04-governance/%E7%AC%AC%2014%20章%E3%80%80Agent%20安全.md)
