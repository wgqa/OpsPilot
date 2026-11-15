# R2-AR04 V2 Mock 来源勘误

## 结论

旧 V2 Mock 对 Q02-A 发生了跨 Trace 错配：`run_v2.py` 通过 `retention_evidence.OLD_TRACE` 读取 ABC 实验 `live_run_02/LIVE_REQUESTS.jsonl.gz` 的 Q02-A 首轮摘要正文，正文对应 Provider Response ID `fa6d38a4-d50e-4735-9732-2c48bfc54746`；provenance 却把它标成复测 Trace 中的 `c3435ff4-fc27-4ffb-b053-bbfcabc600e0`。两条回复来自不同请求，不能互相标注。

本次 Q02-A 固定为最近一次失败复测 `r2-ar04-live-retention-recheck-01/live_run_01/LIVE_REQUESTS.jsonl.gz` 中的 `Q02-A:SUMMARY:1`。Q02-B 与 Q06-B 固定为 ABC 实验 `abc-live-env-unblock-01/live_run_02/LIVE_REQUESTS.jsonl.gz` 中各自的首轮 Summary。

## 重新核对的来源

| Case | Trace SHA-256 | Logical ID | Request SHA-256（SEND=RESPONSE） | Provider Response ID | 原始响应体 SHA-256 | 摘要文本 SHA-256 |
|---|---|---|---|---|---|---|
| Q02-A | `3c6552bfe411a4bd362e355c7725f5185717fb621308cb0493dcd36aaa5d50f7` | `Q02-A:SUMMARY:1` | `c8bb2ae2573eb6c019e5acc0db912e7e0fd20b6b80c34790c70f8eef7710b3a7` | `c3435ff4-fc27-4ffb-b053-bbfcabc600e0` | `8f2d2a23392ce7732b50a50633fdbf5fa3b47d395dd71759b578c90970999b6d` | `2ef286e22a44b927352d3dd45797f34baa331bbe48ae65a247e2d56caf81a136` |
| Q02-B | `80dab676295960017bf31ba25c1aef62657d0eb0c437aa0fa1f0f6f56a8da05c` | `Q02-B:SUMMARY:1` | `25fdf3c03b198d46ebc44055582d2ad2d1daf8a75e1aa12a9c1568ea9b9f8176` | `d52800ab-6315-4374-ae93-8ff98c5b20a2` | `209feb98fade698d59d40deeb49950872ec3b79e01ebfeafaa8ebf7fa1659f5b` | `be035b0ff1894321a08a49dfbf9a934d163c2fcad62c409797281619221376ee` |
| Q06-B | `80dab676295960017bf31ba25c1aef62657d0eb0c437aa0fa1f0f6f56a8da05c` | `Q06-B:SUMMARY:1` | `2b804b493d1f1c27c881cfd8ea745b8d0a88798f101cf238ad8b85c8e53cd794` | `2a3e15cc-5127-468b-b892-9ce8d194459f` | `832fa7ad11e2625c0b794cb6d1d55faffa5ea4218946f3734139685378ed8fab` | `7d624dd829dbf786f749d08e4880f4df8a94906147dfc06d56c943fbff42b755` |

`response_body_sha256` 是原 Trace 在 Provider HTTP 响应接收时对原始响应字节计算并记录的摘要；源 Trace 的整体 SHA 固定了该元数据。`summary_text_sha256` 则由本次从固定 Trace 解出的 assistant `content` UTF-8 文本重新计算。发送和响应事件必须具有相同 Case、Logical ID 和 Request Body SHA。

## 修复与验证范围

- V2 Runner 改为按 Case 从显式冻结表选择回复，并在任何 Mock 请求前校验 Trace SHA、Case/Logical ID、发送响应关联、Provider Response ID、原始响应体摘要、模型与摘要文本摘要。
- 错 ID、正文变化但保留原摘要、Q02-A/Q02-B 来源互换均在 Mock dispatch 前拒绝。
- 旧 V2 的 `MOCK_RESULTS.json`、`MOCK_TRACE.jsonl.gz`、`MOCK_COST_LEDGER.json`、`MOCK_REPLY_PROVENANCE.jsonl.gz`、`FROZEN_INPUTS.json` 与 `PREFLIGHT.json` 在本 Base 上逐个核对 Git blob，均未修改。
- 新一轮实际 Assistant → Domain 持久化 → 后续摘要 → 最终回答 Prompt 的 Mock 证据位于 [`mock_run_01/`](mock_run_01/)；其摘要和回答均为离线 Mock。本轮没有真实 Provider 请求，费用为 USD 0，也没有外部 MCP 调用。

证据级别：来源关联为原始 Trace 静态独立核对加 SHA-256 校验；应用路径为 HTTPX MockTransport 集成运行；语义回答质量未评测。
