# AR-02-REAL-JOURNEY-01 — execution report

**Submission status:** `ACCEPTANCE_CANDIDATE`
**Experiment result:** `UNKNOWN_STOPPED`
**Base:** `69e7267de03f13651f3e54aaf956a919284be845` on `codex/ar02-live-01`
**Final commit:** recorded in the delivery summary; this report preserves the authorized base SHA.

## What the user received

The user submitted the frozen S01 question in one isolated Session. FastAPI accepted it and the single local Worker dispatched `ASSISTANT_V1`. The Provider connection failed before any completion arrived. The user-facing message was a program-generated connection-failure notice stating that this turn did not complete and that the request/charge status was not confirmed. It was not a model answer.

S01 therefore **failed**. No S02 turn was started. The user did not receive a protocol explanation, a Knowledge citation, an order investigation, or a draft.

## What the model decided

Nothing can be attributed to the model. The only Provider request did not return an HTTP response. One Knowledge tool schema was present in the request, but no tool call was returned or executed. There were zero MCP calls and zero MCP Observations.

The locally prepared order fixture (`ar02-order`, order state COMPLETED, delivery 202, receiver QUEUED) is test setup only. No TaskBinding was created, and none of those setup facts were observed by the Agent.

## Actual IDs and durable state

- Session: `session-d9da0f2e-bbde-41bc-ba23-c687d79c2839`
- User Message: `message-08395bdd-e4be-4b7f-a516-0e17258c97c9`
- Run: `run-b5f22395-0792-47d1-857d-32525b5667e3` (`FAILED`)
- Program notice Message: `message-ab8e4398-f58f-42b7-a4b8-6a666d71aa4b` (`PROGRAM_LIMIT`)
- Provider dispatch: `ar02-live-dispatch-a8efc5d8-a9d3-4402-93f1-317beedac996` (`UNKNOWN`)
- Provider HTTP events: 1 outbound request, 0 responses. Completion ID, request ID, HTTP status, Usage, and actual billed cost are unknown.
- Application ledger: 1/16 Provider dispatches, 0/12 MCP calls; reserve USD 0.645600 retained; settled USD 0; campaign `BUDGET_BREACH`.

The recorded wire request used `https://api.deepseek.com/v1/chat/completions`. The prior successful CONN-02 contract and raw evidence used `https://api.deepseek.com/chat/completions`. The actual request included `parallel_tool_calls=false`, `max_tokens=2048`, `thinking.type=disabled`, and `stream=false`, but it omitted `tool_choice=auto` while one Knowledge tool was offered. These are frozen configuration deviations. Since the request outcome is unknown and the stop rule forbids retries or parameter corrections after dispatch, execution ended immediately.

## Safety and side effects

There was no TaskBinding, diagnosis, Approval, ActionIntent, Ledger action, handoff queue/receipt, ticket write, or external business write. Main was not modified; no browser automation occurred. Test setup HTTP posts were loopback-only and are recorded as preparation, not Agent behavior.

## Evidence index

- `RESULTS.json`: consolidated machine-readable outcome.
- `attempt-03/RESULTS.json`: exact run/ledger snapshot from the live run.
- `attempt-03/PROVIDER_HTTP.jsonl`: actual redacted outbound wire capture; no response event was received.
- `attempt-03/TRACE.jsonl`: API/Worker/Run/answer/dispatch correlation.
- `attempt-03/PREPARATION.json`: isolated local fixture setup, distinct from Agent observations.
- `attempt-03/runs/live.log`: fresh execution log.
- `attempt-01/` and `attempt-02/`: preserved local-only pre-provider failures.
- `run_live.py`: one-shot evidence runner. Product code was not modified.

## Scope and limitations

Not run: S02-1 through S02-5; Provider response/Usage/billing; any second request; browser; full pytest. This experiment does not establish model behavior, autonomy, S01 success, or S02 continuity. Remote GitHub refs could not be freshly read because HTTPS 443 was unreachable; the local branch started from the exact authorized SHA. No subsequent task or architecture stage is implied.

## North Star §8 six checks

1. **User change:** None demonstrated; S01 did not complete and S02 was not run.
2. **Agent decision:** None observed; Provider returned no completion.
3. **Observation-driven action:** None; no MCP tool call or Observation occurred.
4. **New constraint:** The existing fail-stop on UNKNOWN prevented further spending or duplicate execution; it did not block a completed legal action because none was available after the unknown result.
5. **Simplification:** No production code or decision logic changed; the existing formal Assistant, Worker, MCP and ledger were used.
6. **Evidence and stop line:** One actual HTTP request, no response/Usage; one held USD 0.645600 reserve; all later rounds NOT_RUN. The experiment stopped at the first unknown outcome.

**Final status:** `ACCEPTANCE_CANDIDATE` for independent review; experiment `UNKNOWN_STOPPED`. No PASS claim is made.
