# R2-AR04 final live recheck preparation

Status: `READY_FOR_LIVE_AUTHORIZATION` (preparation only; no Provider request).

Start with [PLAN.md](PLAN.md), then see [RUNNER_DESIGN.md](RUNNER_DESIGN.md), [RESULTS.json](RESULTS.json), [PREFLIGHT.json](PREFLIGHT.json), [FAILURE_MATRIX.json](FAILURE_MATRIX.json) and [TEST_RUN.txt](TEST_RUN.txt). `FROZEN_INPUTS.json` records source and input hashes. The authoritative 3-Case Mock trace and ledger are under [`mock_run_03/`](mock_run_03/); `MOCK_RESULTS.json` is the top-level index copy. The corrected historical reply source list is inherited from the accepted V2 provenance validator.

## Commands

The preparation command is one-shot and refuses to reuse an existing `mock_run_03` or `live_run_01`:

```powershell
python docs/evidence/r2-ar04-live-recheck-v2-final-01/run_live_final.py prepare
```

To start a later live execution, first obtain a **new explicit paid authorization for this exact task**, recheck the current official model and price, then create a non-secret authorization JSON matching `AUTH_FIELDS` and `price_snapshot` in `run_live_final.py`. No authorization JSON is included in this candidate. The live command is:

```powershell
python docs/evidence/r2-ar04-live-recheck-v2-final-01/run_live_final.py live --authorization <fresh-task-authorization.json>
```

The Runner rejects old task authorization, expires authorization/price snapshots after 24 hours, enforces the fixed case order and budget, performs a fresh zero-cost Grant preflight, and writes to a new `live_run_01` only after the checks. Do not edit Gold, reuse old ledgers or continue after failure/UNKNOWN. This preparation is not authorization to run that command.

## Current outcome

The fresh Mock completed 3/3 Cases, 6 summary calls and 3 answer calls. All three used `tool_choice=none`, no MCP attempt occurred, and all had two persisted summaries and sourced text in the final Mock answer context. Q06-B still labels the early `max_attempts` value `PARTIAL`; the later sequence contains the complete `v1.2 → v1.3` and `3 → 5` transition. This is deterministic/mock evidence only. The old live recheck previously stopped after one Q02-A summary with `KeyError`; final live L2 and L3 are still unverified. AR-04 cannot be declared closed from this preparation.
