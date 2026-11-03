# AR-03-MATERIAL-LIVE-01 Runner Recovery 02 — report

**Status: `ACCEPTANCE_CANDIDATE`**
**Scope: free offline fix and verification only.**

## Result

The two confirmed runner defects now pass through the same local formal Assistant execution path. The paid experiment remains stopped: no new claim was created or consumed, no real Provider request was sent, and no business write occurred.

## Minimal fixes

1. In `docs/evidence/ar-03/material-live-01/run_live.py`, `_CampaignState.begin()` now imports `PRICE_VERSION` from `opspilot.domain.assistant_experiment`, the authoritative owner. The existing persisted budget price-version comparison remains in force; no price or budget value changed.
2. `_audit_case()` now reads `error_code` only when the selected row actually contains that field. If the active `assistant_calls` schema has no such column, the audit reports `error_code_state=UNKNOWN_NOT_IN_ASSISTANT_CALLS_SCHEMA` and leaves the code null. For FAILED/BLOCKED Runs it also preserves `waiting_reason` as `run_failure_reason`, so a second audit error cannot mask the original failure. No schema migration or error-code fabrication was added.
3. The existing zero-cost preview regression now snapshots hashes for the previous experiment's Domain DB, checkpoint, and WAL/SHM files. It checks immutability instead of asserting these historical files do not exist.

## Real send-path simulation

The new tests use temporary SQLite and checkpoint files, the formal FastAPI app and Worker, the real Assistant model factory and SDK serialization, and an explicit HTTPX `MockTransport`. A handler assertion observes both `assistant_calls` and `ar02_live_dispatches` already `RESERVED`, with the durable campaign budget incremented, before it returns a synthetic response. Thus the exercised send path includes `_CampaignState.begin()` and the request-before-transport guard; the synthetic response is not a real Provider result.

The captured outbound request was checked for the frozen URL, `deepseek-flash`, disabled thinking, `max_tokens=2048`, `stream=false`, `tool_choice=auto`, `parallel_tool_calls=false`, and the allowed tool schemas. A request with `max_tokens=512` was rejected before the MockTransport handler. Success persisted the synthetic MAT-01 answer with Usage 92/25/117 and zero business writes. The injected `httpx.ConnectError` was wrapped as `OpenAIConnectionError`; the Run failure reason remained auditable, the assistant call stayed UNKNOWN, and the temporary test ledger retained USD 0.645600.

The one-shot authorization predicate is stubbed only inside these offline tests. The tests therefore do not prove a fresh paid claim works, and deliberately create or consume none. No real HTTP client or external network request is used.

## Evidence and tests

- Valid RED: 3 failed, 1 passed, reproducing the undefined price constant and two KeyErrors for the absent schema column.
- Focused GREEN: 4 passed in 9.18 seconds.
- Relevant regression: 28 passed in 24.68 seconds.
- `git diff --check`: passed; only a non-failing LF/CRLF checkout warning was reported.
- Full pytest: not run.
- Historical RESUME-01 manifest SHA-256 remains `9DE01F4B04D0B80C5BB8FA1B6873AD78A320F6A71CBC2C763544FF64387C622A`. The prior claim, UNKNOWN dispatch, USD 0.645600 reserve, Domain/checkpoint DB, Trace, and failure artifacts were not changed; prior artifact comparison recorded all 15 entries unchanged using the stored path aliases.

Raw pytest logs remain private and are identified by SHA-256 in `RESULTS.json`; they are not copied into this public repository.

## Limits

This proves the local serialization, durable pre-reservation, MockTransport success/failure handling, and audit behavior only. It does not verify DeepSeek reachability, live billing/Usage, a new paid one-shot claim, successful real MAT-01, MAT-02–MAT-06, browser behavior, or full-suite status. No new paid execution is authorized by this task.

The patch intentionally leaves the original `AR-03-MATERIAL-LIVE-01-RESUME-01` claim consumed and its historical result unchanged. A future paid attempt requires a new experiment identity and new explicit authorization.

## North Star §8 closing check

1. **User change:** no new live capability; the runner can now reach the modeled send boundary and audit either outcome without losing the original failure.
2. **Agent decision:** no model autonomy claim; responses are synthetic offline fixtures.
3. **Observation driven:** request serialization and durable reservations are observed before the MockTransport response; live business observations were not run.
4. **New constraint and legal path:** existing price, request, tool, and budget checks remain; valid frozen requests pass and invalid `max_tokens` is still rejected before transport.
5. **Simplification:** reuse the authoritative price constant and existing audit schema; no new schema, guard, or runner service.
6. **Evidence and stop line:** RED/GREEN logs and historical hashes are recorded; stop at this free acceptance candidate, with live Provider execution still unauthorized.
