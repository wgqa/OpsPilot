# Failures and limitations

## Frozen RED before implementation

`logs/red-expiry-and-authorization.txt` preserves the original focused RED: 4 failed, 1 passed. Expired source Evidence prevented an otherwise identical fresh-fact revalidation; changed/disabled or superseded Plan paths left old AVAILABLE permissions; the UNKNOWN direct source-recovery assertion was already passing before the Worker recovery correction.

## Full pytest attempt

`logs/full-pytest.txt` is one full-suite attempt, not a pass. Command: `python -m pytest --basetemp D:\tmp\ops-pilot-ar05-s1-d3-close-hf01-full -vv -o faulthandler_timeout=180`, with `PYTHONPATH` set to the checkout and `OPSPILOT_MODEL_API_KEY` / `OPSPILOT_ASSISTANT_EXPERIMENT_ID` explicitly empty. It reached 28%, recorded one unrelated AR-03 runner preflight test failure, and then stopped after the QUEUED/OFF repeated-MCP test body passed but Starlette TestClient teardown waited at `wait_shutdown`. The faulthandler stack records the wait location. The run was interrupted rather than repeated; no root cause for the shutdown wait is claimed.

The preflight test was rerun alone and failed with `GIT_PREFLIGHT_FAILED:rev-parse HEAD`; its fixture sets the runner root to `tmp_path`, which is not a Git checkout, before the intended wrong-branch condition can be checked. It is not part of this task's scope and was not changed. Output: `logs/full-run-existing-failure-followup.txt`.

## Tool availability

`ruff check` could not run because `ruff` is not installed or discoverable in this environment. `compileall` and `git diff --check` passed.

## Not run

- Paid Provider requests: 0.
- Browser validation: 0; existing STOP remains effective.
- External/production business writes: 0.
- No second full pytest run was started.
