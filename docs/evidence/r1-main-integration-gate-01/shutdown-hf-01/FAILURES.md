# Failures and retained limitations

## Current complete suite

One failure remains in the one full run:

- `tests/test_m4_autonomy_c1_red.py::test_explicit_protocol_followup_is_accepted_as_same_task_readonly_run_before_ttl_fix`
- Response: HTTP 502, `INVALID_MODEL_CLASSIFICATION`.
- Applicability: the historical test sends deprecated `READONLY_FOLLOWUP`. The active contract uses `FOLLOW_UP + readonly_action=INVESTIGATE`.
- Current-contract evidence: three legal follow-up tests passed in the same full run (see `REPORT.md`).
- Treatment: preserved; no production compatibility path and no historical Gold edit.

## Shutdown diagnosis

The pre-fix targeted run passed its assertions, so it is not a pytest RED assertion. Its lifecycle trace is the RED evidence: TestClient shutdown cancelled the Worker while MCP `Client.__aexit__()` was in progress, although the Run result was already committed. The prior full-suite faulthandler stop at `TestClient.wait_shutdown` is retained in the earlier closeout artifacts. The post-fix target and complete run finished without that stall.

No production Worker defect was reproduced. The old full-suite hang did not capture a stuck task stack, so a distinct environment-specific source of intermittent waiting cannot be completely excluded.

## Other scope exclusions

- Browser/R1 interactive acceptance: `NOT_RUN / BLOCKED_BY_TOOL_ENVIRONMENT`.
- Frontend typecheck/build: not rerun because no frontend source changed; prior PASS remains the applicable evidence.
- Real Provider and external business writes: 0.
