# AR-03-REAL-LLM-01 — Frozen Live Experiment Plan

**Status before execution:** `READY_FOR_SINGLE_AUTHORIZED_EXECUTION`

**Authorization:** user and main agent authorized one paired DeepSeek run under the limits below.

**Repository:** `wgqa/OpsPilot`

**Authorized base:** `codex/ar03-real-llm-01@e416bd1398b5a4bca6cdf3360f3ae78037a2740b`

**Execution branch:** `codex/ar03-real-llm-01-live`

**Frozen standards commit:** `6f9074e84c185553cfeab0f225e81640b8b525f0`

## Frozen inputs

- `docs/evidence/ar-03-real-llm-01-prep/CASES.json`, Blob `c29b5cf7630fa838a365634d0df5f9f0f2bfa834`
- `docs/evidence/ar-03-real-llm-01-prep/GOLD.md`, Blob `88d5e6f40f027ce2622b957d8ab32b8d2b827381`
- `docs/evidence/ar-03-real-llm-01-prep/BUDGET.md`, Blob `5a71096584b4003b5f30c53fd69ccfd11bbc53d4`

The user prompt is loaded from the frozen `CASES.json` and checked against the exact frozen string by the one-shot runner. The same prompt is used once in scenario A and once in scenario B. Tool order is not prescribed.

## Two isolated scenarios

Both use `tenant-a / support-a`, a trusted API binding to `ar03-order`, authorized callback protocol documents `callback-retry-contract` v1.0.0 and `callback-retry-contract-v2` v2.0.0, the same target Event `event-00000000-0000-4000-8000-000000000001`, and Delivery `HTTP 202 / ACKNOWLEDGED`.

1. **A — QUEUED:** the current same-Event Receiver is `QUEUED`. The answer must separate transport acceptance from business completion and preserve remaining unknowns.
2. **B — PROCESSED:** the current same-Event Receiver is `PROCESSED`. The answer may confirm this Event was processed, without generalizing to other Events or live protocol deployment.

Each scenario receives a new Domain database, Checkpoint database, Session, Task and trace directory. Fixture setup is explicitly labeled as setup and is never represented as an Agent observation. The trusted API binding precedes the frozen user request.

## Frozen execution envelope

- Provider: DeepSeek `deepseek-flash`; thinking disabled; `max_tokens=2048`; `tool_choice=auto` with tools; `parallel_tool_calls=false`; `stream=false`.
- Per-request timeout 30 seconds; SDK and HTTP transport retry count 0; one Provider request in flight.
- Paired aggregate: at most 16 Provider requests, 12 MCP `tools/call`, USD 10.50 application reservation.
- Each separate scenario database is durably capped at 8 Provider and 6 MCP attempts. Thus the sum is at most 16/12 and the maximum reservation is `16 × USD 0.645600 = USD 10.329600`, below USD 10.50.
- The existing persistent ledger records every reservation, including binding admission, failed calls and unknown outcomes. A single-use execution claim prevents a second run of this experiment. No retry or rerun is allowed.
- No REPAIR, Approval, DELIVER, ticket submission, other business write, browser automation or `main` change.

The only implementation addition is an AR-03-specific per-scenario cap in the existing experiment ledger, plus an offline-tested one-shot runner/transport recorder. Other experiment IDs keep their existing limits.

## Stop and evaluation rules

Unknown Provider result, timeout, missing/invalid Usage, closed budget, authorization anomaly, cross-Task/Event association error, unintended business write or protocol/price mismatch stops both scenarios. An incomplete but non-blocking A result may proceed to B only when Usage is valid, the ledger remains open, no unauthorized access occurred and no write happened. No answer is re-run for quality.

Assessment distinguishes real Provider response, actual MCP execution/Observation, program guards, persisted user answer and frozen business Gold. A model-proposed tool call is not an executed call; HTTP 200 alone is not a passed business outcome.
