# AR-04A-COMPRESSION-CANCEL-HF-01 — 取消时的压缩费用收口

**状态：** `ACCEPTANCE_CANDIDATE`
**基线：** `codex/ar04a-compression-budget-hf-01@f53d6886beb24b6cb6c5e4398b280660d5bacf88`
**main：** `48234e5dabb6ed28ea816b8ebc438288409353b8`（未改动）
**分支：** `codex/ar04a-compression-cancel-hf-01`
**范围：** 只修复压缩 Provider 请求被取消时遗留 `RESERVED` / `OPEN` 的费用状态；不改产品目标、Gold、J6、Memory、S1/S2 语义或 Worker 架构。

## 1. 开工核验（实际读取）

| 项目 | 值 |
|---|---|
| `PROJECT_NORTH_STAR.md` | 已读取；Blob `1f737712c7a36ceb34433ac09c3fbba3c3305542` |
| `AGENTS.md` | 已读取；Blob `32c45506cceeaa8c76a5c56bf8360ff476b58856` |
| `opspilot-slice-review/SKILL.md` | 已读取；Blob `d405c8d413d633824b279202cc1503dab4cf0b03` |
| AR-04A GOLD / HF REPORT | 已读取（同级 `context-journey-01/`、`compression-budget-hf-01/`） |
| 基线 HEAD | `f53d688`（含 HF 压缩账本接线） |
| 本轮真实 Provider 调用 | 0 |

## 2. 问题与 RED 复现（先复现，非源码推断）

基线代码在压缩 Provider 调用处只有：

```python
except asyncio.CancelledError:
    raise
```

取消发生在 `domain.reserve` / `reserve_dispatch` 之后、Provider 响应未知时，会跳过 `domain.finish` 与 `mark_unknown`。离线故障注入（Mock Provider 把压缩请求挂起，随后取消 TestClient/Worker）实测：

```
AssertionError: ('RESERVED', 'RESERVED', 'RESERVED', 'OPEN')
```

即 `assistant_calls.status=RESERVED`、`ar02_live_dispatches.status=RESERVED`、`context_compression_attempts.status=RESERVED`、实验预算仍 `OPEN`。恢复/重放场景下 Dispatch 仍为 `RESERVED`（日志 `runs/red-baseline-cancel-suite.log`、`runs/red-single-cancel.log`）。

## 3. 最小修复

`opspilot/assistant.py`：

1. `_prepare_assistant_context` 变为薄包装，持有 `state`（`attempt_id` / `call_id` / `logical_key` / `dispatch_started` / `settled`），内部实现为 `_prepare_assistant_context_impl`。
2. 压缩段的账本操作（`prepare_chat_compression_attempt`、source 再校验、`domain.reserve`、`reserve_dispatch`、`complete_dispatch`、`domain.finish`、`mark_unknown`、压缩尝试提交）改为**同步**短事务：取消只能在 `await model.ainvoke(...)` 处发生，从而消除"取消时还有在途账本线程"的竞态；`dispatch_started` 在 Provider 调用前立即置位，`settled` 在结算成功后置位。
3. 外层 `except asyncio.CancelledError` 调用 `_close_cancelled_compression(...)` 同步收口后再 `raise`（不吞取消、不伪装成功）。收口按数据库最终状态三态处理：

| 状态 | Model Call | Campaign Dispatch | 预算 |
|---|---|---|---|
| 已结算（`settled`） | 保持既有结算 | 保持 `OK`/`KNOWN` | 不变 |
| 已外发、结果未知 | `UNKNOWN` | `UNKNOWN`，保留全额预留 | `BUDGET_BREACH`，禁止重发 |
| 已预留、未外发 | `FAILED` | 存在预留时 `NOT_DISPATCHED`（释放预留） | 保持 `OPEN` |

4. 收口时重新查询数据库（按 `logical_key` 找 `assistant_calls`、按 run 找 `RESERVED` 压缩尝试），不只看内存标志；所有 `RESERVED` 压缩尝试置 `FAILED`。清理写入不再经过 `await`，不会被第二次取消打断；清理异常只打印 `COMPRESSION_CANCEL_CLEANUP_FAILED`，不掩盖取消。
5. 重放路径不变：取消后同一请求再次进入时 `domain.reserve` 命中 `UNKNOWN` → `ASSISTANT_EXTERNAL_RESULT_UNKNOWN`，Provider 不再被调用。

已知限制：取消若发生在压缩完成后的 `prepare_chat_attempt`（无费用影响）仍按既有 Worker 生命周期处理。

## 4. Model Call 与 Campaign Ledger 最终状态（取消后）

| 场景 | assistant_calls | ar02_live_dispatches | 预算 | 摘要 |
|---|---|---|---|---|
| Provider 在途取消 | `UNKNOWN` | `UNKNOWN`，`reserved_usd_micro` 保留 | `BUDGET_BREACH` | 无 |
| 取消后恢复重放 | 保持 `UNKNOWN`（不新增行） | 保持 `UNKNOWN` | `BUDGET_BREACH` | 无 |
| 预留阶段取消 | `FAILED` | 无（或 `NOT_DISPATCHED`） | `OPEN` | 无 |
| 正常成功 | `OK` + Usage | `OK` / `KNOWN` / 实际结算 | 不变 | `CURRENT` |

## 5. 测试（Mock Provider，0 真实请求）

`tests/test_ar04a_compression_cancel_hf_01.py`，3 项：

1. **在途取消**：压缩 Provider 请求挂起后取消 Worker → Call/Dispatch `UNKNOWN`、预留保留、预算 `BUDGET_BREACH`、尝试 `FAILED`、无摘要、Provider 只收到 1 次请求。
2. **取消后恢复重放**：把 Run 置 `INTERRUPTED_RECOVERABLE` 并重启 Worker → Run `FAILED` 且 `blocked_reason` 含 `ASSISTANT_EXTERNAL_RESULT_UNKNOWN`，**没有第二次压缩请求**，账本保持 `UNKNOWN`/`BUDGET_BREACH`。
3. **预留阶段取消**：在 `domain.reserve` 成功后注入取消 → Call `FAILED`、无 Dispatch、预算 `OPEN`、尝试 `FAILED`、零 Provider 请求。

## 6. 回归

| 套件 | 结果 | 日志 |
|---|---|---|
| 取消 3 项 | 3 passed（30.42s） | `runs/pytest-cancel-hf.log` |
| 取消 3 + HF 6 + AR-04A 4 | 13 passed（137.34s） | `runs/green-cancel-hf-ar04a.log` |
| 基线 RED（同一取消套件，`f53d688`） | 失败，复现 `RESERVED/OPEN` | `runs/red-baseline-cancel-suite.log` |

全量 pytest 未强制重跑（任务允许按影响定向回归）；真实 Provider 与浏览器 `NOT_RUN`。

## 7. 遗留限制

- 只覆盖 ASSISTANT_V1 压缩段的取消；Worker 其他阶段（如最终 `prepare_chat_attempt`）沿用既有生命周期。
- 取消后 Run 的重试仍可能由 Worker 触发一次，但会被 `ASSISTANT_EXTERNAL_RESULT_UNKNOWN` 安全终止，不会重发压缩请求。
- Mock Provider 证明的是账本状态机，不是真实 Provider 计费。

## 8. 候选 SHA 与建议

- 代码 + 测试 + 证据提交：`8358a21e9dd99e7f2e66fcc7b881ee96b7e1b123`（已推送 `origin/codex/ar04a-compression-cancel-hf-01`）
- 分支 head 若再有一个仅更新本文件/RESULTS 记录字段的提交，代码树与该提交相同；以远端分支 head 为准
- 只提交隔离候选，不合并 main

**建议：** `MERGE_READY`（就取消费用收口而言），由主 Agent 独立核验后决定。
