# R2-AR04-REMAINING-LIVE-EXEC-01 — Stop A

## Status

`ACCEPTANCE_CANDIDATE` for independent review at Stop A. The Mock binding defect is fixed, a fresh `mock_run_06` passed, and default/explicit Preflight resolve to the same pinned file and SHA-256. **No Live request was made and no effective paid Authorization Manifest was created. Stop here pending independent review.**

## Candidate and scope

- Repository: `wgqa/OpsPilot`
- Branch: `codex/r2-ar04-live-admission-hf01`
- Original Gate Base: `fa4cd8a7ea6dd36babccbbfc5fcdb7a179729fd3`
- HF-01 reviewed parent: `2e6da26fc6fc8efa42273ef8bf9bacea23376865`
- Mock-binding code commit, pushed: `ae74ef505849deed65677fed1dd45e13f7b1dad3`
- Review ID: `R2-AR04-LIVE-ADMISSION-HF-01`
- Authorization Task ID remains exactly `R2-AR04-REMAINING-LIVE-GATE-01`.

The code change is task-local to the existing Live Gate Runner and tests. No production Assistant, Domain, Context, Gold, or historical Trace was changed. Full source and frozen-input pins are in [SOURCE_BINDINGS.json](SOURCE_BINDINGS.json).

## Defect and correction

Before this change, `MOCK_RESULTS_PATH` pointed to `mock_run_04`, while Preflight and `run_live()` accepted arbitrary `mock_path` values. Authorization validation hashed the default file, but Preflight and Live could read a different file. The approved `mock_run_05` was therefore not the same artifact used by authorization validation.

The Runner now pins `docs/evidence/r2-ar04-remaining-live-gate-01/mock_run_06/MOCK_RESULTS.json`. Authorization artifact pins require both `mock_results_path` and `mock_results_sha256`. `run_preflight()`, `run_live()`, and authorization loading normalize to this one path and reject any other path with `AUTH_MOCK_RESULTS_PATH_MISMATCH`. Live also compares the Preflight path and SHA to the values loaded for the run. The exact path guard remains active at each per-request authorization check.

The old `mock_run_04` and `mock_run_05` files were left untouched. Their current SHA-256 values match the values recorded before this fix.

## Stop A evidence

- `mock_run_06/MOCK_RESULTS.json`: Q02-B and Q06-B both succeeded; four Mock summaries and two Mock answers; zero Provider requests, zero MCP, USD 0.00.
- Q02-B `/callback` is visible in the final answer prompt with source sequence 3.
- Q06-B `v1.2 → v1.3` and `max_attempts 3 → 5` are visible with source sequence 11; the earlier seq3 record remains explicitly `PARTIAL`.
- Default and explicit-path Preflight both report `READY_FOR_NEW_LIVE_AUTHORIZATION`, and both bind the same relative path and Mock SHA-256. See [LIVE_PREFLIGHT_DEFAULT.json](LIVE_PREFLIGHT_DEFAULT.json) and [LIVE_PREFLIGHT_EXPLICIT.json](LIVE_PREFLIGHT_EXPLICIT.json).
- Supplying the previous `mock_run_05` to the CLI is blocked with `AUTH_MOCK_RESULTS_PATH_MISMATCH`; no output artifact is created.
- The isolated preflight reports no production database open/write, no authorization created, no Provider transport invocation, and no Live dispatch.

The shared Grant reserve remains USD 0.028974 under the USD 0.06 task ceiling. Limits remain 12,000 input, 1,024 summary generation, 512 answer generation, and 512 persisted summary tokens.

## Stop line

This report only establishes offline code, Mock, frozen-source, and zero-cost Preflight readiness. The previously stored price snapshot is not refreshed here. Before any Live stage, independently review this candidate; then recheck the official model/version and price, create a new short-lived exact-scope authorization, and execute only if every contract check passes. No authorization file, API authentication request, Provider send, semantic score, or business write is part of this candidate.

Commands and exit states are in [TEST_RUN.txt](TEST_RUN.txt); machine-readable results are in [RESULTS.json](RESULTS.json).
