# AR-04C-PRELIVE-HF-01 — Candidate report

**Status:** `ACCEPTANCE_CANDIDATE`
**Base / tested source:** `d99843b501df10a4411b44f43d900f7b997e8ab2`
**Branch:** `codex/ar04c-real-journey-01`
**Main at verification:** `60eee87bfe3cca522011316cb4cd2c0064ad291b`

## Result

The formal paid-execution authorization path now has positive and negative offline coverage without using a real authorization or paid claim. The authorization must match the current branch, exact execution HEAD, frozen contract digest, and exact parameters. A claim is created with exclusive file creation and a process-only capability; the formal Assistant HTTPX transport consumes it durably before forwarding a request. A new process cannot replay it. Unknown transport results persist a stop state and cannot trigger a follow-up send.

The test suite uses temporary authorization and claim files under pytest `tmp_path`; the actual AR-04C authorization and claim paths do not exist. The successful MockTransport callback observes the claim already `CONSUMED` and the OFF database identity pinned before it receives the simulated request. A different database for the same condition is rejected. The unknown MockTransport callback is invoked once, leaves the claim `STOPPED`, and a later call is refused.

The AR-04C formal Worker test previously stalled while exiting `TestClient`, after its Run had reached a terminal state. The captured stack stops at `TestClient.wait_shutdown`. The R1 closeout documents the same test lifecycle race more fully: Worker shutdown can begin before MCP cleanup and `_dispatch_run()` have returned. The AR-04C test now waits for its final dispatch completion and an empty Worker queue before context exit. The test-only change passed; production Worker behavior remains unchanged.

## Verification

- Pre-fix authorization/claim RED: 4 failing cases against the old source, `pytest-auth-red-03.log`.
- AR-04C formal Worker lifecycle target after the test-only wait: 1/1 passed in 14.04s.
- AR-04C original tests plus pre-live authorization tests, rerun against committed code `d42838cf33a6da78723746fb89ddbd70adde406f`: 17/17 passed in 25.90s.
- Related AR-03 formal Worker/MCP target: 4/4 passed in 13.05s, run earlier in this task before the AR-04C-only test adjustment.
- `Provider HTTP = 0`; external business writes = 0; real paid claim created/consumed = no.
- Full pytest, real DeepSeek, browser, and live MCP were not run.

Raw relevant logs are in [`runs/`](runs/). Earlier setup failures and the first shutdown stall remain preserved. The frozen AR-04C Gold and contracts are unchanged. The generated `runs/offline-formal-pair.json` was restored to its opening version and is not part of this patch.

## Six-question summary

1. **User change:** No new user-facing capability; the change makes paid execution fail closed unless the authorized execution identity is valid, and makes the formal offline Worker test close only after its work has unwound.
2. **Agent decision:** No change to model decisions or tool selection.
3. **Observation-driven:** No business observation changes; this is an authorization and test-lifecycle correction.
4. **New constraints:** The exact authorization/claim and one-process capability prevent replay or unauthorized outbound calls. Positive MockTransport and official Worker tests show the authorized offline path still runs; real Provider remains blocked pending separate authorization.
5. **Simplification:** Existing budget ledger and official Worker are reused; no production Worker shutdown condition, business Gate, or Gold was changed.
6. **Evidence and stop:** 17/17 focused tests pass, plus the AR-03 target passed 4/4. Full pytest and live Provider are not run. Stop here for independent review; no live execution is authorized.

## Remaining limits

MockTransport validates serialization, authorization checks, claim persistence, and ordering, not actual DeepSeek protocol, network, or billed usage. The AR-04C shutdown trace proves the wait location, while the R1 evidence supports the same underlying test teardown race; it does not prove every possible Worker/MCP shutdown order in the full suite. The implementation is a candidate for independent review only and does not authorize LIVE.
