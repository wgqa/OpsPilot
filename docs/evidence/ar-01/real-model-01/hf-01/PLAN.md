# AR-01-RM-01-HF-01 freeze

Base `458a5f02f31b1ad0b056d3d0466a0bf73fd076a2`, branch
`codex/ar01-free-agent`; fetched remote main
`ec8c3582f6d145eec9979c43607302731411ead8`. Tracked experimental tree clean;
existing untracked test directories preserved. Dirty original main checkout
`D:/学习/agent新项目` (AGENTS modified) is read-only for this task.

Actual Skill A/B, North Star and AGENTS reads: blobs respectively
`d405c8d413d633824b279202cc1503dab4cf0b03`,
`1f737712c7a36ceb34433ac09c3fbba3c3305542`,
`32c45506cceeaa8c76a5c56bf8360ff476b58856`.
Read original P0 PLAN/PREFLIGHT/REPORT/RESULTS/FAILURES and both budget/adapter
modules; retained Stage B HOLD/browser STOP, M2-01/M2-02 DEFERRED_GATES and
historical provider-meter evidence. User reports P0 ACCEPT_WITH_LIMITS, P1 HOLD;
this is not an independently reissued acceptance.

## Limited design to test, before implementation

Preserve legacy ledger policy/default and all old 48 tests unchanged. Add an
explicit opt-in experiment reservation policy `REQUEST_WIRE_V1`; never reinterpret
old reservations or silently migrate a ledger's policy.

Its input bound is the documented model context ceiling, **not** a byte-count or
12,000-token estimate. The bound covers messages, six complete tool schemas and
server framing together. The public offline tokenizer does not certify current
server tool serialization (download inspected, no remote Python executed).
Only the output bound narrows to the documented, actually serialized max_tokens
512 in disabled-thinking mode. Both A/B retain exact tools/context. Formula in
microUSD: `ceil(1048576*0.30 + 512*1.20) = 315188`, USD 0.315188.
This is conservative request-contract accounting, conditional on vendor compliance,
not an absolute billing guarantee or a new inference from old success rates.

Calculate from the installed SDK's prepared body, then verify the actual HTTP
body digest before sending. Unknown modality/parameter/model/mode, malformed
output limit or changed body fail closed. Save per-request bound/provenance;
Usage outside either bound halts future calls, while unknown outcomes retain
the full reserve. Global cap remains USD 0.50 and <=80 reservations, single-flight.
Two unknown small requests cannot both fit; settlement releases unused exposure.

No unsupported-field deletion/retry or model switch. parallel_tool_calls=false
stays on the wire; current Chat Completions documentation does not explicitly
list it, so acceptance is REQUIRES_AUTHORIZED_PROVIDER_PROBE. It is a scheduling
preference, not trusted authorization. x-request-id is not documented as mandatory:
under the opt-in policy a real returned Completion ID may provide correlation when
the header is absent; preserve null header and explicit correlation kind. Missing
Completion ID, Usage, model/fingerprint or finish reason still stop as appropriate.
Compatibility changes are candidates for main-Agent review, not auto-accepted rules.

No paid authorization exists. Ordinary P1 authorization cannot activate the new
policy. Any future live probe must have a separate one-request, USD 0.50,
exact-wire-digest authorization; no path automatically launches the five pairs.
This round implements/tests the gates only and never constructs a paid client.

## Frozen HF01 tests

| ID | Bidirectional evidence |
|---|---|
| 01 | Small valid actual request reserves <=0.50 with explicit bound basis; legacy policy still refuses. |
| 02 | Unknown/malformed/high-cost contracts or changed wire reject before send; full valid tool schemas remain accepted. |
| 03 | Settled charges + unknown reserve + next request cannot cross global cap; legal known-small charges permit continuation. |
| 04 | Timeout/cancel/lost response retains request/count/exposure. |
| 05 | Independent OS processes compete, restart retains reservations, same logical key cannot resend. |
| 06 | Missing/inconsistent/excess input or output Usage and unexpected thinking halt continuation. |
| 07 | A/B actual wire schemas/config/initial facts/permissions equal, no business writes. |
| 08 | Same five local paired cases continue under USD 0.50, without shrinking goals/schema/context or changing old Gold. |
| 09 | Default off, absent/mismatched/P1-only authorization never constructs a paid client; only an isolated synthetic gate test may replace the client factory. |
| 10 | Old 48 experimental tests and necessary 72-test S1/S2/S3 safety subset freshly rerun; old tests/records unchanged. |

Save preimplementation RED and all subsequent attempts in this new directory.
Local fixture responses prove mechanics only. Final result must be either
READY_FOR_AUTHORIZED_PROBE (with assumptions and pending main-Agent review) or
HOLD_WITH_BLOCKERS; no self PASS, P1/P2/AR02/main/browser execution.

## Skill B six questions

1. User change: remove a needlessly coarse experimental fee refusal if justified;
no production user capability or autonomy improvement is claimed.
2. Agent decisions: A/B tools/continue/clarify/stop unchanged.
3. Observation-driven behavior: preserve paired 202/503 and Event cases; this
patch changes accounting/compatibility, not the decision policy.
4. Restrictions: block unpaid, duplicate, unknown-cost or mutated sends while
valid same-scope small requests can continue; test both paths and legacy behavior.
5. Simplicity: one versioned policy in the current experiment ledger/adapter,
no Cost Service, tokenizer runtime or Domain/Agent loop refactor.
6. Evidence/stop: official docs + inspected old records + actual local wire,
RED/GREEN/recovery/SQLite/MCP logs, then branch commit/push and stop for review.
