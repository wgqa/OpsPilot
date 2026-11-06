# AR04C-F01-RECHECK-01 — 一次有界真实复验

用户已批准该任务卡，并对一次真实 DeepSeek 实验及修正后的预留明确回复“授权”。本合同用于绑定一次新实验，不改变原 AR-04C Gold、原始 Trace 或已消费的 Claim。

- Base：`codex/ar04c-f01-context-currentness-01@08b007dda384b03a3b7d1ac6351d8c4ee1dcfb45`。
- 实验身份：`AR04C-F01-RECHECK-01`；唯一新 Claim 与独立 SQLite、Checkpoint、账本和私有 Trace。
- 正式路径：FastAPI → Worker → ASSISTANT_V1 → DeepSeek → MCP / Domain；Memory ON。
- 冻结问题：原 CASES.json 中的 J2；随后“请解释上一轮结论的依据，区分历史快照和这次实际做的查询。”；再两次问“请现在重新核实同一个事件的接收方是否处理完成。”
- 初始 Receiver 为 QUEUED；最后一次问题之前只在隔离 Demo 中把同 Event 改为 PROCESSED 并增加版本。该夹具变化不是 Agent 的业务写入或 Observation。
- 模型：`deepseek-flash`，`thinking.type=disabled`，`max_tokens=2048`，有工具时 `tool_choice=auto`，`parallel_tool_calls=false`，`stream=false`；30 秒、单并发、零自动与人工重试。
- Campaign：最多 8 次 Provider，应用费用不超过 USD 5.25；出站前持久预留 USD 0.668468，已知 Usage 按官方峰值计费结算。MCP 由既有权限、持久计数、Run/Task 时间及递归保护约束，不新增低次数门槛。
- USD 0.668468 是按官方模型目录示例 1,048,576 上下文 / 393,216 最大输出及 USD 0.30/M 输入、USD 1.20/M 输出计算的最坏额度并向上取整；实际 Usage 和供应商账单另报。发送前重新核对官方文档。
- 同一 Session/Task 完成四轮。模型自主选择直接解释、合法工具、澄清或停止；无新 Observation 时不能声称本轮重新取证。
- UNKNOWN、Usage 失效、授权/来源异常、预算或时间耗尽、非法业务写入等触发立即停止，不重试、不重跑、不重置额度。外部业务写入为零。

评估实际用户答复和工具 Observation 是否一致；允许诚实的未知结果。离线 Mock 只验证接线，不得作为真实模型成功。完成一轮或触发首次硬停止即结束，由主 Agent 独立验收。
