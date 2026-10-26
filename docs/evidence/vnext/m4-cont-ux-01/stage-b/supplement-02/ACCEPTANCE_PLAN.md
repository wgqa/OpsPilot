# Stage B Supplement 02 — Same-Task Read Response Ordering

Status: `FROZEN_BEFORE_RED`; targeted follow-up to Stage B, with no Gold changes.

## Baseline and authority

- Repository: `wgqa/OpsPilot`; `origin/main` and worktree HEAD: `4c891cbd5e28c8b43391ac99ca886f8c8af2ef44`.
- North Star blob: `1f737712c7a36ceb34433ac09c3fbba3c3305542`; AGENTS blob: `32c45506cceeaa8c76a5c56bf8360ff476b58856`; project Skill blob: `d405c8d413d633824b279202cc1503dab4cf0b03`.
- Stage B plan blob: `3cba9bb63b42ce5f02042709058ce9dcd496623c`; immutable Gold blob: `1290ef276690f00b6e9683f0251302f376a70098`.
- Prior Stage B supplement plan/report blobs: `c6482d72e8c1f4344abee40c540810966e4f1b94` / `e1c21b107b80094c7a7c9e663183ed13c0aabe51`.
- The only pre-existing untracked paths are historical pytest `basetemp` trees and `frontend/.npm-cache/`; they are preserved and excluded.
- Applicable Stage B and SUP-01 contracts remain in force. Browser/Computer Use and Provider remain `NOT_RUN` under the explicit execution boundary. M2 deferred gates are informational and are not reopened.

## Frozen cases

| ID | Controlled order | Required result |
|---|---|---|
| SUP02-RACE-01 | Same Task Inspector request A starts while authorized and is delayed. Scope is revoked. Later request B returns the existing authorization-unavailable Inspector and clears restricted cache. A returns last. | A is rejected as stale; restricted Inspector fields, source refs, receipts, Evidence, and answer bodies cannot return to Inspector or conversation projection. |
| SUP02-RACE-02 | Session Message request M starts before the revocation response. B reports authorization loss and clears cache. M returns last with the old authorized body. | M is rejected; the cleared conversation remains free of restricted assistant body/source/result content. |
| SUP02-POS-01 | Multiple same-Task refreshes while authorized; latest response wins. A second Task has its own read sequence. | Current authorized Task results are accepted; a stale same-Task response cannot overwrite newer data; another Task's messages/results remain intact. |
| SUP02-POS-02 | A Task is denied, then a fresh Inspector read after authorization recovery is started and accepted. | Denial does not permanently block the newly authorized Inspector or a subsequent fresh Message read. |

## RED/GREEN and evidence boundary

1. Commit this plan and baseline before the controlled-promise RED tests.
2. Add a narrow frontend read-response fence used by the existing App refresh paths; first preserve a failing same-Task ordering run, then implement generation and denial invalidation.
3. Run Node's deterministic frontend tests, frontend typecheck/build and scoped lint. Do not use browser automation, Computer Use, Provider calls, or alter backend/domain authority.
4. Preserve prior 402-pass logs, 20 deep-path environment failures, the historical obsolete-intent C1 RED, and all old Stage B logs unchanged.
5. Stop after the targeted non-browser evidence. Stage B remains pending its separately required permitted real-browser DOM/SSE journey.

## Stop line

Only same-Task Inspector and Session Message response admission/cache protection are in scope. Do not alter S3 history querying, authorization semantics, business Gate, budgets, TaskControl, Gold, or the UI business projection. No adjacent slice, J1–J4, or M5 work.
