# Failures and limits

- The baseline reproduction failed as expected before the fix: the isolated Windows API remained alive after the SSE Stop request for 6.007 seconds. See `RED-before-fix.txt`.
- An initial broader regression command without legacy Provider opt-in had 14/15 pass. The only failure was `test_ops_02_expired_total_deadline_blocks_run_without_model_call`, whose setup was rejected by the existing `LEGACY_PROVIDER_AUTHORIZATION_REQUIRED` check before the deadline assertion. The failure and the offline opt-in rerun are preserved in `REGRESSION-targeted.txt` and `FINAL_TEST_LOG.txt`.
- Full repository pytest, browser automation, the actual PowerShell Stop script, and shutdown during an active business Run were not executed. The task did not authorize browser automation; ports 8000 and 5173 and the owner's running demo were left untouched.
- No unresolved SSE shutdown defect was observed in the tested stop-file/Uvicorn/HTTPX process path. Independent review should still verify the PowerShell script against the candidate and decide whether browser-owner validation is needed.
