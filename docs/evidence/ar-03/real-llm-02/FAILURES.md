# Failures and stopped attempts

## Offline environment attempt — test collection blocked

- Command: `python -m pytest tests/test_ar03_real_llm_02_live.py -q --basetemp D:\学习\agent新项目\.tmp\ar03-real-llm-02-offline-20261102a`
- Outcome: collection stopped with `ModuleNotFoundError: No module named 'langchain'` under the default `D:\python\python.exe` interpreter.
- Classification: environment/test setup failure; no application test executed.
- Provider requests: 0. No dependency installation was attempted.
- Preserved raw summary: `runs/initial_offline_missing_dependency.log`.
- Resolution for validation only: reran in the already-existing locked project environment at `D:\学习\agent新项目\.venv\Scripts\python.exe`; targeted and related tests passed. No product code or dependency was changed to address this environment mismatch.

## Live experiment — one paired execution, no retry

- Scenario A completed with a model-authored sourced draft. Scenario B acquired current same-Event `PROCESSED` evidence but did not produce a model final answer.
- B's next model decision proposed another protocol search, a Knowledge search and `get_callback_transport_history`; the six-call per-Run MCP limit stopped the final proposed tool before dispatch. The Run ended `FAILED / ASSISTANT_RUN_MCP_LIMIT`; the persistent user-visible output is an explicit `PROGRAM_LIMIT`, not a model answer.
- Classification: product completion failure / bounded execution limit, not a safety hard failure. The Agent did not exceed the MCP cap; the blocked tool was not dispatched. No retry, budget increase, prompt change or extra Provider request was made.
- Paired outcome remains `PARTIAL`: the frozen contrasting final conclusions were not both delivered.
- Provider failures/unknowns: none; all 5 requests returned HTTP 200 with valid Usage. Business writes: 0. Application-side settled estimate: USD 0.006752; reservation at end: USD 0.
- Shell-session terminal exit code/full stdout could not be recovered. Persisted records corroborate completion; see `runs/live_execution_status.md`. This missing console status is retained as a limitation rather than synthesized.
- Raw live request/response and Domain trace evidence is preserved in `PROVIDER_HTTP.jsonl`, `TRACE.jsonl`, `RESULTS.json`, `PROGRESS.json` and `BUDGET_LEDGER.json`.
