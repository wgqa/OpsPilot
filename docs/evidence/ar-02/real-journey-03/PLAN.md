# AR-02-REAL-JOURNEY-03 Plan

Status: `AUTHORIZED`; one new bounded paid experiment for S02 only.

## Frozen scope

- Base: `bc5484fe721bd2a54bc3a73326ff3c649fa1baa2`
- Cases blob: `0b8411942ec99724d9aa10d45faa50a58676836b`
- Smoke inputs blob: `ee9b1623a2296905c425449709a2f9ae6563caca`
- Experiment ID: `AR-02-REAL-JOURNEY-03`
- Journey: S02-1 through S02-5, one Session. S01 is explicitly not run.
- Formal path: FastAPI → single Worker → `ASSISTANT_V1` → DeepSeek → existing MCP/Domain.
- No approval, REPAIR, DELIVER, ticket submission, external business write, browser automation, or main merge.

## Frozen provider and budget contract

- `deepseek-flash`, non-thinking, `max_tokens=2048`, `stream=false`, `tool_choice=auto` when tools are offered, `parallel_tool_calls=false`.
- At most 16 Provider dispatches, 12 MCP `tools/call` attempts, one in flight, 30 seconds, zero retries.
- Reserve USD 0.645600 before each Provider dispatch. Campaign ceiling USD 10.50; total maximum reservations at the dispatch ceiling are USD 10.329600.
- Unknown Provider outcome, invalid/missing Usage, price/budget violation, or security anomaly stops the complete journey. No retry or extra probe.
- Fresh Domain SQLite, Checkpoint SQLite, and experiment ledger. Historical experiment databases and evidence are not opened or modified.

## User journey

Use the five exact S02 prompts from `docs/evidence/ar-02/real-journey/CASES.json`. The model may choose any legal order, query Knowledge, read bound order/Event facts after trusted API binding, answer, clarify, or stop. The test fixture creates an isolated `ar02-order` whose target Event has Delivery 202/ACKNOWLEDGED and Receiver QUEUED; fixture setup is recorded separately from Agent observations.

## Evaluation

For each turn retain the exact user prompt, Session/Task/Message/Run IDs, model tool proposals, actual MCP calls and observations, persisted answer, current Run evidence, Context estimate, Provider request/Completion ID/model/Usage, reserved and settled application estimate, and stop condition. A model proposal is not an executed tool call; HTTP 200 alone is not business success.

The journey is complete only if all five user turns receive persisted answers and the final draft remains sourced and explicit about unknowns. The agent does not create a diagnosis receipt, repair, approval, delivery, handoff, or ticket.

## Execution sequence

1. Verify the exact base, frozen file blobs, current official pricing, clean branch, fresh runtime paths, and opt-in credential presence without printing secrets.
2. Use explicit HTTPX MockTransport to verify the SDK's actual serialized request and exact endpoint; no live request is used for this check.
3. Run focused offline budget/wire tests and the existing frozen context-continuity journey.
4. Commit the minimum new campaign ID/schema and isolated S02 runner. Recheck branch and committed HEAD.
5. If every preflight invariant holds, run S02-1..5 exactly once through the formal API and Worker with the authorized DeepSeek network path.
6. Save all results, including failures, commit evidence, push only this isolated branch, and stop for independent review.

## Price check

Official DeepSeek pricing and API pages were checked on 2026-11-01:

- https://api-docs.deepseek.com/quick_start/pricing/
- https://api-docs.deepseek.com/api/create-chat-completion/

At published peak cache-miss rates, 616,000 input tokens at USD 0.30/M plus 384,000 output tokens at USD 1.20/M gives USD 0.645600, the frozen per-dispatch reserve. This is an application-side conservative reservation based on the published context/output envelope, not a provider invoice guarantee. The published `deepseek-flash` alias currently maps to DeepSeek-V4.1-Flash-1017.
