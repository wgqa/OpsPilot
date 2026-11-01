# Failures and non-success evidence

All entries are retained as run logs. The first test preparation errors are not counted as business RED.

1. **Test import setup error — not business RED.** Initial `pytest` used the system interpreter without `PYTHONPATH=.` and failed to import `opspilot`. Log: `runs/budget-cap-red.log`.
2. **Environment dependency mismatch — not product regression.** A first corrected-PYTHONPATH run used `D:\python\python.exe`, whose environment lacked `langchain_core`; 16 tests passed and 11 failed during imports. No Provider call occurred. Log: `runs/budget-cap-green.log`.
3. **Valid budget RED before implementation.** With the project venv, the new half-allocation test reproduced that AR-03 initialized each isolated database at 16/12 rather than the required 8/6. Both focused assertions failed as expected. Log: `runs/budget-cap-red-corrected.log`.
4. **Initial safety-regression command typo — not a test result.** One named test path did not exist; pytest ran no tests. Log: `runs/ar03-safety-regression.log`.
5. **Transport preflight defect found before live use.** HTTPX URL in the installed version has no `is_https` property. The runner was corrected to compare `url.scheme`; an offline MockTransport test now exercises the recorder and pre-send wire check. No real Provider traffic was sent during this correction.

No previous UNKNOWN reservation, historical Gold, prior trace or old experiment database was modified. The live run's own failures, if any, are appended after execution; no quality reruns are permitted.

## Live execution — 2026-11-01 UTC / 2026-11-02 local

**One authorized paired execution only; no retry or quality rerun.** `RESULTS.json` and `PROGRESS.json` record overall `PARTIAL`, 13 real Provider HTTP requests (A=7, B=6), 12 actual budgeted MCP dispatches (A=6, B=6), zero in-flight Provider calls, zero business writes, and no historical experiment modification.

Both frozen-goal Runs ended `FAILED` with `ASSISTANT_STOP:TaskControlError:ASSISTANT_RUN_MCP_LIMIT`; the user received a program-generated `PROGRAM_LIMIT` notice rather than a model answer. This is not a Provider transport or Usage failure: all 13 responses were HTTP 200 with valid Usage and no retry.

The bound-order admission endpoint itself accepted an `initial_message` and ran a real `CHAT_READONLY` before the frozen prompt. The model used four actual MCP calls in each admission Run to inspect order, delivery, receiver and transport history, leaving two of six per-scenario MCP slots for the frozen goal. A used those slots for a scoped protocol listing that returned zero and one Knowledge result (callback retry v2); later repeated v1 searches and proposed current-state reads had no dispatch. B used them for a topic listing returning zero and an all-documents listing returning six; subsequent Knowledge/version-comparison proposals had no dispatch. Neither case executed `compare_scoped_protocols` or delivered the required upgrade-impact draft.

The two admission answers correctly differed on current same-Event Receiver state: A said `QUEUED` and distinguished 202 acceptance from processing; B said `PROCESSED` for this Event only. These are genuine user-visible partial results, but are not counted as completion of either frozen goal. No frozen-goal Run claimed the admission observation as a new current-Run Observation.

The Provider wire capture shows 11 post-cap tool proposals across both scenarios. None became a MCP dispatch. Eight budget-refusal records are persisted in the Domain assistant-call rows; three additional late proposals appear in the raw Provider responses but do not have individual Domain call rows because execution terminated while dispatching at the limit. The raw Provider log is retained to preserve this discrepancy.

The refusal reason has the legacy text prefix `AR02_LIVE_MCP_LIMIT`; read-only inspection of both fresh database ledgers showed only `experiment_id=AR-03-REAL-LLM-01`, with 7/6 MODEL and 6/6 MCP rows respectively. This is an error-label/audit clarity issue; it is not evidence of writes to historical AR-02 databases. A and B protected business-write table counts are all zero.

No additional Provider request, browser run, business write, main merge or second Runner was performed after the frozen A/B execution. Root cause and follow-up options are for main-agent review; this task does not authorize a code fix or another paid run.
## Post-run evidence verification setup

Two failures came from the offline evidence-check script, after the real experiment had completed; neither caused a Provider request or changed experiment data.

1. `postrun-evidence-check-path-red.log`: the checker resolved frozen CASES under an extra `ar-03/` directory and raised `FileNotFoundError`. The path was corrected to the repository's actual `docs/evidence/ar-03-real-llm-01-prep/CASES.json`.
2. `postrun-evidence-check-syntax-red.log`: the first corrected script had one unindented Python statement inside a `try` block and stopped with `SyntaxError` before running. The checker was rewritten and retained as `verify_evidence.py`.
3. `postrun-evidence-check-green.log`: offline verification then passed for the frozen prompt, 13 HTTP request/response pairs, exact model/wire settings and Usage, budget totals, isolated A/B databases, six MCP dispatches per scene, zero protected writes, SQLite quick checks and runtime hashes.

These are evidence-check preparation errors, not live Provider, MCP, product, or safety failures.
A final `git diff --check` initially flagged trailing spaces used for Markdown hard line breaks in `REPORT.md`. They were removed without changing content; the next staged check is retained as the final result.