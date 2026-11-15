# E09-D 首次真实 Live 运行报告

- 候选分支：`codex/r2-ar06-e09-d-live-01`（证据专用；本轮未改生产代码）
- 基线 SHA：`17850fab6a947a8adc876b88682fc04883c8b67e`
- 隔离 Runtime：`user-demo-r2-e09-live01`
- Session：`session-77a58c7d-e62b-4bc4-88ef-0eab7ffe0de9`（tenant `tenant-a` / SUPPORT）
- 固定轮次脚本 SHA256：`744abd7ae909b4e4bac02b2b9fa389a98a0ba8a1450d75f735199d5856da99cc`；启动、停止、初始化、Runtime Admin、Runner、路径解析与 Trace Exporter 的 SHA256 已逐项记入 `E09_LIVE_EVIDENCE_INDEX.json`
- 费用授权上限：USD 0.22
- 真实 Provider 派发：11（普通回答 8，Context Compression 3）
- 真实 Provider 请求：0 UNKNOWN；重试 0；重复提交 0
- 结论：`STOPPED_AFTER_RUN_09_FAILURE`。不是完整 E09 旅程，不作 Gold 评分。

## 结果

逐轮按固定脚本发送 Turn 1–9，各一次。Runs 1–8 为 `SUCCEEDED`，Run 9 为 `FAILED / CHAT_CONTEXT_COMPRESSION_FAILED`。Turn 9 没有 Assistant 答案。遵守停止线：没有发送 Turn 10，没有创建 TaskBinding，也没有执行当前 Delivery/Receiver 查询；没有尝试重新提交 Turn 9。

Run 9 的压缩 Provider 请求返回 HTTP 200，记录到 512 个输出 Token，正好达到该次请求的 `max_output_tokens=512`。返回内容不是有效 JSON，压缩 Attempt 以 `TaskControlError` 失败，Run 终止。Trace 未持久 `finish_reason`；“输出可能被 Token 上限截断”是推断，不是已确认根因。错误标识、原始脱敏响应、请求和调用关联见 `E09_LIVE_TRACE.json`、`E09_LIVE_RUN09_FAILURE_CONTEXT.json`。

## Context Summary 证据与限制

- 实际执行 3 次压缩：2 次成功、1 次失败；持久化 2 个 Summary（v1 `SUPERSEDED`、v2 `CURRENT`）。所有已知 Summary 正文与来源依赖 Digest 均通过当前隔离 DB 的只读核对：`True`。
- 后续模型请求的实际输入包含历史 Summary 标记/ID；完整消息在 Trace，按调用归纳的检查在 `E09_LIVE_MODEL_INPUT_AUDIT.json`。
- Summary 保留了初始目标、先解释 HTTP 202、不要假设已查订单，以及“HTTP 202 不证明业务完成”的语义；配置/日志仍被标为用户提供的非可信材料。
- 当前 Summary 没有保留关键配置的逐字段值（例如 `max_attempts` 与 endpoint）；因此不能宣称材料细节保真完整。未手工修订 Summary。
- 由于 Run 9 失败，Summary 未在 TaskBinding 后验证；Taskless Summary 未跨 Task 注入，当前业务事实也未被查询。

## 调用与费用

| 项目 | 实际值 |
|---|---:|
| Provider 派发 / HTTP 200 | 11 / 11 |
| 普通回答 / Compression | 8 / 3 |
| Input / Output / Total tokens | 69,406 / 12,378 / 81,784 |
| 应用费用账本结算 | USD 0.035680 |
| 已批准上限 / 账本剩余 | USD 0.220000 / USD 0.184320 |
| UNKNOWN / MCP / Observation / Evidence | 0 / 0 / 0 / 0 |
| TaskBinding / 业务写入 | 0 / 0 |

费用取自隔离 Domain 的应用 Spend Ledger，不能替代 Provider 最终账单。当前模型与峰时费率配置为 `deepseek-flash`、`DEEPSEEK_FLASH_PEAK_2026-11-14`（输入 USD 0.30/百万、输出 USD 1.20/百万）；创建 Grant 前已与 [DeepSeek 官方价格页](https://api-docs.deepseek.com/quick_start/pricing/)核对。按每请求 12,000 输入/2,048 输出、最多 33 次派发的保守上界为 USD 0.199914，在 USD 0.22 Grant 内。

## 生命周期与证据

API、内部 Worker、Vue 已通过本地服务流程运行；完成后使用现有 Stop 脚本优雅关闭。执行日志包含 `STOPPED`，本次结束时 API/UI 监听端口均已关闭。Runtime Domain DB、Checkpoint、Session、Summary、Run、请求响应、Spend 和 Grant 账本均保留；没有清理或重置历史数据。 当前 Runtime Grant 仍为 ACTIVE，至 2026-11-16T02:00:00Z 到期；本地 runtime_admin CLI 没有撤销子命令。API、Worker 和 Vue 已停止，未尝试任何后续请求；剩余 Grant 余额不代表本轮失败后获准再运行。

全部轮次输入、实际模型请求/响应、Summary 正文及依赖、费用明细、失败上下文、Preflight 与提交日志均在本目录。单次顺序执行驱动也一并归档为 `E09_LIVE_EXECUTION_DRIVER.py`。冻结脚本原文件、Gold、Rubric 和生产代码未改。`E09_LIVE_EVIDENCE_INDEX.json` 列出证据文件 SHA256。导出复用脱敏导出器；对本地产物执行了密钥/凭据值扫描，扫描结果仅记录是否通过，不记录敏感值。

## 独立验收边界

不提交 PASS/PARTIAL 评分；由主 Agent 按冻结 Rubric 独立裁决。当前证据支持“部分连续对话与 Summary 工程链路已发生”，但完整 10 轮、TaskBinding、当前 MCP 查询、最终来源区分回答均未完成。此 Run 失败是正式首次结果，不重跑、不覆盖。
