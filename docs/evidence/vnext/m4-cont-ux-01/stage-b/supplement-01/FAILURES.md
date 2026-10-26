# Failure and RED Record — Stage B Supplement 01

All entries below are preserved from fresh executions against frozen implementation commit `ffff924` (base `ad056c38da1f925fca80b74aef0a88a686ac97e1`). No product source had been modified at the time of these runs.

## Valid RED: Inspector scope revocation

- Run: `runs/red-01/`
- Command: `python -m pytest tests/test_m4_contux_stage_b_supplement_api.py::test_inspector_redacts_initial_and_persisted_followup_after_scope_revocation -vv -s --basetemp=docs/evidence/vnext/m4-cont-ux-01/stage-b/supplement-01/runs/red-01/basetemp`
- Exit: `1` (`pytest.log`, `exit-code.txt`).
- Evidence: the authorized response contained both the current S3 initial answer and a persisted `ANSWERED` C1 Follow-up with evidence and Knowledge references. After changing the bound route's required Scope and incrementing the policy version, the API response filtered the initial S3 answer but still returned the C1 answer body, its source Message ID, source references, and result JSON. Assertion: `INSPECTOR_SCOPE_REVOCATION_LEAK`.
- `api-responses.json` contains the exact deterministic authorized and revoked HTTP Inspector JSON responses. Fixture credentials are local test-only values; no real credentials or Provider output were used.
- The persistent answer and diagnosis row snapshots were equal before and after the denied read. The failure is a read-path authorization gap, not a write or mutation.

## Test-preparation failure: first projection attempt

- Run: `runs/red-02/node-test.log` (exit `1`).
- The test fixture omitted the `followup-run` from the Run relation. Consequently, the pure projection correctly treated that Follow-up as unassociated; the assertion expecting it to be attached was invalid. This run is retained as a test-preparation error and is not counted as a product RED.

## Valid RED: duplicate ordinary Follow-up card

- Run: `runs/red-03/`
- Command: `node --test test/conversation.test.ts` from `frontend/`.
- Exit: `1`; existing 4 projection tests passed and the new case failed.
- After fixing the fixture's missing Run relation, the ordinary `FOLLOW_UP` assessment appeared beside its persisted Follow-up answer as `assessment:ordinary-followup` plus `followup:followup-run`. This is a duplicate user-facing classification card. In the same fixture, classification waiting, confirmation waiting, the routed Chat sidecar, genuine FAILED Run, PARTIAL answer, and PROGRAM_LIMIT result are independently asserted to retain their distinct projection behavior.

## Additional valid RED: Inspector source metadata remains after revocation

- Run: `runs/red-04/`; command matches `runs/red-01/` with the response artifact path changed to `runs/red-04/api-responses.json`.
- Exit: `1`.
- Extending the same deterministic case to inspect the entire API object found that, in addition to the C1 answer row, the revoked response still includes the immutable diagnosis receipt ID in `trusted_state.s3_outcome` and current S3 Evidence IDs in trace metadata. The old `evidence` list itself is correctly empty. This confirms the Inspector response needs one shared authorization decision for the S3 answer and source/result projection, including its summary fields.
- Full authorized and revoked responses are saved in `api-responses.json`; the failed assertions are preserved in `pytest.log`.

## Preserved incomplete-fix and test-fixture runs

- `runs/green-01/` is an intermediate implementation failure, not a Green result. After filtering answer rows and S3 receipt/Evidence metadata, the Follow-up's source Message ID was still present on its successful Investigator Run and blocked Chat sidecar in the Inspector's generic Run list. The implementation was then narrowed to suppress only those S3 Follow-up-associated Run rows when current Scope is unavailable. The immutable Run rows in Domain are unchanged.
- `runs/green-02/` and `runs/green-03/` are retained frontend test-preparation failures. Their synthetic source Messages had the default `task-a` while the revoked S3 Inspector/Run used `task-s3`, so the projection correctly reported the Run as unassociated. The fixture now uses matching Task IDs. These runs are not counted as product regressions.
- `runs/green-04/` is the corrected 6/6 pure projection test run; `runs/green-05/` is the corrected 1/1 authenticated API test run.
- `runs/frontend-01/` preserves a fresh static-check failure: the projection interface lacked the already-returned optional `failure_code`, and a temporary destructuring form triggered ESLint unused-variable errors. Both typing/lint issues were corrected before the final frontend checks.

## Not run

- Browser / Computer Use: `NOT_RUN / BLOCKED_BY_TOOL_ENVIRONMENT` per the explicit execution boundary.
- Real Provider: `NOT_RUN`; tests use deterministic Domain data and the local HTTP service only.

## Regression execution failures and reruns

- `runs/regression-01/pytest.log` is a test-environment collection failure: the system Python lacks the locked `langchain_core` dependency. No test ran. The run was repeated with the isolated `.venv-stageb` environment.
- The first attempt to write `runs/regression-02/pytest.log` happened before the output directory existed. PowerShell reported `Could not find a part of the path`; pytest did not start. The directory was then created and the same test selection was rerun in `runs/regression-02/`.
- `runs/regression-02/pytest.log`: the corrected isolated-environment regression completed with 127 passed and exit 0.
- `runs/full-pytest-01/pytest.log`: 382 passed, 20 failed, 1 deselected. All 20 failures were M1 Web approval tests failing at LangGraph SQLite checkpoint setup with the same `sqlite3.OperationalError: unable to open database file`. The basetemp was nested under the deep evidence path on Windows. This run is retained unchanged and is not counted as a product pass or ignored failure.
- `runs/full-pytest-02/` is an incomplete/unverifiable attempt: the short basetemp accumulated test directories, but the evidence output directory had not been created before invoking `Tee-Object`, so no pytest stdout, summary, or trustworthy exit code was captured. It is not counted as a pass or failure. Its basetemp is retained and was not reused.
- `runs/full-pytest-03/` is the complete rerun using a fresh short path `C:/Temp/ops_sb01_full_03` and a pre-created evidence directory: 402 passed, 1 historical obsolete-intent test deselected, exit 0. No source or Gold changed between the failed long-path run and this run. The 20 checkpoint setup errors therefore reproduce only with the deep Windows basetemp path, not with the same suite and short path.
- The full suite appended two rows to the tracked historical C1 RED trace. That file was clean before the run; the exact diff contained only those generated rows. After preserving the current supplement's own logs, the historical file was restored byte-for-byte to its committed `HEAD` contents. No historical evidence change is included in the candidate.
