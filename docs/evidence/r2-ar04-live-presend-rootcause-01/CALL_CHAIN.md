# Presend Call Chain

## Failure path before the fix

The execution was already inside the authorized task Runner's Live path. The top-level Live path had run its preflight, loaded its task-specific authorization, and entered the outer task contract before delegating to the Assistant adapter.

```text
run_live()
  -> with _task_contract()                       outer task scope installed
  -> legacy.run_cases(..., mode="LIVE")
  -> abc._run_case(..., 29 frozen Q02-B messages)
  -> run_assistant(...)
  -> _prepare_assistant_context_impl()
       -> create compression attempt in isolated Domain
       -> _compression_model(...).ainvoke(messages)
       -> PurposeCappedTransport._validate_request(request, body)
            1. decode JSON body                          PASS
            2. identify SUMMARY purpose                  PASS
            3. _assert_request_cap(..., 1024)            PASS
            4. append SUMMARY/1024 request-cap metric    PASS
            5. load_authorization(test-only stub)         PASS in offline reproduction
            6. _task_assert_frozen()
                 -> with _task_contract()                nested entry
                      -> require adapter path count == 1 FAIL: count was 0
                      -> GateStop("V2_PROTECTED_PATH_LAYOUT_DRIFT")
            7. parent BudgetedAsyncTransport validation   NOT REACHED
            8. GlobalBudgetLedger.next_slot               NOT REACHED
            9. GlobalBudgetLedger.start_send               NOT REACHED
           10. Mock/Provider HTTP handler                  NOT REACHED
       -> Assistant compression exception handler maps missing .code to
          CHAT_CONTEXT_COMPRESSION_FAILED
       -> Domain attempt becomes FAILED; no Summary and no Answer Manifest
```

The outer `_task_contract()` had already validated the original V2 protected-path layout and removed the broad adapter directory so only the exact adapter file could be exempted. The nested context re-ran the precondition against that already-narrowed list. That duplicate setup check was the first failing check.

## Difference from ordinary Mock

`PurposeCappedTransport._validate_request()` runs the authorization and `_task_assert_frozen()` checks only when `self.mode == "LIVE"`. In `MOCK` mode it goes directly to `super()._validate_request()`. The parent transport performs request validation, selects the logical slot, calls `start_send`, records a trace event, then delegates to the configured MockTransport. Thus the accepted Mock suite could complete while the Live per-request path stopped before any slot was reserved.

## Path after the fix

The first `_task_contract()` entry still performs the full frozen path checks and installs the narrowed V2 list. Re-entry now increments the Runner's context depth counter, yields under those same installed values, then returns without repeating setup. `_task_assert_frozen()` still calls `v2.assert_frozen()` while the checks are active. The Runner then continues to the parent request and ledger validations.

The full Assistant/Domain test replaces the `httpx.AsyncHTTPTransport` factory with a function that always constructs `httpx.MockTransport`, replays the six immutable response payloads from final `mock_run_09`, and substitutes only the per-request authorization validator. It verifies six requests reach MockTransport, both Cases complete, no local tool observation occurs, and no authorization file exists. No real `run_live()` authorization manifest was created or used.

## Error-code boundary

`GateStop.code` is present only for bounded ASCII identifiers matching `[A-Za-z0-9_]+`. The Assistant may safely persist that identifier. A negative full-path test injects an adapter Blob mismatch and verifies `PROVIDER_ADAPTER_BLOB_DRIFT` reaches the failed compression attempt without dispatch. Messages containing filesystem paths or other unsafe material do not expose `.code`.

## Source locations

- `opspilot/assistant.py`: `_compression_model` at 2375; `_prepare_assistant_context_impl` at 2542; compression `ainvoke` at 2712; generic fallback to `CHAT_CONTEXT_COMPRESSION_FAILED` at 2778.
- `docs/evidence/r2-ar04-remaining-live-gate-01/run_remaining_live_gate.py`: `_task_assert_frozen` at 145; `_task_contract` at 211, including the path-layout guard at 232; `PurposeCappedTransport._validate_request` at 276; per-request `load_authorization` call at 296; `_assert_request_cap` at 790.
- `docs/evidence/abc-live-env-unblock-01/run_abc_eval.py`: `BudgetedAsyncTransport` at 521; request validation at 539; `GlobalBudgetLedger.next_slot` at 413; `start_send` at 423; send handler at 588.
