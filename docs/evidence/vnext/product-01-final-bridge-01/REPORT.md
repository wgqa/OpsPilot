# PRODUCT-01-FINAL-BRIDGE-01 — Acceptance Candidate

## Result

The offline implementation connects the ordinary Assistant to the existing S1/S2 professional workflows without creating another workflow engine or state authority.

The deterministic end-to-end S2 journey completed through the formal API, Worker, Assistant MCP server, existing S2 Investigator, Domain, local queue, and same-Session Assistant follow-up. It ended at `SCOPE_ESCALATED / PENDING_REVIEW`: the request is waiting for a human reviewer; no new scope was granted and the 403 was not repaired. The persisted user answer says this explicitly.

The existing S1 local Worker/MCP/HTTP test still reaches `WAITING_APPROVAL`. A same-Session Assistant read projection exposes the trusted Plan and source references while labeling the result `PERSISTED_OUTCOME_NOT_CURRENT_PROBE`. No approval or repair was created.

This is deterministic offline evidence, not proof of real LLM behavior or browser usability.

## User journey evidence

S2 input: “接口访问失败，我怀疑是权限问题，帮我查一下。”

The deterministic Assistant selected `propose_controlled_auth_investigation`. The proposal was tied to the exact source message and reported that it created no Task or authorization. Before user confirmation, the isolated database had zero TaskBinding, approval, and action ledger rows.

The test then used the existing explicit Session Task API with that same source message. The professional Investigator used the existing local MCP/HTTP path and produced a current 403/Authz denial (`SCOPE_INSUFFICIENT`, missing `orders.read`) and `HANDOFF_READY`. The user submitted the existing handoff draft once. The existing Domain produced one queue entry, one immutable receipt, and one outbox entry.

On the user's same-Session follow-up (“现在修好了吗？交给谁了？给我一段客户说明。”), the unbound Assistant selected `read_session_professional_outcomes`. It read the trusted diagnosis and receipt, then answered that the request is waiting for human handling, no new scope has been granted, and recovery has not been proven. The outcome was not presented as a repair or approval.

The trace preserves the actual local MCP observations, including two valid observations and two rejected repeated authorization calls (`TOOL_NOT_ALLOWED_FOR_CURRENT_S2_EVIDENCE`, each with zero evidence progress). Those calls are recorded as failures, not hidden or represented as useful evidence.

## Changes

- Added two narrowly scoped, read/proposal-only tools to the existing Assistant MCP server for unbound SUPPORT runs:
  - `propose_controlled_auth_investigation(rationale)` is advisory and tied server-side to the exact current user message, its digest, Session, tenant, and sequence.
  - `read_session_professional_outcomes()` accepts no model-supplied IDs. It derives the Session and caller from the trusted run, then reads only active same-tenant/same-actor Tasks linked to that Session.
- Reused existing `get_task_outcome()` and `get_s2_handoff()` Domain reads. Results retain Plan/Receipt/Run/Evidence references and explicitly label persisted S1 verification as historical rather than a current probe.
- Revalidated saved proposal and outcome sources before delivery. A TaskControl revision change makes the previous result stale and removes it from the source response.
- Updated the existing System prompt to permit an advisory suggestion while preserving the user's explicit confirmation requirement.
- Added frontend projection for a current proposal tied to the exact question, with a button that opens the existing confirmation flow. No Task is created by the Assistant tool.
- Updated result labels so S1/S2 states share “专业调查结果” while statuses distinguish waiting, rejection, repair, verification, and handoff outcomes.

No new API route, Task/Approval/Receipt state table, Agent loop, or business permission was added. Professional outcome reads are bounded to four latest linked tasks and return `omitted_count`; a larger-session UX remains a product consideration.

## Security and compatibility checks

- Unbound session has no access to another Session's professional outcome, even when the user message includes a forged Task ID.
- A different tenant/actor receives 404 for the Assistant source endpoint.
- Incrementing the TaskControl revision invalidates the saved S2 outcome source; the UI answer becomes an invalid-source notice.
- SUPPORT proposal path creates no Task or approval. Task creation uses the existing explicit confirmation endpoint.
- Local S2 handoff created one queue/receipt/outbox; repair count and scope-policy write attempts were zero. External business writes were zero.
- S1 projection includes the trusted Plan hash, investigation Run, Evidence IDs, and `WAITING_APPROVAL`; it does not imply repair or live recovery.
- Existing S3 assistant paths were included in the relevant Python regression.

## Tests and evidence

- Focused formal journeys: 2 passed (`focused-journeys.log`).
- Relevant Python regression across PRODUCT bridge, S1, S2, AR-02 runtime, and S3: 41 passed (`python-regression.log`).
- Frontend unit suite with persisted S1 trace: 23 passed (`frontend-tests-with-s1-trace.log`).
- Vue typecheck and production build: passed (`frontend-build.log`).
- ESLint on changed frontend files: passed (`frontend-eslint.log`).
- `git diff --check`: run before final commit.
- Full repository pytest: not run.

Trace files: `TRACE-S1.json`, `TRACE-S1-SESSION.json`, `TRACE-S2.json`.

## Six-dimension review

1. **User result:** A same-Session path now carries an access question from ordinary chat through explicit S2 investigation and back to a truthful handoff explanation. Existing S1 plan results can also be read back in the same Session.
2. **Agent decision:** The Assistant can choose to suggest investigation or read the linked outcome; neither tool writes business state. The existing Investigator still owns S1/S2 execution.
3. **Observation:** Current Domain diagnosis and immutable receipt drive the S2 answer. The S1 result is explicitly historical. Invalidated TaskControl scope cannot be reused from a prior Assistant response.
4. **Constraints:** No authority was added to the model. Existing owner, tenant, actor, TaskBinding, active TaskControl, explicit confirmation, and existing handoff submission rules remain in force.
5. **Simplification:** Existing MCP server, Task API, Investigator, `get_task_outcome()`, `get_s2_handoff()`, receipt, queue, and frontend confirmation flow are reused; no parallel status service or state machine was introduced.
6. **Evidence and stop:** Offline deterministic traces and targeted regressions support the implementation. Real Provider, browser, and full-suite outcomes remain unverified; implementation stops at this candidate.

## Remaining limits

- Real Provider model choice and answer quality were not tested.
- Browser CTA, page refresh, and visible source detail were not tested because Browser STOP remains active.
- The full pytest suite was not run.
- Same-Session outcome reading currently returns at most four latest linked professional tasks; if older results are omitted, the tool reports the count but does not page them.
- Current user-visible status of a past S1 verification is explicitly historical; the feature does not perform a new probe.

Implementation status: `ACCEPTANCE_CANDIDATE`, pending independent review.
