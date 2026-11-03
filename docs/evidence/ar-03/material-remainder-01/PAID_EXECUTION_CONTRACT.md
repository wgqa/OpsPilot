# Proposed next paid execution contract — not authorized in this slice

- Experiment ID: `AR-03-MATERIAL-REMAINDER-01`
- Cases: frozen `MAT-05-BOUND-PROCESSED`, `MAT-06-SKILL-OFF`, and `MAT-06-SKILL-ON`; preserve MAT Gold. MAT-05 reuses the exact MAT-04 input because the frozen MAT-05 row has no separate `input` field.
- Isolation: one new Domain DB and campaign ledger shared across the three serial conditions; separate Session, Task and checkpoint per condition; new one-shot claim. Never reuse RESUME-01/02 claim, DB, ledger or trace.
- Provider: DeepSeek `deepseek-flash`, thinking disabled, `max_tokens=2048`, tool choice auto when tools exist, `parallel_tool_calls=false`, `stream=false`, 30-second timeout, single flight, zero automatic/manual retries. Keep the 12,000-token input budget.
- Caps: 16 Provider requests; no MCP count cap, but every MCP call remains durably counted. Application cost cap USD 10.50, with USD 0.645600 reserved before each Provider request under the current frozen price version. Re-check official model price and exact serialized request before use; if the reserve no longer covers the approved envelope, stop before sending.
- Time bounds: preserve 60 seconds per Assistant Run, 12 seconds per MCP handler, 300,000 ms durable Task active time and recursion limit 36. Enforce the existing 36,000-second Campaign wall-clock cap in the one-shot runner across the entire sequence, including after process restart; do not reset it per condition.
- Stop: any Provider UNKNOWN/timeout, Usage missing or invalid, price/request mismatch, source/authorization anomaly, campaign budget/time stop, or attempted business write ends the campaign. Never retry or rerun. Normal content PARTIAL may continue to the next frozen condition only if all integrity checks remain sound.
- Writes: none. Do not expose REPAIR, Approval, DELIVER, handoff or ticket submission.
- Evidence: preserve raw private HTTPX/Provider/MCP/SQLite trace; publish only reviewed redacted summaries. Separate model choices, tool facts, program guards and final user answers.

This proposal is not an authorization. The current slice performed zero real Provider requests and created/consumed no paid one-shot claim.
