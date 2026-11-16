# R2-AR04 Live Presend Root Cause

## Result

`ROOT_CAUSE_CONFIRMED_BY_ZERO_COST_REPRODUCTION`. The Q02-B summary request was rejected by the task-local Live freeze wrapper before `BudgetedAsyncTransport` validation and before any ledger slot was reserved. The historical report retained only `CHAT_CONTEXT_COMPRESSION_FAILED`; it did not retain the underlying exception. Replaying the same frozen Q02-B history with the same pre-fix Runner SHA reproduced the underlying exception as `GateStop("V2_PROTECTED_PATH_LAYOUT_DRIFT")`.

The failure was caused by a non-reentrant `_task_contract()` context. The outer Live runner contract checks that the broad adapter directory appears once in `v2.PROTECTED_DIFF_PATHS`, then removes that broad directory because the task permits only the exact adapter file pinned by its own Blob check. During a Live request, `_task_assert_frozen()` enters `_task_contract()` a second time. That nested entry sees the intentionally narrowed list and incorrectly raises `V2_PROTECTED_PATH_LAYOUT_DRIFT`.

Ordinary Mock execution does not enter that Live-only per-request block. It proceeds to the parent budget transport, where the logical slot is selected, `start_send` is recorded, and the in-process MockTransport receives the request. The Live path failed between authorization validation and the parent transport, explaining why its request-cap record existed while the Provider ledger remained untouched.

## Error masking

Before this fix, `GateStop` was a plain `RuntimeError` without a `.code` attribute. The compression boundary in `opspilot/assistant.py` therefore replaced the more specific Runner reason with `CHAT_CONTEXT_COMPRESSION_FAILED`. The local `GateStop` now exposes `.code` only when its reason is an ASCII identifier of at most 100 characters. Path-bearing or otherwise unsafe diagnostics remain in the exception message and are not passed as a Domain error code. A full Assistant-path negative test confirms a frozen adapter Blob violation is retained as `PROVIDER_ADAPTER_BLOB_DRIFT` and stops before MockTransport dispatch.

## Minimal change

The only runtime code change is in the task Runner. `_task_contract()` now tracks nested entry depth and reuses the already-installed outer task contract during re-entry. The outer entry still performs the original path-layout check, narrows the V2 protected paths, and restores all V2 globals on exit. The exact adapter Blob pin, frozen production Blob checks, historical digest checks, authorization revalidation, budget checks, source-currentness checks, and UNKNOWN/no-retry handling remain active. Regression tests and evidence were added separately.

The default Mock artifact now points to `mock_run_09`. `mock_run_07` and the intermediate `mock_run_08` remain unchanged; both are rejected for the final Runner because their embedded Runner SHAs are stale.

## Evidence and limits

- The failed historical Q02-B result remains unchanged: one compression attempt, generic Domain error, no Answer Manifest, and zero Provider requests. Historical `LIVE_RESULTS.json` SHA-256: `4b4915eee9f0fceec0dac560b1e95c10c6c13c44a6e6f01146d2427462f8eb3a`.
- The historical cost ledger remains unchanged. SHA-256: `9822ff1bd9109f9e821a8c191c6272f95ff7f5a7956049f5dc733fdfd7898ad9`.
- The pre-fix reproduction used the exact prior Runner SHA `e31956fb0ec381458f5271d4ccbf580daf36a54c69737ee8fcd59eba65976a1e`, frozen Q02-B inputs, an isolated temporary Domain/Checkpoint, a test-only authorization validator, and `httpx.MockTransport`. It made no network request.
- The repaired full Assistant/Domain path completed both frozen Cases against six responses replayed through `httpx.MockTransport`; that proves the per-request Live-shaped path reaches the budgeted transport and can complete offline. It is not a real Provider run and does not prove live authorization or L3 model behavior.
- The zero-cost Runner preflight is `READY_FOR_NEW_LIVE_AUTHORIZATION`; it created no authorization and performed zero Provider requests. This status does not authorize a paid run. The prior one-time authorization remains ended and was not loaded or reused.
- Final Runner SHA-256: `5e7cd43b83de56f37504d82f95da3880ac57c262044a4edba8e3525ab2427923`. Final `mock_run_09/MOCK_RESULTS.json` SHA-256: `1ecff482b0ce8089c47c9d8fd42d206b46b0076a995a8b4a0cf74bec7c66938a`.
- The historical execution did not preserve its raw exception stack. The exact historical exception object is therefore not independently recoverable; the same Runner SHA and same failing call path reproduce the cause deterministically.

No production Assistant or Domain file changed. No historical Trace, Gold, ledger, C06 RED record, or prior Mock artifact changed. Provider requests: `0`; cost: `USD 0.00`.
