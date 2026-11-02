# HF-01 Failure and Correction Log

## Preserved RED — `red-focused-01.log`

Command: `python -m pytest tests/test_ar02_ar03_integration_01.py -k "scoped_protocol_discovery_matches_callback_retry_topics or full_frozen_goal_in_trusted_order" -q --basetemp D:\学习\agent新项目\.tmp\ar03-live-hf01-red-20261102-01`

Result: **6 failed, 3 passed, 8 deselected**. Four failures reproduced the product defect: `callback retry`, `回调`, `回调重试`, and `回调 重试` did not return the authorized `callback-retry-contract` v1/v2 pair. The existing single-word English `retry`/`callback` and Chinese `重试` positives passed. Two other failures were test preparation mistakes: the new fixture patched `uuid4` with one ID although the existing S3 fixture consumes two (Event and transport IDs), causing `StopIteration` before the API path ran. No product code was changed for those setup failures.

## Test preparation correction — `red-initial-message-check-01.log`

The fixture was corrected to provide both preselected UUIDs. Re-running the trusted full-`initial_message` API path for both Receiver states plus the existing in-scope/out-of-scope authorization pair returned **3 passed, 14 deselected**. This confirms the existing `/assistant/order` endpoint can take the exact frozen user goal and its single ASSISTANT_V1 run can complete the deterministic offline investigation; the prior live run's extra investigation came from submitting a second user request after binding, not from a missing server entrypoint.

These logs are immutable; later GREEN results are recorded separately.

## GREEN and related regression

- `runs/green-focused-02.log`: the frozen topic cases and trusted `initial_message` route passed, **10 passed / 7 deselected**.
- `runs/green-regression-03.log`: related AR-02/AR-03 integration, prep, wire-preflight, and Assistant regression passed, **25 passed / 0 failed**.
- Earlier repeat executions are retained as `green-focused-01.log`, `green-regression-01.log`, and `green-regression-02.log`; these are repeated deterministic offline runs, not additional independent model samples.
- Full repository pytest: **NOT_RUN**. Real Provider, browser, and business writes: **0** by scope.

The two setup failures in the original RED were resolved only in the test fixture by supplying both deterministic UUIDs; no product expectation was relaxed. All original RED output remains preserved.
