# AR-05 Integrated Acceptance Prep Report

**Status:** `ACCEPTANCE_CANDIDATE`

**Merge recommendation:** `HOLD`

**Base under test:** `e011e7cbbbef3bbd28210120d4165169cf761183`

**Remote main at final read:** `60eee87bfe3cca522011316cb4cd2c0064ad291b`

**Remote integrated candidate at final read:** `e011e7cbbbef3bbd28210120d4165169cf761183`

This is offline integration evidence. It does not authorize or perform a main merge, browser run, real Provider call, or external business write.

## Outcome

- The historical `TestClient.wait_shutdown` stall did **not** recur. Its target passed alone and in the one full-suite run; the full pytest process reached the final test and exited normally after 16m49s. The test now waits for dispatch completion and Worker idle before closing TestClient. No production shutdown semantics were changed.
- The AR-03 Runner failure was reproduced only when pytest's basetemp was outside Git. The old test supplied a temporary `ROOT` without a Git checkout, so it failed at `rev-parse HEAD` before testing wrong-branch rejection. Initializing a real temporary repository in the fixture produced a stable RED/GREEN and keeps the production Git preflight intact.
- The new same-Session S1 and S2 deterministic journeys remain green in targeted regression: 71/71 and 22/22 respectively.
- The single complete pytest run is **not green**: 701 passed, 40 failed out of 741, exit code 1. Failures and evidence limits are itemized in `FAILURES.md` and the original run is `logs/full-pytest.txt`.
- Frontend typecheck/build and pure Node tests passed. ESLint retained two existing errors in an untouched E2E file.
- Browser, paid Provider, external writes, and main merge were not run.

## Findings by work package

### A1 — shutdown

Historical R1 evidence describes a test-lifecycle race: the TestClient context closed after the business Run became terminal but while dispatch/MCP cleanup was still returning, causing lifespan shutdown to wait. Current target code waits for dispatch completion and Worker idle before leaving TestClient. The current target passed alone (1/1, 5.65s) and in the full sequence; the full run exited normally. This establishes that the requested reproduction does not currently hang. It does **not** prove all shutdown races are absent; no new stuck state existed from which to capture a thread dump, and production Worker code was not changed.

### A2 — Runner Git preflight

The original fixture mocked `_git` to force an unapproved branch but did not create a real Git repository at the Runner's temporary root. With basetemp outside the worktree, `git rev-parse HEAD` failed first (`GIT_PREFLIGHT_FAILED:rev-parse HEAD`). The smallest correction creates and commits a fixture repository and switches it to `codex/unapproved-branch`; the real preflight then rejects it with `MATERIAL_LIVE_BRANCH_MISMATCH`. Only `tests/test_ar03_material_live_exec_prep.py` changed. Before/after logs are preserved.

### B — frozen local business journeys

- **J-S1:** Existing formal API/Worker/Investigator/MCP/Domain path remains green in the 71-test group. The trace evidence links the original Assistant Session message to the confirmed S1 Task and Run, fresh evidence, READY/Plan, independent approval, approval-time revalidation/reapproval, CAS, same-identity local HTTP 200, VerificationReceipt, frozen report, independent DELIVER, and same-session `DELIVERED` outcome. Negative paths remain in the targeted group. See `TRACE_INDEX.md` and `logs/s1-offline-regression.txt`.
- **J-S2:** Existing formal API/Worker/Investigator/MCP/Domain path remains green in the 22-test group. It verifies a current same-request 403/Authz DENY, DiagnosisReceipt and frozen draft, explicit submit, one local Queue/Receipt/Outbox, replay, and same-session `SCOPE_ESCALATED / PENDING_REVIEW`. Scope/Policy/Grant remain unchanged. See `TRACE_INDEX.md` and `logs/s2-offline-regression.txt`.
- These are deterministic-model and isolated local-HTTP results, not real LLM or browser acceptance.

### C — integration/release difference

Remote `main` remains the ancestor at `60eee87`; the candidate remains `e011e7c`. The 14-commit/208-path Diff classification is in `MERGE_READINESS.md`. AR-05 S1/S2 code is distinct from the AR-04C experiment's execution-head-bound one-shot authorization and its historical `PARTIAL` result. No history or Gold was edited. A local scan found no likely real API key assignment and no tracked `.env`, SQLite, DB, or checkpoint file; AR-04C Provider traces remain present as historical evidence and must retain their truthful `PARTIAL` / G7 ON FAIL status.

### D — Web readiness

`WEB_ACCEPTANCE_PREP.md` contains separate future browser scripts and expected Domain snapshots for SUPPORT → APPROVER → S1 `DELIVERED`, and SUPPORT → S2 explicit handoff → refresh-stable receipt. It explicitly remains `BROWSER_NOT_RUN` under the existing STOP. API/tests are not represented as browser evidence.

## Full regression interpretation

The 40 failures fall into four groups:

1. **12 AR-04C cases:** paid execution/claim tests are bound to their frozen execution HEAD and claim. This integration candidate is a different branch/SHA and the formal authorization guard refuses it. Tests that expect the shared parent `.runtime/ar04c-real-journey-01/claim.json` to be absent observe that path as present. This run did not create, inspect, consume, or modify that artifact. The correct resolution is an isolated test runtime/authorized original identity, not weakening the one-shot guard.
2. **24 D4 recovery cases:** legacy `_ready()` fixtures create READY + Approval and immediately call the action API/Graph, but do not create the current trusted revalidation receipt and executor/Run/loopback context. The current gate rejects at `REVALIDATION_REQUIRED` or the revalidation node. These results do not establish that crash/replay after a valid current revalidation works. That important coverage gap remains.
3. **3 M1/M4 cases:** same missing current-revalidation fixture precondition; the failure occurs before the behavior those cases intend to test.
4. **1 historical C1 RED:** the test still requires retired `READONLY_FOLLOWUP`. Current `FOLLOW_UP + readonly_action=INVESTIGATE` positive cases pass. No obsolete production branch was restored.

The AR-04C and retired-C1 failures are scoped to separate experimental/historical contracts. The D4/M1/M4 failures are not proven production regressions, but they leave current-contract action replay/recovery insufficiently verified. That is why this report recommends `HOLD`, despite the new S1/S2 journey groups passing.

## Validation commands and side effects

Commands, environment, and machine-readable totals are in `RUN_METADATA.json` and `RESULTS.json`; per-command stdout/stderr is in `logs/`.

- Full pytest: one controlled run only, external unique basetemp, `faulthandler_timeout=180`, provider env explicitly disabled; 741 collected, 701 passed, 40 failed, exit 1.
- Targeted regression: S1 71/71; S2 22/22; AR-03 runner/recovery 13/13; shutdown target 1/1.
- Frontend: typecheck PASS; production build PASS; Node unit tests 27 passed / 1 skipped; ESLint 2 existing errors.
- Real Provider HTTP: 0. Production/external business writes: 0. Browser automation: not run. Main merge: not run.

## Six-dimension review

1. **User change:** Offline evidence still demonstrates a same-session path from an Assistant report into a trusted S1 repair journey and S2 handoff; no claim of live LLM/browser delivery.
2. **Agent decisions:** This run uses deterministic model fixtures; model autonomy was not evaluated. In production, legacy S1/S2 Investigator remains the executing core.
3. **Observation response:** Local same-identity HTTP 401→200 and same-request 403/Authz DENY paths remain covered. These are isolated Demo observations, not production facts.
4. **Constraints:** No authorization, evidence-currentness, Approval, TaskControl, ActionIntent, ledger, or handoff rule was relaxed. The sole code change corrects a test's Git fixture.
5. **Simplification:** Reuses the existing S1/D3 and S2/M2-03 implementations; no Runtime, state machine, or service was added.
6. **Evidence/stop:** Current remote SHAs, RED/GREEN, full-run exit status, journey tests, browser STOP, and no-paid/no-write facts are recorded. Full-suite D4 recovery coverage remains unresolved; the implementation agent does not self-approve.

## Recommendation

`HOLD` for main merge pending main-agent review of the 40 failures, especially a bounded update/replay of the D4/M1/M4 tests using valid current revalidation evidence. Do not change production gates to make legacy setup green. Browser STOP remains a separate future prerequisite, not an offline regression finding.
