# AR-02 × AR-03-INTEGRATION-01 — Frozen Offline Plan

## 1. Preflight snapshot

- Repository: `wgqa/OpsPilot`
- Worktree: `.worktrees/ar02-real-journey-02`
- Branch: `codex/ar02-ar03-integration-01`
- Base / initial HEAD: `a6935a0944b27d0f5598242eb5e1deaa756af1f4`
- Diff at freeze: empty; implementation branch is created from the verified AR-02 base.
- `origin/main`: `ec8c3582f6d145eec9979c43607302731411ead8` (read-only)
- AR-03 source: `255087bae4dc0e9990a650786f5b9aae26f9f1db` (selective port only; no branch merge)
- `PROJECT_NORTH_STAR.md` Blob: `1f737712c7a36ceb34433ac09c3fbba3c3305542`
- `AGENTS.md` Blob: `32c45506cceeaa8c76a5c56bf8360ff476b58856`
- `.agents/skills/opspilot-slice-review/SKILL.md` Blob: `d405c8d413d633824b279202cc1503dab4cf0b03`
- Frozen AR-02 journey: `docs/evidence/ar-02/real-journey-03/REPORT.md`; its status is PARTIAL because S02-4 did not obtain a fresh Receiver Observation. That historical result remains unchanged.
- AR-03 source contract: `docs/evidence/ar-03/upgrade-investigation/ACCEPTANCE_PLAN.md` and `REPORT.md` at source commit `255087b`; the source candidate's own tests are reported there, not treated as this implementation's verification.
- Applicable deferred gates: M2-01/M2-02 gates remain unchanged; this read-only assistant integration does not authorize S1/S2 business writes, handoff, approval, or scope mutation.

## 2. Product and decision boundary

The user can ask about protocol changes without knowing internal document IDs, receive a scoped version comparison, and—only when a trusted TaskBinding exists—ask the Assistant to relate that comparison to current order/Delivery/Receiver facts and prepare an unsubmitted draft. The model may choose whether and when to discover, compare, query, clarify, or answer. Tests will not prescribe one mandatory tool order as a product rule.

The Domain/MCP layer remains authoritative for Session/Tenant/Actor/project grants, document IDs and digests, TaskBinding, current business observations, budgets, and all side effects. Protocol artifacts are investigation material, not live deployment proof or authorization. Historical protocol summaries remain bounded historical leads and never become current business evidence.

## 3. Frozen acceptance matrix

| ID | Frozen check | Required result |
|---|---|---|
| I01 | Valid Session discovers authorized protocol family without caller knowing IDs | Only currently authorized, integrity-checked documents/versions appear with source and digest |
| I02 | Valid Session compares two authorized versions | Real section-level changes, line locations, summary, source refs and digest are returned |
| I03 | Formal API → Worker → `ASSISTANT_V1` → local stdio MCP, no TaskBinding | Discovery/comparison can complete; no business tools or current customer claim is available |
| I04 | Same formal route with trusted binding and Receiver `QUEUED` | The draft distinguishes HTTP 202/acceptance from processing completion and lists unknowns; no handoff/write occurs |
| I05 | Same formal route with trusted binding and Receiver `PROCESSED` | The conclusion differs based on the current same-Event observation; no handoff/write occurs |
| I06 | Unauthorized document and cross Session/Tenant/Actor | Discovery/comparison or current-source revalidation fails closed; legal same-scope query still succeeds |
| I07 | Current grant version/project or document file/digest changes | Persisted discovery/comparison cannot be reused as a currently valid source |
| I08 | Tamper comparison summary/diff evidence while preserving older partial digest | Full current comparison revalidation rejects the tamper |
| I09 | Prior discovery/comparison enters a later Run | Only bounded versions, source refs, summary, digest and selected section metadata are projected; explicitly historical, no complete diff accumulation |
| I10 | Prior result is revoked/expired/cross-scope or current business evidence is from another Run | It is excluded from historical prompt sources; it cannot become a fresh Observation |
| I11 | Ordinary Knowledge, S3 TaskBinding/current Evidence, budget and context guards | Existing AR-02 contracts and the 12,000-token hard refusal remain effective |
| I12 | No side effects | No Diagnosis, Approval, ActionIntent, Ledger, Handoff Queue/Receipt, external write, real Provider request, or browser automation |

## 4. Implementation constraints

- Keep one formal Assistant and existing API/Worker/MCP path.
- Add only the two requested read-only MCP tools: `list_scoped_protocol_documents` and `compare_scoped_protocols`.
- Preserve AR-02 Knowledge behavior, S3 source checks, history selection, 12,000-token budget and provider experiment accounting.
- Selectively port the protocol comparison library/domain bridge from AR-03. Recompute/revalidate persisted output against current trusted documents, including all user-visible diff fields; do not rely only on a partial caller-visible digest.
- Keep historical protocol content bounded and typed; never carry the full comparison forward unbounded.
- No true Provider calls, no browser, no business mutation, no main merge, no new agent/runtime/worker/frontend.

## 5. Verification and evidence boundaries

RED will be captured before product implementation for missing tools, source revalidation, tamper acceptance, and bounded history projection. GREEN will use deterministic `FixtureModel` through the real test API and Worker, with the actual local stdio MCP server and SQLite/HTTP domain paths. Domain negative tests will cover cross-scope, revocation, and Digest/content changes. Existing AR-02 suites will be rerun after integration. Results distinguish fixture-driven control-flow proof from real model autonomy; no inference about paid model quality is allowed.

## 6. Six-question scope check

1. **User change:** Natural language can discover and compare authorized protocol versions and relate them to a bound order's current read-only facts, yielding an unsubmitted, sourced draft.
2. **Agent decision:** The model chooses whether to invoke discovery, comparison, business reads, clarification, or answer; the fixture proves route capability only, not model quality.
3. **Observation-driven:** The same protocol change paired with `QUEUED` versus `PROCESSED` must produce different fact-grounded conclusions; no fixed call order is mandated.
4. **Constraint:** Revalidation blocks stale, forged, revoked, cross-session or cross-tenant sources while valid same-session reads and bound same-task observations remain available.
5. **Responsibility/simplification:** Reuse current Assistant/MCP/Domain checks and AR-03 comparison implementation; do not add a new runtime, workflow, gate, or state store.
6. **Evidence/stop:** Stop after offline API/Worker/MCP, source-security and AR-02 regression evidence is recorded and the isolated candidate is pushed. Paid Provider, browser, main merge and business writes remain unrun.

