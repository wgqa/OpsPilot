# Failures and setup findings

Historical AR-02 failures and Gold were not edited. The following records are only for this preparation slice.

| Attempt | Evidence | Result | Classification / disposition |
|---|---|---|---|
| First pytest launch used `.venv` inside the worktree | `runs/pre-test-setup-error.txt` | Python executable path did not exist; pytest did not start and no test exit code was produced | Test setup error. Corrected to the shared D-drive venv; the failed launch is retained and is not counted as a test result. |
| Valid frozen-prep RED before implementation | `runs/red-offline-preflight-valid.log` | 3 failed, 1 passed, exit 1. `AR-03-REAL-LLM-01` was rejected by the current Python allowlist; formal `create_app()` rejected the ID; stale-schema check received the earlier scope error rather than schema error. | Expected missing experiment-ID/schema wiring. The ID was then added only to the existing allowlist and CHECK constraint. |
| Initial paired deterministic run used independently randomized Event IDs | `TRACE-random-id-first-run.jsonl`; `runs/paired-receiver-regression.log` | Both isolated cases passed and each Delivery/Receiver relation was internally correct, but the two cross-case Event IDs differed. | Comparison-fixture fidelity issue, not a product failure. The existing test now fixes the same Event and Transport Request IDs during fixture setup only; final paired rerun passes and uses a single Event ID. The initial trace is retained. |

After the allowlist/schema correction, the four preparation tests passed. The final relevant regression commands and exact exits are in `RESULTS.json`; all selected final commands passed. No Provider call was sent, so there is no real-model failure or paid result to report.

The remaining live-execution gates are procedural/time-sensitive, not repaired here: current remote `main` could not be re-read after the push, and current official model price must be rechecked before a separate live authorization. The isolated candidate branch push itself succeeded.
