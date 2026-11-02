# Failures and stopped attempts

## Offline environment attempt — test collection blocked

- Command: `python -m pytest tests/test_ar03_real_llm_02_live.py -q --basetemp D:\学习\agent新项目\.tmp\ar03-real-llm-02-offline-20261102a`
- Outcome: collection stopped with `ModuleNotFoundError: No module named 'langchain'` under the default `D:\python\python.exe` interpreter.
- Classification: environment/test setup failure; no application test executed.
- Provider requests: 0. No dependency installation was attempted.
- Preserved raw summary: `runs/initial_offline_missing_dependency.log`.
- Resolution for validation only: reran in the already-existing locked project environment at `D:\学习\agent新项目\.venv\Scripts\python.exe`; targeted and related tests passed. No product code or dependency was changed to address this environment mismatch.

## Live experiment

Not started as of this file's preparation. No live failure, response, Usage or charge is claimed here. The one-shot runner will record any future live exception/unknown result and must not be rerun after a claim is persisted.
