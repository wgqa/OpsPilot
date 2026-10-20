# HF-01 failure history

Failures are append-only and retained as originally observed. Historical M3-01 evaluation failures remain in `../m3-01/FAILURES.md` and are not modified.

## HF-C02 RED-01: test runner temp-directory permission failure

- Run: `runs/revoke-race-01/`
- Command: `python -m pytest tests/test_d5_context.py::test_hf01_c02_revocation_after_attempt_reservation_blocks_provider_outbound -vv`
- Exit: 1 before test setup.
- Observed: pytest could not scan the shared Windows `TEMP\pytest-of-tu me manques` directory (`PermissionError: [WinError 5]`). This was an environment/setup failure, not evidence about the code.
- Follow-up: reran with an explicit isolated `--basetemp` in `runs/revoke-race-02/`.

## HF-C02 RED-02: stale Memory crossed the Provider boundary

- Run: `runs/revoke-race-02/`
- Command: see `command.txt`; deterministic pytest Provider, real local HTTP 401 Probe, current Task Run and actual Domain attempt reservation.
- Exit: 1; one assertion failed after the Provider capture.
- Synchronization: wrapper called the real `reserve_attempt`, then revoked the selected Memory in Domain before `ChatOpenAI.ainvoke` was entered. No timing sleep was used.
- Observed: revocation committed (`state=REVOKED`), but the captured actual Provider messages still contained the revoked Memory ID. The prompt was therefore sent after revocation with stale context.
- Classification: confirmed HF-C02 safety violation. This is a real post-reservation/pre-Provider race. Minimal implementation repair is authorized by the task card; no frozen Gold or strategy changes are needed.

## HF-C02 GREEN-01: test accounting assertion corrected

- Run: `runs/focused-03/`
- Exit: 1; 29 passed and 1 failed.
- Failure was in a new test assertion that assumed the full Investigator graph would issue exactly two model attempts. The actual run used the normal bounded investigation path: one reserved context invalidated before Provider I/O, followed by seven distinct post-revocation model requests while continuing the real evidence workflow (eight total model reservations, within the existing limit). The security assertions had already confirmed every captured Provider payload excluded the revoked Memory, the invalidated call had no model trace, and each request had a distinct call ID.
- Follow-up: changed only the test accounting assertion to verify the frozen invariant (invalidated call is not a Provider trace; each actual Provider capture maps to a unique reserved attempt) without assuming a fixed graph call count. No budget, tool, or strategy behavior changed. Rerun is `runs/revoke-race-05/` and the full targeted rerun follows.
