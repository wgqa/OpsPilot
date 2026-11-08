# 简历表述候选与面试讲解索引

以下内容是可编辑候选，不是已签署的简历结论。每条把真实模型、确定性本地 Demo 和未验证部分分开。

## 简历表述候选

### 候选 A：连续技术支持 Assistant

> 基于 FastAPI、LangGraph 与 MCP 构建连续技术支持 Assistant，将协议知识、用户提供的配置材料及 TaskBinding 范围内的订单回调观察接入同一 Session；在一次隔离 DeepSeek Campaign 中完成协议比较、配置分析和当前 Event 调查，并按冻结标准保留 J2-02 的部分失败。

证据边界：最近 Campaign 共 9 次 DeepSeek 请求、11 次实际 MCP 调用。J1-01、J1-02、J2-01 达标；J2-02 正确保留目标 Event 的未知状态，但草稿包含没有行动回执支持的后续承诺，故整体结果不是全通过。应用估算 USD 0.024332，不代表供应商发票。见 [真实 Campaign 报告](../r1-j2-live-recheck-02/LIVE_REPORT.md)。

### 候选 B：受控 S1 修复与验证

> 在隔离 Demo 中实现并验证 S1 401 故障的受控处置链：独立审批和审批后事实复核、幂等 ActionIntent、配置 CAS、同一业务身份 HTTP 401→200、VerificationReceipt、冻结报告及独立交付；同时覆盖事实变化、主体禁用和来源失败等拒绝路径。

证据边界：确定性模型/隔离 Domain 与本地 HTTP，不是生产修复，也没有证明真实 LLM 自主完成该写入链。见 [S1 报告](../../ar-05/s1-d3-close-01/REPORT.md) 和 [S1 Results](../../ar-05/s1-d3-close-01/RESULTS.json)。

### 候选 C：受控 S2 诊断与交接

> 在隔离 Demo 中把同 Session 的用户问题接入既有 S2 Investigator；使用真实本地 HTTP/Authz 观察形成 403/Scope 不足诊断，经显式用户确认后产生幂等 Queue、HandoffReceipt 与 Outbox，并准确停在 `SCOPE_ESCALATED / PENDING_REVIEW`。

证据边界：没有扩大 Scope、没有证明 403 恢复，未连接企业队列；交接链由确定性本地旅程证明。见 [S2 报告](../../ar-05/s2-assistant-handoff-01/REPORT.md) 和 [S2 Results](../../ar-05/s2-assistant-handoff-01/RESULTS.json)。

## 面试讲解顺序

1. **用户目标与模型选择：** 从用户问协议差异开始，说明模型在 J1-01 实际发现、比较协议及读取资料；不要以工具数量代替价值。
2. **Context 与连续性：** J1-02 复用同 Session 的协议背景分析 JSON；用户材料仍是未验证输入。解释 Context 如何装配历史、当前用户目标和来源。
3. **观察与纠错：** J2-01 取得 `event-current` 的 Delivery/Receiver 观察；J2-02 接受 Event 更正并把 `event-previous` 当前 Receiver 留为未知。拿两个 Event 的不同 Evidence 讲清楚范围。
4. **真实失败：** 展示客户草稿的无回执跟进承诺。说明事实判断正确不代表最终交付合格；随后说明原始请求体字节不在归档中，按冻结合同停止重放，重复性仍未知。
5. **受控业务副作用：** 讲 S1 如何在可信 Domain 中把调查结果变为经审批、复核、CAS、在线验证和交付的隔离 Demo 因果链；明确受控状态转换不由模型文字授权。
6. **交接而非修复：** 讲 S2 的 403/Authz DENY、显式提交与 `PENDING_REVIEW`，并说明未授 Scope、未修复 403。
7. **工程边界与取舍：** 展示 Runtime Grant 发送前持久预留、Session/TaskBinding 隔离及 MCP/Domain 职责；把 59/60 和旧 Runner 0/3 当作保留的技术债，不包装为全绿。

## 源码索引（当前候选 `3659393...`）

| 主题 | 入口 |
|---|---|
| Assistant Provider 工厂和请求循环 | [`create_assistant_model`](../../../../opspilot/assistant.py#L931)、[`Loop.context`](../../../../opspilot/assistant.py#L1244)、[`Loop.awrap_model_call`](../../../../opspilot/assistant.py#L1401)、[`_run_assistant`](../../../../opspilot/assistant.py#L2173) |
| 发送上下文与持久授权 | [`Runtime Grant dispatch reserve`](../../../../opspilot/domain/assistant_runtime_grant.py#L1133)、[`runtime_provider.dispatch_context`](../../../../opspilot/runtime_provider.py#L17) |
| 正式产品入口 | [`POST assistant message`](../../../../opspilot/web/app.py#L692)、[`run_worker`](../../../../opspilot/web/worker.py#L583) |
| 工具选择与可信结果读取 | [`assistant_mcp.py`](../../../../opspilot/assistant_mcp.py#L25)、[`propose_controlled_auth_investigation`](../../../../opspilot/domain/assistant.py#L308)、[`read_session_professional_outcomes`](../../../../opspilot/domain/assistant.py#L519) |
| S1 权限、Intent、复核与 CAS | [`submit_web_plan_approval`](../../../../opspilot/domain/task_control.py#L353)、[`get_or_create_action_intent`](../../../../opspilot/domain/d3.py#L932)、[`revalidate_approved_plan`](../../../../opspilot/domain/d3.py#L1170)、[`execute_repair`](../../../../opspilot/domain/d3.py#L1525) |
| S2 诊断与回执 | [`freeze_handoff_draft`](../../../../opspilot/domain/s2_diagnosis.py#L621)、[`submit_s2_handoff`](../../../../opspilot/domain/s2_handoff.py#L243)、[`get_s2_handoff_outcome`](../../../../opspilot/domain/s2_handoff.py#L440) |
| 前端可信结果状态 | [`App.vue`](../../../../frontend/src/App.vue#L1797) 中恢复和 HandoffReceipt 展示 |

相关实证入口：[R1 集成报告](../r1-final-integration-01/INTEGRATION_REPORT.md)、[真实 J1/J2 报告](../r1-j2-live-recheck-02/LIVE_REPORT.md)、[S1 本地闭环](../../ar-05/s1-d3-close-01/REPORT.md)、[S2 本地交接](../../ar-05/s2-assistant-handoff-01/REPORT.md)。

## 不应使用的表述

- 不说“生产系统已修复 API 401/403”；证据来自隔离本地 Demo。
- 不说“真实模型自主完成了 S1 修复或 S2 交接”；未验证。
- 不说“客户草稿完全可靠”；J2-02 为 PARTIAL。
- 不说“Memory 或 Skill 已证明提升 Agent 质量”；真实样本有限且有失败。
- 不说“R1-INTERACTIVE 已通过”或“全量 pytest 全绿”；浏览器未运行，完整测试未在当前 SHA 执行。
