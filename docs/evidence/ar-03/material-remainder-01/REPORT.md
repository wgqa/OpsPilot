# AR-03-MATERIAL-REMAINDER-01 — Acceptance Candidate

Repo `wgqa/OpsPilot`; branch `codex/ar03-material-remainder-01`; Base/initial HEAD `305a59c25e4161a5712a1e0127012761e63cf90f`; remote `main` before commit `ec8c3582f6d145eec9979c43607302731411ead8`; candidate branch did not exist remotely at preflight. North Star, AGENTS, project Skill and frozen MAT Gold blobs are listed in `ACCEPTANCE_PLAN.md` and matched the checkout.

## User-facing result

This slice creates a bounded offline path to evaluate the remaining material-investigation conditions without an arbitrary low MCP count stopping a legitimate investigation. It does **not** provide a new real DeepSeek answer: no live Provider request was sent. A formal API/Worker/Assistant/MCP test with deterministic responses reads the same Event's Delivery and Receiver and commits a local answer; that verifies wiring and current-fact boundaries, not real LLM autonomy.

In four isolated MockTransport conditions, the actual local MCP path recorded the same target Event, Delivery `ACKNOWLEDGED / HTTP 202`, and either Receiver `QUEUED` or `PROCESSED`. The deterministic fixture delivered different bounded answers for these states. `load_protocol_upgrade_skill` appeared in the outbound tool schema only when Skill mode was ON. The fixture did not call it, so there is no observed Skill benefit.

All four conditions used the same frozen user input (SHA-256 `012e88fc9fe2352155f1def94a3dcf37395592e76ae5d151e5e05c86d99e3110`); each had its own Task/Session/Run and SQLite. This is a deterministic wiring comparison only, not an LLM Skill A/B.

## Implementation

- Added `AR-03-MATERIAL-REMAINDER-01` as a separate supported but paid-authorization-pending experiment ID.
- Campaign and Assistant Run limits are scoped to 16 Provider calls and no MCP count ceiling. MCP calls continue to be persisted and counted. All old identities keep their existing limits.
- Added an internal Task policy for untouched, same-tenant `orders-async-demo` Tasks only when the matching Campaign row is open and configured for this identity. It preserves 300,000 ms active time and expresses the no-MCP-count policy as a version-scoped zero sentinel in the existing NOT NULL Task column; other policies reject that sentinel.
- The campaign still has a shared $10.50 persisted application cap, $0.645600 pre-send reservation, exact idempotency, and UNKNOWN/invalid Usage stop. No old Campaign schema is migrated; a DB whose schema does not allow this new campaign ID fails closed.
- Provider model construction stays fail-closed for this experiment. ID/key presence alone cannot enable real calls; this slice creates no paid authorization/claim.

## Evidence and results

- Base `305a59c25e4161a5712a1e0127012761e63cf90f`; branch `codex/ar03-material-remainder-01`.
- New focused tests: 15/15 passed in the final focused rerun.
- Combined targeted MAT/AR-03/S3/D2/S2 regression: 125/125 passed.
- Real HTTP Provider requests: 0. Eight HTTPX MockTransport requests returned synthetic HTTP 200 responses. The repeated-read probe used a deterministic local BaseChatModel and no HTTP Provider.
- The repeated-read probe recorded 11 MCP dispatches, Attempts and Observations; repeated calls reused one Evidence ID and only the first Observation added progress. This is a limit-path probe, not a claim that repeated calls are useful.
- For each of the four status/Skill fixtures, the test asserted the pre-send Campaign and Assistant reservations, actual serialized provider contract, same-Event MCP facts, context estimate below 12,000, and no diagnosis, queue or receipt rows.
- Three direct authorization/currentness negatives also passed: order lookup cannot be authorized by chat text, a model-proposed unexposed order tool is rejected without Observation/Evidence, and an unavailable Receiver query remains unknown rather than becoming a completion claim.
- Current assertions distinguish protocol Delivery acceptance from Receiver processing. `QUEUED` does not become completed; `PROCESSED` only supports a statement about the target Event.
- Full pytest was not run. Prior reported full-suite failures remain historical and are not represented as passing here.

## Risks and limits

- Real model behavior for MAT-05 and Skill OFF/ON is untested. The fixture selected the two business reads and did not load Skill.
- This slice doesn't change or prove the LangGraph recursion limit's suitability. The graph remains at recursion limit 36; Run, MCP and durable Task active-time bounds remain in force.
- The existing Campaign ledger does not itself persist an overall wall-clock deadline. Any later one-shot runner must apply the existing 36,000-second Campaign wall-clock contract across all three conditions and after restart.
- The frozen price version is inherited; current prices and the live serialized request must be rechecked before the next paid authorization is used.
- The 11 repeated reads have no new-fact value after the first. Real model evaluation must score redundant calls as efficiency cost without turning “new Evidence per call” into an authorization gate.

## Six-question review summary

1. **User task:** The remaining three conditions now have an offline formal API/Worker/MCP route and sufficient scoped MCP capacity for a later real run. No real-user outcome is claimed yet.
2. **Agent decisions:** Real models may still choose Knowledge, Skill, protocol, business reads, order, clarification and stop. The tests use a fixture and do not prove that decision quality.
3. **Observation-driven behavior:** A paired QUEUED/PROCESSED fixture returns distinct bounded answers from current same-Event observations; OFF/ON toggles only Skill-loader exposure. No live A/B claim.
4. **Constraints:** Only the new experiment's MCP count gate is removed. Provider count/cost, UNKNOWN, time, recursion, binding, authorization and current-source checks remain; ordinary and old experiments retain their limits.
5. **Simplification:** Reuses the same Assistant, Worker, MCP, SQLite attempt ledger and campaign ledger; no new budget service, graph or workflow.
6. **Evidence/stop:** 15 focused plus 125 combined targeted tests pass; no full suite, live Provider or browser run. Next paid execution needs independent review and explicit user authorization.

**Status: `ACCEPTANCE_CANDIDATE`.** This is not a PASS and does not authorize real Provider execution.
