# Failures and stopping records

This file is append-only for this experiment. Historical AR-02 UNKNOWN records, real-journey-02 failure evidence, and frozen inputs are not edited here or elsewhere.

## Preparation

- The remote GitHub HEAD query was attempted before work and failed with a connection reset. Remote SHA is `UNVERIFIED`; local base was verified as `bc5484fe721bd2a54bc3a73326ff3c649fa1baa2`.
- After the preparation commit was pushed, a fresh `git ls-remote` succeeded and verified the remote main and candidate branch; see `PREFLIGHT.md`.
- No Provider request has been made for AR-02-REAL-JOURNEY-03 as of the initial freeze.
- The first focused offline command passed 5/5; the wider selected regression command passed 63/63. No current-task test failure has occurred.
- A separate no-network formal-runner preflight initially stopped with `PROVIDER_ENDPOINT_MISMATCH` because the current local Base URL has path `/v1` while the copied check allowed only an empty path. The exact exception chain is preserved in `runs/offline-live-preflight.log`. No DB/Checkpoint was created and no Provider/MCP request was sent. An official DeepSeek integration guide documents `/v1/chat/completions`; the preflight and MockTransport check were narrowly aligned to this official configured path. This was a runner preflight defect, not a Provider failure.
- After the narrow runner correction, the same no-network formal preflight passed on implementation SHA `635e000bb2957643e1b642403218d7aa1f807a03`; see `PREFLIGHT_LOCAL.json` and `runs/offline-live-preflight-green.log`. No external request occurred during either preflight.


## Authorized live run

- The single authorized S02-1..S02-5 execution completed with 9 known-usage HTTP 200 Provider responses and 8 successful MCP calls. There was no connection error, timeout, unknown dispatch, retry, budget stop, or security anomaly. Raw requests/responses and all five persisted answers are retained in PROVIDER_HTTP.jsonl, TRACE.jsonl, RESULTS.json, runs/live.log, and runs/live-console.log.
- Product limitation retained as PARTIAL: S02-4 made one model request and no MCP call. The answer did not claim the Receiver was processed and included the S02-3 observation timestamp, but that observation belonged to the prior Run. No S02-4 current Receiver Observation was obtained. The frozen one-run authorization forbids repair-by-rerun, so this was not repeated.
- S02-5 produced a sourced, unsubmitted handling draft with explicit unknowns and no business write. It used the prior same-Event observation with its time; it is not evidence of a fresh S02-5 check.
- No other live-run failure was observed. A complete repository-wide pytest suite and browser verification were not run.
