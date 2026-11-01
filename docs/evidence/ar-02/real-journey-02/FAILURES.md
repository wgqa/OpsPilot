# Failures and stops

All attempts are retained; no paid Provider request has been made as of this file's creation.

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

## Post-fix verification

The first GREEN run of the focused offline wire and AR-02 regressions is recorded in `runs/preflight-green.log`. Paid execution remains unstarted until the final preflight is recorded and the formal worker can run in the approved network-enabled execution context.
