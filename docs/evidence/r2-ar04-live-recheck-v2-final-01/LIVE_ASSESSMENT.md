# R2-AR04 final live recheck — preliminary assessment

**Candidate status:** `ACCEPTANCE_CANDIDATE`

**Live outcome:** `STOPPED` after Q02-B failed before summary persistence.
**Review authority:** `IMPLEMENTER_PRELIMINARY_REVIEW`; independent main-agent review has not occurred.

## Frozen execution and preflight

- Repository: `wgqa/OpsPilot`; branch: `codex/r2-ar04-live-recheck-v2-final-01`.
- Authorized dispatch HEAD: `d69b06c3005b07df9c7c8619b373c4d7547e991d`. The runner revalidated this candidate HEAD and the frozen production blobs before dispatch and before each request.
- Live request order was Q02-A → Q02-B → Q06-B. Q06-B was not started after Q02-B stopped.
- DeepSeek's official [Models & Pricing page](https://api-docs.deepseek.com/quick_start/pricing/) was checked on 2026-11-15. It lists `deepseek-flash` as `DeepSeek-V4.1-Flash-1017`; peak cache-miss input/output prices are USD 0.30/1M and USD 1.20/1M tokens. The documented weekend off-peak rates are half those prices. The runner reserved against peak rates: USD 0.004215 per maximum-size request and USD 0.037935 for all nine possible requests, below the USD 0.06 cap.
- The task-specific authorization manifest was generated with a new ID, a 30-minute expiry and the exact limits. It remains outside Git under the worktree's `.local/` directory. Only its SHA-256 is recorded in the live result; the manifest itself is not part of this candidate.
- Fresh zero-cost preflight passed at `2026-11-15T12:10:52Z`: main repository `.env` loaded; API key presence was recorded without its value; model and base URL were present; the three non-secret Runtime configuration values were supplemented for the isolated run; isolated Runtime Grant binding succeeded; Mock transport invocations and Provider requests during preflight were both zero. The production database was not opened or written.

## Provider requests and cost

Four unique logical requests were sent. Each received HTTP 200; there was no UNKNOWN result and no retry. The fourth response reached the configured 512-token output limit and ended with `finish_reason=length`.

| # | Case / purpose | Input / output tokens | Ledger status | Provider response ID | Conservative peak-price estimate |
|---|---|---:|---|---|---:|
| 1 | Q02-A / summary 1 | 4,106 / 505 | `COMPLETED` | `f90b5beb-436b-4b4a-a7fa-bfe48be78849` | USD 0.001838 |
| 2 | Q02-A / summary 2 | 3,236 / 373 | `COMPLETED` | `97b59654-47eb-4fe4-8167-6121eb21ec46` | USD 0.001419 |
| 3 | Q02-A / answer | 4,493 / 248 | `COMPLETED` | `a35a2fd4-36e3-421f-8926-4101a5cd97cc` | USD 0.001646 |
| 4 | Q02-B / summary 1 | 4,103 / 512 | `INCOMPLETE`, `finish_reason=length` | `9a2e0db7-153f-4419-91b2-416d2e7ef9ff` | USD 0.001846 |

Total usage was 15,938 input and 1,638 output tokens. The persistent ledger conservatively settles USD 0.006749 using peak rates and records zero currently reserved/UNKNOWN cost. Based on the page's Sunday off-peak rates, the token-price estimate is approximately USD 0.003374. **Provider account debit was not independently checked**, so neither estimate is an account statement.

No external MCP calls occurred. All unattempted slots are `NOT_SENT_FINAL`. There were 3 summary requests, 1 answer request, 4 unique response IDs and 0 automatic retries.

## Case results

| Case | L2: target facts in final model input | L3: actual answer | Comparison with prior real ABC run |
|---|---|---|---|
| Q02-A / HYBRID | `PASS_FOR_TARGET_FACT`: the CURRENT summary covered seq 1–18; the actual answer wire included `/callback` with its source message, the seq 7 correction to `req-483` (with `req-482` marked erroneous), `evt-731`, and deployment version `unknown`. This is a target-scoped pass, not lossless-history proof. The CURRENT summary and final wire omitted the rejected timeout hypothesis and the `v1.2 → v1.3` / `max_attempts 3 → 5` transition; those facts are outside this Case's `/callback` target. | `CORRECT_SUPPORTED` (implementer preliminary): the model answered `/callback`, cited the historical source, distinguished the corrected Request ID, said the deployed version was unknown, and did not treat HTTP 202/QUEUED as completion. | Previously `SAFE_ABSTENTION`: the endpoint was absent from the final prompt. This Case now has target fact visibility and a supported correct answer. The separate earlier retention recheck had stopped after one summary with `KeyError`; this run persisted two summaries and completed the answer. |
| Q02-B / ROLLING_SUMMARY | `FAILED_BEFORE_FINAL_PROMPT`: the first summary response was truncated at 512 output tokens, failed JSON validation and was not persisted. No final answer prompt was built. | `NOT_RUN`; no answer request was sent. | Previously `SAFE_ABSTENTION` because the endpoint was absent from the final prompt. This run cannot establish improvement; it failed during summary generation. |
| Q06-B / ROLLING_SUMMARY | `NOT_RUN`; Case not started. | `NOT_RUN`. | Previously `SAFE_ABSTENTION` because the protocol transition was absent from the final prompt. No new evidence for this Case. |

The old categories above come from `abc-live-env-unblock-01/IMPLEMENTER_PRELIMINARY_ASSESSMENT.json` and its preserved live trace. They are the previous implementer's review, not an independent reassessment. The new L3 result is also preliminary and must not be represented as main-agent review.

## Stop reason, integrity and recommendation

The fourth provider response had HTTP 200 but was incomplete: usage reported 512 output tokens and `finish_reason=length`. Domain rejected the response with `CONTEXT_SUMMARY_INVALID_JSON`; the runner stopped with `PROVIDER_OUTPUT_NOT_COMPLETE`. The second summary and answer slots for Q02-B and all Q06-B slots are `NOT_SENT_FINAL`. No request was retried.

`LIVE_RESULTS.json`, `COST_LEDGER.json`, `LIVE_REQUESTS.jsonl.gz`, the two persisted Q02-A summaries and its Answer Manifest are preserved under [`live_run_01/`](live_run_01/). The raw trace contains 4 request records and 4 response records; a local scan found no Authorization/Bearer value or API-key assignment. Historical trace/Gold/ledger hashes matched the frozen baseline; production Context code was not changed; no business action or production database write occurred.

The legacy result's `base_sha` field is `d8a526daa9c811814a5e2463b34eb37037ae1a8e`, inherited from the underlying harness metadata. Its `candidate_head_at_check`, frozen pre-dispatch check and the actual checkout HEAD are all the authorized `d69b06c3005b07df9c7c8619b373c4d7547e991d`. This metadata discrepancy is recorded here; the existing runner was not edited.

**Recommendation:** do not close AR-04 yet. Q02-A demonstrates a real improvement for its target fact, but Q02-B is blocked by output truncation and Q06-B remains untested. This authorization is exhausted by the stopped run; no further Provider call is made in this candidate. Main-agent review decides whether a new task is warranted.

## Evidence hashes

- `LIVE_RESULTS.json`: `3c3d889c6fe5e5b2053de9e7a2185404774631aaad32731c630916d7f568e5ff`
- `COST_LEDGER.json`: `cb104366e5df3989eff8e2231e7a498baaf6ff96450953e8da031a2467404136`
- `LIVE_REQUESTS.jsonl.gz`: `6c6d5b8d006c775a4393894b59ce5a8b722aa89a71c8ca427868a2b8c3db20e2`
- Authorization manifest SHA-256: `3c50e2d883d1cbbf7856c8dd95b3a6810f0cc8fb7b498f42902ca82bfad507f6` (manifest not committed).
