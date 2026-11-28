# R2-AR04-SUMMARY-OUTPUT-HEADROOM-HF-01

**Status:** `ACCEPTANCE_CANDIDATE`
**Base:** `d4ca2c914b6b99f26d1941d780f838d61a6a75d0`
**Provider requests:** 0
**Provider cost:** USD 0

## Finding

The prior Q02-B summary call returned HTTP 200 but stopped at the configured 512 output-token limit. Its response used 512 output tokens and had `finish_reason=length`; the JSON ended incomplete. The historical Domain error was `CONTEXT_SUMMARY_INVALID_JSON`, and the runner stop reason was `PROVIDER_OUTPUT_NOT_COMPLETE`; both records remain unchanged with the original response in `docs/evidence/r2-ar04-live-recheck-v2-final-01/live_run_01/`. The source Trace SHA-256 is `6c6d5b8d006c775a4393894b59ce5a8b722aa89a71c8ca427868a2b8c3db20e2`; Provider response ID is `9a2e0db7-153f-4419-91b2-416d2e7ef9ff`; response content SHA-256 is `6c4da759c0c27112b4db6fa2984cd171c7e4420f7a006328be8a767c48e40f3d`.

The previous persisted-summary ceiling was also used as the Provider generation cap. Those are separate constraints: the Provider needs room to finish a valid document, while Domain still must compact the validated document into its existing 512-token persistence limit.

## Changes

- Added distinct constants: Provider summary generation is capped at 1,024 tokens; Domain summary persistence and compaction remain capped at 512.
- Summary context planning now reserves the 1,024-token generation allowance.
- The compression request cap is `min(1,024, Runtime Grant max_output_tokens)`. A lower Grant still clamps the request; an isolated Grant at 1,024 authorizes it. The existing product maximum of 2,048 remains unchanged.
- The compression prompt now prioritizes complete valid JSON and required facts, asks for concise output, and leaves the 512-token limit to downstream application compaction.
- Known `finish_reason=length` results and reported usage above the effective request cap stop before Domain summary persistence. Usage is durably settled first where a ledger applies; the request is never resent.
- The normal answer model path is unchanged. In the frozen live matrix, the answer request cap remains 512; this offline change only raises the compression request cap.

## Evidence

`MOCK_TRACE.jsonl.gz` records three full Assistant/Domain Mock cases: the exact historical incomplete Q02-B response replayed through MockTransport, a synthetic complete 700-token JSON response, and a synthetic 1,025-token over-cap response. The complete synthetic JSON is test-only; it is not represented as the missing portion of the historical Provider response.

The Q02-B historical response was rejected with `CONTEXT_SUMMARY_OUTPUT_TRUNCATED`, with no summary persistence. The valid synthetic response completed the Assistant path; Domain persisted a 226-token summary. The over-cap fixture stopped with `CONTEXT_SUMMARY_OUTPUT_LIMIT_EXCEEDED`, without summary persistence. All are offline Fixture/Mock evidence, not live semantic evidence.

The existing Q02-A/Q02-B/Q06-B fact and provenance regressions, the C06 gate, and the Runtime Grant regression passed in the combined targeted suite. The Runtime Grant fixture verified the 1,024-token authorization ceiling, an effective 1,024 summary request, a narrower 512 answer request, and a $0.004829 pre-send reserve.

## Budget and boundaries

The previous final-runner task recorded an official DeepSeek price snapshot on 2026-11-15: $0.30 per million uncached input tokens and $1.20 per million output tokens. This offline task reuses that frozen snapshot only for arithmetic; it does not claim current pricing and does not authorize a future send. A later live task must recheck the Provider model and prices and obtain its own authorization.

With 12,000 input tokens, the summary request envelope reserves $0.004829, and the unchanged 512-token answer envelope reserves $0.004215. Six summaries plus three answers total $0.041619 under the previous $0.06 hard cap. Runtime Grant reservation is based on the entire Grant ceiling: a 1,024-token Grant reserves $0.043461 across nine calls; the existing 2,048-token ceiling reserves $0.054522. Both stay under that cap. Full arithmetic is in `BUDGET.json`.

The previous V2/live runner remains unchanged because it pins the older production blobs and a single 512-token request limit. It must reject this new source Blob; it is not reused or silently relaxed here. This task does not prepare or authorize a real Provider runner.

No historical Trace, Gold, failure record, C06 RED artifact, production database, or main branch was modified. No `.env` value was read, no real Runtime Grant was created, and no external MCP was called.
