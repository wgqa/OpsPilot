# Failure and limitation record

This slice does not rewrite the original J2 live results or their Gold.

## Preserved historical failures

- `docs/evidence/vnext/r1-live-journey-02/live-execution-01/REPORT.md`: J2-01 remained PARTIAL because the real model asked for separate confirmation rather than attempting a same-bound-order Event read.
- `docs/evidence/vnext/r1-live-journey-02/live-execution-01/TRACE.jsonl`: original Provider/MCP requests and persisted answers remain the source evidence. J2-02 correctly kept `event-current` and `event-previous` separate, but its customer draft implied follow-up was already underway.
- The original Campaign remains STOPPED with its spend and send counts unchanged. No claim, budget or run was recreated or replayed.

## This slice

- One expected RED was recorded before the fix: the offline API/Worker MockTransport test rejected the old prompt because it lacked the distinction between a bound-order Event query and a TaskBinding change. The test had no external Provider send.
- Final targeted offline tests passed. This does not prove a new real model will follow the revised semantics; a new paid model run is outside this authorization.
- The private Runner predicate correction was checked against existing captured J1-01 calls and synthetic positive/negative rows only. The STOPPED Campaign was not resumed.
