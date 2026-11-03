# Failures and preserved history

| Log | Result | Cause / disposition |
|---|---:|---|
| `runs/red-01-initial-contract.log` | 4 failed | Initial command used the machine Python 3.14 environment without the project `langchain` dependency. Environment/setup issue; rerun under the repository `.venv`. |
| `runs/red-02-project-venv.log` | 3 failed, 1 passed | Effective RED: new experiment ID rejected; new ID fell back to 8/6 Run limits; Task budget configuration was absent. The Provider fail-closed case passed. |
| `runs/green-01-initial-implementation.log` | 5 passed, 7 failed | First implementation exposed test/setup mismatches: untouched new Tasks are initialized as `CONTUX_S3_V1` 24/18, and frozen MAT-05 has no `input` field. Updated only the isolated policy acceptance and used MAT-04's frozen input for MAT-05; Gold unchanged. |
| `runs/green-02-after-policy-input-fix.log` | 11 passed, 1 failed | Test called the two-argument `execution_budget_snapshot` with three arguments. Corrected the test to call `investigation_budget_snapshot` for the Run projection. |
| `runs/green-03-focused.log` | 13 passed, 1 failed | A second fresh temp DB lacked trusted Demo identities, so API login returned `TRUSTED_IDENTITY_REQUIRED`. Reused existing `reset_fixture()` before experiment-ledger initialization; isolated test DB only. |
| `runs/green-04-shared-budget.log` | 1 passed | The direct shared Provider and fee ceiling test passed after fixture correction. |
| `runs/green-05-focused.log` | 14 passed | Focused GREEN before the active-time reservation assertion was added. |
| `runs/green-06-deadline-gate.log` | 1 passed | New active-time expiry test confirmed a would-be unbounded MCP Attempt is refused before insert. |
| `runs/green-07-focused-final.log` | 14 passed | Focused suite before the matching Campaign-row guard and schema-compatible sentinel finalization. |
| `runs/green-08-focused-final.log` | 15 passed | Focused suite after policy-scope and `NOT NULL`-compatible sentinel checks. |
| `runs/green-09-focused-with-http-trace.log` | 15 passed | Final focused suite after adding captured sanitized HTTPX MockTransport request summaries. |
| `runs/regression-03-final-scope.log` | 125 passed | Final combined targeted MAT, protocol authorization, campaign recovery, S3/D2 and S2 regressions. |
| `runs/regression-04-unbound-receiver-negative.log` | 3 passed | Explicit negative evidence: user text cannot authorize order reads, an unexposed model-proposed order tool is rejected without an Observation, and unavailable Receiver facts remain UNKNOWN. |

The trace-export attempt initially selected nonexistent `d2_evidence.result_json`; actual schema stores Evidence facts in `facts_json`. No product test failed. The read-only exporter was corrected and generated `TRACE.jsonl` from actual pytest SQLite records. The original command error is preserved in `runs/trace-export-01-schema-mismatch.log`.

Historical RESUME-01/02 claims, UNKNOWN dispatches, USD 0.645600 reserves, source traces, databases, frozen MAT Gold and prior failures were not modified. Full repository pytest was not rerun. No live Provider request, browser automation, paid claim, business write or `main` change occurred.
