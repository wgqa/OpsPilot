# AR-03 Material Live — Post-Live Closeout

**Status:** `ACCEPTANCE_CANDIDATE`

**Base:** `559aeeedf0ac87521dae467bdf0bacfd52a3df9c`

**Branch:** `codex/ar03-material-live-01-post-live-closeout`
**Scope:** offline audit repair and read-only inspection of RESUME-02. No Provider request, Worker start, claim consumption, or business write was performed for this closeout.

## Opening verification

- North Star and root `AGENTS.md` were opened from Base `559aeeedf0ac87521dae467bdf0bacfd52a3df9c`; their Git blob IDs are `1f737712c7a36ceb34433ac09c3fbba3c3305542` and `32c45506cceeaa8c76a5c56bf8360ff476b58856`.
- `.agents/skills/opspilot-slice-review/SKILL.md` was opened and its A/C workflow applied; blob `d405c8d413d633824b279202cc1503dab4cf0b03`.
- The frozen MAT cases Blob is `faf16fbb857278e98f8afbe179fe327855132967`. Remote `main` was `ec8c3582f6d145eec9979c43607302731411ead8` at opening; this candidate is isolated from `main`.
- Read the RESUME-02 frozen report/results/failures and the applicable M2-02 deferred-gate record. Historical Gold and archived execution artifacts were not edited.

## User outcome and recovered evidence

RESUME-02 persisted a real model-generated, unsubmitted support draft for MAT-04. It says the target Event's transport was acknowledged with HTTP 202 while the Receiver observation was `QUEUED`; it does not claim processing completed. It distinguishes the user's pasted `retry_at` clue from the current bound order facts, notes that no trusted `retry_at` exists on the current delivery, and lists the source Event/order/environment and online deployed protocol version as unknown. It recommends a follow-up observation or receiver-operator contact after the SLA boundary. This is a persisted answer, not a submitted ticket, diagnosis receipt, or business repair.

The draft is linked through Run `run-3ecadd9f-c329-4fef-a261-b79ddfa224c1`, Task `task-62990628-9d80-4cab-bb18-248ba574acde`, Session `session-b96c0b94-9807-4021-89bd-fa0c2c6546e`, source Message `message-79900f64-3f8d-44dd-a6e6-e926b6cc350b`, and persisted Answer Message `message-a6a78420-7ac2-485f-ad91-7e72cd4a7c5d`. The answer body digest is `d7c20027f5cbd14451837e5e4343f8330dcc7bc32b7882bf26c46a177ecf14bb`.

The three persisted business observations are all `OK`, tied to that exact Task and Run and to Event `event-d0f3a599-e85e-4b69-9cd5-5709375b390b`. They are historical observations now; their Evidence TTL has expired, so they are not current facts for a new investigation:

| Tool | Observation | Evidence | Finding |
|---|---|---|---|
| `get_callback_delivery` | `observation-cea00a94-2efc-4e41-904b-603997c5ab89` | `evidence-fb4a800d-ca90-42b4-964f-2d6f738d7501` | `ACKNOWLEDGED`, receiver HTTP 202 |
| `get_receiver_processing` | `observation-62025a5c-41fa-4cd8-87ee-7e956a9ce494` | `evidence-3f257994-1c7e-49e6-b046-8a9d667de429` | `QUEUED` |
| `get_callback_transport_history` | `observation-59875c28-80f0-4aac-aa16-d5159b9776d8` | `evidence-21bbc4ae-5036-4474-becb-12584c53290f` | No attempts in recorded-observation coverage; absence is not proof no send occurred |

Protocol reads were sourced from `receiver-ack-contract-v2` v2.1.0 and `callback-retry-contract-v2` v2.0.0. Those document versions do not prove the online deployed version. `TRACE_SUPPLEMENT.jsonl` contains a content-minimized, read-only derivation from the preserved HTTP trace and Domain DB; original request/response bodies remain private and unchanged.

## Frozen condition status

This supplemental audit does not rewrite RESUME-02's original `PARTIAL_STOPPED` result or historical `RESULTS.json`.

| Condition | Supplemental status | Evidence boundary |
|---|---|---|
| MAT-01 protocol excerpt | `PASS` as previously recorded | 3 real Provider completions, 2 successful MCP calls, persisted answer and versioned source references; original result says `ACCEPTED` |
| MAT-02 unbound user material | `PASS` as previously recorded | 1 real Provider completion, no MCP call, persisted answer; original result says `ACCEPTED` |
| MAT-03 malformed material | `PASS` as previously recorded | 2 real Provider completions, 2 successful MCP calls, persisted answer and Knowledge/source result; original result says `ACCEPTED` |
| MAT-04 bound Receiver QUEUED | `PARTIAL` | Real completion, successful Run, persisted answer, and three same-Run/current-at-capture business observations independently verified. A successful original case audit was not persisted; source-currentness at capture is inferable from failure order but not directly saved. Current revalidation correctly rejects the expired evidence. |
| MAT-05 Receiver PROCESSED | `NOT_RUN` | No Run or Provider request in RESUME-02 |
| MAT-06 Skill OFF | `NOT_RUN` | No Run or Provider request in RESUME-02 |
| MAT-06 Skill ON | `NOT_RUN` | No Run or Provider request in RESUME-02 |

The original campaign used 9 Provider requests and 10 MCP calls; its stop reason is `KeyError:'run_id'`, after MAT-04's answer had been persisted. The 10/10 MCP ledger was also exhausted, so there was no remaining MCP allowance. These are separate facts; the audit exception is the recorded stop reason.

## MCP consumption from the real trace

| Case | Calls | Calls by tool | Evidence increment |
|---|---:|---|---:|
| MAT-01 | 2 | `list_scoped_protocol_documents` ×1; `read_scoped_protocol_excerpt` ×1 | 0 business Evidence rows |
| MAT-02 | 0 | none | 0 |
| MAT-03 | 2 | `list_scoped_protocol_documents` ×1; `search_project_knowledge` ×1 | 0 business Evidence rows |
| MAT-04 | 6 | `get_callback_delivery` ×1; `get_receiver_processing` ×1; `list_scoped_protocol_documents` ×1; `read_scoped_protocol_excerpt` ×2; `get_callback_transport_history` ×1 | 3 business Evidence rows |
| **Total** | **10** | All recorded MCP calls completed `OK` | **3** |

MAT-04's six calls were not a repeated same-tool loop: three obtained distinct same-Event delivery, receiver, and transport-history observations; one discovered scoped protocols; two read different, versioned excerpts. The calls added useful but differently authoritative evidence. The transport-history result explicitly has `RECORDED_OBSERVATIONS_ONLY` coverage, so its empty attempt list is not a complete send audit. Full per-call references and sanitized parameters are in `MCP_ANALYSIS.json` and `TRACE_SUPPLEMENT.jsonl`.

## Provider, cost, and side effects

- 9 real HTTPX Provider requests and 9 HTTP 200 completions, each with a unique Completion ID and returned Usage; no retry was recorded.
- Aggregate Usage: 28,599 prompt tokens, 3,891 completion tokens, 32,490 total tokens.
- Application ledger estimate: USD 0.013253 settled; USD 0 reserved. This is an application estimate, not a Provider invoice.
- Original campaign limits remained 16 Provider, 10 MCP, USD 10.50; it consumed 9/16 and 10/10 respectively.
- The archived DB passes `PRAGMA integrity_check`. Direct counts of diagnosis, plan, approval, permission, ActionIntent/Ledger, verification, report, delivery, and handoff write tables are all zero. No business write is inferred from ordinary task/session outbox events.
- Closeout activity itself: 0 Provider requests, 0 MCP calls, 0 business writes, 0 Worker starts, 0 claim consumptions.

## Audit defect and repair

The SQL selected `a.run_id AS attempt_run_id`, while `_audit_case()` read `item["run_id"]`. The resulting `KeyError` masked completion of the case audit. The fixed query also verifies Task and Evidence ownership and includes observations linked by the current Run's persisted MCP call, so a wrongly cross-Run-linked observation is detected instead of disappearing from the audit selection. `_validate_audit_observation_links()` runs before current-source rejection so the association failure remains explicit.

The original Run/Answer/Evidence records remain untouched. A current-source check performed against the archived MAT-04 database now returns `BUSINESS_SOURCE_INVALIDATED` because its Evidence TTL has expired. At capture time, source currentness is not directly present in the persisted case result. It is only inferable because the original audit checks source currentness before the line that raised `KeyError`; this is not promoted to direct evidence.

## RESUME-01 claim archive check

The configured RESUME-01 runtime claim is present at the workspace runtime path and its SHA-256 is `f8f4b2618fa263c10e8ea85def4140218d62ccd571ad3a9e06b2bd1ebcd11458`, matching the immutable hash in the RESUME-02 Runner. Its allowlisted metadata identifies the old claim as `CLAIMED_ONE_SHOT_NO_RETRY`. The tracked `resume-01/authorization/claim.json` archive copy is absent. Therefore the earlier “missing” finding was a missing archived copy/reference, not absence from the configured runtime path at this inspection. This does not establish the historical file's availability at the time RESUME-02 ran. The root historical claim remains SHA-matched at `db65416c9e361a064fe2bf29b0864793343e81d0d38edb637b89b4b8069d1e3a`.

## Validation performed

- RED-03: the old audit failed same-Run validation with `KeyError('run_id')`; cross-Run reference was not reported as `CROSS_RUN_OBSERVATION_ASSOCIATION`.
- GREEN-01: initial 2/2 targeted audit tests passed.
- GREEN-04: after checking Task-link visibility as well as Run-link visibility, 3/3 targeted audit tests passed, including the cross-Task negative.
- GREEN-03: initial project `.venv` regression: 20 passed.
- GREEN-05: final project `.venv` run after the last query change, covering the closeout + RESUME-02 + Recovery-02 modules: 21 passed.
- The first broad attempt with system Python is retained as an environment failure: 8 failures caused by missing `langchain`, 12 passed. No dependency was installed; the same tests passed with the repository `.venv` (`langchain 1.4.1`).
- Historical audit-failure setup logs RED-01/02 are retained as fixture setup errors; they are not counted as product RED.
- Full `pytest` was not run. No live Provider/MCP/HTTP or browser verification was performed for this closeout.

## Six-question closeout

1. **User change:** RESUME-02's real MAT-04 answer can now be reviewed with its exact persisted message, Run and three same-Event Evidence associations, while keeping the missing formal case-audit result visible.
2. **Agent decision:** The real model selected delivery, receiver, protocol discovery/read and transport-history tools; no fixed order was imposed by this repair.
3. **Observation-driven:** HTTP 202/ACKNOWLEDGED and Receiver QUEUED came from current same-Event observations; the answer did not equate acceptance with processing completion.
4. **Constraints and legitimate paths:** The audit rejects cross-Run or cross-Task Evidence association and accepts a legitimate same-Run observation; no investigation or tool budget contract changed.
5. **Simplification:** Reused the Runner's existing audit query and a narrow link validator; no schema, budget, business gate, or new framework was introduced.
6. **Evidence and stop line:** Original hashes, private DB/checkpoint, claim, traces, and historical results remain unchanged. Only free tests and read-only inspection ran. The follow-up paid experiment is a proposal only; no further execution is authorized here.

**Candidate decision:** `ACCEPTANCE_CANDIDATE` for independent review. This report is not a PASS or an authorization for another paid experiment.
