# Failures and limits

## Resolved during implementation

- Initial RED: the formal Assistant did not expose the controlled-investigation proposal tool. The end-to-end test failed at the expected tool-availability assertion. The existing Assistant MCP server now exposes the advisory tool only to unbound SUPPORT chat runs; the final formal-path test passes.
- An early S1 projection attempt rejected a completed read-only Assistant run because the helper required an active run. The read path now validates the persisted run with `active=False`; the S1 projection and final regressions pass.
- An early cross-tenant test left the shared TestClient authenticated as the second actor. The test now restores the SUPPORT identity before checking the original session. This was a test setup issue, not a permission change.

## Final observed results

- Final focused journey run: 2 passed, 0 failed (`focused-journeys.log`).
- Relevant Python regression: 41 passed, 0 failed (`python-regression.log`).
- Frontend suite with the persisted S1 trace supplied: 23 passed, 0 failed, 0 skipped (`frontend-tests-with-s1-trace.log`).
- Typecheck/build and changed-file ESLint passed.
- No full repository pytest run was performed.

## Not run by authorization

- Real Provider: 0 requests; deterministic models were used for the offline journeys.
- Browser automation: not run; the historical Browser STOP remains in effect.
- External business writes: 0. The S2 handoff queue, receipt, and outbox were written only in the isolated local Demo SQLite fixture.

No historical Gold, Provider ledger, one-shot claim, or prior experiment trace was modified.
