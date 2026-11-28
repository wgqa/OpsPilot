# Failures and limits

## Current regression result

The selected Context/Assistant regression group collected 60 tests: 59 passed and one existing assertion failed:

`tests/test_ar04c_f01_context_currentness.py::test_zero_tool_followup_can_explain_valid_historical_snapshot`

The failure is `KeyError: 'completed_tools'`. The frozen Base implementation of `source_context_for_model()` already projects `current_run` with only `run_id`, `business_observations`, and the currentness description; it does not expose `completed_tools` to the model. The test separately verifies zero MCP rows in the Domain database and the “not re-queried” explanation. This patch does not alter that projection or F1 behavior. The assertion mismatch is retained for independent review and was not changed to manufacture a green result.

The relevant J1→J2 continuity test, current-source revalidation cases, assistant/runtime tests, and both new headroom tests passed in that run.

## Test environment

The first combined pytest attempt used the default Windows temp root and failed 52 fixture setups because Python could not enumerate `%LOCALAPPDATA%\\Temp\\pytest-of-tu me manques` (`PermissionError`). The suite was rerun with a dedicated `--basetemp` in this worktree. The initial bare `pytest` command also could not import `opspilot` because the checkout was not on `PYTHONPATH`; subsequent commands set `PYTHONPATH` explicitly. These are preserved in `TEST_LOG.txt` and `TEST_LOG_RETRY.txt`.

## Measurement difference

The prior closeout artifact recorded 11,900 estimated input tokens after its F2 projection. Reconstructing the same saved request, actual response tool calls, and three actual MCP results from the private execution record with the Base projection produced 11,960, a 60-token difference that is not reconciled here. The original F2 failure record remains 12,199. The exact same-request before/after comparison in `HEADROOM_REPLAY.json` uses one reconstruction method for both sides and leaves 1,406 tokens of headroom after compaction.

## Not run

- Real Provider request: 0 (not authorized).
- Browser automation: 0.
- External business write: 0.
- Historical STOPPED Campaign: unchanged and not resumed.
