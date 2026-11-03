# AR-03-MATERIAL-LIVE-01-RESUME-01 — 真实执行结果

**最终状态：`BLOCKED_BEFORE_PROVIDER_SEND`**
**执行身份：** `AR-03-MATERIAL-LIVE-01-RESUME-01`
**本次源码候选：** `6cd3a34187f4a480a5e840a84d30e154cb536672`
**远端 main：** `ec8c3582f6d145eec9979c43607302731411ead8`（未修改）

## 用户旅程结果

正式 FastAPI 接受了冻结的 `MAT-01-PROTOCOL-EXCERPT` 用户消息，并创建 `ASSISTANT_V1` Run。提交消息摘要与冻结 CASES 输入摘要一致。

- Session：`session-bff6523b-d260-4958-bc41-82462087ad57`
- Message：`message-f08a6307-06b9-48b9-a123-bc1832ca08e1`
- Run：`run-7af74a92-094b-463c-bccf-5ddf5dc5b74b`
- TaskBinding：无（符合该用例）
- Run：`FAILED`；Chat Attempt：`FAILED`；没有 Provider Completion 或 Usage。
- 用户仅收到程序生成的“调查未完成”通知，不是模型答案。
- 模型没有选择工具；MCP `tools/call` 为 0。Campaign 准备时的本地 Receiver fixture 记录为 `202/ACKNOWLEDGED + QUEUED`，属于测试准备数据，不是 Agent Observation。

## 冻结 Gold 状态

| Gold | 状态 | 结果 |
|---|---|---|
| MAT-01 协议原文 | `FAIL` | 用户消息已受理；Runner 在真实 Provider 发送前失败，未形成模型调查或回答。此状态是执行基础设施失败，不评价模型回答质量。 |
| MAT-02 未绑定用户材料 | `NOT_RUN` | 第一项失败后按停止条件未执行。 |
| MAT-03 不完整日志 | `NOT_RUN` | 未执行。 |
| MAT-04 同 Event Receiver QUEUED | `NOT_RUN` | 未执行。 |
| MAT-05 同 Event Receiver PROCESSED | `NOT_RUN` | 未执行。 |
| MAT-06 Skill OFF | `NOT_RUN` | 未执行。 |
| MAT-06 Skill ON | `NOT_RUN` | 未执行。 |

## Provider、预算与副作用

| 指标 | 观察结果 |
|---|---|
| HTTPX Provider 传输尝试 | 0；没有创建 `PROVIDER_HTTP.jsonl` |
| Provider Completion / Usage | 无；无响应 ID、无 Usage |
| Durable Provider reservation | 1 次，USD 0.645600，`usage_state=UNKNOWN`，未结算 |
| Campaign 账本 | `provider_used=1`（预留计数），MCP=0，状态 `BUDGET_BREACH`；预留保留 |
| 外部 MCP | 0 次 |
| 业务写入 | 0；S3 Diagnosis、Plan、Approval、ActionIntent、Ledger、Verification Receipt、Delivery Record、S2/S3 Handoff 队列及回执均为 0 |
| 旧实验账本与证据 | claim、RESULTS、TRACE、BUDGET_LEDGER 的 SHA-256 与运行前快照一致 |

应用账本按保守规则留下 UNKNOWN 预留；这不是 Provider 实际收费凭证。未释放或重置预留，也未尝试重复执行。一次性 claim 已消费，本候选不再启动请求。

## 失败归因

1. Runner 的 `_CampaignState.begin()` 在 `docs/evidence/ar-03/material-live-01/run_live.py:356` 读取 `PRICE_VERSION`。该名字只在 `_validate_preflight()` 的局部作用域导入，未定义为 Runner 模块全局值，所以在 `handle_async_request()` 调用时抛出 `NameError`。异常发生在 `request_count` 增加、Provider HTTP 日志写入和底层 `AsyncHTTPTransport.handle_async_request()` 之前。`assistant_calls`/Task Run 因保守错误处理被持久标为 UNKNOWN/FAILED，保留了 USD 0.645600 预留。
2. 随后的 `_audit_case()` 在 `docs/evidence/ar-03/material-live-01/run_live.py:711` 读取 `assistant_calls.error_code`；当前 `assistant_calls` 表结构（`opspilot/domain/assistant.py:18` 起）没有该列。这引发次生 `KeyError('error_code')`，使 Runner 的汇总停止原因没有保留最初的 `PRICE_VERSION` NameError。

这两项均为本次实际执行触发的 Runner 缺陷。本轮只记录根因，未实施修复，也未消费第二次 claim。

## 证据保存

原始 TRACE、RESULTS、账本、独立 Domain/Checkpoint、已消费 claim 和全部测试日志保留在本地私有证据区，并已生成 SHA-256 清单。原始材料未纳入公开 Git 提交。MockTransport 与恢复相关免费回归为 24/24；这只证明离线路径，不代表真实模型执行成功。

## 六问摘要

1. **用户变化：** 用户问题通过正式 API 持久化，但没有获得模型调查答案。
2. **Agent 决策：** 没有真实模型 Completion，因此没有可评价的自主工具或调查决策。
3. **观察驱动：** 只记录了准备阶段的本地 fixture；Agent 未取得业务 Observation。
4. **新增约束与合法任务影响：** 一次性授权和预算门禁正常阻止重放；合法调查在 Provider 传输包装器异常前无法开始。无业务写入。
5. **简化结果：** 本轮无业务架构变化，只增加了精确的一次性授权接线。
6. **证据与停止线：** HTTPX 实际传输次数为 0，账本仍保留 UNKNOWN 预留；依据冻结停止条件，本轮在第一个 MAT-01 失败处停止，等待独立裁决。

**尚未验证：** 七项 Gold 的真实模型效果、Skill ON/OFF 差异、协议引用质量、QUEUED/PROCESSED 不同行为。不得将离线测试或本地 fixture 记为这些项目的通过。
