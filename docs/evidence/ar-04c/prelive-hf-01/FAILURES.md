# Failures and limits

## Preserved results

- `runs/pytest-auth-red-03.log`: genuine RED against the pre-fix Assistant source; four cases failed because the atomic one-shot claim creator did not exist. This established the missing positive authorization/claim path.
- `runs/pytest-ar04c-final-green-02.log`: the formal Worker test reached `TestClient.wait_shutdown` and faulthandler captured the shutdown wait. The run did not produce a normal pytest summary. This is not counted as a test failure or pass.
- `runs/pytest-ar04c-relevant-01.log`: earlier broad run also stalled and was interrupted; retained as historical evidence, not counted as a completed run. Its separate machine process snapshot remains local and is not needed to establish the shutdown wait location.

## Setup and harness errors

- `pytest-auth-red-01.log` and `pytest-auth-red-02.log` are environment/setup failures (temporary-path permission and missing LangChain in the global Python), not product RED.
- `pytest-auth-green-01.log` records a test-fixture mistake: the replacement-database assertion ran before creating the expected campaign budget row. The fixture was corrected; the current focused run passes.
- `pytest-ar04c-worker-lifecycle-green-03.log` used a nonexistent pytest node name, collected zero tests, and exited 4. The node name was corrected and the exact Worker test then passed.

## Root-cause boundary

The recorded AR-04C stack is in Starlette `TestClient.wait_shutdown` during context exit. R1 previously observed the corresponding test race: the Domain Run can become terminal before the Assistant/MCP cleanup and Worker dispatch return, after which TestClient shutdown cancels the still-unwinding Worker. That is a confirmed mechanism in the R1 test; it is a strong match for the AR-04C test, but the AR-04C stack alone did not identify a specific blocked asyncio task or prove every cleanup step was the cause.

The AR-04C test now waits for the final `_dispatch_run()` wrapper to return and for the Worker to observe an empty queue before leaving `TestClient`. The focused Worker test passed with a 60-second faulthandler threshold. No production Worker change was made. This removes the known test teardown race from the exercised path; it does not certify all full-suite shutdown behavior.

## Not run

- Full pytest was not rerun; the task explicitly called for bounded diagnosis and no repeated full-suite attempts.
- No real Provider request, browser automation, external MCP service, or external business write was performed.
- AR-03 shutdown target was not rerun after the AR-04C test-only change; its earlier 4/4 result remains applicable because production code was untouched.
