# R1-LIVE-RECOVERY-HF-01

**Status:** `ACCEPTANCE_CANDIDATE`
**Base:** `6d36f06a0c9824764bdadfe390083e685d592231`
**Branch:** `codex/r1-live-recovery-hf01`
**Isolated worktree:** `D:\学习\agent新项目\.worktrees\r1-live-recovery-hf01`
**Main checked at start:** `60eee87bfe3cca522011316cb4cd2c0064ad291b`

## Scope and source baseline

Work was performed only in the isolated worktree above. The project's active Live demo worktree, its database, checkpoint, credentials, Grant, processes, and environment files were not opened or modified.

At Base, the actual Git blobs read for the required project instructions were:

- `PROJECT_NORTH_STAR.md`: `43dabda468506717c6956e676dfad4304c4f38e6`
- `AGENTS.md`: `807b928686a4dd2cac7b15b3c354b9943c93c910`
- `.agents/skills/opspilot-slice-review/SKILL.md`: `d405c8d413d633824b279202cc1503dab4cf0b03`

Also reviewed `docs/baseline/v1.0-implementation-baseline.md`, `docs/baseline/STATE_TRANSITIONS.md`, `docs/baseline/API_CONTRACT.md`, `docs/baseline/ACCESS_MATRIX.md`, the S3/TaskControl implementation, and the applicable M2-02 deferred gates. The controlling contract remains: a pending critical correction blocks business Runs and writes until a trusted Investigator consumes it; `CHAT_READONLY` must not alter TaskControl, Plan, Approval, Intent, or business outcome.

## Root cause confirmed from the RED reproduction

The isolated RED run reproduced the reported sequence:

1. The formal `CORRECT_TASK_INPUT` was durably accepted at message sequence 2. TaskControl advanced to revision 1, set `pending_critical_message_seq=2`, and kept the message `RECEIVED_NOT_APPLIED`.
2. The new formal `INVESTIGATE` Run was stopped before a Legacy Provider request because Legacy Provider authorization was disabled: `LEGACY_PROVIDER_AUTHORIZATION_REQUIRED`.
3. The later same-Task `CHAT_READONLY` Run had current revision 1 and message sequence 3, but failed with `TASK_INPUT_PENDING` before an Assistant call.

There were two independent guards behind the collateral failure. `assistant.domain.state()` called the common TaskControl check, which rejected every Run while a correction was pending. After that check was narrowly allowed for a current read-only chat, `d2.reserve_attempt()` still applied the same blanket pending-correction rejection to the Assistant's MCP calls. The second guard was exposed by the first GREEN attempt and was then fixed as part of the same root cause.

The original RED state is preserved in `RED_TEST_LOG.txt` and `RED_STATE.json`. The initial pytest setup attempt also hit a Windows temp-directory permission error; rerunning with a `--basetemp` under this isolated evidence folder reached the product failure.

## Minimal implementation

- `opspilot/domain/task_control.py`: the pending exception now requires an active, persisted Run in the same tenant and Task, with persisted kind exactly `CHAT_READONLY` and `consumed_message_seq >= pending_critical_message_seq`. Existing TaskControl revision equality, active Task state, and high-water checks still apply. Calls without this explicit condition remain fail closed.
- `opspilot/domain/assistant.py`: only an Assistant Run whose persisted kind is `CHAT_READONLY` asks the shared TaskControl check to use that narrow exception.
- `opspilot/domain/d2.py`: only an active `CHAT_READONLY` Run selected by ASSISTANT_V1 for an MCP attempt receives the same narrow exception. Trusted TaskBinding, scope, source, attempt budget, and D2 checks remain in place.
- `frontend/src/App.vue`: when a formal correction's Investigator Run stops for missing Legacy Provider authorization, the stale “正在提交关键更正” notice is cleared. The error now says the correction remains unapplied, the formal investigation did not run, and the user may continue with same-Task read-only queries limited to the bound order. Other Run failures retain their existing status/reason presentation.

No schema, new state authority, recovery service, or business workflow was added. The formal correction is not consumed, cleared, or converted into trusted Evidence by the read-only exception.

## User journey and safety results

| Check | Result | Evidence |
|---|---|---|
| R1: correction accepted; formal Investigator stops; user continues same-Task read-only chat | PASS | Actual FastAPI/Worker path in isolated SQLite; deterministic FixtureModel only |
| R2: current `async-order-2` facts retrieved | PASS | Two successful MCP calls; both return the same Event ID, Delivery `HTTP 503 / FAILED`, Receiver `NOT_RECEIVED` |
| R3: current facts belong to the new read-only Run | PASS | Current Run's Assistant source validation is current; both Observation rows link to that Run and its D2 attempts |
| R4: correction and TaskControl remain pending and auditable | PASS | Revision 1, pending seq 2, applied seq 0; correction remains `RECEIVED_NOT_APPLIED`; binding remains `WAITING_INPUT` |
| S1: Task ID from another Session | PASS | `SESSION_TASK_LINK_REQUIRED`; no user message or Run created |
| S2: stale Plan/approval or business write eligibility revived | PASS | No Diagnosis, Plan, Approval, ActionIntent, Ledger, Delivery, Handoff queue, or Handoff receipt created |
| S3: formal Investigator uses read-only exception | PASS | Real Worker still blocks it at Legacy Provider authorization; direct guard test confirms even an explicit read-only allowance cannot authorize a persisted `INVESTIGATE` Run |
| S4: other tenant/owner and revoked scope | PASS | Other tenant receives `TASK_SCOPE_DENIED`; existing scope-revocation MCP regressions pass |
| S5: correction retry creates duplicate work | PASS | Replaying the same idempotency key returns the same correction Message and Run; one correction row remains |
| S6: ordinary formal correction-consumption path | PASS | Existing M1 TaskControl and M4 confirmed-correction tests pass in the focused regression run |

The actual fixture answer was: “当前同一 Event … 的 Delivery HTTP 503 / FAILED；Receiver 为 NOT_RECEIVED。…线上部署版本仍未知。” It did not claim the pending correction had been applied. The fixture deliberately selects the two read-only tools; this verifies the program path, not real-model tool autonomy.

## Verification

- New recovery tests: **3 passed**.
- Focused TaskControl, correction, S3, C1, and D3 regression: **112 passed, 1 failed**. The one failure is the unchanged `tests/test_m1_task_control.py::test_schema_migration_is_idempotent_and_preserves_frozen_plan_hash`, which still asserts schema version 18. The unchanged Base `database.py` already migrates through versions 19 and 20; the assertion mismatch is unrelated to this change and was not edited.
- Ordinary Assistant and Runtime Grant regression: **59 passed**.
- `git diff --check`: passed.
- Python compile check for the changed Domain modules and test: passed.
- Frontend typecheck: not verified. `npm run typecheck` could not find `vue-tsc`; `npm ci --offline` could not complete because the lockfile package `yocto-queue@0.1.0` was not cached. No online install was attempted.
- Full repository pytest: not run.
- Real Provider requests: **0**. Browser automation: **0**. External business writes: **0**.

Commands and complete logs are in `RED_TEST_LOG.txt` and `FINAL_TEST_LOG.txt`. Generated local pytest databases remain under this evidence directory and are excluded by its `.gitignore`; only compact `RED_STATE.json` and `GREEN_STATE.json` are published as state evidence.

## Six-dimension review and limits

1. **User change:** after a formal correction run is blocked, the user can continue a same-Task read-only investigation instead of losing access to the bound order.
2. **Agent choice:** no tool sequence was added to production; the offline FixtureModel chose the tools for the test.
3. **Observation-driven result:** the response followed current same-Event MCP facts; it did not rely on the blocked Investigator's absent result.
4. **Authorization:** same tenant, owner, Session/Task link, TaskBinding, current revision, and message high-water remain required. Pending correction still blocks formal Runs and business writes.
5. **Minimality:** the exception reuses the existing TaskControl check at both Assistant state and D2 attempt reservation; no new system was introduced.
6. **Evidence and stop line:** deterministic offline evidence only. Real DeepSeek behavior, browser presentation, and frontend typecheck remain unverified. No paid or external operation was attempted.

The isolated candidate is ready for independent review, not a self-signed PASS. The separate Live demo remains untouched.
