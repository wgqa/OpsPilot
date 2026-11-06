# AR-05-S1-D3-CLOSE-HF01 — Implementation Candidate

**Status: `ACCEPTANCE_CANDIDATE` — independent review required.**

## Result

The focused D3 and TaskControl/Worker recovery regressions pass. When the original Evidence has expired, D3 now accepts newly acquired, currently valid facts only if they still match the approved Plan and its exact service, integration, principal, route, versions, credential references, and 401 auth-rejection scope. The original approval remains in force in this case. A changed configuration creates a replacement Plan and requires separate approval; deterministic BLOCKED results cancel the old authorization and revoke any AVAILABLE permissions. A transient UNKNOWN read remains recoverable and cannot create a Repair Intent until a valid fresh recheck succeeds.

## Exact changes

- `opspilot/domain/d3.py`: compare newly acquired facts against the immutable approved Plan without requiring the old Evidence to remain current; revoke AVAILABLE permissions atomically when a Plan is cancelled or superseded, and cancel/revoke on deterministic BLOCKED revalidation.
- `opspilot/investigator.py` and `opspilot/web/worker.py`: propagate revalidation source UNKNOWN through the existing bounded Worker recovery path instead of finishing the approval Run in a state that cannot be resumed.
- `tests/test_d3_actions.py`: cover same-fact TTL renewal, changed-fact blocking, UNKNOWN then recovery, cancellation, and stale intent replay.
- `tests/test_m1_web_approval.py`: cover changed-Plan reapproval and recovery of a real approval-resume Run after one transient source failure.

No frozen Gold, main branch, old evidence, paid claim, browser state, or historical ledger was changed.

## Verification

| Check | Result |
|---|---:|
| Frozen RED before implementation | 4 failed, 1 passed; 5.68 s |
| Focused GREEN | 7 passed; 11.34 s |
| First related regression, before the cancellation/replay case was added | 62 passed; 89.54 s |
| Related D3 / approval / TaskControl / Worker recovery suite | 63 passed; 84.43 s |
| `compileall` for changed Python modules | passed |
| `git diff --cached --check` on source, tests, reports and the Ruff availability note (pytest transcript logs excluded) | passed |
| Full pytest attempt | stopped at 28%; see below |
| Real Provider / browser | not run |
| External business writes | 0 |

The focused test `test_d3_expired_source_evidence_with_same_fresh_facts_reuses_approval` performs one CAS in its isolated demo SQLite database to prove the authorized path. This is test-fixture state only; no external or production write occurred.

The final related suite also includes the existing `test_ar03_new_run_resumes_original_graph_and_completes_domain_closed_loop` and `test_hf04_hf05_hf06_approval_resume_recovers_after_domain_commit` coverage for committed REPAIR recovery and independent DELIVER idempotency.

## Full-suite interruption and unrelated failure

The one authorized full-suite attempt used `pytest -vv -o faulthandler_timeout=180`. At 28%, the test body `test_remainder_mocktransport_formal_worker_observes_same_event_and_serializes_live_contract[QUEUED-OFF]` had passed, but TestClient teardown was blocked in Starlette `TestClient.wait_shutdown` waiting through `anyio.from_thread.run`. The captured worker threads were idle/waiting; the asyncio portal thread remained in its event loop. The process was interrupted after the faulthandler snapshot. This identifies the observed wait location, not its underlying cause; no shutdown fix was made in this D3 slice. Raw run output is in `logs/full-pytest.txt`.

The same full run also marked `test_resume_runner_preflight_rejects_wrong_branch_and_existing_campaign_state` failed. Running it alone reproduced `GIT_PREFLIGHT_FAILED:rev-parse HEAD` before the intended wrong-branch assertion because the test points the Runner root at a non-Git temporary directory. It is outside this task's changed files and remains unmodified. The run is incomplete and must not be described as a full-suite pass.

`ruff` was not available in the environment (`ruff` command not recognized); this was not treated as a test pass. Python compilation and whitespace checks on code/report files passed. Raw pytest transcript logs are preserved as emitted and contain captured blank/trailing whitespace, so they were excluded from the whitespace check.

### Commands

Frozen RED before the source changes:

```powershell
python -m pytest --basetemp D:\tmp\ops-pilot-ar05-s1-d3-close-hf01-red -q `
  tests/test_d3_actions.py::test_d3_expired_source_evidence_with_same_fresh_facts_reuses_approval `
  tests/test_d3_actions.py::test_d3_revalidation_blocks_changed_current_fact_without_creating_repair `
  tests/test_m1_web_approval.py::test_ar05_approved_plan_fact_change_creates_new_plan_and_requires_new_approval `
  tests/test_d3_actions.py::test_d3_unknown_revalidation_source_cannot_authorize_repair
```

Focused GREEN:

```powershell
python -m pytest --basetemp D:\tmp\ops-pilot-ar05-s1-d3-close-hf01-green -q `
  tests/test_d3_actions.py::test_d3_revalidation_blocks_changed_current_fact_without_creating_repair `
  tests/test_d3_actions.py::test_d3_expired_source_evidence_with_same_fresh_facts_reuses_approval `
  tests/test_d3_actions.py::test_d3_blocked_revalidation_revokes_preexisting_intent_before_replay `
  tests/test_d3_actions.py::test_d3_unknown_revalidation_source_cannot_authorize_repair `
  tests/test_m1_web_approval.py::test_ar05_approved_plan_fact_change_creates_new_plan_and_requires_new_approval `
  tests/test_m1_web_approval.py::test_ar05_transient_revalidation_unknown_keeps_approval_resume_recoverable
```

Related regression:

```powershell
python -m pytest --basetemp D:\tmp\ops-pilot-ar05-s1-d3-close-hf01-related-final -q `
  tests/test_d3_actions.py tests/test_m1_web_approval.py `
  tests/test_m1_task_control.py tests/test_m1_worker_recovery.py
```

The single full-suite attempt and isolated unrelated preflight failure are recorded in `FAILURES.md`; see the raw command output in the referenced logs.

## Side-effect boundary

- Real Provider calls: 0.
- Browser automation: 0.
- External/production business writes: 0.
- Isolated demo DB: deterministic fixture tests include the expected single CAS success path; blocked, UNKNOWN, cancellation, and replay paths assert no additional CAS or ledger action.

## Six-dimension handoff

1. **User task:** An approved S1 repair can continue after TTL expiry when current facts still exactly support the same Plan; the user is not forced into a redundant approval.
2. **Agent decision:** The existing Investigator still decides its workflow; this change only makes the trusted D3 write boundary re-read and compare facts.
3. **Observation-driven behavior:** Fresh same facts allow the existing approval; changed facts require a new Plan/approval; UNKNOWN waits for a recoverable recheck; disabled principal or non-READY Gate does not CAS.
4. **Constraints:** Old Evidence is not re-trusted. Fresh scoped observations are acquired and compared; stale or cancelled authorization cannot be replayed.
5. **Responsibility:** Existing Domain transactions, D3 receipts, approval-resume Run, and bounded Worker recovery are reused.
6. **Evidence / stop line:** 63 related tests pass. Full pytest remains incomplete due to a shutdown wait at 28% and one unrelated preflight test failure; no paid or browser work was run. This is a candidate for independent review, not a self-signed PASS.
