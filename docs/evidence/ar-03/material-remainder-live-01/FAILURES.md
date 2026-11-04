# Failures and stops

## Frozen implementation RED

- `runs/red-01-live-entry-and-claim.log`: before the one-shot authorization and Runner existed, 2 tests failed and 1 fail-closed control passed. The failures were the missing three-condition entry point and missing exact one-shot claim validator. This was a preparation RED, not a live model or business result.
- The original AR-03 material RESUME-01/02 failure history is unchanged and remains in its original evidence directories.

## Free-test setup failures retained

- The first GREEN attempt for `test_live_authorization_requires_a_new_exact_one_shot_claim` failed because the test fixture had not set the two required process opt-ins. The authorization guard correctly rejected it. The test now supplies the frozen experiment ID and provider opt-in, and retains wrong-token/wrong-branch negatives.
- The first combined regression run had 3 failures in the existing POST-LIVE CLOSEOUT audit tests. Root cause was test-only environment leakage from the one-shot claim test: it wrote process variables directly after an untracked `delenv`, leaving the remainder experiment ID visible to later tests. The fixture now registers empty baseline values with pytest's monkeypatch before the Runner sets them. No production behavior was weakened.
- The failing combined run is preserved in the private runtime evidence store as `targeted-regression-01.log` with exit code `1`; the corrected run is `targeted-regression-02.log` with exit code `0`. These include local absolute paths and remain private.
- The first single-test assertion failure was observed in the tool transcript but was not redirected to a raw file. Its exact failing assertion and cause are preserved here; it is not represented as a saved raw log.

Further failures, business partials and stop conditions will be appended without deleting this record.
