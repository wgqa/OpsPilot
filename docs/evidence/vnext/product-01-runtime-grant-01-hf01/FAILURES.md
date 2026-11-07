# Failures and remaining limits

## Preserved RED

Before the P0 guard, the targeted offline regression was `2 failed, 1 passed`. The two failed cases captured serialized HTTP requests through HTTPX `MockTransport` from (1) formal `CHAT_READONLY` `/messages` with an unsupported endpoint and no legacy authorization and (2) the legacy Investigator Worker with no legacy authorization. The explicit legacy Chat case passed. This is the intended RED evidence; the full raw output remains locally at the Git-ignored `logs/red2.log`, with the result summarized in `TEST_LOG.txt`.

## Test fixture compatibility findings

After adding the required authorization guard, legacy D4/M1/D5 tests that exercised the old Investigator without declaring its authorization stopped before reaching their original assertions. The first combined runs recorded 24 and 7 such fixture failures; no real Provider request occurred. The relevant deterministic test modules now explicitly set the two authorization switches as an offline deployment fixture. The preserved earlier `regression3.log` reports 106 passes, but its raw output does not include the invoked file list; the final explicitly recorded command is 97/97, and the independent D5/M1/AR-02 group is 28/28. The 106-pass log remains preserved as an earlier result, not combined into final coverage. Intermediate raw logs remain locally under the Git-ignored `logs/` directory; their failure counts and causes are summarized here.

One early implementation run had a test-only `NameError` from a missing import while asserting the pool version; it was corrected and the final targeted suite passes. See `logs/green-first.log` and `logs/runtime-final3.log`.

## Remaining risks / limits

- `OPSPILOT_LEGACY_PROVIDER_ENABLED=1` is an explicit operational opt-in, not a second persistent spend pool. Any deployment that uses a legacy path must separately authorize and budget that use; leaving the flag unset keeps it blocked. This HF does not create a legacy billing ledger.
- The formal M4 investigation-update classifier also makes a direct Provider request and is now behind the same legacy opt-in. Its model output remains an untrusted classifier result; this change does not move that request into the Runtime Grant pool.
- Pool resume is a trusted local Python operation, not a Web/admin API. The operator must independently verify the current provider price/config and provide the evidence reference and digest. The code checks that the current environment matches the persisted Grant and that the ledger can safely resume; it cannot independently verify external price documents or supplier billing.
- Only `PROVIDER_CONFIGURATION_OR_PRICE_VERSION_STALE` is resumable here. Usage violations, ledger-integrity errors, active sends, exhausted balances, revoked/expired Grants, or unresolved configuration mismatches remain fail-closed.
- The full repository suite was not run. No real Provider, browser, or production/external business action was run.
