# AR-03-LIVE-HF-01 — Frozen Offline Acceptance Plan

**Status:** Frozen before the HF-01 regression run  
**Base:** `codex/ar03-real-llm-01-live@03d6248bf00439d3e189ac437fd805c1366b93c5`  
**Branch:** `codex/ar03-live-hf-01`  
**Scope:** Two offline-only product/entry-point corrections. The prior AR-03 live Gold, Provider traces, runtime databases, and failures remain immutable.

## Starting contract records

- `PROJECT_NORTH_STAR.md` blob: `1f737712c7a36ceb34433ac09c3fbba3c3305542`
- `AGENTS.md` blob: `32c45506cceeaa8c76a5c56bf8360ff476b58856`
- `.agents/skills/opspilot-slice-review/SKILL.md` blob: `d405c8d413d633824b279202cc1503dab4cf0b03`
- Frozen cases blob: `c29b5cf7630fa838a365634d0df5f9f0f2bfa834`
- Frozen Gold blob: `88d5e6f40f027ce2622b957d8ab32b8d2b827381`
- Frozen budget blob: `5a71096584b4003b5f30c53fd69ccfd11bbc53d4`
- Remote main at start: `ec8c3582f6d145eec9979c43607302731411ead8`

## Frozen checks

1. **Trusted binding can carry the full goal.** POST the exact frozen prompt in `CASES.json` as `initial_message` to the existing authenticated `/assistant/order` API for `ar03-order`. The resulting single ASSISTANT_V1 Run must perform its own investigation through the existing Worker/MCP/Domain path. There must be exactly one user Message, one Task, and one Run for that operation; no second `/assistant/messages` request or separate admission investigation may be introduced.
2. **Paired facts remain distinct.** Run the offline formal API/Worker test once for same-Event Receiver `QUEUED` and once for `PROCESSED`, with HTTP 202/ACKNOWLEDGED. The same initial API request must lead to a sourced answer appropriate to each current observation.
3. **Usable investigation budget remains.** The model fixture may choose the legal protocol discovery/comparison and same-Task read-only order/Delivery/Receiver tools. All actual MCP calls must be associated with the single binding Run and stay within its existing limit of six; assert successful execution and 12,000-token Context cap. No tool order is required by the Gold.
4. **English phrase retrieval.** `retry`, `callback`, and `callback retry` must retrieve the authorized callback retry protocol pair where applicable. The multiword query must not return empty merely because words occur in separate authorized metadata fields.
5. **Chinese topic retrieval.** `回调`, `重试`, `回调重试`, and `回调 重试` must reasonably find the authorized callback retry protocol pair. This is metadata matching, not a new content/vector search service.
6. **Authorization remains scoped.** A permitted same-Session lookup succeeds. An actor/session/tenant without current project authorization cannot read documents. A search query for a document outside the current `document_ids` scope must not return it, even if the catalog contains it.
7. **No side effects or paid calls.** Use the existing deterministic FixtureModel and local HTTP/MCP/SQLite test path only. Provider HTTP requests, Diagnosis, Approval, Plan, ActionIntent, Ledger, Handoff/Receipt and external business writes remain zero.

## Stop line

Run focused RED/GREEN and the relevant existing AR-03 integration/security tests. Do not change the frozen Gold or historical traces; do not invoke DeepSeek, automate a browser, modify `main`, alter budgets, or begin further AR-03 work. Report any tests not run and submit only an acceptance candidate for independent review.
