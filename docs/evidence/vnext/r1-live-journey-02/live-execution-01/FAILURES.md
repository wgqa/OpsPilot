# Failures and remaining limits

## False runner stop after J1-01

Runner required formal Task Evidence/Observation IDs for successful unbound Knowledge MCP calls. Calls were OK; ToolMessages appeared in later real Provider requests; persisted Run and answer were SUCCEEDED. This was a runner defect, not a Provider failure or UNKNOWN.

The original STOPPED record remains private. One audited local correction resumed the same Campaign in an immediate transaction; audit key: r1-live-journey-02-runner-false-stop-20261108. Grant, DB, Session, send count and settlements were preserved; no resend or quota reset. This is not a supported resume API and needs independent review.

## J2-01 did not obtain current facts

After trusted binding, the user explicitly named event-current, but the model asked for a separate confirmation that it belonged to the bound order and did not call MCP. The answer was cautious, yet this was an over-restrictive response and the task remained incomplete.

## J2-02 draft wording

Current event-current Delivery/Receiver and recorded event-previous transport history were retrieved. Model kept event IDs separate and did not say event-previous was PROCESSED. Draft says verification is underway although no current Receiver Observation for event-previous was obtained. Exact answer is in TRACE.jsonl.

## Not run

- J3/J4: no trusted prior S1/S2 outcome in the fresh DB.
- Browser/Playwright: not run by authorization boundary.
- Full pytest after live Campaign: NOT_RUN; no production source changed.
- Legacy Provider and external business writes: zero.
- Remaining 5 provider slots and USD 7.985235 are not authority for another Campaign.
