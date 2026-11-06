# Failures and limits

## Preserved RED / implementation findings

- `logs/red-missing-revalidation.txt` records the original defect: an approved plan could create and commit a REPAIR without an approval-time fresh read. The test observed `COMMITTED` where the required result was `REJECTED_PRECONDITION`.
- `logs/revalidation-negative-cases.txt` preserves the first new stale-evidence negative run. It exposed a missing `executor_id` argument when persisting the `BLOCKED` receipt for an expired source with no active approval-resume Run. The call was corrected; the final negative suite passes 6/6.
- Earlier compatibility/regression failures are retained in `backend-targeted-regressions.txt` and `backend-safety-regressions-final.txt`. Direct D3 tests now perform the required revalidation step; no production guard was weakened.

## Non-product test/tooling failures

- An initial `pytest` invocation did not put the checkout on `PYTHONPATH`; it failed during import before tests ran.
- The host default pytest temp root on C: was inaccessible. A first explicit D: basetemp attempt also failed because its parent directory did not exist. The final successful runs used unique basetemp directories inside this isolated worktree.
- `node --experimental-strip-types --test ...` could not parse the project's TypeScript parameter-property syntax. The supported local invocation `node --experimental-transform-types --test ...` passed 4 tests with 1 existing trace-dependent test skipped.
- Full `npm run lint` reports two errors in unchanged `frontend/e2e/m4-03-s3-journey.mjs` (`access` unused; `setTimeout` undefined). ESLint passes for all changed frontend files. No unrelated lint changes were made.
- Captured failure logs retain their original output, including whitespace on source-context lines. They were not normalized because they are evidence artifacts.

## Not run / limitations

- Full repository `pytest` was not run; only the five affected backend test files were rerun (68/68).
- Real DeepSeek/Provider requests: 0.
- Browser automation and DOM acceptance: `NOT_RUN_HISTORICAL_STOP`.
- Production or external business writes: 0. The local deterministic demo made exactly one isolated CAS repair and one isolated ticket entry.
- No claim is made about real-LLM autonomy or browser usability.
