# Failure and limitation analysis

## Stop event

The live run stopped after the Q06 response returned a `list_scoped_protocol_documents` tool call (`topic: callback retry protocol`). The response did not state the requested version transition. The direct evaluator recorded the complete request, response, tool name, and arguments, executed nothing, and sent no Q07/Q08/Q10/Q12 request. The returned function is read-only in the app schema, but external MCP was outside this experiment's permitted execution path. This is an observed answer-path interruption, not a compaction failure.

## Information availability versus answer quality

| Observation | Context evidence | Assessment |
|---|---|---|
| Q02 correctly recalled `/callback` | Source message sequence 3 was present in the actual D prompt; sequences 11, 21, and 29 also supported the related correction/deployment/status statements | Information was visible and the answer was supported |
| Q03 gave `req-483` and the superseded `req-482` relationship correctly | Formal correction sequence 7 was present in the actual D prompt | The core fact was available and correct, but the answer falsely said the correction was in the current message. The source-provenance error remains even with full history visible |
| Q06 did not answer the `v1.2` to `v1.3` question | Source sequence 11 was present in the actual D prompt | The answer was interrupted by a tool-call response; no history fact was missing and no tool ran |
| Q07/Q08/Q10/Q12 have no live result | No request was sent after the Q06 stop condition | `BLOCKED_AFTER_STOP_CONDITION`; do not infer success, failure, or recall quality |
| A/B/C have no live result | No isolated Runtime Grant was available to bind their Assistant runs | `BLOCKED_BEFORE_PROVIDER_SEND`; no compression outcome was measured in this pilot |

For each sent D input, the scorer compared the actual request messages with the frozen 29-row snapshot in order. All 15 user messages were exact. The 14 historical assistant messages were retained with the context projection prefix `历史答复（不是本 Run 新观察）：`; the original text followed the prefix intact. D contained no generated summary and no message omission. Thus the Q03 source misattribution and Q06 tool call cannot be attributed to missing prompt context in these requests.

## Runtime Grant block

The isolated worktree had no `.env` or default runtime database, and its process environment lacked the required Assistant runtime configuration. There was no bindable Runtime Grant whose model, validity window, spend pool, token caps, and permissions could be checked. A/B/C were therefore blocked before any Provider send. No Grant was created, and no existing Domain database was migrated or modified.

This is a setup prerequisite for the A/B/C comparison, not evidence that the production Runtime Grant feature is faulty. A future separately authorized run would need a valid isolated Grant binding before those groups can be evaluated. This task does not provision one.

## Token and billing limits

The fixture estimator predicted about 39.5k input tokens per D prompt; the Provider reported about 26.3k. This is an estimator difference, not missing prompt content. The sender reserved each request at the authorized 60,000-input/512-output maximum and stopped before another call once Q06 returned a tool call.

The USD 0.0242682 value is a conservative estimate from Provider usage and official peak no-cache rates. The API response does not include the actual billed dollar amount. No billing endpoint or unrelated account data was queried. No unknown send state occurred, and the request counter, token usage, and cost estimate remain in `COST_LEDGER.json`.

## Repair decision

No production compaction fix is supported by this partial live result. The observed Q03 issue is answer provenance; Q06 is a tool-call interruption. Neither shows a lost source in the D prompt. The stop condition was honored, and remaining questions stay unmeasured. Do not tune the compression policy from this sample or treat Phase A fixture results as live validation.
