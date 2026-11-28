# HF-01 Verification Addendum

## Finding after the first push

An independent post-push call to `_task_assert_frozen()` failed with `PRODUCTION_OR_HISTORICAL_EVIDENCE_DIFF_FROM_BASE`. The V2 validator protects the complete `docs/evidence/abc-live-env-unblock-01` directory, while HF-01 deliberately changes exactly `run_abc_eval.py` and pins its new Git blob. The outer HF-01 path allowlist already limited changes in that directory to this single adapter file, but the nested V2 directory pathspec did not express that exception.

This was an execution-gate compatibility defect: without the fix, the final Live runner would reject its own reviewed Adapter before sending. No Provider request occurred during reproduction.

## Minimal correction

`run_remaining_live_gate.py` now temporarily removes only the broad ABC directory pathspec while invoking V2's frozen check. Before doing so it requires that pathspec to exist exactly once. The outer task guard still compares staged and committed paths against the original gate Base and permits only the exact `run_abc_eval.py` path plus this task's evidence directory. V2 continues checking its other protected pathspecs, frozen input hashes, production source blobs and protected historical file hashes. `_task_contract()` restores the original V2 constants on exit.

No production `opspilot/` code, Gold, historical Trace, authorization file or live accounting path changed.

## Fresh verification

- Targeted HF-01 suite: 31/31 passed.
- Existing remaining-gate and ABC Adapter suites: 19/19 passed.
- Fresh Mock matrix `mock_run_05`: Q02-B and Q06-B succeeded; four Mock summaries and two Mock answers; zero Provider requests.
- Fresh zero-cost preflight `LIVE_PREFLIGHT_05_FINAL.json`: `READY_FOR_NEW_LIVE_AUTHORIZATION`; no live dispatch, no authorization created, zero Provider requests and USD 0.00.
- The current official price was not rechecked. This status is technical preparation only and does not authorize a Live run.

The failed pre-fix commands and passing post-fix commands, with exit codes, are recorded in [TEST_RUN_02.txt](TEST_RUN_02.txt). The original `TEST_RUN.txt`, Mock runs 01–04 and earlier preflight evidence remain unchanged.
