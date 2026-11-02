# HF-01 Failure and Correction Log

## Preserved RED — `red-focused-01.log`

Command: `python -m pytest tests/test_ar02_ar03_integration_01.py -k "scoped_protocol_discovery_matches_callback_retry_topics or full_frozen_goal_in_trusted_order" -q --basetemp D:\学习\agent新项目\.tmp\ar03-live-hf01-red-20261102-01`

Result: **6 failed, 3 passed, 8 deselected**. Four failures reproduced the product defect: `callback retry`, `回调`, `回调重试`, and `回调 重试` did not return the authorized `callback-retry-contract` v1/v2 pair. The existing single-word English `retry`/`callback` and Chinese `重试` positives passed. Two other failures were test preparation mistakes: the new fixture patched `uuid4` with one ID although the existing S3 fixture consumes two (Event and transport IDs), causing `StopIteration` before the API path ran. No product code was changed for those setup failures.

## Test preparation correction — `red-initial-message-check-01.log`

The fixture was corrected to provide both preselected UUIDs. Re-running the trusted full-`initial_message` API path for both Receiver states plus the existing in-scope/out-of-scope authorization pair returned **3 passed, 14 deselected**. This confirms the existing `/assistant/order` endpoint can take the exact frozen user goal and its single ASSISTANT_V1 run can complete the deterministic offline investigation; the prior live run's extra investigation came from submitting a second user request after binding, not from a missing server entrypoint.

These logs are immutable; later GREEN results are recorded separately.
