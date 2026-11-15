# Runner and compatibility design

## Version lock

`run_remaining_live_gate.py` pins the task Base, current `chat.py` and `assistant.py` blobs, frozen Questions/History/Gold inputs and the historical source traces. It imports the accepted V2 adapter without editing it and binds the V2 Base, Case matrix and Blob pins inside a scoped compatibility context. `assert_frozen()` still runs before each Mock request and at any future live request boundary. A production Blob drift or a tracked task diff outside this evidence directory stops the run.

The V2 fixed three-case matrix is narrowed to Q02-B and Q06-B; the existing per-case harness then seeds separate 29-message histories and grants. The source table pins the completed ABC first-summary replies by trace digest, logical request ID, Provider response ID, response body digest and summary text digest. Their contents are replayed only through `httpx.MockTransport`.

## Output-cap split

The Runtime Grant authorizes 1,024 output tokens. The task adapter changes only the newly constructed task-local ChatOpenAI model's default `max_tokens` to 512 after the Grant has been validated. The existing production compression path binds its own model to `min(1,024, Grant.max_output_tokens)`, so summary requests use 1,024 while the base answer path remains 512. The transport checks every request purpose and cap before its single underlying transport call. The Domain's 512-token persisted summary cap is unchanged.

## Shared budget

The offline snapshot arithmetic is:

| Envelope | Reserve per request | Slots | Total |
|---|---:|---:|---:|
| Summary: 12,000 input + 1,024 output | USD 0.004829 | 4 | USD 0.019316 |
| Answer: 12,000 input + 512 output | USD 0.004215 | 2 | USD 0.008430 |
| Purpose-specific requests | — | 6 | USD 0.027746 |
| Grant ceiling: 12,000 input + 1,024 output for each of 6 requests | USD 0.004829 | 6 | USD 0.028974 |

Each of the two isolated case Grants reserves three request envelopes (two summaries and one answer), USD 0.014487 each. Their summed Grant reserve is USD 0.028974 under the single USD 0.06 shared ledger ceiling. The request ledger has six one-shot slots; historical UNKNOWN and prior experiment ledgers are not imported.

## Authorization gate

Future `live` mode requires an exact current task/base/case/limits manifest, `actual_live_send_authorized=true`, a short validity window, no retries, no external MCP, `tool_choice=none`, at most 1,024 output tokens for summaries and 512 for answers, at least the conservative shared reserve and no more than the USD 0.06 hard cap. A price snapshot must be no more than 24 hours old, from the official DeepSeek pricing URL, for the pinned model/version and within the reserved price ceiling. The manifest is revalidated at each live request boundary together with the source and Blob checks.

The authorization also binds the exact Runner digest, accepted Mock result digest, source-manifest digest and production Blob pins. A Mock or source artifact replacement after authorization invalidates that authorization.

This task does not create that manifest, and only `mock`, `preflight`, and `prepare` were invoked. The live mode is not entered.

## Reused stop behavior

- Failed Domain summary persistence prevents an answer manifest.
- Source invalidation stops the Case before an answer and stops later Cases.
- A request at an incorrect purpose-specific cap is rejected before dispatch.
- UNKNOWN uses the existing shared ledger's UNKNOWN reservation, cannot retry the logical request and stops later Cases.
- An existing live output directory is not resumed or overwritten.
