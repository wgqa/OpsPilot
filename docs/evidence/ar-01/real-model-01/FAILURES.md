# Failure history — append-only release record

All numbered raw logs retained. No historical AR-01/Stage B Gold, RED or reports
were rewritten. Failures below concern free local preparation, not paid DeepSeek.

| Log | Observed result | Classification / action |
|---|---|---|
| 01-red | pytest collection error, missing provider_budget module; exit 2 | Frozen preimplementation capability absence, not a business vulnerability reproduction. |
| 02-green-budget | 1 passed / 10 setup errors; exit 1 | Test preparation: pytest basetemp parent `.tmp` absent. Created only our own parent; no user folders removed. |
| 03-local-protocol-attempt | 12 passed / 8 failed; exit 1 | Adapter implementation: Pydantic copied runtime dict, hook saw no reservation/expected schema; refused before HTTP. |
| 04-wire-inspection | 1 failed / 19 deselected; exit 1 | Actual pre-send JSON valid; runtime reservation null. Fixed shared runtime identity, not the model settings or safety expectation. |
| 05-local-protocol-attempt | 19 passed / 1 failed; exit 1 | B framework tool_choice=None rejected; no B Provider send. Explicit mapping of unspecified framework policy to frozen auto. |
| 06-b-binding | 1 failed / 19 deselected; exit 1 | Captured actual create_agent binding, confirming None sentinel. Original failure retained. |
| 07-local-protocol-green | 19 passed / 1 failed; exit 1 | Stub preparation: B tool messages have no wire name; fake model lost completed Skill action, hit Run MODEL cap. Restore name using prior tool_call_id, preserving actual protocol and Gold. No A/B Prompt tuning. |
| 08-local-protocol-green | 20 passed; exit 0 | All then-current local cases pass. |
| 09-additional-green | 7 passed / 20 deselected; exit 0 | OS exit, cancellation, timeout, protocol batch stop, authorization and redaction checks. |
| 10-all-experiment-tests | 47 passed; exit 0 | Original 20 + then-current 27; fresh run, not inherited results. |
| 11-safety-regression | 72 passed; exit 0 | Fresh S1/S2/S3/approval/HF/TTL safety subset; full pytest NOT_RUN. |
| 12-offline-preflight | exit 0, ready=false, requests=0 | Expected money/authorization blocker, not a successful paid run. |
| 13-exact-cap | 1 passed / 27 deselected; exit 0 | Exact request 81 refused, settled+next reservation cap checked. |
| 14-release-all-tests | 48 passed; exit 0 | Full isolated experiment test directory re-run at implementation commit 47e2bd4, including the exact-cap addition. |

Protocol-negative tests deliberately preserve 400, response loss, invalid/missing
Usage, missing fingerprint, output above 512 and fingerprint drift. These are
test-controlled local responses. No real vendor incompatibility has been
dynamically established, and no hidden retry is allowed. UNKNOWN keeps its full
reservation after reopening; known Usage with a protocol fault retains settled
charge and a sticky halt. No repeated success-only paid samples were collected.

The older meter's output-limit finding is inherited source/history evidence only;
this release neither hides nor re-runs that paid failure. It motivates conservative
preflight. USD 0.50 is not spending approval, and the conservative bound currently
prevents paid dispatch. P1/P2 remain NOT_RUN; Stage B HOLD/browser STOP unchanged.
