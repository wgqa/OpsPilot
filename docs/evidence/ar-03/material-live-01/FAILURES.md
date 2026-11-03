# AR-03-MATERIAL-LIVE-01 failures and repair history

No real Provider request has been sent at the time this file was prepared. Historical experiment failures are not edited.

| Run | Result | Classification | Resolution / disposition |
|---|---|---|---|
| `runs/red-01-budget-scope.log` | 4 expected failures | Frozen pre-implementation RED | Proved the new experiment ID, per-Run 16/10 scope, and Skill OFF/ON control were not implemented. Kept byte-for-byte. |
| `runs/green-01-budget-skill.log` | 4 passed | Offline green | Earlier focused implementation check. |
| `runs/green-02-formal-worker-budget.log` | 5 passed | Offline green | Formal API/Worker budget path. |
| `runs/green-03-budget-and-skill-integration.log` | 8 passed | Offline green | Campaign budget and Skill visibility. |
| `runs/green-04-mock-http-worker.log` | 9 passed | Offline green | Serialized request verified through explicit MockTransport. |
| `runs/green-05-final-budget-skill-mock.log` | 9 passed, 1 failed | Test preparation failure | The new test queried nonexistent `s3_task_bindings`; the actual binding table is `s3_task_resources`. The failure remains unchanged; corrected test passed in later runs. |
| `runs/green-06-material-live.log` | 10 passed | Offline green | Corrected binding-table assertion; before the cross-Run campaign-cap assertion was added. |
| `runs/green-07-ar03-material-and-comparison.log` | 53 passed | Offline regression green | AR-03 material/protocol-comparison coverage. |
| `runs/green-08-ar02-ar03-integration.log` | 28 passed | Offline regression green | AR-02 Assistant and integrated Assistant coverage. |
| `runs/green-09-material-live.log` | 10 passed, 1 failed | Test preparation failure | The campaign ledger correctly rejected fabricated Run IDs by foreign key. The test was changed to create two persistent Runs via the formal API; the ledger assertion then passed. |
| `runs/green-10-material-live.log` | 11 passed | Final targeted offline green | Current 11-test suite, including shared MCP cap across two real persisted Runs. |
| `runs/green-11-final-targeted.log` | 11 passed | Final targeted offline green | Fresh rerun after aligning the campaign wall clock with the first Provider dispatch and the Worker wait ceiling with the existing 300-second Task deadline. |
| `runs/green-12-final-targeted.log` | 11 passed | Final targeted offline green | Fresh rerun after adding persisted campaign-cap and price-version checks to the pre-send Runner guard; Python compilation and `git diff --check` also passed. |
| `runs/preflight-01-machine.jsonl` | Blocked before send | Runner preflight assertion defect | The guard compared the new experiment MCP ceiling (10) to the legacy default (12). Fixed to assert new ID = 10 and legacy constant = 12 separately. Provider requests and campaign DB initialization remained zero. |
| `runs/preflight-02-machine.jsonl` | Process exit 0, invalid preflight payload | Runner reporting defect | The preflight JSON incorrectly labeled the experiment MCP allowance as 12 by shadowing the new experiment cap with the legacy constant. No Provider request or campaign initialization followed. The output is preserved and will not be treated as READY; the report now emits the scoped cap 10. |
| `runs/preflight-03-machine.jsonl` | `PREFLIGHT_READY`, exit code 0 | Final free preflight | The corrected preflight reports the frozen 16 Provider / 10 MCP campaign caps, 0 requests before execution, no exposed business-write tools, and fresh isolated runtime paths. Remote refs remained unverified. No Provider or MCP request was sent. |

The four `red-01` failures and both later test-preparation failures remain in the evidence directory. They are not counted as current product failures or silently removed. A malformed PowerShell exit-code capture also created a root marker file named `1`; its exact content was verified as an accidental test-log path string and that generated marker alone was removed. No user file was changed.

The raw pytest tracebacks contain whitespace-only lines. `git diff --check` reports those lines inside the preserved raw logs; the source, tests, Runner, and Markdown files are checked separately and are clean. The raw logs were not edited to silence that report.

Live failures, if any, will be appended after the authorized one-shot run. Provider UNKNOWN, timeout, Usage anomaly, authorization/source anomaly, side effect, or budget inconsistency is an immediate campaign stop; no retries or reruns are allowed.

## Authorized live attempt (2026-11-03)

- One invocation of `run_live.py --execute-once` exited 1. The runner had already recorded `EXECUTION_CLAIM.json`; this experiment identity is consumed and must not be rerun.
- The runner's repeated pre-send check was `PREFLIGHT_READY`. It then stopped with `IntegrityError:FOREIGN KEY constraint failed` during `_prepare_fixture`, before any formal Session/Task/Run or Provider/MCP dispatch. See `RESULTS.json`, `TRACE.jsonl`, `BUDGET_LEDGER.json`, and `REPORT.md`.
- Post-stop read-only audit found zero tenant, credential, principal, integration, service, S3 business fact, Session, Task Run, Message, Assistant Run/Call, Evidence, Diagnosis, Handoff, or business action rows in this isolated DB; `PRAGMA foreign_key_check` returned zero violations. The campaign ledger is OPEN with Provider=0, MCP=0, reserved=$0, settled=$0.
- Source path and DB state locate the missing prerequisite: the Runner calls schema-only `initialize()` and then `prepare_s3_fixture()` without first seeding the tenant/credential fixture. The first principal insert references absent `tenant-a`; the run captured the exception type/message but not a Python traceback, so the exact failing statement is inferred from the inspected call order and empty DB, not a captured stack frame.
- The fixture helper's source issues a local loopback receiver POST before inserting the DB rows. The helper did not return, so no fixture Trace was emitted; this local setup call is not a Provider or MCP attempt and is not independently captured in the emitted trace. No external business write occurred.
- All seven Gold cases are `NOT_RUN`; Skill OFF/ON effect is `NOT_RUN`. No answer, model decision, Usage, Provider charge, or business Observation was produced. No retry or fixture replay was attempted.
