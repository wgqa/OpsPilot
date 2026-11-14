# Live semantic comparison

**Result:** partial live evidence; stopped at the first returned tool call. This does not establish an A/B/C/D ranking.

## Group coverage

| Group | Configuration | Answers sent | Summary calls | Result |
|---|---|---:|---:|---|
| A | HYBRID, input 12,000 | 0/7 | 0 | `BLOCKED_BEFORE_PROVIDER_SEND`: no bindable isolated Runtime Grant or complete runtime configuration |
| B | ROLLING_SUMMARY, input 12,000 | 0/7 | 0 | `BLOCKED_BEFORE_PROVIDER_SEND`: same Grant boundary |
| C | RECENT_WINDOW, input 12,000 | 0/7 | 0 | `BLOCKED_BEFORE_PROVIDER_SEND`: same Grant boundary |
| D | FULL_HISTORY_REFERENCE, input 60,000 | 3/7 | 0 | Two complete answers; Q06 returned a tool call; four questions were not sent after the stop condition |

The 21 A/B/C slots remain in `RESULTS.json` as blocked; they are not excluded from the 28 planned answer slots. D was run through the task-authorized `DIRECT_EVAL_REFERENCE` path with its own persistent request counter and cost reservation. Its tool schemas were supplied, but the evaluator has no tool dispatcher.

## Actual D responses

| Question | Provider result | Review |
|---|---|---|
| Q02 | Answered `/callback`; distinguished historical config from deployment, treated the latest `QUEUED` fixture as synthetic, and proposed read-only verification | `CORRECT_SUPPORTED` |
| Q03 | Correctly returned `req-483`, noted `req-482` was an entry error, and preserved `evt-731`; it incorrectly claimed the correction was in the current message, while the source is earlier history sequence 7 | `INCORRECT_OR_UNSAFE` due to the false source-provenance claim; no unsafe action was proposed |
| Q06 | Began a scoped-document lookup and returned `list_scoped_protocol_documents` with topic `callback retry protocol`; it did not answer the version transition | `INCOMPLETE`; tool call recorded and not executed. This triggered the stop rule |
| Q07, Q08, Q10, Q12 | Not sent | `BLOCKED_AFTER_STOP_CONDITION` |

The main Agent reviewed every completed live answer and the Q06 non-answer. Across two complete answers, one was correct and supported, and one had correct core facts but a false provenance statement. This tiny, question-selected sample is not an accuracy estimate. No second paid evaluator was used.

## Prompt and token evidence

For all three sent requests, the final D prompt contained one system message, all 29 history messages in order, and the exact current question. There were no summary messages and no pending historical tool calls. All 15 historical user messages matched the frozen snapshot exactly. The 14 historical assistant messages retained their contents with the context label `历史答复（不是本 Run 新观察）：`; no message was omitted. The required source sequences for Q02, Q03, and Q06 were visible in the corresponding request. Full message bodies and the selected-source manifests are in `LIVE_REQUESTS.jsonl.gz`.

| Q | Fixture estimate | Provider prompt tokens | Completion tokens | Response ID | Response model |
|---|---:|---:|---:|---|---|
| Q02 | 39,475 | 26,257 | 255 | `e2218b38-9c49-4b5a-ac77-6289c459c9fd` | `deepseek-flash` |
| Q03 | 39,474 | 26,256 | 196 | `8850e205-aef7-48f6-8a90-de8ddb027de7` | `deepseek-flash` |
| Q06 | 39,473 | 26,253 | 81 | `68aab07c-7a64-4ba9-891d-3baf6018101e` | `deepseek-flash` |
| **Total** | **118,422** | **78,766** | **532** | — | — |

Provider-reported prompt tokens were 39,656 below the local fixture estimates (33.49%). The request used thinking disabled, temperature 0, `max_tokens=512`, and the same tool schema digest as Phase A. Returned model identity stayed `deepseek-flash`; usage was present for all three calls. No retry, summary request, unknown send state, truncation, or external tool execution occurred.

## Cost and limits

At the checked official peak no-cache rates, reported usage gives a conservative token-cost upper estimate of **USD 0.0242682**: 78,766 input tokens and 532 output tokens. Each request was preceded by a durable USD 0.0186144 maximum reservation; the largest prior usage plus next-request reservation was USD 0.0349095. No reservation remains active. The official API response does not report the billed dollar amount, so `COST_LEDGER.json` leaves `actual_billed_usd` unset instead of presenting the estimate as a charge.

The full task's theoretical upper envelope remains USD 0.3368064 under the USD 0.50 hard cap. This partial run stopped at 3 Provider requests, well below the 56-call cap. No A/B/C or later D calls were attempted after the stop condition.

## Phase A comparison boundary

Phase A was deterministic fixture evidence only: A/B each had 9/12 fully available questions, C had 3 complete plus 3 partial and 6 missing, and D had 12/12 available. Its `provider_requests=0` and L3 `NOT_EVALUATED` remain unchanged. Those results describe prompt availability under the fixture; they are not real-model answers and are not mixed into this live score.
