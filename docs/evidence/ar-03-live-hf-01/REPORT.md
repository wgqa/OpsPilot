# OpsPilot AR-03-LIVE-HF-01 — Offline Fix Report

**Implementation status:** `ACCEPTANCE_CANDIDATE`
**Base:** `codex/ar03-real-llm-01-live@03d6248bf00439d3e189ac437fd805c1366b93c5`
**Branch:** `codex/ar03-live-hf-01`
**Frozen plan commit:** `d11af42a463cfd8b7ad013b831bf3bdb5c40c058`
**RED commit:** `36415ae`
**Implementation commit:** `7f7a49c`
**Freeze standards:** `6f9074e84c185553cfeab0f225e81640b8b525f0`

This is an offline-only correction. It does not alter the historical AR-03 live experiment, its Gold, Provider records, failures, budget, or business outcome. No real Provider request, browser automation, or business write was performed.

## User-visible behavior verified

The trusted `POST /api/sessions/{session_id}/assistant/order` API already accepts the full frozen business question in `initial_message`. With the authenticated `tenant-a / support-a` request binding `ar03-order`, that single operation creates one Task, one user Message, and one `ASSISTANT_V1` Run. The Run can perform the actual local MCP/Domain investigation and persist its answer; no follow-up `/assistant/messages` request is needed. The previous live trace remains unchanged and still records its two-request pattern. This work verifies the one-request path for future use; it does not rewrite or reinterpret that historical run.

In the offline paired test, the exact frozen prompt was submitted through the trusted order API. One run per case discovered and compared the authorized callback retry contracts, queried current same-Event order/Delivery/Receiver facts, and returned a sourced unsubmitted draft:

| Receiver fact | Run | Formal API/Worker outcome | Actual MCP calls | User-facing distinction |
|---|---|---|---:|---|
| `QUEUED` | `run-a973fe1c-3c2f-49f4-85ee-592fa200ff47` | `SUCCEEDED` | 5 of 6 allowed | HTTP 202/ACKNOWLEDGED is transport acceptance; same Event Receiver remains QUEUED and processing is not confirmed. |
| `PROCESSED` | `run-17e3230f-d912-4f6a-a113-51af635d05d8` | `SUCCEEDED` | 5 of 6 allowed | Same Event Receiver is PROCESSED; the conclusion is limited to that Event. |

Each run used six deterministic model decisions (five tool selections and a final answer), the actual `list_scoped_protocol_documents` MCP call used `topic="callback retry"`, and the persisted request and result are in `TRACE.jsonl`. Both runs retained the 12,000-token Context cap. The tests assert one user message and one Run, current trusted binding fields, five successful MCP calls/attempts within the existing six-call ceiling, correct same-Event Observation/Evidence, and zero protected business-action rows. The fixture model is deterministic and does not prove real DeepSeek autonomy.

## Topic search correction

`list_scoped_protocol_documents` previously treated the complete `topic` string as a substring that had to occur inside one metadata field. Therefore `callback retry` missed documents where `callback` was in the ID/title and `retry` appeared elsewhere; Chinese `回调` and `回调重试` also missed the retry protocol pair.

The minimal change in `opspilot/domain/scoped_protocol_comparison.py` tokenizes English terms and matches all terms across the catalog entry's ID, title, filename, and keywords. A small catalog-aligned synonym map supports `回调` → `callback`, `重试` → `retry`, `失败` → `failure`, and `策略` → `policy`; unknown Chinese-only text retains normalized substring matching. This remains metadata matching, not content search.

The authorization order is unchanged: a document must first be present in the current Session project's trusted `document_ids`; only then is topic matching applied and the document resolved with its digest/source validation. Paired tests show authorized hits for `retry`, `callback`, `callback retry`, `回调`, `重试`, `回调重试`, and `回调 重试`; the same authorized Session cannot discover the catalog's out-of-scope `api-scope-current`, and a different actor cannot use the first actor's Session. Existing source/digest revalidation tests remain in the regression run.

## RED → GREEN and regression

The valid RED run (`runs/red-focused-01.log`) had 6 failures and 3 passes: four were product failures for `callback retry`, `回调`, `回调重试`, and `回调 重试`; the other two were test setup errors from supplying one UUID to a fixture that consumes separate Event and transport IDs. The corrected test fixture was rerun before source changes (`runs/red-initial-message-check-01.log`): the direct full-question entry point, both Receiver states, and the authorization pair passed, 3 passed / 14 deselected. This also established that no server source change was needed for the binding entry point.

After the matcher fix, the focused suite passed 10 / 10 (`runs/green-focused-02.log`). Final related regression passed 25 / 25 across the AR-02/AR-03 integration, AR-03 prep, offline wire-preflight, and Assistant suites (`runs/green-regression-03.log`). The full repository pytest suite was not run. Earlier intermediate test runs and their logs are retained alongside the final run.

## Changed files and side effects

- Production source: `opspilot/domain/scoped_protocol_comparison.py` only.
- Tests: `tests/test_ar02_ar03_integration_01.py`.
- New isolated evidence: `docs/evidence/ar-03-live-hf-01/`.
- No lockfile, dependency, API contract, Session/Task lifecycle, MCP tool set, budget, or Gold changed.
- No real Provider requests, external business writes, Diagnosis, Approval, Plan, ActionIntent, Ledger, Handoff, or Receipt were created by this test path.
- `main` and the historical `docs/evidence/ar-03/real-llm-01/` evidence remain untouched.

## Six-question implementation review

1. **User change:** The trusted binding request can carry the user's full goal and produce its answer in one run, avoiding the separate generic investigation that previously consumed budget. Short English phrases and common Chinese callback/retry topics now find the authorized protocol pair.
2. **Agent decision:** In the offline fixture only, the Assistant selected protocol discovery, comparison, and current read-only business queries; this is not evidence of real-model autonomy.
3. **Observation-driven:** With the same user prompt and HTTP 202, current same-Event `QUEUED` versus `PROCESSED` observations produced different, properly scoped answers.
4. **Constraints:** No new authorization restriction was added. Discovery remains limited to existing Session project document IDs; legal in-scope hits pass while out-of-scope document and actor/session reads remain denied.
5. **Simplification:** No new service, runtime, search platform, or additional binding Run was introduced. The existing API entry point and scoped Domain retrieval were reused.
6. **Evidence and stop:** RED, focused GREEN, the final 25-test regression, and deterministic formal Worker/MCP traces are saved. Real Provider, browser, full pytest, and future live acceptance were not run. Stop here and await independent review.

**Requested review status:** `ACCEPTANCE_CANDIDATE`; the implementation agent does not sign a PASS.
