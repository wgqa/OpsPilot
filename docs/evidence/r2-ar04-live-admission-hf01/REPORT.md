# R2-AR04 Live Admission HF-01

## 状态

`ACCEPTANCE_CANDIDATE`。本轮仅执行 MockTransport 和离线验证：真实 Provider 请求 0 次、费用 USD 0.00、外部 MCP 0 次、业务写入 0 次。没有创建可执行授权，没有运行 Live。

## 基线与冻结

- HF-01 review base：`bf9e5d84f4aa2e57d1f195dbe7933d74c5586a3b`
- 原 Live Gate base：`fa4cd8a7ea6dd36babccbbfc5fcdb7a179729fd3`
- 前一远端候选：`9412c05bd095d3f4abba58e7a23a076633654e6b`
- 前一本地提交：`bf9e5d84f4aa2e57d1f195dbe7933d74c5586a3b`
- 工作分支：`codex/r2-ar04-live-admission-hf01`
- 生产 `chat.py`、`assistant.py` Blob 与冻结 Gold、历史 Trace、账本均未改。当前冻结检查确认历史受保护文件与原 Gate base 一致。

固定源码和配置证据见 [SOURCE_BINDINGS.json](SOURCE_BINDINGS.json)。主 `.env` 只记录了 Key 是否存在和 URL 结构；未输出凭据。当前 URL 结构为 `https://api.deepseek.com/v1`，OpenAI SDK 的 MockTransport 实际生成 `/v1/chat/completions`。

## 三项准入阻断

### 1. Provider 路径

在 `docs/evidence/abc-live-env-unblock-01/run_abc_eval.py` 的 `BudgetedAsyncTransport` 增加结构化 URL 校验。期待地址必须是 HTTPS、固定 DeepSeek 主机、443 端口、无用户信息/查询/片段，配置 Base Path 仅可为空、`/` 或 `/v1`。实际请求路径必须精确等于配置 Base Path 加 `/chat/completions`；同时校验原始编码路径和 Host header。非预期方法、主机、端口、路径、查询和编码绕过均在预算预留及内层发送前拒绝。

3xx 响应不返回给 SDK。即使 HTTPX 设置 `follow_redirects=True`，Adapter 也先记录响应并以 `PROVIDER_REDIRECT_BLOCKED` 停止，不会让 Location 触发第二个目标请求。测试验证内层 MockTransport 只收到原始 DeepSeek URL 一次，Location 不写入 Trace。

### 2. 异常 `tool_calls`

Adapter 先记录 Provider 响应、Usage、Response ID、状态和 Trace，再拒绝所有非完整纯文本结果。`finish_reason=tool_calls` 与 `finish_reason=stop` 但带非空 `tool_calls` 都落为 `UNEXPECTED_TOOL_CALL` / `TOOL_CALL_BLOCKED`，并抛出停止结果；不再把原工具调用或合成占位答案返回 Assistant。

两个异常响应都经过真实 Assistant、隔离 Domain、Checkpoint、Runtime Grant 和 MockTransport 调用路径。最终 Assistant 尝试是 `FAILED`，没有成功答案；工具派发观察、MCP 尝试及 Action/Memory/Delivery 写入表均为 0。账本保留 3 次 Mock 调用（两次摘要、一次回答）、回答请求 ID、Token Usage 与已结算费用；Q06-B 没有发送。

另外对无效 JSON、无效 Choice、`finish_reason=length` 和 3xx 做了“记录后拒绝”检查。Q02-B 冻结截断 Trace 仍通过既有 Domain 回放测试，未持久化不完整摘要。

### 3. 授权 Task ID

唯一授权 Task ID 保持为 Runner 原有精确值 `R2-AR04-REMAINING-LIVE-GATE-01`。本次审查号 `R2-AR04-LIVE-ADMISSION-HF-01` 只作为必填 `review_task_id` 审计元数据。验证器继续精确匹配稳定 Task ID 和原 Gate base，且要求 review 元数据精确匹配；复核任务号、历史任务号和旧 base 均不能替代授权身份。

未来授权的 Schema 增加 Adapter Blob pin，防止路径守卫源码漂移。提案 [AUTHORIZATION_PROPOSAL.json](AUTHORIZATION_PROPOSAL.json) 的授权 ID、价格快照、Artifact Pins 均为空，发送标志为 `false`，不是可执行授权。

## 结果

- Q02-B、Q06-B 完整成功 Mock：2/2 Case、4 次摘要、2 次回答；每例隔离 29 条冻结历史、Domain、Checkpoint、Session、Run 和 Grant；Summary 持久化仍不超过 512 Token，生成上限 1024、答案上限 512。
- 关键事实与来源在最终 Prompt 可见；Q06-B 早期 `max_attempts` 仍标为 `PARTIAL`，新版本/参数事实来自后期来源。
- 共享 Grant 最坏预留 USD 0.028974，低于 USD 0.06 硬上限。
- 零费用预检状态 `READY_FOR_NEW_LIVE_AUTHORIZATION`；它只说明隔离配置、Grant 绑定和新鲜 Mock Gate 可用，不代表付费授权、Provider 价格复核或 L3 通过。
- 当前官方价格本轮未重新查询；后续实际发送前仍须重查价格并取得新的明确付费授权。

细项见 [RESULTS.json](RESULTS.json)、[FAILURE_RESULTS.json](FAILURE_RESULTS.json)、[LIVE_PREFLIGHT_04_FINAL.json](LIVE_PREFLIGHT_04_FINAL.json) 和 [TEST_RUN.txt](TEST_RUN.txt)。

## 限制与遗留

- 未做真实 Provider 身份验证、实时价格核验或模型语义评分。
- 一次宽泛的 `pytest -k ar04` 扫描因长用例无进展被中止，退出码 1，不计为 PASS；本报告只认定列明的定向回归结果。
- 开发过程中早期预检和 Mock Digest 曾失败；相关初始 JSON/Mock 输出保留在本目录，没有覆盖。最终结论仅引用新鲜 `mock_run_04` 和 `LIVE_PREFLIGHT_04_FINAL.json`。
- 不修改生产 Context / Assistant / Domain 逻辑；不改历史结果；不合并 main。
