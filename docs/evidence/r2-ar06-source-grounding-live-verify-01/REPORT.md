# R2-AR06-SOURCE-GROUNDING-LIVE-VERIFY-01

Status: `ACCEPTANCE_CANDIDATE` — independent Main Agent scoring is pending.

## Basis and scope

- Code base: `codex/r2-ar06-source-grounding-hf01@c8f32b1fce792a3a9e3984e2ce5c3d7cc86ee7cf`
- Execution branch: `codex/r2-ar06-source-grounding-live-verify-01`
- User-authorized budget: USD 0.05 per isolated Runtime, USD 0.10 aggregate.
- Cases: one first-attempt E07-D QUEUED run and one exploratory PROCESSED contrast run using the unchanged E07-D prompt.
- No production code, system prompt, tool schema, Gold, Rubric, prior trace, or business state was changed.
- No retries, resubmissions, external business writes, or UNKNOWN requests occurred. No automated tests were run; this turn was a bounded live evaluation.

The exploratory contrast is not E08-H, is not a frozen benchmark case, and is not included in the frozen 12-case denominator. Both Runner results retain `assessment_status=UNVERIFIED`; this report does not award a formal PASS.

## Results

| Run | Current Receiver | Run / Session | Provider requests | Input / output tokens | App-settled cost | MCP / Observations / Evidence |
|---|---|---|---:|---:|---:|---:|
| E07-D | `QUEUED`, target Event `...0001` | `run-49471cb5-314d-4f2e-b86f-1b0b2335a86b` / `session-89628dd6-0730-486d-998f-d86310c402fc` | 2 | 8,073 / 821 (8,894 total) | USD 0.003408 | 3 / 3 / 3 |
| Exploratory PROCESSED | `PROCESSED`, target Event `...0101`; decoy Event `...0102` remains `QUEUED` in the prepared profile | `run-52c2442a-cf60-4dd1-8dfe-63ebb65860fc` / `session-7dd9c918-6ff2-4379-a49b-7f38eb850f86` | 2 | 8,022 / 676 (8,698 total) | USD 0.003219 | 3 / 3 / 3 |
| **Total** | 2 isolated successful Agent Runs | — | **4** | **16,095 / 1,497 (17,592 total)** | **USD 0.006627** | **6 / 6 / 6** |

Each Agent Run used two Provider responses: one model turn to choose read-only MCP tools and one turn to answer from their results. These were not retries. The model selected `get_order_status`, `get_callback_delivery`, and `get_receiver_processing`; it did not call `memory_remember` or any business-write tool. Each Run terminated `SUCCEEDED`; UNKNOWN count was zero.

The application spend ledger records configured-rate estimates, not the provider invoice. The configured price inputs were checked against the [official DeepSeek pricing page](https://api-docs.deepseek.com/quick_start/pricing/).

## Source-grounding observations

Both final Provider requests contain one system message, one user message, one prior AI tool-call message, and the three actual `ToolMessage` results. `tool_result_projections` is empty in both requests, so the model received the complete paired tool results. The final input token estimates were 5,115 and 5,070, under the configured 12,000 input budget.

The system context states that the order Observation supports only fields actually returned by that order response, does not supply the callback business `event_id`, and that `authn_event_id` is a distinct authentication identifier. It permits same-Event attribution only when Delivery and Receiver each return the same `event_id`.

- **E07-D / QUEUED:** The answer separates the order's `COMPLETED` status from callback processing. It says the order response has no callback `event_id`; it identifies `authn_event_id` as an authentication identifier. Delivery and Receiver identify the same target Event, while Receiver remains `QUEUED`. The answer does not treat HTTP 202 as completed processing.
- **Exploratory / PROCESSED:** The current Run's task-scoped Receiver Observation and Delivery Observation both identify target Event `...0101`; Receiver is `PROCESSED`. The order Observation remains order-scoped and is not attributed a callback Event ID. The answer's completed-processing conclusion relies on the Receiver observation, not HTTP 202. The runner result records target Event `...0101`, decoy Event `...0102`, and `supports_target_processed_conclusion=true`; the decoy was not substituted as the target.

No three-source Event-ID over-attribution appeared in these two answers. This is one answer per scenario and does not establish statistical improvement or eliminate arbitrary natural-language attribution errors. Main Agent must independently review the full traces and score the outputs.

## Spend and shutdown

- E07-D Runtime `user-demo-r2-sg-live-queued01`: USD 0.003408 settled; USD 0.046592 remains in its USD 0.05 pool; 2 sends; 0 UNKNOWN.
- PROCESSED Runtime `user-demo-r2-sg-live-processed01`: USD 0.003219 settled; USD 0.046781 remains; 2 sends; 0 UNKNOWN.
- Both Runtime Grants report `ACTIVE` with expiration `2026-11-15T07:30:00Z` in the captured summaries. API, Worker, and frontend were gracefully stopped after each run. No Grant was extended or reused. The remaining grant balances are still within their original expiry window; do not restart these Live runtimes for another request without new authorization.
- Runtime Domain DBs, Checkpoint DBs, logs, traces, and spend ledgers remain in their isolated `.runtime` directories and were not reset or copied.

## Evidence and verification limits

- `LIVE_RESULTS.json` links each immutable Runner result to its sanitized trace and SHA256.
- Exported trace scans found zero sensitive credential fields/patterns with non-redacted values; each trace's redaction metadata reports API keys, authorization, cookies, configured passwords, bearer tokens, and `sk-` tokens removed.
- New Worktrees: 0. Provider requests: 4. Browser automation: 0. External business writes: 0. Production code changes: 0. Gold/Rubric changes: 0.
- Formal M1-M6 semantic scoring and acceptance are pending independent review.

## Candidate publication

- Local candidate commit is retained on `codex/r2-ar06-source-grounding-live-verify-01`.
- Remote publication is `BLOCKED`; no remote branch was created. Two Git HTTPS pushes failed because the connection to `github.com:443` was reset/unreachable. The connected GitHub integration also rejected Git Blob creation with HTTP 403 (`Resource not accessible by integration`).
- No PR or merge was created. The evidence is complete in this local candidate commit; a remote SHA is unavailable until repository write access or Git transport recovers.
