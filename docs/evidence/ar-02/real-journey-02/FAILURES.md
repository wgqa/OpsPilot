# Failures and stops

All attempts are retained. The first two entries are preflight-only failures. The live journey result is recorded below; no request was retried.

## Offline preflight RED 1: missing dependencies in default Python

- Command: `python -m pytest -q tests/test_ar02_real_journey_02_preflight.py`
- Result: 2 failed.
- One failure exposed the intended RED: `AR-02-REAL-JOURNEY-02` was not in the allowlist (`AR02_LIVE_EXPERIMENT_SCOPE_INVALID`).
- The SDK-wire test also failed at import because this shell's default Python lacked `langchain`; this is an environment selection failure, not evidence about the product code.
- Raw log: `runs/preflight-red.log`.

## Offline preflight RED 2: project environment

- Command: `.venv\Scripts\python.exe -m pytest -q tests/test_ar02_real_journey_02_preflight.py`
- Result: 2 failed.
- Both reached the product path and failed specifically because the new experiment ID was not supported by the existing allowlist. This confirms the authorization-scope/schema wiring gap before repair.
- Raw log: `runs/preflight-red-project-env.log`.

## Offline post-fix verification (before the live run)

The focused offline wire and AR-02 regressions first passed in `runs/preflight-green.log`; the final relevant regression result (80 passed) is in `runs/ar02-regression-final.log`. At the time of those logs, no paid Provider request had been made. The later authorized live run is recorded in the next section.

## Authorized live journey stop: S02-4 context budget

- The formal API accepted S02-4, but its `ASSISTANT_V1` Run ended `FAILED` before any Provider or MCP dispatch.
- Persisted program notice: `ContextBudgetExceeded: INVESTIGATOR_CONTEXT_EXCEEDS_BUDGET (12029 > 12000 tokens)`.
- Per-run `assistant_trace` and dispatch list are empty; campaign counts stayed at 7 Provider / 7 MCP. No model result was unknown, no Usage was missing, and the campaign remained `OPEN`.
- The runner stopped at its terminal Run-failure condition. S02-5 was not submitted. No Worker restart, rerun, prompt change, or context-budget increase occurred.
- This is a product/continuity failure caused by the existing context limit on the accumulated S02 session, not a Provider connectivity failure or safety violation.
- Raw evidence: `RESULTS.json`, `TRACE.jsonl`, `runs/live.log`, and `PROVIDER_HTTP.jsonl`.
- Final app ledger: 7 HTTP 200 Provider responses, all with known Usage; USD 0.013902 settled; USD 0 reserved; 7/16 Provider and 7/12 MCP used.
- S02-4 and S02-5 are incomplete; the required support-note draft was not produced. This run is not a full-journey PASS.
