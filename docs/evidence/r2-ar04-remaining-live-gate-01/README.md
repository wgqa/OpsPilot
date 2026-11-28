# R2-AR04-REMAINING-LIVE-GATE-01

## Status

`ACCEPTANCE_CANDIDATE` — offline Mock preparation completed; no live authorization was created and no Provider request was sent.

## Reproduce

From the repository root, run:

```powershell
python docs/evidence/r2-ar04-remaining-live-gate-01/run_remaining_live_gate.py mock
python docs/evidence/r2-ar04-remaining-live-gate-01/run_remaining_live_gate.py preflight --mock-results docs/evidence/r2-ar04-remaining-live-gate-01/mock_run_04/MOCK_RESULTS.json
python -m pytest -q docs/evidence/r2-ar04-remaining-live-gate-01/test_remaining_live_gate.py --basetemp=<fresh-temp-dir>
```

The runner pins the task Base, production `chat.py` and `assistant.py` blobs, frozen question/history/Gold/rubric/tool-schema inputs, and the accepted V2 reply-provenance records. The current production Blob checks remain enabled. The accepted output is `mock_run_04/`.

## Evidence summary

- Q02-B and Q06-B each start from 29 frozen history rows and isolated Domain, Checkpoint, Session, Run, and Runtime Grant state.
- The complete Assistant-to-Domain Mock path makes 4 summary calls and 2 answer calls through `httpx.MockTransport`.
- Summary generation and Runtime Grant output caps are 1024 tokens; answer output is 512; persisted summaries are 501/501 and 510/510 estimated tokens respectively, within the 512-token Domain limit.
- The final prompts contain Q02-B `endpoint=/callback` with source seq3 and Q06-B `v1.2 -> v1.3` plus `max_attempts 3 -> 5` with source seq11. The earlier seq3 `max_attempts` is marked `PARTIAL`.
- The frozen Q02-B historical response with `finish_reason=length` is replayed through the normal path and stops with `CONTEXT_SUMMARY_OUTPUT_TRUNCATED`; no summary or answer is persisted/dispatched.
- Source invalidation and an UNKNOWN send each stop after one Mock request; no answer, retry, or Q06-B continuation occurs.
- The shared Mock ledger contains six request slots and a USD 0.06 hard cap. Mock usage/cost values are synthetic accounting fixtures, not Provider usage or charges.
- The zero-cost preflight loaded the main repository `.env` without recording secret values, supplied only the three missing non-secret Runtime configuration values in isolation, and bound a temporary Grant. It did not authenticate against the Provider, recheck current pricing, create a task authorization, or dispatch a live request.

## Live boundary

`READY_FOR_NEW_LIVE_AUTHORIZATION` means the offline preparation is ready for independent review. It does not authorize sending. A future live task must provide a new task-specific authorization, recheck official model pricing immediately before sending, and use the existing single-case stop and UNKNOWN no-retry gates. Historical authorization manifests are rejected.

See `PLAN.md`, `RUNNER_DESIGN.md`, `SOURCE_MANIFEST.json`, `FREEZE.json`, `BUDGET.json`, `PREFLIGHT.json`, `FAILURE_MATRIX.json`, and `RESULTS.json` for exact pins and evidence.
