# R1-SHUTDOWN-HF-01 — Shutdown Diagnosis and Closeout

**Status:** `ACCEPTANCE_CANDIDATE`

**Merge recommendation:** `MERGE_READY` for the backend/code candidate, subject to the main Agent's review.
**Scope:** Test-only lifecycle correction; no production Worker or ASGI code changed.

## User-visible effect

No product behavior changed. The repeated-MCP capacity test now waits for its Worker dispatch and MCP cleanup to finish before closing `TestClient`. This removes a test-created shutdown race while keeping the production shutdown contract unchanged.

## Opening verification

| Item | Verified value |
|---|---|
| Repository | `wgqa/OpsPilot` |
| Branch / base HEAD | `codex/r1-main-integration-gate-01` / `759d0af9ff09c8995bc6fcfa01870264f201d258` |
| Remote candidate at opening | `759d0af9ff09c8995bc6fcfa01870264f201d258` |
| Remote `main` at opening | `ec8c3582f6d145eec9979c43607302731411ead8` |
| Opening worktree | Clean |
| North Star / AGENTS / Skill Blobs | `1f737712c7a36ceb34433ac09c3fbba3c3305542` / `32c45506cceeaa8c76a5c56bf8360ff476b58856` / `d405c8d413d633824b279202cc1503dab4cf0b03` |
| Prior closeout report Blob | `68284f00cbd730f54caf8081543457be5f439be2` |

The project-authored Skill was actually read from this target checkout. North Star §8 remains authoritative. The only implementation diff is in `tests/test_ar03_material_remainder_01.py`.

## Blocking mechanism found

The target test's `_wait_run()` returns as soon as the Domain Run is terminal. That status can be persisted before `run_assistant()` exits its MCP `Client` context and before `_dispatch_run()` returns. The test then leaves the `TestClient` context while the Worker is still unwinding.

The pre-fix probe directly observed this order: the MCP child was alive; `TestClient.wait_shutdown` began; lifespan requested Worker cancellation; `Client.__aexit__()` and `run_assistant()` were cancelled; the Worker acknowledged cancellation; `worker.release()` ran; the MCP child was gone by the next process snapshot. The target test itself still passed because its business result had already been committed. This is a test lifecycle race, not evidence of a broken production Worker or a failed business transaction.

The prior 60-second faulthandler record stopped at `TestClient.wait_shutdown` / `TestClient.__exit__`. It did not capture an internal blocked asyncio task, SQLite lock, or active `to_thread()` function. The exact historical hang was intermittent: another earlier full run completed with the target passing. Therefore, the shutdown cancellation race is confirmed; attributing every detail of the earlier 60-second wait exclusively to it remains an evidence-based explanation rather than a separately captured stuck-task stack.

## Minimal correction

The target test now wraps `_dispatch_run()` and signals completion, then observes `next_worker_run()` returning no pending work. It exits `TestClient` only after both signals. It does not add a production event, sleep, timeout suppression, or shutdown behavior change.

Post-fix probe order: `mcp_client_exit_begin` → `mcp_client_exit_end` → `run_assistant_return(SUCCEEDED)` → Worker polls and finds no work → `TestClient.wait_shutdown` → Worker cancellation acknowledgement → `worker.release()` begin/end → lifespan shutdown complete. The MCP child was already gone before shutdown cancellation.

## Verification

Environment: Windows, Python 3.14.0, pytest 9.1.1, AnyIO 4.15.1, LangSmith pytest plugin 0.14.11.

| Run | Result |
|---|---|
| Pre-fix target with private shutdown probe | 1/1 passed; probe captured cancellation inside MCP cleanup; no hang in this isolated run |
| Pre-fix ordered adjacent composition with probe | 8/8 passed in 13.27s; same cancellation race observed |
| Post-fix target with probe | 1/1 passed in 5.50s; MCP exit and Assistant return precede TestClient shutdown |
| Post-fix target without probe | 1/1 passed in 4.98s; exit 0 |
| One full suite after correction, private probe enabled only for target | 674 passed, 1 failed in 728.94s; exit 1; suite passed the former ~31% point and completed |
| `git diff --check` | Passed |

The sole full-suite failure is the preserved historical test `test_explicit_protocol_followup_is_accepted_as_same_task_readonly_run_before_ttl_fix`. It still expects deprecated `READONLY_FOLLOWUP`; the current contract is `FOLLOW_UP + readonly_action=INVESTIGATE`. The current-contract positive tests `test_follow_up_request_for_bound_protocol_is_routed_to_same_task_readonly_investigation`, `test_follow_up_investigation_uses_real_mcp_and_persists_a_readonly_result`, and `test_readonly_followup_completion_label_fails_closed_to_partial` all passed in the same full run. No compatibility branch or Gold edit was added.

The full run also passed the target capacity test and both adjacent QUEUED Worker MockTransport cases. Existing frontend typecheck/build evidence remains applicable because no frontend file changed; neither command was rerun. Browser verification remains `NOT_RUN / BLOCKED_BY_TOOL_ENVIRONMENT` under the existing STOP and is not presented as passed.

## Side effects and preserved history

The full suite appended fresh rows to two tracked historical C1 trace files. Because the opening worktree was clean and those edits were produced by the tests, only those exact generated additions were restored to their opening HEAD versions. Both files are clean in the final diff. The existing C1 RED, Gold, reports, and other evidence were not edited.

Provider calls: 0. External business writes: 0. Production source changes: 0. Frontend changes: 0. No `main` merge.

The complete full pytest console log and raw pre/post diagnostic logs remain in the local private evidence directory; SHA-256 hashes and the local evidence location are in `runs/LOG_INDEX.txt`. `runs/target-shutdown-events.json` contains the sanitized event-level comparison without PIDs or machine-specific stack paths.

## Remaining limits

- The earlier full-suite hang did not yield an asyncio task dump or a blocked `to_thread` frame. The current corrected full run completed; a separate hang under another environment/order is not ruled out.
- The full suite exits 1 only because of the obsolete historical C1 RED described above.
- R1 browser/interactivity acceptance remains on its existing HOLD/STOP.

## Skill §8 six questions

1. **User change:** None in product capability; the capacity regression test now reliably waits for full Worker cleanup.
2. **Agent decision:** Not applicable; this is test lifecycle only.
3. **Observation-driven:** No business decision changed. The observed ordering was Domain Run terminal before MCP client/Worker dispatch completion.
4. **New constraint:** No new product restriction. The test waits for actual completion and still permits all 11 MCP calls; existing no-write assertions remain.
5. **Simplification:** No production condition was added or removed; no Worker, TaskControl, or MCP policy was changed.
6. **Evidence and stop:** One post-change full run completed (674/675; one obsolete C1 RED). The target passed instrumented and plain. No more full runs are authorized by this task; stop here for independent main-agent review.

**Recommendation:** `MERGE_READY` for the backend integration candidate with the known historical C1 RED explicitly excluded as non-applicable. This is an implementation recommendation, not a self-signed main-agent PASS. Final merge permission remains with the main Agent. The R1 browser acceptance remains separate and unverified.
