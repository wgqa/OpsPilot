# AR-03-MATERIAL-LIVE-01-RESUME-02 failures and stops

These records are additive. Earlier RED logs, the first dirty-worktree preflight, the single live campaign, and all raw private evidence remain preserved.

## Free-test history

- The initial focused RESUME-02 tests produced 7 expected RED failures before the exact experiment budget identity, one-shot gate, and result classifier were implemented. The private raw RED logs remain unchanged.
- Intermediate expanded regressions exposed a case-sensitive SHA expectation and an unverified source-association classification edge; both were corrected in the candidate and the focused regression subsequently passed.
- The first test invocation using global Python lacked project dependencies; later test commands used the project virtual environment.
- A full combined rerun completed successfully: 41 passed, 0 failed in 27.06s (`GREEN_FINAL_RERUN01.txt`). Some redundant rerun attempts were interrupted or left partial logs; they are retained privately and do not replace the completed full run.

## Preflight history

- The initial preflight correctly refused the dirty worktree with `WORKTREE_OR_INDEX_NOT_CLEAN`; it created no claim and sent no Provider or MCP request.
- After the implementation commit and clean-worktree checks, preflight returned `PREFLIGHT_READY_AUTHORIZED_ONE_SHOT`. The campaign claim was then consumed once.

## Live campaign hard stop

- The authorized campaign received nine HTTP 200 responses with valid Usage and zero UNKNOWN Provider outcomes. No request was retried.
- The formal Worker persisted MAT-04's successful Run, final assistant message, and three successful same-Run business observations (Delivery, Receiver, and transport history).
- The Runner then raised `KeyError('run_id')` in `_audit_case()`. The SQL query selects `o.*` plus `a.run_id AS attempt_run_id`, but the later audit reads `item['run_id']`. This is a Runner audit defect after the user result was persisted; it is not evidence of a Provider or Assistant failure.
- The exception occurred before MAT-04 was appended to the campaign result rows. MAT-05 and both MAT-06 conditions were not run. MCP usage was already at 10/10.
- No hotfix, retry, resumed Runner, new claim, extra request, or additional experiment was made. MAT-04 is reported PARTIAL, not PASS.

## Remaining evidence limitation

A pre-existing RESUME-01 private evidence manifest records the historical authorization claim SHA-256, but the manifest's referenced raw `authorization/claim.json` is not present in the current private archive path, so that specific old claim file could not be independently re-hashed after this campaign. The current root historical claim still matches its recorded SHA. No historical evidence paths were changed by this task; the RESUME-02 runner used a distinct database, checkpoint and raw evidence directory.
