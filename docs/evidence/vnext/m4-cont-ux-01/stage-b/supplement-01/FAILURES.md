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

## Not run

- Browser / Computer Use: `NOT_RUN / BLOCKED_BY_TOOL_ENVIRONMENT` per the explicit execution boundary.
- Real Provider: `NOT_RUN`; tests use deterministic Domain data and the local HTTP service only.
