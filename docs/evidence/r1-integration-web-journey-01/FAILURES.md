# Failures and unverified items — R1 Integration Web Journey 01

Historical attempt logs are retained under `runs/`. They are not overwritten by the later passing run.

## Corrected test/setup failures

1. `pytest-engine-regression-01.log` — the system interpreter `D:\python\python.exe` could not import `langchain_core`; six modules failed during collection and no assertions ran (exit 2). No package install was performed. Switching to the already-present project virtualenv resolved the environment issue.
2. `pytest-r1-offline-journey-01.log` — initial fixture repeated the full protocol discovery/comparison and business-read sequence. J4 stopped with `TASK_AUX_PROVIDER_LIMIT`. The run exposed a possible capacity risk for a redundant but legal sequence; it did not establish that normal model behavior is blocked. No production budget was changed. The final fixture focused J3/J4 on fresh same-Event reads.
3. `pytest-r1-offline-journey-02.log` and `pytest-r1-offline-journey-03.log` — the material fixture searched for text formatted as `max_attempts=5`, while the frozen user input was JSON (`"max_attempts":5`). The persisted outbound request and test model input contained the JSON. This was a fixture assertion mismatch, not missing product context.
4. `pytest-r1-offline-journey-04.log` — the answer check passed, but a raw substring assertion against outer-serialized JSON did not account for escaped inner quotes. The assertion was changed to parse the persisted request and inspect human-message content.
5. `frontend-pure-unit-01.log` — the all-files Node test attempt ran 17 subtests but could not load `assistant-entry.test.ts` because the installed Node strip-only TypeScript runner rejects a parameter property in `frontend/src/api.ts`. No frontend code was edited to accommodate the runner.

## Passing reruns

- `pytest-engine-regression-04.log`: 82 passed, exit 0.
- `pytest-r1-offline-journey-08.log`: 1 passed, exit 0, with the enriched API/MCP/Domain trace.
- `frontend-projection-unit-01.log`: 17 passed, exit 0, pure projection/recovery tests only.

After the successful final 82-test run, the same selected regression command was started once more as an extra confirmation. It continued for more than four minutes without flushing output; the run was interrupted. `pytest-engine-regression-05.log` is preserved as an empty raw output file because the PowerShell pipeline had not flushed before interruption. The outer tool returned 1 on interruption; a pytest exit code/result was not recoverable. The earlier complete `pytest-engine-regression-04` result remains the valid final regression record, and the latest changed R1 test separately passed in run 08.

## Still unverified / blocked

- Browser use remains prohibited by the active Computer Use stop: no DOM, screenshot, browser send, UI source expansion, refresh, SSE replay, or reconnect evidence exists for this candidate.
- No live Provider call was permitted; real LLM choices and a real-model R1 journey are not verified.
- The new journey uses Receiver `QUEUED` only. Its PROCESSED counterpart is covered only by existing deterministic regression, not by this new journey.
- No full pytest run, frontend TypeScript typecheck, production build, or ESLint run was performed.
- The earlier `TASK_AUX_PROVIDER_LIMIT` sequence should remain a capacity/strategy observation for the independent reviewer. This task did not authorize changing budgets.
