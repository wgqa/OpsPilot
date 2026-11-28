# 失败、限制与未运行项

## 当前相关回归的既有断言差异

本次受控相关回归 60 项中 59 项通过。唯一失败：

`tests/test_ar04c_f01_context_currentness.py::test_zero_tool_followup_can_explain_valid_historical_snapshot`

失败为 `KeyError: 'completed_tools'`。测试预期模型上下文中的 `current_run.completed_tools` 空列表；当前 `source_context_for_model()` 刻意只投影 `run_id`、时间语义描述和业务观察的来源引用。该字段省略已在前次 Headroom HF 报告中作为历史断言不一致记录。Run 状态、零 MCP 事实及历史快照解释路径仍分别由其他断言/测试覆盖。没有修改生产行为、历史 Gold 或该断言；也不把它计为通过。

## 新真实旅程未运行

新 Campaign 的独立付费授权缺失，这是任务卡预设的授权停止条件，不是 Provider 或产品执行失败。J1-01、J1-02、J2-01、J2-02 均为 `NOT_RUN`。本轮没有建立任何可发送 Grant/Claim，没有读取凭据，不会通过旧 Campaign 恢复、重启 Worker 或换 Session 绕过授权。

## 剩余执行前核验

- 真实执行当天重核 DeepSeek 价格与模型版本；价格可变。
- 当前官方 Chat Completions 文档没有明确描述 `parallel_tool_calls` 参数，虽然冻结本地 MockTransport 会序列化并断言 `false`；不能把离线断言写成供应商实时兼容证明。
- 本轮未检查凭据可用性，也未创建新的独立 DB、Checkpoint、Grant、Claim；这些应在新授权后按冻结流程准备。
- 原历史 Campaign 的私有 DB/Checkpoint 未在本轮打开或哈希；本地公开结果文件哈希见 `EVIDENCE_HASHES.json`，旧运行报告记载其当时前后哈希一致。本轮未接触旧私有运行目录。
- 全仓 pytest、浏览器、真实 Provider、R1-INTERACTIVE 和 J3/J4 新助手真实回读均 `NOT_RUN`。

## 安全与副作用

真实 Provider HTTP=0；外部业务写入/Approval/Repair/Deliver/Handoff=0；浏览器自动化=0。隔离 pytest Fixture 使用临时 Demo DB 和 MockTransport；不能将其当成真实 DeepSeek、真实外部业务观察或浏览器验收。
