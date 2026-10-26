# M4-CONT-UX-01 Stage B — Intermediate Implementation Report

Status: `INTERMEDIATE_IMPLEMENTATION`
Browser acceptance: `NOT_RUN / BLOCKED_BY_TOOL_ENVIRONMENT`
Stage B acceptance candidate: **not submitted**. This report is not a Main Agent verdict.

## Handoff facts

- Repository: `wgqa/OpsPilot` (`origin=https://github.com/wgqa/OpsPilot.git`).
- Frozen remote-main base: `0453d6c75fbe244ad7a4e401cf2b07066a2979f5`.
- Frozen plan: `5a33f3e`; RED tests: `3549b18`; preserved RED logs: `d2f1c09`.
- Implementation commit: `da7d3255ec8359b7745302987d3215d5ac678b65`.
- This implementation was made in the existing isolated integration worktree. The user's primary checkout and its uncommitted files were not updated.
- Applicable rule reads are recorded in `BASELINE.json`: North Star blob `1f737712c7a36ceb34433ac09c3fbba3c3305542`, AGENTS blob `32c45506cceeaa8c76a5c56bf8360ff476b58856`, project Skill blob `d405c8d413d633824b279202cc1503dab4cf0b03`. The Skill was read and its entry checklist applied; North Star §8 remains authoritative.

## What changed

The Vue workbench now derives question-anchored conversation threads from persisted user Message IDs. `frontend/src/conversation.ts` joins Chat answers, initial/C1 investigation answers, run status, correction assessments, and the active stream only through exact source IDs and matching Task IDs. Missing links remain explicitly unassociated; equal message text is never used for association or deduplication. Existing type-batched result sections and nearest-prior-user inference were removed from the main conversation.

The existing message-read endpoint adds read-only Chat association fields. Model answers are linked through the persisted Chat answer, Run, successful Attempt, exact source Message, and its source digest. Program limit notices are linked through the persisted `budget-notice:<run_id>` command and `chat_message_sources`; they are labeled `PROGRAM_LIMIT`, not model success. Current S3 authorization redacts the protected answer body and all association fields together.

No new Domain state, Timeline table, Gate, budget rule, write permission, or business Runtime was introduced. Legal same-binding cross-Event history behavior is untouched. No real Provider was called.

## Evidence summary

Fresh final focused run (`runs/final-01/`):

- FastAPI/SQLite association and revocation cases: **2 passed**.
- Pure conversation projection: **4 passed**.
- `npm run build` (includes `vue-tsc --noEmit`): passed.
- ESLint on the three changed frontend source files: passed.

Fresh safety regression: **149 passed** across M1 API/chat, M2 facts/S2, M4-03 HF/S3, C1 follow-up, C1-HF, Stage A, VS01 and EG01-HF-01. Fresh full pytest: **401 passed, 1 deselected**. The deselected case is the preserved historical C1 test using the retired `READONLY_FOLLOWUP` intent; a separate fresh run still fails with `INVALID_MODEL_CLASSIFICATION` as expected under the current `FOLLOW_UP + INVESTIGATE` contract. See `FAILURES.md` and raw logs.

`TRACE.jsonl` records actual IDs and persisted rows from the final deterministic API tests. This is TestClient/SQLite evidence, not browser, Provider, or user-journey evidence. No Stage B browser action was attempted. Under the explicit tool-environment stop instruction, DOM/screenshot, browser refresh, and browser SSE replay remain unverified.

## Scope and remaining limits

- Verified: exact persisted source association for Chat and durable program limit results; no nearest-message inference; same-text independent messages remain separate; linked correction and new Run projection; route sidecar suppression; failed Run visibility; replayed stable IDs/chunks deduplicate in the pure projection; S3 answer association is redacted after current Scope revocation.
- Not verified: real browser DOM/screenshots, browser refresh and live SSE reconnection; the full user-visible four-turn S3 journey; a real Provider response; current browser-side cached content after a live revocation.
- Browser evidence remains `NOT_RUN / BLOCKED_BY_TOOL_ENVIRONMENT`. Non-browser test success does not substitute for those checks. Stop here for Main Agent review; do not call Stage B accepted and do not start J1–J4 or M5.

## North Star §8 handoff summary

1. **User change:** answers and progress can now be projected beneath the exact persisted question in deterministic UI logic; browser usability is still unverified.
2. **Agent decision:** this UI projection adds no new model autonomy and does not reinterpret any Agent decision.
3. **Observation-driven:** each projected result depends on its own persisted source Message/Run/Task; no Event or business fact is inferred by UI order.
4. **New constraints:** no new business restriction. Exact source IDs prevent misattribution; positive Chat/limit associations and revoked-S3 redaction were both tested.
5. **Simplification:** type-batched cards and nearest-prior-message source guessing were replaced by one pure projection module; Domain status and authorization remain server-owned.
6. **Evidence and stop line:** RED/GREEN, frontend build/lint, 149 targeted regressions, and 401 full pytest passes are recorded. Browser verification is blocked and explicitly not run. This is an intermediate implementation handoff only.
