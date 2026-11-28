# Failures and limitations

## Historical full-suite failures retained

The earlier integrated full-suite run remains unchanged: `40 failed, 701 passed in 1009.46s`. Its 12 AR-04C failures and the retired C1 RED are classified in `SCOPE_MATRIX.md`. The original log is not edited.

## Controlled current-contract run

The one controlled full pytest run collected 751 tests, selected 733, passed 732 and failed 1; 18 were explicitly deselected and are not passes. The pytest summary implies exit code 1 after 990.36 seconds. The yielded shell wrapper's native exit value was not retained, so this distinction is recorded rather than presenting a captured wrapper code.

The sole failure was:

`tests/test_ar03_material_live_resume_02.py::test_static_resume02_authorization_and_immutable_history_hashes_are_valid`

The disposable clone was located at `D:\tmp\opspilot-ar05-release-boundary-20261106\repo`. In that layout, the tested runner's `ROOT.parent.parent / .runtime / ...` path resolved to `D:\tmp\.runtime`, not the original repository's private historical-claim location. The expected claim was therefore absent from the disposable clone. The test performs read-only digest checks; it does not consume the current RESUME-02 claim.

The same exact test was then run once in the canonical candidate worktree, where the intended relative path resolves to the repository's existing private runtime. It passed `1/1` with exit code 0. No claim was copied, mutated, or replayed. This supports an environment-layout diagnosis, but does not change the recorded full-suite exit code or turn the full run into PASS.

## Remaining limits

- Five additional identity-sensitive AR-04C nodes were excluded to avoid false-pass results caused by synthetic or mocked old branch identity; see the exact list and rationale in `SCOPE_MATRIX.md`.
- The ten isolated AR-04C mock authorization/claim tests were not re-run against their original frozen source identity. The actual paid one-shot claim cannot be reused.
- The two pre-live AR-04C absence tests cannot be re-run after the real authorization/claim exists; one also writes to an immutable historical evidence path.
- The old `READONLY_FOLLOWUP` RED is preserved and excluded. Current `FOLLOW_UP + readonly_action=INVESTIGATE` positives passed.
- This work did not establish overall merge approval and did not perform a merge.
