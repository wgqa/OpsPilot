# Failures and preserved history

This file supplements; it does not overwrite historical failure records.

## New RED/GREEN sequence

- **RED-01 / RED-02 — test preparation errors.** The test fixture passed a filesystem path to `get_s3_binding()` where the function expects an existing DB connection. These runs did not reach the behavior under test. The raw logs are retained and are not counted as product failures.
- **RED-03 — valid product reproduction.** The same-Run audit failed with `KeyError('run_id')`; the SQL provides `attempt_run_id`. The cross-Run negative also failed to report the intended explicit association error because invalidated-source handling ran first.
- **GREEN-01 — initial targeted tests.** 2 passed after the narrow audit change.
- **GREEN-04 — final targeted association tests.** 3 passed, covering same-Run success, cross-Run rejection, and cross-Task rejection.
- **GREEN-03 — initial focused regressions.** 20 passed across the closeout, RESUME-02 and Recovery-02 modules.
- **GREEN-05 — final focused regressions after the Task-link query correction.** 21 passed across the same modules.

## Environment and inspection failures

- The first related-regression attempt used the system Python. It produced 8 failures because `langchain` was absent and 12 passes. This was an interpreter/environment mismatch, not a source regression. The same tests were run with the repository `.venv` (`langchain 1.4.1`): 20 passed initially, then 21 passed after the final Task-link query correction. Both logs are preserved.
- The committed copy of `GREEN-02-related-regression.txt` has trailing whitespace removed for `git diff --check`; its test output and failure lines are unchanged. The unmodified raw capture is preserved locally at `.runtime/ar03-post-live-closeout-private/GREEN-02-related-regression-raw.txt` (SHA-256 `f3f8cd5e7711833456a94ead837aaa0a7a504e8f9ed23b7f77dd24a007b3d2ac`).
- A read-only schema probe first assumed `task_runs.finished_at` and `d2_evidence.source_version`; actual columns are `ended_at` and `observed_versions_json`. No data was changed. Subsequent queries used the actual schema.
- The original archived MAT-04 audit failure is `KeyError('run_id')`; it stopped the campaign after the real answer had persisted. The historical raw `RESULTS.json` says 3 of 7 conditions audited, `PARTIAL_STOPPED`, and no later condition executed. MCP used had already reached 10/10.

## Remaining uncertainty

- MAT-04 source-currentness at capture was not persisted as a successful audit response. It can only be inferred from the historical audit's check order. The archived Evidence is now outside TTL and current revalidation rejects it.
- Historical `MAT-04` is therefore not upgraded from PARTIAL to PASS. MAT-05 and both MAT-06 conditions remain NOT_RUN.
- This task did not test a live Provider, browser, Worker, or fresh MCP call. No Provider/Worker/business write was performed.
