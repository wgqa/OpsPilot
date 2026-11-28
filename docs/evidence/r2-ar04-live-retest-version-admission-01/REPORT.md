# R2-AR04 Live Retest Version Admission

**Status:** `ACCEPTANCE_CANDIDATE`
**Provider requests:** 0
**Provider cost:** USD 0
**External MCP / production writes:** 0 / 0

## Result

The new adapter is bound to the accepted `chat.py` Blob `6a57360de6f5579fa65dc008de4fcf37148c43f0`, with `assistant.py` unchanged at `288559c6e9b77549939501f4cedb1a8097a79918`. It reuses the reviewed freeze, authorization, budget, request-cap and UNKNOWN-stop logic. The old Runner, Gold, historical Trace, Ledger and failure records were not edited.

Q02-B and Q06-B both completed through the normal Assistant/Domain path under MockTransport. Each used 29 frozen messages, two successful persisted summaries and one synthetic answer. Six send slots passed request and budget checks and reached `httpx.MockTransport`; the Mock ledger records four summary slots and two answer slots. Both final prompts included the target facts with valid source. Q06-B seq3 remains `PARTIAL`; the seq11 version and retry transition remains complete with source.

The final zero-cost preflight is `READY_FOR_NEW_LIVE_AUTHORIZATION`. The main `.env` was loaded without logging values. Three non-sensitive Runtime fields absent from the file were supplied from the isolated task defaults; all six required fields were present in the effective configuration. An isolated temporary Runtime Grant was bindable, and the preflight confirmed zero transport invocations. API-key authentication was not tested and the key value was not recorded.

## Important limits

The preflight is not live permission. The repository's price snapshot is historical and was not rechecked in this zero-cost task. Before any future send, recheck the official model/version and prices, bind the fresh snapshot to a new exact-scope authorization, and rerun the frozen/preflight gates. No paid authorization was created here.

Rollback across compact summaries stored with sequence citations remains unverified. See [ROLLBACK_LIMITS.md](ROLLBACK_LIMITS.md).

An initial preparation pass is preserved as `PREFLIGHT_INITIAL.json` and `mock_run_01/`. It showed a successful Mock but a blocked preflight because Task ID and Review ID were initially identical, making the review-identity rejection probe ambiguous. The IDs were separated; the canonical final run is `mock_run_02/` plus `PREFLIGHT_RUN_02.json`. The initial Mock is not accepted as the current binding.

## Evidence

- `mock_run_02/MOCK_RESULTS.json`: two-case results and current runner/source digests.
- `mock_run_02/MOCK_TRACE.jsonl.gz`: pre-send and Mock response events.
- `mock_run_02/MOCK_COST_LEDGER.json`: six MockTransport slots and zero reserved balance.
- `SOURCE_MANIFEST.json`: case-specific frozen reply identities, request/response digests and production Blob pins.
- `PREFLIGHT_RUN_02.json`: isolated configuration/Grant readiness, zero Provider calls and no secret values.
- `FREEZE.json`: source, adapter, governance and historical-file verification at the base used for the Mock preparation.
- `TEST_RUN.txt`: commands, initial diagnostic, final test results and post-commit HEAD check.
