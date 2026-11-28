# R2-AR04 Remaining Live Execution — Stop B

## Result

`ACCEPTANCE_CANDIDATE` for independent review. The one authorized Live invocation stopped during Q02-B compression before the transport ledger began a Provider send. No retry was made and Q06-B was not started.

- Frozen candidate at send: `cd8b2a5055d2b5bd2dc219740cd14f99b2b702af` on `codex/r2-ar04-live-admission-hf01`; original task base `fa4cd8a7ea6dd36babccbbfc5fcdb7a179729fd3`.
- Provider/model checked from official DeepSeek documentation: `deepseek-flash` / `DeepSeek-V4.1-Flash-1017`.
- Provider requests started: **0/6**; summaries **0/4**; answers **0/2**.
- Cost ledger settled: **USD 0.000000**; reserved after stop: **USD 0.000000**. Account billing was not independently queried.
- Stop reason: `CHAT_CONTEXT_COMPRESSION_FAILED`. Q02-B has one failed Domain compression attempt (`estimated_input_tokens=6000`, no Summary ID or Provider Response ID); Q06-B is `NOT_STARTED`.
- L2: `NOT_EVALUATED` (no final prompt); L3: `NOT_RUN` (no model answer). Prior Mock L2 evidence is retained but is not counted as Live.
- External MCP calls: 0; production database writes: 0.

## Request and cost evidence

`COST_LEDGER.json` records zero started requests, six `NOT_SENT_FINAL` logical slots, zero settled cost, zero reservation, and no UNKNOWN request. `LIVE_REQUESTS.jsonl.gz` was not created because the `SEND_STARTED` boundary was never reached; no synthetic empty Trace is substituted. The Runner's `live_dispatch_performed` flag means the authorized Live code path was entered; the ledger is the authoritative send counter.

## Case results

| Case | Result | L2 | L3 | Detail |
|---|---|---|---|---|
| Q02-B | STOPPED before Provider dispatch | NOT_EVALUATED | NOT_RUN | `CHAT_CONTEXT_COMPRESSION_FAILED` during first compression attempt; no persisted Summary, response ID, final prompt, or answer. `/callback` was not tested in Live. |
| Q06-B | NOT_STARTED | NOT_EVALUATED | NOT_RUN | Stopped because the contract requires stopping the series on the first Case failure. Version and `max_attempts` facts were not tested in Live. |

The failed attempt records `error_class=CHAT_CONTEXT_COMPRESSION_FAILED`, `status=FAILED`, `attempt_no=1`, and prompt digest `aa4a04476220e224193521702ea0272b5be3fa5b21a86e3949d2b2f55b391a49`. The exact lower-level exception details were not preserved by the Runner; no cause is inferred here.

## Frozen provider snapshot and budget

The official pricing page was rechecked at `2026-11-16T12:43:20Z` UTC. It lists `deepseek-flash` as `DeepSeek-V4.1-Flash-1017` and peak rates of USD 0.30/M cache-miss input tokens and USD 1.20/M output tokens. Snapshot SHA-256: `f5f3650c356b9c7e460919b5f0162c1c32a165a6a7d437ae1ba28c5d32d39b2b`; normalized observation digest: `52f47edfc0b391c93afd02980bc2f94b2a9ddf5fb686f9674d1d6716f99cf6ce`. The existing Runner rates match these figures.

Worst-case purpose reserve was USD 0.027746; shared Runtime Grant reserve was USD 0.028974, below the USD 0.06 hard cap.

## Authorization and artifact digests

- Authorization ID digest: `f32dfa1a27d0b7fefc1cf171548732d4790fd1021956a0a7b818f41f600c41f6`
- Authorization Manifest digest: `ea40efd6c2ef0b1331a98573d3e84fc411a132be2694ea589736629e8364ba91`
- Runner SHA-256: `e31956fb0ec381458f5271d4ccbf580daf36a54c69737ee8fcd59eba65976a1e`
- Fixed Mock SHA-256: `84bdf25e883215cb059ab1f82681ff9a0a1b26a9d0ca1e3dcb52a85b95b3b94b`
- Source Manifest SHA-256: `c2ac084686f113eb0f9782557ff83eb4dd983007072de56512d065c2b83446ba`
- Live Results SHA-256: `4b4915eee9f0fceec0dac560b1e95c10c6c13c44a6e6f01146d2427462f8eb3a`
- Cost Ledger SHA-256: `9822ff1bd9109f9e821a8c191c6272f95ff7f5a7956049f5dc733fdfd7898ad9`
- Live Preflight SHA-256: `85724c23e1544b22d0791ce1a0e42e7e3cfc5af0e165ab8ecf900b307a921bf0`
- Comparison SHA-256: `abce0b4cbf85bf97ebc6ddc555e62a7989733e0b9070cbf9cdfc66788bba0b30`

The effective Authorization Manifest remains only in the isolated local `.local` directory and is not committed. `AUTHORIZATION_RECORD.json` preserves its non-sensitive digests and scope.

## Operational integrity note

Two existing tracked Preflight files were initially selected by mistake as output names. Their contents were copied to new `LIVE_PREFLIGHT_STOPB_*_20261116.json` files, then the tracked files were restored to the exact HEAD blobs (`9cab3364…` and `3e085614…`) and verified clean before any Live request. The final default and explicit Preflights use new filenames. No historical artifact remains changed. A transient `git ls-remote` connection reset was followed by a successful read confirming the remote branch still pointed at the frozen send SHA before dispatch.

## Stop line

The one-time Live execution is consumed. No retry, alternate output path, or further Provider request was made. Resolving the compression failure requires a separate diagnosis and authorization; this report does not reopen the Live round.
