# AR-03-MATERIAL-LIVE-01 — frozen live evaluation plan

Status: `FROZEN_BEFORE_LIVE_IMPLEMENTATION`

## Baseline and authority

- Repository: `wgqa/OpsPilot`
- Branch / Base: `codex/ar03-material-01-public` / `3ec06caa6a2d8ef370592d33164be3077a0a5f6f`
- Working tree at freeze: clean.
- Remote `main` and candidate refs: `UNVERIFIED`; `git ls-remote` could not reach GitHub (TCP 443). No remote SHA is inferred.
- `PROJECT_NORTH_STAR.md` blob: `1f737712c7a36ceb34433ac09c3fbba3c3305542`
- `AGENTS.md` blob: `32c45506cceeaa8c76a5c56bf8360ff476b58856`
- Project Skill blob: `d405c8d413d633824b279202cc1503dab4cf0b03`
- Frozen offline cases: `docs/evidence/ar-03/material-01/CASES.json`, blob `faf16fbb857278e98f8afbe179fe327855132967`.
- Frozen offline plan: `docs/evidence/ar-03/material-01/ACCEPTANCE_PLAN.md`, blob `db5a196ca3db3cbde51c84af1fd649c13d1b142d`.
- Existing material offline verdict/limitations remain historical and immutable. The AR-03-REAL-LLM-02 B `PARTIAL` result and all raw traces remain unchanged.

## User journey and frozen cases

Use only the exact inputs and Gold in frozen `CASES.json`; no rewriting, selective omission, or new success definition. The live evaluation covers MAT-01 through MAT-05 and the paired MAT-06 Skill OFF/ON conditions, each in isolated Session/Task/DB/Checkpoint state where applicable. Bound cases use trusted setup for `tenant-a / support-a / ar03-order`; no user text creates or changes a binding.

The model may select any lawful read tools, their order, ask for clarification, answer from sufficient current material, or stop with a bounded unknown. No tool order is required. Pasted logs/configuration remain untrusted user material. Catalog protocol versions never establish deployment version. Current business conclusions require current same-Task/Event observations. A draft is never a submitted ticket or business write.

Skill OFF removes only the scoped protocol-upgrade Skill loader from that isolated run's exposed MCP tools. Skill ON makes the existing authorized loader available. The model is free to use or not use it. Compare actual tool proposal/execution and prompt/context evidence; do not claim an effect if the model does not load it or if the two conditions otherwise differ.

## Execution and budgets

- Provider: `deepseek-flash`, `thinking.type=disabled`, `max_tokens=2048`, `tool_choice=auto` when tools are supplied, `parallel_tool_calls=false`, `stream=false`.
- One active Provider call at a time; 30-second per-call timeout; automatic and manual retries: zero.
- Campaign-wide durable caps, shared across all cases: 16 Provider dispatches and 10 actual MCP `tools/call` dispatches. Any reserved/unknown dispatch consumes its slot; rejected pre-dispatch calls do not.
- Application-side campaign cap: USD 10.50. This uses the previously approved AR-03 live experimental ceiling as a ceiling only; it is a new experiment ID and fresh ledger, not a reuse of any prior ledger or remaining allowance.
- Reserve USD 0.645600 before each Provider dispatch. At 16 dispatches the maximum reservation is USD 10.329600, below the $10.50 cap; usage settlement is recorded separately and is not represented as the provider invoice.
- Input context cap: 12,000 tokens. Existing 30-second request and 12-second tool timeout semantics remain.
- Campaign wall-clock stop: 60 minutes from first real Provider dispatch. No run starts once a hard stop or deadline is reached.
- Existing normal Assistant/D2 limits (8 MODEL / 6 MCP) remain unchanged. Only the new experiment ID may receive scoped live limits up to the campaign ceiling; campaign ledger remains the aggregate authority.

## Hard stops

Stop the entire campaign before any further dispatch on unknown Provider outcome, missing/invalid/violating Usage, request-count/cost/MCP/time cap, authorization or source-currentness anomaly, cross-Task/Event fact association, attempted/actual business write, model/protocol/price mismatch, or inability to prove a durable pre-send reservation. Do not retry, switch model/network/identity, reopen a completed case, or send a connectivity probe. Preserve all attempted/failed/partial outcomes.

If prerequisites cannot be proven (including a usable credential in the execution environment, legal network access, isolated DBs/checkpoints, and aggregate budget enforcement), stop before the first Provider request and record `BLOCKED_BEFORE_PROVIDER_SEND`.

## Evidence required

Per case retain the exact input, Session/Task/Run/Message identities, model decisions visible in tool calls, actual MCP calls/observations, validated sources, final persistent user answer, context count, Completion IDs, Usage, reservation/settlement, stop reason, and business-write counts. Separate real Provider evidence from deterministic/offline checks. Preserve failures and unknowns. No browser, main merge, approval, repair, delivery, ticket submission, or other business write.

## Six-question check

1. **User change:** This evaluates whether a user can move from raw material and authorized protocol sources to a useful bounded interpretation and a sourced support draft without treating pasted data as authority.
2. **Agent decision:** The real model chooses whether and how to read protocol text, load Skill, query the trusted bound order, clarify, continue, or stop; programs enforce identity, sources, budgets, and read/write boundaries.
3. **Observation-driven behavior:** Same Event/Delivery with Receiver `QUEUED` versus `PROCESSED` must produce appropriately different conclusions; unbound pasted `202/QUEUED` must not trigger trusted business reads.
4. **Constraints:** The hard limits protect spend, duplicate/unknown dispatches, scope and zero-write guarantees; legal same-scope document and business reads remain available and are verified in both offline preflight and live traces.
5. **Simplification:** Reuse existing Assistant, MCP, TaskBinding, source revalidation, Skill loader, and durable campaign ledger. Only per-experiment allowlisting/limit alignment may change; no new Runtime, workflow, or budget service.
6. **Evidence and stop:** Complete the frozen cases once within the shared envelope, or stop at the first hard condition; no retry or success-driven rerun. Main remains unchanged and final status is `ACCEPTANCE_CANDIDATE` for independent review.

## Official pricing/protocol reference used for preflight

- DeepSeek model pricing: https://api-docs.deepseek.com/quick_start/pricing/
- Chat Completions request/response schema: https://api-docs.deepseek.com/api/create-chat-completion/

The implementation preflight must recheck these sources and the final serialized HTTP request before any paid dispatch. If the price envelope or request contract differs, stop and do not adjust limits locally.
