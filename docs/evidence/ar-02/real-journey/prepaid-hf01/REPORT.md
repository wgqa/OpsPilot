# AR-02-REAL-JOURNEY-PREPAID-HF01 Report

## Result

`ACCEPTANCE_CANDIDATE` — implementation and scoped local verification are complete; independent review remains required.

The candidate fixes the prepaid experiment's stop boundary. It does not establish real Provider behavior, billing correctness, or S01/S02 product success.

## User-visible result and behavior

If a Provider response has missing or invalid Usage, or its outcome becomes unknown, the experiment now stops before another model or tool investigation. The current Run is not committed as a normal model answer. A later Run cannot bypass the stop with a new logical key. With valid Usage within limits, a later legal dispatch still reserves normally.

## Implementation

- `opspilot/domain/assistant_experiment.py`
  - Missing/malformed Usage writes `usage_state=UNKNOWN`, records `AR02_LIVE_USAGE_UNKNOWN`, keeps the full USD 0.645600 reservation, and atomically closes the campaign using the existing `BUDGET_BREACH` state.
  - Model `mark_unknown()` keeps the reservation and closes the campaign in the same SQLite transaction.
  - New logical keys are rejected when a persisted Model dispatch is UNKNOWN or has non-KNOWN Usage. This also fail-closes older ledgers whose dispatch row is unsafe while the budget row still says OPEN; that compatibility check does not mutate the old rows.
  - Same-key replay of a confirmed UNKNOWN result retains the existing `AR02_LIVE_CALL_OUTCOME_UNKNOWN` response.
- `opspilot/assistant.py`
  - The model response is not marked successful or returned to the Agent until campaign Usage settlement returns KNOWN.
  - UNKNOWN/VIOLATION results are retained as failed audit records and raise a controlled stop before ToolNode or another model step.
  - Cached campaign responses with UNKNOWN/VIOLATION settlement are rejected rather than replayed into the Agent loop.
- `tests/test_ar02_prepaid_hf01.py`
  - Adds valid Usage, malformed/missing Usage, cost violation, provider outcome UNKNOWN, a fresh OS subprocess after restart, legacy-row preservation, and Assistant no-tool/no-answer cases.

No schema/table migration was added. The existing `BUDGET_BREACH` label is used as the fail-closed accounting state because the frozen schema has no distinct campaign STOPPED status. For unknown spend it means compliance with the cap cannot be demonstrated, not that an overcharge was observed.

## Evidence

- Frozen base: `8c665912f3f544e208cdeb863c058707f7a99236`.
- Acceptance plan commit: `a8a218cce1fd29ab8f271c8b7c72cbca520b87bc`.
- Initial frozen-test commit: `0562c6c6769fe04c66be1c8380570b7fdd7ded0a`.
- Test fixture correction commit: `196acd7b82a8a0347800c49be171f79ee9b642c2`.
- Source/test commit: `c77d54e7fcc3479086fa0d2339716c4e39d2ee6a`.
- `TRACE.jsonl` is derived from persisted rows in the successful isolated SQLite tests. It distinguishes deterministic-model/local MCP/HTTP evidence from real Provider evidence.
- Raw RED, intermediate GREEN, final GREEN, and regression logs are in `runs/`.

Environment: Windows worktree on D:, Python 3.14.0, pytest 9.1.1, `langchain` 1.4.1, `langchain-core` 1.6.12, `langgraph` 1.2.16, and `httpx` 0.28.1. Pytest used isolated SQLite databases under this evidence directory. Actual Provider requests: 0. Browser: not run. External business writes: 0. Main branch: unchanged.

## Related verification

- New HF01 tests: 8 passed, exit code 0 (`runs/green-focused-final.log`).
- Related existing AR-02 modules: 54 passed, exit code 0.
- Final command lines and results: `RESULTS.json`.
- Historical failure and intermediate test-preparation details: `FAILURES.md`.
- `git diff --check`: clean before source commit.

Full repository pytest was not rerun. No paid Provider experiment, browser session, or business write was executed.

## North Star review questions

1. **User change:** Users do not receive an apparent normal answer or repeated investigation when experiment cost accounting is unknown; they get a failed/incomplete result.
2. **Agent decision:** This is a reliability repair, not an autonomy increase. The Agent's proposed tool call is not executed until the trusted campaign accepts Usage settlement.
3. **Observation-driven behavior:** Valid Usage permits the next legal request; missing/invalid Usage, a cap violation, or unknown Provider outcome stops the campaign.
4. **New constraint and legitimate work:** The stop applies only to the explicitly scoped paid AR-02 experiment. The positive control proves valid in-budget requests continue. Ordinary unscoped deterministic assistant use is unchanged.
5. **Simplification:** Reuses existing dispatch and budget rows and the existing stop enum; no new budget service, table, Gate, or runtime was introduced.
6. **Evidence and stop line:** Frozen RED reproduced the escape; final HF01 and related AR-02 tests passed. Real Provider, full repository pytest, browser, and paid S01/S02 remain unverified and outside authorization.

## Stop

No P1 rerun, paid request, browser use, business write, main merge, or AR-03 work was started. Awaiting independent main-Agent review.
