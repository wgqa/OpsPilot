# Stage B Supplement 01 — Inspector Authorization and Cached Result Redaction

**Status:** `ACCEPTANCE_CANDIDATE` for this targeted supplement only. Stage B remains unaccepted until the authorized real-browser journey is run in a permitted environment.

## Baseline and scope

- Repository: `wgqa/OpsPilot` (`origin` = `https://github.com/wgqa/OpsPilot.git`).
- Frozen implementation base and `origin/main` at test freeze: `ad056c38da1f925fca80b74aef0a88a686ac97e1`.
- Freeze commit: `daa475b`; RED test commits: `ffff924`, `b222e3c`, `f25e380`, `6fba3d9`.
- Current code changes are limited to the existing Domain Inspector read, the existing App Inspector refresh/cache behavior, and pure conversation projection plus regression tests. No Gate, TaskBinding, answer lifecycle, approval, budget, Gold, or business-write contract changed.
- The target commit's North Star, AGENTS, Skill, Stage B plan and Gold blob IDs are recorded in `BASELINE.json`.

## Findings and correction

### SUP-01: Inspector authorization after Scope revocation

The valid RED showed an authenticated SUPPORT could read an initial S3 answer while Scope was valid, but after the route policy was changed and its version incremented, the Inspector filtered that initial answer while still returning the persisted C1 Follow-up answer, source refs, result payload, and source Message ID. Expanded RED also found an invalidated diagnosis receipt ID and S3 Evidence IDs in trusted-state/trace metadata.

`opspilot/domain/chat.py::get_task_inspector()` now opens one SQLite read snapshot and rechecks the current S3 binding with the existing `get_s3_binding()` authorization path before projecting protected rows. Initial answers continue through `answers_in_transaction()` under the same snapshot; C1 Follow-up rows, S3 observations, associated Follow-up/sidecar Run source metadata, and S3 trace/provenance detail are withheld when current Scope is unavailable. The returned S3 summary contains only a minimal `S3_AUTHORIZATION_UNAVAILABLE` reason and does not include the old receipt or Evidence IDs. Persisted answer, diagnosis, and Follow-up rows are not modified.

The deterministic authenticated HTTP test demonstrates both directions: the authorized Inspector contains an initial `ANSWERED` result and a persisted same-Task C1 Follow-up with source refs; after the policy Scope/version change the HTTP Inspector response no longer contains either answer or their restricted source/result details. The test also verifies the immutable answer/diagnosis snapshots are identical before and after the read.

### SUP-02: Frontend stale Inspector/cache results

`App.vue::refreshInspector()` captures the requested Task ID so a delayed response cannot overwrite another selected Task. A sanitized Inspector with the current S3 authorization-unavailable marker or a rejected refresh for a previously loaded S3 Task clears the in-memory Inspector result/evidence/context, S3 handoff/outcome state, Task-scoped assistant result rows, associated Follow-up Runs, and active S3 chat chunks. It then attempts to refresh persisted Session messages and clears the restricted result cache again. User anchors and unrelated Task/session messages remain. The message API's existing S3 authorization redaction remains in force; this supplement does not change its Domain contract. Existing SSE rendering displays event labels/time/sequence and does not render old payload bodies.

Pure projection tests exercise an initial answer, C1 Follow-up answer, a task-linked Chat answer and an orphaned result together with unrelated messages. After revocation cache clearing, restricted text/receipt/Evidence references do not reach the conversation projection, while the USER anchors and unrelated messages remain. SSE event rendering now passes through a small display projection that retains only sequence, event kind, and time; a test injects a prior event payload containing a restricted body/receipt/Evidence reference and verifies none reaches the rendered event model. The App still uses event payloads internally only to identify the active run for a chunk refresh; clearing revoked S3 chat state removes the active run/chunks so an old event cannot repopulate that view.

### SUP-03: User-facing projection states

The projection now suppresses only an ordinary `FOLLOW_UP` assessment with `NO_UPDATE` and no `failure_code` when its persisted Follow-up answer is already present. Failed classification remains visible. Tests keep classification-in-progress and confirmation-wait states visible, suppress the routed Chat sidecar, and distinguish genuine FAILED, PARTIAL, and PROGRAM_LIMIT outcomes.

## RED/GREEN and verification

- Valid API RED: `runs/red-01/` and expanded source-metadata RED `runs/red-04/`.
- Valid projection RED: `runs/red-03/`.
- Corrected authenticated API GREEN: `runs/green-05/` — 1 passed.
- Corrected pure projection GREEN: `runs/green-04/` — 6 passed before the explicit SSE payload test was added. Final frontend verification after the cache-race and SSE projection changes: `runs/frontend-04/` — Node tests 7/7; TypeScript typecheck, Vite build, and scoped ESLint passed.
- Relevant security/TaskControl regression: `runs/regression-02/` — 127 passed, exit 0.
- Full pytest outcomes, including the preserved long-path failure and short-path rerun, are listed in `RESULTS.json` and `FAILURES.md`.

## Six review questions

1. **User change:** When S3 Scope is revoked, the user no longer sees stale initial or Follow-up business answers in Inspector or the cached conversation projection; while Scope is valid, both remain readable.
2. **Agent decision:** No Agent decision or autonomy was added. The existing Domain authorization result controls whether the read projection may include S3 details.
3. **Observation driven:** A changed current Scope policy/version produces a different read result; a valid policy preserves the legal same-Task read.
4. **New restriction and legal use:** The restriction blocks S3 facts/source details after current authorization fails. The positive authorized HTTP case and unrelated-message projection test show permitted reads and unrelated content remain.
5. **Simplification:** Reused the existing `get_s3_binding()` and `answers_in_transaction()` paths and existing conversation projection; no new Gate, policy service, or Timeline store was added.
6. **Evidence and stop:** Deterministic API, projection, frontend build, and pytest evidence is retained. Browser/Computer Use and real Provider are not run under the current boundary; stop here and return for independent review.

## Limitations and stop

- Browser/Computer Use: `NOT_RUN / BLOCKED_BY_TOOL_ENVIRONMENT` per the explicit instruction. Pure projection tests are not browser acceptance.
- Real Provider: `NOT_RUN`; no paid or external model request was made.
- The Scope change is performed in the deterministic test's Domain transaction; the subsequent Inspector request itself is a real local HTTP API request. This proves the protected read behavior, not an external IAM integration.
- Stage B as a whole is still pending its previously required real-browser journey, DOM/screenshot, refresh, and live SSE reconnection checks. This report does not sign Stage B PASS.

## Changed source and tests

- `opspilot/domain/chat.py`
- `frontend/src/App.vue`
- `frontend/src/conversation.ts`
- `tests/test_m4_contux_stage_b_supplement_api.py`
- `frontend/test/conversation.test.ts`
- `docs/evidence/vnext/m4-cont-ux-01/stage-b/supplement-01/`
