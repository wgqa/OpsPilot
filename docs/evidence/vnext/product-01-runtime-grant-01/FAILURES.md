# Failures and limits

## During this slice

- Initial pytest startup used the default C: temporary directory and failed with Windows access-denied setup errors. Subsequent test runs used an isolated `_test-temp/` directory on the D: worktree; no production code change was made for this environment issue.
- The first formal API/Worker mock test asserted that an experiment table existed but was empty. The ordinary Runtime path intentionally does not initialize the experiment ledger. The assertion was corrected to verify that those experiment tables were absent.
- The first compression fixture used a 1,400-token context budget, lower than the existing required system/tool context. It correctly failed before sending. The fixture was changed to exercise a long history under the existing 12,000-token application limit; the production limit was not raised.

All resulting targeted and applicable regression runs pass. These initial failures are retained here as development evidence; they are not counted as passing attempts.

## Not run / unresolved

- Real DeepSeek request, live price verification, and supplier invoice reconciliation: `NOT_RUN` (not authorized in this task).
- Browser journey: `NOT_RUN` (not authorized).
- Full repository pytest suite: `NOT_RUN`; the reported 70 tests are the targeted Runtime Grant and applicable Assistant/Worker/Context regression set only.
- Runtime Grant covers the formal `ASSISTANT_V1` provider path only. The older Chat/Investigator provider path is deliberately outside this pool.
- Token cost preflight relies on the existing pinned local estimator. The runtime reserves the configured maximum and pauses on Usage overrun; it cannot guarantee an absolute upper bound on a provider's billing behavior without live protocol and price validation.
