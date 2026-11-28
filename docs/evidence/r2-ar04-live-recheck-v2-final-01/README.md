# R2-AR04 final live recheck

Candidate status: `ACCEPTANCE_CANDIDATE`. The preparation snapshot at `d69b06c3005b07df9c7c8619b373c4d7547e991d` was `READY_FOR_LIVE_AUTHORIZATION`; the single newly authorized live run is recorded below and stopped after Q02-B's first summary was truncated.

Start with [PLAN.md](PLAN.md), then see [RUNNER_DESIGN.md](RUNNER_DESIGN.md), [RESULTS.json](RESULTS.json), [PREFLIGHT.json](PREFLIGHT.json), [FAILURE_MATRIX.json](FAILURE_MATRIX.json) and [TEST_RUN.txt](TEST_RUN.txt). `FROZEN_INPUTS.json` records source and input hashes. The authoritative 3-Case Mock trace and ledger are under [`mock_run_03/`](mock_run_03/); `MOCK_RESULTS.json` is the top-level index copy. The corrected historical reply source list is inherited from the accepted V2 provenance validator.

## Commands

The preparation command was one-shot and refused to reuse an existing `mock_run_03` or `live_run_01`:

```powershell
python docs/evidence/r2-ar04-live-recheck-v2-final-01/run_live_final.py prepare
```

The single live command authorized for this task was:

```powershell
python docs/evidence/r2-ar04-live-recheck-v2-final-01/run_live_final.py live --authorization <local-one-shot-authorization.json>
```

The Runner revalidated the fixed case order, budget, authorization, official price snapshot and isolated Runtime Grant before dispatch. It wrote the result to [`live_run_01/`](live_run_01/). The non-secret authorization manifest stayed in the local untracked `.local/` directory and is not part of this candidate. This authorization has been consumed; do not rerun or resume this live command. Any further Provider call requires a new task and new explicit authorization.

## Current outcome

The fresh Mock completed 3/3 Cases, 6 summary calls and 3 answer calls. All three used `tool_choice=none`, no MCP attempt occurred, and all had two persisted summaries and sourced text in the final Mock answer context. Q06-B still labels the early `max_attempts` value `PARTIAL`; the later sequence contains the complete `v1.2 → v1.3` and `3 → 5` transition. The Mock is not L3 evidence. The earlier real ABC run had safe abstentions for all three target cases because their facts were absent from the final prompt.

## Single live run 01

The live runner completed Q02-A (two summaries and one supported correct answer), then stopped on Q02-B's first summary. Its Provider response ended at `finish_reason=length` with 512 output tokens; Domain returned `CONTEXT_SUMMARY_INVALID_JSON`, so Q02-B's answer and Q06-B were not sent. Four Provider requests were made in total; no UNKNOWN, retry or external MCP call occurred. The peak-price ledger estimate is USD 0.006749; actual account debit was not checked. See [LIVE_ASSESSMENT.md](LIVE_ASSESSMENT.md), [LIVE_ASSESSMENT.json](LIVE_ASSESSMENT.json), and the preserved [live artifacts](live_run_01/). The preliminary assessment finds a supported Q02-A improvement but does not recommend closing AR-04 because Q02-B failed and Q06-B was not run.
