# M4-CONT-UX-01 Stage B — Targeted Authorization and Display Supplement

Status: `FROZEN_BEFORE_RED` (supplement to the already-authorized Stage B; no Gold changes).

## Baseline

- Repository: `wgqa/OpsPilot`; remote `origin/main`, current detached integration worktree, and base commit: `ad056c38da1f925fca80b74aef0a88a686ac97e1`.
- Worktree tracked files were clean before this freeze. Pre-existing untracked pytest `basetemp` directories and `frontend/.npm-cache/` remain untouched and excluded.
- Target-commit North Star blob: `1f737712c7a36ceb34433ac09c3fbba3c3305542`; AGENTS blob: `32c45506cceeaa8c76a5c56bf8360ff476b58856`; project Skill blob: `d405c8d413d633824b279202cc1503dab4cf0b03`.
- Existing Stage B contract and immutable Gold remain at `docs/evidence/vnext/m4-cont-ux-01/stage-b/ACCEPTANCE_PLAN.md` and `docs/evidence/vnext/m4-cont-ux-01/GOLD.json`. This supplement adds no journey or business outcome.
- Browser / Computer Use and Provider: `NOT_RUN` by explicit execution boundary. This supplement can only produce deterministic API and projection evidence.

## Frozen cases

| ID | Positive path | Negative path / expected result |
|---|---|---|
| SUP-01A | Create a real S3-bound Task, obtain its diagnosis through existing local HTTP facts and persist an initial user answer; create and persist a completed C1 Follow-up answer; authenticated owner GETs Inspector and receives both answers, source refs, and result details. | None; this is the authorized baseline proving legal same-Task reads continue. |
| SUP-01B | Preserve immutable diagnosis and Follow-up rows, then revoke current route Scope by changing the Scope Policy version/required scope. | Authenticated owner GETs Inspector; both initial and C1 answers, their bodies, source refs, result payloads, and answer-source metadata are absent. Historical audit rows remain unchanged. The GET must not grant or mutate business authority. |
| SUP-02A | Existing loaded UI state receives a sanitized current Inspector after S3 Scope invalidation. | Replace/clear cached S3 answers, Follow-ups, source details, handoff presentation and stale streamed chunks; refresh persisted Message reads so their server-side S3 redaction replaces cached Chat bodies. Earlier SSE entries remain event labels only and must not supply answer payloads. |
| SUP-02B | Existing Inspector refresh is successful for a non-S3 task. | Failure handling must not clear unrelated task/session data. On S3 Inspector refresh rejection, restricted S3 result state is cleared fail-closed and cannot be projected as an unassociated result. |
| SUP-03A | Projection shows an actual FAILED Run with reason, a pending critical-correction assessment, and ordinary user Follow-up under its exact source question. | No duplicate ordinary `FOLLOW_UP` classification card; `FOLLOWUP_ROUTED_TO_INVESTIGATOR` sidecar remains suppressed; a real FAILED Run, `PARTIAL`, and `PROGRAM_LIMIT` retain distinct meanings. |

## RED / GREEN sequence

1. Commit this plan and `BASELINE.json` before adding the focused failing API/projection tests or changing product code.
2. RED: execute the deterministic API test on the frozen implementation, archive complete pytest stdout/stderr/exit status and the exact sanitized before/after API JSON. Do not change expectations after observing RED.
3. Add pure frontend projection tests for SUP-02/SUP-03 and preserve their RED. No browser automation or Provider call is allowed.
4. Apply the smallest Domain read correction and UI cache invalidation needed; keep `answers_in_transaction()` and the existing S3 current authorization semantics authoritative.
5. GREEN: fresh focused API/projection tests, relevant C1/HF/S3/TaskControl and S1/S2 security regressions, frontend typecheck/build/lint, then full pytest. Keep pre-existing untracked workspaces and historic logs untouched.

## Scope and stop line

Only `get_task_inspector()`'s existing trusted read path, `App.vue::refreshInspector()` cache behavior, and pure conversation projection/tests are in scope. Do not add a Gate, weaken cross-Event reads, change message/Run lifecycle, modify budgets, Gold, browser automation, or paid Provider tests. Stop after implementation evidence and direct main push; report the browser journey as still unverified and submit only an implementation candidate for independent Main Agent review.
