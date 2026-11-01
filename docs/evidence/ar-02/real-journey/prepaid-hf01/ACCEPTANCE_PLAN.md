# AR-02-REAL-JOURNEY-PREPAID-HF01 Acceptance Plan

Status: FROZEN BEFORE RED

## Baseline and scope

- Repository: `wgqa/OpsPilot`
- Branch: `codex/ar02-live-01`
- Base: `8c665912f3f544e208cdeb863c058707f7a99236`
- Scope: close the paid-experiment stop conditions for unknown/invalid Provider Usage and unknown Provider outcomes.
- No real Provider request, browser automation, business write, main change, or Antigravity change is authorized.
- Preserve existing dispatch rows and reservations; do not settle or release unknown cost.
- Preserve the prior AR-02 Gold, traces, failures, and UNKNOWN ledger evidence.

## Frozen acceptance cases

| ID | Setup | Required result |
| --- | --- | --- |
| PHF-01 | A MODEL dispatch receives valid Usage within the frozen limits. | Its reservation settles; the campaign remains open; a distinct subsequent legal dispatch can reserve. |
| PHF-02 | A MODEL dispatch completes without Usage or with malformed Usage. | Dispatch retains its reservation and records UNKNOWN Usage; the campaign is durably closed; new MODEL and MCP keys cannot reserve, including under another Run. |
| PHF-03 | A MODEL Usage result violates the frozen cap. | Existing violation handling closes the campaign; the Assistant must not consume the response or proceed to tools/another model request. |
| PHF-04 | A MODEL provider call has unknown outcome (`mark_unknown`). | Dispatch remains UNKNOWN with its full reservation; campaign closes; same-key replay and a new Run/new logical key are refused after reopening the SQLite database. |
| PHF-05 | An Assistant model response proposes a tool call but its Usage is UNKNOWN or VIOLATION. | No tool handler/MCP call occurs, no normal model answer is committed, the Run is not reported as successful, and no automatic retry occurs. |
| PHF-06 | An existing historical UNKNOWN ledger row is inspected and a later dispatch is attempted. | Historical dispatch and reservation remain byte-for-byte unchanged; the existing durable marker still blocks a new dispatch. |

## Evidence and stop rules

- RED tests must reproduce PHF-02, PHF-04, and PHF-05 against the frozen base before implementation.
- GREEN must rerun those tests and valid-path controls PHF-01/PHF-03.
- Tests use isolated SQLite, deterministic model fixtures, and explicit MockTransport/local MCP only.
- Any Provider network request count above zero is an automatic failure of this task.
- Keep original RED logs and record each command and exit code; do not rewrite earlier evidence.
- Final state is `ACCEPTANCE_CANDIDATE`, pending independent review.
