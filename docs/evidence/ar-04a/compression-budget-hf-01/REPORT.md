# AR-04A-COMPRESSION-BUDGET-HF-01 — 压缩模型调用预算边界修复

**状态：** `ACCEPTANCE_CANDIDATE`
**基线：** `codex/ar04a-context-journey-01@1624d7bddab535495a758f5e22fc79ad0ced9174`
**main：** `48234e5dabb6ed28ea816b8ebc438288409353b8`（未改动）
**分支：** `codex/ar04a-compression-budget-hf-01`
**范围：** 只关闭 AR-04A 压缩调用的模型费用/次数边界；不改 Task/授权/写入，不做新框架、Memory、J6、跨 Task 摘要、浏览器或 AR-05。

## 1. 开工核验（实际读取）

| 项目 | 值 |
|---|---|
| `PROJECT_NORTH_STAR.md` | 已读取；Blob `1f737712c7a36ceb34433ac09c3fbba3c3305542` |
| `AGENTS.md` | 已读取；Blob `32c45506cceeaa8c76a5c56bf8360ff476b58856` |
| `opspilot-slice-review/SKILL.md` | 已读取；Blob `d405c8d413d633824b279202cc1503dab4cf0b03` |
| AR-04A GOLD / REPORT | 已读取（本目录同级的 `context-journey-01/`） |
| 基线 BLOCK 对象 | `assistant.py::_prepare_assistant_context` 中 `model.ainvoke(messages)` |
| 本轮真实 Provider 调用 | 0 |

## 2. 问题与复现

AR-04A 新增的压缩调用只写 `context_compression_attempts`，**没有**经过 `Loop.awrap_model_call` 使用的
`domain.reserve` / `reserve_dispatch` / `complete_dispatch` / `mark_unknown`，因此不受 Run 模型次数、Task 辅助预算和 AR-02/AR-03 实验费用账本约束。

基线（`1624d7b`）实测，同一 Mock Provider 测试：

| 复现 | 结果 |
|---|---|
| 正例：长会话压缩请求 | 压缩 wire `max_tokens=2048`（未使用 512 压缩上限）；`assistant_calls` 无 MODEL 行、`ar02_live_dispatches` 无记录 → 未预留、未结算 |
| 反例：实验 Provider 额度已用尽（16） | 仍发出第 17 次 Provider 请求：`AssertionError: compression must not reach the Provider (17 == 16)` → 绕过已冻结的单次实验预算 |

原始日志：`runs/red-baseline-compression-cap.log`、`runs/red-baseline-provider-limit.log`。

## 3. 最小修复

`opspilot/assistant.py`（+ 现有 Domain 原语，不新增账本）：

1. **先预留后外发**：压缩请求以稳定 `logical_key = "context-compression:" + digest(messages)` 调 `domain.reserve(..., kind='MODEL', experiment_id=...)`。它同时执行 Run 级 MODEL 次数上限、Task 辅助 Provider 预算，并写入 `assistant_calls`（RESERVED）。
2. **实验账本**：有 `experiment_id` 时，`reserve_dispatch` 先做次数与费用预留；Provider 返回后用 `complete_dispatch(usage=实际 Usage)` 结算；失败/超时 `mark_unknown` 保留 UNKNOWN 与全额预留并关闭实验预算；任何账本拒绝都在 Provider I/O 之前停止。
3. **重放**：相同 `logical_key` 且请求摘要一致时 `domain.reserve` 返回 durable 结果（`fresh=False`），压缩不再外发，仅复用已记录结果并补结算；若该次结果不是 `OK`，返回 `ASSISTANT_EXTERNAL_RESULT_UNKNOWN`（不把未知支出当成零、不重发）。
4. **输出上限**：压缩请求通过 `bind(extra_body={...原 Provider extra_body, "max_tokens": 512})` 下发，保留 `thinking=disabled`，不产生 `max_completion_tokens`；普通回答仍是 2048。

失败语义：预算次数/费用/账本拒绝 → `record_chat_limit_in_transaction` 落程序限制说明并 `FAILED`；Provider 结果未知 → `assistant_calls`/`ar02_live_dispatches` 均为 `UNKNOWN`、实验预算 `BUDGET_BREACH`、压缩尝试 `FAILED`，不重发。

## 4. Model Call / Campaign Ledger / Usage 对应关系

| 层 | 表/记录 | 压缩调用的值 |
|---|---|---|
| Model Call | `assistant_calls` (`kind='MODEL'`, `logical_key='context-compression:<digest>'`) | `request_json` 含 `purpose=CONTEXT_COMPRESSION`、`max_output_tokens=512`；成功 `status='OK'`，`usage_json=[{input_tokens,output_tokens,total_tokens}]` |
| Campaign Ledger | `ar02_live_dispatches`（同 `logical_key`） | 预留 `reserved_usd_micro`；`complete_dispatch` 后 `status='OK'`、`usage_state='KNOWN'`、`settled_usd_micro=实际费用`、`usage_json` 与 Model Call 一致 |
| Compression Attempt | `context_compression_attempts` | `SUCCEEDED`，带 `provider_response_id` 与 token 数 |
| Context | `context_summaries` / `context_summary_dependencies` | `CURRENT` 摘要，随后进入模型输入 |

正例测试逐项断言这四层一致：`assistant_calls` MODEL 行数 == `ar02_live_dispatches` MODEL 行数 == `read_budget()["provider_used"]`，且结算金额 > 0。

## 5. 正反测试（Mock Provider，0 真实请求）

`tests/test_ar04a_compression_budget_hf_01.py`，6 项：

1. **正例**：长会话压缩 → 预留/记账/结算/CURRENT 摘要/摘要进入后续 wire；压缩 wire `max_tokens=512`、无 `max_completion_tokens`、`thinking` 保留；普通回答 `max_tokens=2048`。
2. **次数上限**：真实消耗到实验 Provider 上限后，下一条需要压缩的消息 **零外发**，Run `FAILED` 且 `blocked_reason` 含 `AR02_LIVE_PROVIDER_LIMIT`。
3. **费用不足**：已结算费用占满预算后，压缩 **零外发**，`AR02_LIVE_USD_LIMIT`。
4. **结果未知**：压缩 Provider 抛 `ReadTimeout` → `assistant_calls`/`ar02_live_dispatches` 均 `UNKNOWN`、实验预算 `BUDGET_BREACH`、压缩尝试 `FAILED`、Provider 只收到 1 次请求（不重发）。
5. **重放**：首次提交返回 `INVALIDATED` 触发第二次压缩尝试，相同请求命中 durable 结果，Provider 仍只调用 1 次，摘要最终 `SUCCEEDED`。
6. **非实验路径**：普通（无实验）Run 仍可压缩，且压缩计入该 Run 的 MODEL 次数（压缩 + 回答 = 2），不创建实验表。

既有 AR-04A 长会话旅程 4 项测试保留并通过。

## 6. 测试与回归

| 套件 | 结果 | 日志 |
|---|---|---|
| HF 6 项 | 6 passed（68.77s） | `runs/pytest-hf.log` |
| AR-04A 旅程 4 项 | 4 passed（39.45s） | `runs/pytest-ar04a-journey.log` |
| 定向回归（context / chat / assistant / journey） | 42 passed（151.42s） | `runs/pytest-targeted-regression.log` |
| 全量 pytest | **NOT_COMPLETED_ENVIRONMENT_HANG**：本候选的一次全量运行在 21% 的 MCP/stdio 密集区停滞 16 分钟以上后中止；AR-04A 提交时另一次全量运行也在 31% 停滞。均为环境/测试生命周期停滞，不是失败断言。已知基线全量结果（AR-04A 提交）为 679 收集 / 678 passed / 1 failed（冻结 C1 RED） | `runs/pytest-full-suite.log` |

真实 Provider 调用：0。业务写入：0。

## 7. 限制

- 只覆盖 `ASSISTANT_V1` 路径；经典聊天 Worker 的压缩仍走它自己的 `ChatOpenAI(max_tokens=512)` 与 chat attempt 计数，本轮未改。
- 重放去重依赖压缩消息摘要；来源变化会产生新 key 并重新计费，这是正确行为。
- Mock Provider 证明的是线协议与账本一致性，不是真实模型质量或真实计费。真实 Provider `NOT_RUN`。
- 既有 AR-04A 限制（J6 未覆盖、Task 作用域摘要不复用）不变。

## 8. 候选 SHA 与建议

- 代码 + 测试 + 证据提交：`dcefa8f469a04a7151a9a6807131337057c5c2a1`（已推送 `origin/codex/ar04a-compression-budget-hf-01`）
- 分支 head 若再有一个仅更新本文件/RESULTS 记录字段的提交，代码树与该提交相同；以远端分支 head 为准
- 本轮只提交隔离候选，不合并 main

**建议：** `MERGE_READY`（就本 HF 的预算边界而言），仍由主 Agent 独立核验后决定合并。
