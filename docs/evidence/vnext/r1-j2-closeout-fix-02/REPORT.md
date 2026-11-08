# R1-J2-CLOSEOUT-FIX-02 — 离线修复报告

状态：`ACCEPTANCE_CANDIDATE`
Base：`ebc9a7b31e4e6acc899af39fa37fc23c953980ff`
分支：`codex/r1-j2-closeout-fix-02`
本轮范围：F1 Event 查询语义呈现、F2 工具观察后的 Context 超限。真实 Provider、浏览器、外部业务写入均为 0；未合并 main。

基线规范已从该 Base 实际读取：North Star Blob `43dabda468506717c6956e676dfad4304c4f38e6`，AGENTS Blob `807b928686a4dd2cac7b15b3c354b9943c93c910`，Review Skill Blob `d405c8d413d633824b279202cc1503dab4cf0b03`；冻结 `CASES.json` Blob 为 `320bab6afc5668c675455d370e6a3ded51119b08`。GitHub API 只读核实远端基线分支为 `ebc9a7b31e4e6acc899af39fa37fc23c953980ff`、`main` 为 `60eee87bfe3cca522011316cb4cd2c0064ad291b`，新候选分支当时不存在。终端 Git transport 到 `github.com:443` 失败；GitHub 连接器的创建 Blob 写请求返回 403 `Resource not accessible by integration`，所以候选尚未发布，远端候选 SHA 不存在。

## 用户旅程证据

- J2-01 的保存真实 Trace 显示：用户明确询问 `event-current`，模型仍把当前输入里的 Event 误读为需要重新授权的目标，随后进行了四次协议/Knowledge 查询并要求用户确认。Trace 证明这是实际失败；无法从单次样本证明其唯一心理/因果根因。
- J2-02 的保存真实输入与三个真实 MCP 结果重建出下一次 Provider 请求估算 `12,199` tokens，被原 12,000 上限正确拒绝。模型没有得到该轮最终答复。
- 离线正式路径复验使用 MockTransport、确定性模型和隔离 Demo：同一 Session 运行协议问答、材料分析、可信绑定后的 `event-current` 查询、再更正为 `event-previous`。模型替身在 J2-01 对 `event-current` 取得 Delivery `HTTP 202 / ACKNOWLEDGED` 与 Receiver `PROCESSED`；纠错后围绕 `event-previous` 查询历史传输记录，未借用另一个 Event 的 Receiver 结果，并以未知事项结束草稿。该 Fixture 记录 11 次模拟模型派发、7 次本地 MCP 调用；不是 11 次外部 Provider 请求。
- 以上是正式 API/Worker/Assistant/Runtime Grant/MCP/Domain 链路的离线机制证据，不是新的真实 DeepSeek 行为验收。

## F1 — 当前调查目标与授权来源

**根因判断：** 保存 Trace 中模型明确把 Event 目标当成重新授权请求。当前上下文又将当前用户消息包装为 `ORIGINAL_TASK_INPUT (UNTRUSTED USER INPUT)`，即使它本身就是本轮查询。该标记正确表达了“用户文本不能改变可信授权”，但把当前查询目标额外命名为“原始任务输入”容易混淆查询目标与历史线索。由于真实模型行为具有非确定性，当前证据只能确认这是上下文呈现缺陷及其与失败相符，不能单凭一轮 Trace 断言它是唯一原因。

**修复：** `opspilot/domain/chat.py::_prepare_context` 只对非当前的历史任务锚点保留 `ORIGINAL_TASK_INPUT` 包装；当前用户消息按普通 `USER` 消息传递。它仍是未信任用户输入。可信订单与 TaskBinding 仍由 Domain 提供；模型指定 Event 只是已绑定订单范围内的只读查询目标。未改 System Prompt 权限、工具授权、绑定流程或 Event 范围。

**双向证据：** 合法同订单 Event 可以继续只读调查；跨订单 Event 查询仍拒绝。聊天文本提出另一订单时不会改变既有绑定；只有可信的新绑定命令才建立独立 Task/Binding。历史材料中的 `event-previous` 仍是线索，不会变成当前 Observation。

## F2 — 可信 Observation 与 12K Context

修复复用现有 `Loop.context()`、Domain 来源验证及 `source_context_for_model()`。当前 Run 的模型可见来源投影保留 Run、工具名、Domain `call_id`、模型 `tool_call_id`、Evidence/Observation ID 和观察时间。完整版本、摘要及结果 Digest 继续保留在 ToolMessage 与 `wire_source_refs` 审计元数据中，不重复装入 `WORK_CONTEXT`。Tool Call 与 Observation 的关联从 `d2_tool_observations` 按 `task_id + call_id` 读取，不按工具名猜配。TTL、撤权、当前来源校验没有改动。

| 重建状态 | Prompt tokens | 工具 Schema | 估算输入 | 结果 |
|---|---:|---:|---:|---|
| 修复前：保存的真实 J2-02 请求 + 三个真实 MCP 结果 | 11,053 | 1,138 | 12,199 | 发送前拒绝 |
| 修复后：相同历史、三个 ToolMessage 和三条 Observation | 10,754 | 1,138 | 11,900 | 在 12,000 内可继续 |
| 再加一条较大的合成工具结果 | — | — | 12,461 | 正确在 Provider 预留前拒绝 |

节省 299 tokens，未提高 12K 上限，也未删除三条工具结果。额外工具结果仍可能超预算；这种情况继续 fail closed，而非丢弃可信事实或继续外发。

## 修改与验证

- 源码：`opspilot/domain/chat.py`、`opspilot/domain/assistant.py`、`opspilot/assistant.py`。
- 回归：`tests/test_r1_j2_closeout_fix_02.py`、`tests/test_ar02_runtime.py`、`tests/test_ar03_material_01.py`、`tests/test_r1_journey_readiness_01.py`。
- RED/GREEN 原始日志、Token 重建和测试命令见本目录其他文件。
- 最终定向运行：5/5 通过。相关 Context、Assistant、MCP、Runtime Grant 回归：50/50 通过（另见日志）。
- 原 Campaign 数据库仍为 `STOPPED / CAMPAIGN_FINISHED`；8 次发送额度均已授予/交付，0 个 UNKNOWN。原 Domain、Checkpoint、Provider HTTP 与 execution 日志的 SHA-256 与执行前记录相同。

## 六维自检

1. **用户变化：** 可信绑定后，当前 Event 不再被上下文误包装成待重新授权的历史任务；三条工具结果的同等上下文可在 12K 内继续。离线 Fixture 不代表真实模型已完成复验。
2. **Agent 决策：** 模型仍可直接回答、查询、澄清或停止；本轮没有新增强制工具路线。授权仍只由可信 TaskBinding/Domain 决定。
3. **观察驱动：** `event-current` 的 PROCESSED 与纠错后 `event-previous` 只有历史传输、缺少当前 Receiver Observation，离线旅程输出不同且有限的结论。
4. **约束双向检查：** 没有新增权限 Gate。合法同订单查询可继续，跨订单拒绝；预算内三条 Observation 可送往下一轮，真实超额样本在 Provider 预留前停止。
5. **责任归属和简化：** F1 修在现有 Context 装配；F2 修在已有 Observation 投影。完整审计仍保留，模型输入只省去与 ToolMessage 重复的元数据；没有移除来源有效性、撤权或 TTL 检查。
6. **证据与停止线：** 冻结旧 Gold/Trace/账本；本轮 Provider HTTP=0、外部写入=0、浏览器未运行。定向回归完成后停止。下一次真实复验粗估 9–12 次请求：旧旅程用掉 8 次，J2-02 至少还缺一次观察后的最终模型答复；F1 可能减少旧的冗余查询，但不把节省计入保证值。12 次只是建议上限，不是本轮授权。

本结论仅为实施方 `ACCEPTANCE_CANDIDATE`。R1-ENGINE 原裁决仍为 HOLD，是否接受修复由主 Agent 独立决定。
