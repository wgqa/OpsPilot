# AR-05-RELEASE-REGRESSION-BOUNDARY-01

Status: `ACCEPTANCE_CANDIDATE` for independent review. No product source changes were needed; this is an evidence-only candidate.

## Finding

The release boundary is now explicit. The 12 AR-04C failures in the prior full-suite log are experiment-identity or post-execution precondition failures, not current-contract regressions demonstrated on this candidate. The real AR-04C one-shot remains consumed and unchanged. The retired C1 `READONLY_FOLLOWUP` RED remains a historical RED; the current `FOLLOW_UP + readonly_action=INVESTIGATE` path has passing positive coverage.

One controlled current-contract full pytest run was executed from an isolated clone. It collected 751 tests: 733 selected, 732 passed, 1 failed, and 18 were explicitly deselected. The sole failure was the static RESUME-02 historical-claim check resolving its private `.runtime` path differently in the clone. The exact test passed `1/1` when run from the canonical candidate worktree layout. The full run itself remains exit 1 and is not reported as a full-suite PASS.

## Current evidence and limits

- See `SCOPE_MATRIX.md` for the 12-test per-group disposition, 18 exclusions, frozen source identities, and the current C1 contract boundary.
- `pytest-current-contract-regression.txt` is the raw controlled full-run log.
- `resume02-static-history-check.txt` is the supplementary exact-test run from the canonical candidate worktree.
- `pytest-collect-only.txt` and `pytest-current-contract-regression-command.txt` preserve collection and selection details.
- The current positive C1 tests, including same-Task routing and actual local MCP read-only investigation, passed in the controlled run.
- The original historical C1 trace remains 13 lines with SHA-256 `a8c7f6afb65630b4e082682cfa3012b015927c02c7b2e6653c6756394acef2e7`; the controlled suite's append occurred only in the disposable clone and was not copied over it.
- Real Provider HTTP requests: 0. Browser automation: 0. Production business writes: 0. Historical claims modified: 0.
- No merge to `main` was performed.

## Six-dimension closeout

1. **User outcome:** this task adds a reliable release-test boundary; it does not claim new product behavior.
2. **Agent decisions:** no model decision logic was changed.
3. **Observation-driven behavior:** the current C1 read-only follow-up positive path passed; the retired intent remains excluded and preserved.
4. **Constraints:** only identity-bound experiment tests and the retired historical RED were excluded; none were counted as passing.
5. **Simplification:** no new runtime, guard, or authorization compatibility branch was added.
6. **Evidence and stop:** raw logs, exact exclusions, claim hashes, and the supplementary canonical-layout result are recorded; paid Provider, browser, and main-merge work remain out of scope.

## Release assessment

This task's requested applicability review is complete for independent review, with one clearly bounded test-harness layout failure and a passing canonical-layout rerun. It is not an all-green full-suite result, not a `main` merge recommendation, and not a substitute for the owning reviewer’s release decision. The historical AR-04C one-shot and C1 RED remain unchanged.
