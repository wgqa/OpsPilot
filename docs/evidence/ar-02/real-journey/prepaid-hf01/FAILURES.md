# Failures and Reproduction History

All files below are retained as raw logs. None involve a real Provider request.

## RED against the frozen implementation

- `runs/red-focused.log`: first test attempt, 6 failed / 1 passed. One Assistant case was blocked by test data containing an invalid S3 fixture order ID; this is a test-preparation failure, not a product finding.
- `runs/red-corrected-fixture.log`: same acceptance assertions with stable fixture IDs, 6 failed / 1 passed. This is the valid RED evidence:
  - missing/malformed/bool Usage left the campaign budget `OPEN` and allowed later reservations;
  - `mark_unknown()` retained the reservation but a new Run/new logical key could reserve;
  - the Assistant continued past unknown Usage, made repeated deterministic model decisions and issued local HTTP/MCP-backed reads instead of stopping;
  - the valid-Usage control passed.

## Implementation verification attempts

- `runs/green-focused.log`: 2 failed / 5 passed. The new stop behavior worked, but this run exposed a compatibility issue in assertion order and a test's incorrect hard-coded expected cost. No additional product defect was inferred from those two assertions.
- `runs/green-focused-rerun.log`: 8 passed / exit 0 after preserving the prior same-key UNKNOWN error contract and calculating the known Usage settlement using the frozen rate function.
- `runs/green-focused-final.log`: final 8 passed / exit 0, including a separate OS subprocess attempt after the UNKNOWN result.
- `runs/ar02-regression.log`: related existing AR-02 budget, connection, runtime, recovery and offline journey tests: 54 passed / exit 0.

## Retained limitations

- No real DeepSeek request was sent. Provider behavior and actual billing remain unverified by this task.
- The full repository pytest suite was not rerun; only the new HF01 suite and the listed related AR-02 regression modules were executed.
- The existing `BUDGET_BREACH` enum is reused for an unresolved spend-accounting stop. For UNKNOWN Usage/outcome it means the spend ceiling can no longer be certified, not that an actual charge above the ceiling was proven.
