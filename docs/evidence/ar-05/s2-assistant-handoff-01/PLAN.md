# AR-05-S2-ASSISTANT-HANDOFF-01 — 离线验收记录

## 范围

基于 `codex/ar05-s1-d3-close-hf01@65612ff1cb72664c124ec5aa70cbcfa8f869eced`，验证统一 Assistant 会话中的原始 403 问题能够经显式确认进入现有 S2 调查，并在可信本地队列提交后从同一 Session 回查不可变 HandoffReceipt。

冻结问题：

> 我们的 API 返回 403，感觉是调用权限不够。帮我查一下，如果需要人工开通权限，帮我准备交接。

## 验证边界

- 使用正式 FastAPI、`ASSISTANT_V1` Worker、S2 `PROFESSIONAL_INVESTIGATOR` Worker、TaskBinding MCP、loopback HTTP 与隔离 SQLite。
- 使用确定性模型替身；只声明模型/测试夹具实际发出的工具提议，不评价真实 LLM 自主性。
- 用户提交到本地受控审查队列是本任务明确允许的隔离 Demo 写入。
- 禁止真实 Provider、生产 Scope/Policy/Grant 修改、企业队列、浏览器自动化及 main 合并。
- 复用 M2-03 已有 Handoff API、operation ID、Domain 事务与 Receipt；不新增业务实现或状态机。

## 冻结预期

调查前为 `HANDOFF_READY`，当前性为 `CURRENT`，无 Queue/Receipt/Outbox；仅在显式确认并提交后转为 `SCOPE_ESCALATED / PENDING_REVIEW`。该状态不代表 Scope 已授权、403 已恢复或订单业务已恢复。

反例和既有合同回归由 M2-03 与 S1 测试覆盖：非 owner/错误身份、跨租户/伪造来源、已失效事实、关键纠错、相同 Operation 改 payload、响应丢失重放、并发提交、聊天不等于提交、无副作用失败路径。
