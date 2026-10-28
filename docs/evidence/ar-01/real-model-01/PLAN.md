# AR-01-RM-01 — P0 freeze

Status: P0 IMPLEMENTATION_AUTHORIZED; P1/P2 NOT_AUTHORIZED / NOT_RUN.
Base: `55d3dd6f3671755621905d3d1437bd7a8dce053e`, branch
`codex/ar01-free-agent`; remote main `ec8c3582f6d145eec9979c43607302731411ead8`.
No main merge, production code, paid calls, browser use, AR-02 or Gold edits.

## Actual reads and retained contracts

Read target checkout rules and Skill, not an archive or discovery substitute:
North Star blob `1f737712c7a36ceb34433ac09c3fbba3c3305542`, AGENTS blob
`32c45506cceeaa8c76a5c56bf8360ff476b58856`, Skill blob
`d405c8d413d633824b279202cc1503dab4cf0b03`. Skill A/B applied.
Read AR-01 PLAN/CASES/PARITY/REPORT/RESULTS/FAILURES/REAL_MODEL_PLAN,
Stage B HOLD/browser STOP and M2-01/M2-02 DEFERRED_GATES. AR-01's local
acceptance is user-reported ACCEPT_WITH_LIMITS, not new independent verification.
This task supersedes the older real-model sample/budget proposal, not its results.

## Frozen comparison

Five variants, in this order: AR01-01/material, AR01-03/acknowledged,
AR01-03/failed, AR01-04/different-event, AR01-06/scope. One A then one B
per variant; no repeats or tuning. First material A/B pair must pass protocol
preflight before proceeding. Reuse original CASES.json unchanged.
A retains S3Nodes strategy A policy; B retains standard create_agent loop.
Six raw MCP schemas/descriptions, trusted TaskBinding and equivalent independent
fixture states. No SQL fact tool; no Diagnosis/repair/handoff writer.
Prompt/native-message/context and multi-tool execution differences remain confounds.

Same proposed live configuration: https://api.deepseek.com, deepseek-flash,
thinking disabled, nonstreaming, max_tokens 512, auto tools,
parallel_tool_calls false, max_retries 0. Exact outgoing JSON, not SDK field
names alone, must be checked. Unsupported fields/config/response drift stop;
do not retry, silently discard fields or switch models.
Per Run: MODEL 8 / MCP 6, model 30s, tool 12s, entire policy invocation 60s.
Global: at most 80 Provider reservations, 60 MCP attempts, one Provider in flight.
USD 0.50 is a proposed target, not approved spending or an established guarantee.

## Frozen local acceptance (no paid network)

| ID | Positive / negative expectations |
|---|---|
| P0-01 | Default off and absent paid authorization cause zero external HTTP; explicit loopback-only stub can exercise installed SDK. |
| P0-02 | A/B actual wire tool schemas/config match; correct vendor max_tokens field and disabled thinking; unknown parameters reject instead of disappearing. |
| P0-03 | Raw response model, fingerprint, completion/request IDs and strict Usage persisted; missing/malformed Usage, drift, extra output, HTTP failure stop further batch execution. |
| P0-04 | Atomic global request/cost/single-flight reservations; settled known Usage releases unused exposure; UNKNOWN/timeout/cancelled/pre-send failure retain reservation and count on reopen. |
| P0-05 | Two independent connections cannot exceed caps; duplicate logical request or case/group cannot dispatch again. SDK retry count zero, 400/timeout does not issue hidden extra requests. |
| P0-06 | Conservative monetary preflight rejects USD 0.50 if safe bound exceeds remaining exposure; a local-only larger cap proves legal reserve/settle path. No live cap increase authorized. |
| P0-07 | Existing deterministic Agent tests and fresh local MCP A/B tests preserve authorized reads, scope denial, protected business state, exact tool capabilities and bounded nonempty fallback. |
| P0-08 | Fixed batch retains failures and stops on first protocol/accounting error, with incomplete pairs explicit. No P2 intelligence inference from fake model. |

Sources checked 2026-10-28: official [pricing](https://api-docs.deepseek.com/quick_start/pricing/)
and [completion API](https://api-docs.deepseek.com/api/create-chat-completion/).
Use peak uncached input USD 0.30/M and output USD 1.20/M, conservatively ignoring
cache discounts. Prior `opspilot/smokes/m4_continuous.py` records output exceeding
SDK nominal 512; do not overwrite it. Until the actual vendor bound is independently
established, reserve documented model-wide ceilings: input 1,048,576 and output
393,216; USD 0.786432 per request, conservatively overcounting joint context.
This exceeds 0.50, so default live preflight must stop before sending.
Local SDK protocol tests cannot prove vendor compliance or billing.

## Skill B six questions

1. User change: obtain an auditable, disabled-by-default real-model comparison
adapter; no new production user feature or demonstrated intelligence benefit.
2. Agent decisions: existing A/B decide tools/continue/clarify/stop unchanged.
3. Observations: paired 202/503 and same/different Event cases remain frozen;
local models establish mechanics only, not real model responsiveness.
4. Constraints: block unpaid/unaccounted/repeated sends and preserve explicitly
authorized, budgeted legal requests (local positive and negative tests).
5. Simplicity: reuse LangChain, existing Runner/MCP/Attempt tables. One small
experiment-owned reservation ledger follows the existing finite-meter pattern;
SQLite provides cross-process atomicity missing from the older JSONL meter.
6. Evidence/stop: freeze then local RED/GREEN, actual loopback HTTP and MCP,
raw logs/Trace, branch-only commits; P1/P2 remain NOT_RUN, then stop for review.
