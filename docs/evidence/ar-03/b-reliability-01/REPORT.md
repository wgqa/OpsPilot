# AR-03-B-RELIABILITY-01 — 修复报告

**状态：** `ACCEPTANCE_CANDIDATE`
**Base：** `332f93cca4daad308a8d57730f141e8cc5ed96b3`
**工作分支：** `codex/ar03-b-reliability-01`
**冻结/RED Commit：** `7e63610000caa885f0a86cff189b7eff68f75996`
**实现 Commit：** `845d5d0`
**远端 HEAD：** `UNVERIFIED`（此前 GitHub 443 不可达；未虚构远端 SHA）

## 用户现在能完成什么

在相同的授权订单与同 Event Observation 下，当 Agent 已完成六次合法 MCP 查询、又提议第七次只读查询时，预算层会明确告诉 Agent 该提议没有执行、不能视为事实。模型仍可基于本 Run 已验证的观察回答：Fixture 对 QUEUED 说明“202 已受理，Receiver 仍排队，处理未确认”；对 PROCESSED 则只确认该 Event 已处理。完整同 Event 对照来自确定性模型，不是新真实模型验证。

若 MODEL 总额度本身耗尽，Run 仍失败，程序给出 `PROGRAM_LIMIT`。失败 Run 的 Evidence 按现有 Domain 规则不再是当前事实，因此不会把 QUEUED/PROCESSED 填入降级消息。这是保留 fail-closed 当前性语义的结果，不宣称完成调查。

## 修复

1. `scoped_protocol_comparison.py` 将检索改为轻量词项规范化和授权集合内候选召回/排序。常见英文描述词不再要求逐字存在于元数据；中文使用有界字符二元组，并保留既有术语映射。查询顺序先读取可信 Session scope，候选只来自其允许的文档 ID。ID、版本、source、Digest、有效期与再验证路径未改。
2. `assistant.py::Loop.awrap_tool_call()` 仅拦截精确的 `ASSISTANT_RUN_MCP_LIMIT`。它返回 `executed=false`、`TOOL_REFUSAL_NOT_FACT` 的 ToolMessage，不写成功 MCP Call/D2 Attempt，不执行 Handler，不产生 Observation/Evidence。其他错误仍抛出。
3. MCP Run 限额仍为 6；Task / Provider / Context 限额、权限和业务 Gate 未变。未因一条真实轨迹提高默认预算：原始 B 首次协议检索空结果后进行宽泛补查，真实模型未在本轮重跑，所以无法证明检索修复会让模型减少调用。

## 测试证据

- RED：13 项，9 passed、4 failed；两种正常协议描述漏召回、相关度排序错误，以及 QUEUED/PROCESSED 下限额终止，见 `runs/red-01.log`。
- GREEN：15 passed；`callback retry`、`callback retry protocol`、`callback retry behavior`、`回调重试协议` 等均找回两个授权重试版本，重试家族在前；无关查询为空；越权文档和不同 Actor 仍被拒绝。
- 正式 API/Worker 确定性旅程：6 次合法 MCP 后，第 7 个 `search_project_knowledge` 提议不出站；Agent 从当前 Run 观察完成回答。QUEUED 与 PROCESSED 有不同且有边界的答案；诊断、Approval、ActionIntent、Ledger、Handoff Queue/Receipt 均为 0。
- MODEL 耗尽反例：8 个 Fixture MODEL 调用后 Run FAILED；失败 Run 来源当前性为 false，未提交模型答案，PROGRAM_LIMIT 未泄漏测试中的 Receiver 状态。
- 相关回归 48 passed。完整 pytest 为 595 passed / 4 failed（599 项）；所有失败及归因见 `FAILURES.md` 和完整原始日志。

## 限制和未验证

- 确定性模型只验证调度与业务事实边界，不能证明真实 LLM 会在第六次后主动结束，也不能证明修复后真实 B 会少用 MCP。
- 不提高 6 次 MCP 限额；若主 Agent 认为应提高，需另有可复现的合法路径证据和限额双向测试。
- `PROGRAM_LIMIT` 终止时没有安全的当前事实摘要，因为 Domain 将 FAILED Run 来源判为非当前。若未来需要在失败后仍交付事实，必须在现有合同内另行设计并证明不会复活旧 Evidence；本轮不改 Gate。
- 远端状态未验证，浏览器、DeepSeek、完整付费实验均未运行。
