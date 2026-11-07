# PRODUCT-01-RUNTIME-GRANT-01 · HF-01 Report

**Status:** `ACCEPTANCE_CANDIDATE`

**Base:** `20cdc22a10c1a443059e96f5b126c5b7c7b959c9`

**Branch:** `codex/product-01-runtime-grant-01-hf01`

**Result SHA:** see the final candidate commit reported with this evidence.

## Findings and changes

The default dispatch selected `CHAT_READONLY` into `_process_chat_run()` and business Runs into `run_investigation()`. Both were constructing their own `ChatOpenAI` clients outside the new Runtime Grant spend pool. Final source review also found the investigation-update classifier (`classify_input`) creating a Provider client directly from a formal API route, outside that pool. All three legacy outbound paths now require the separate legacy opt-in. The ordinary `ASSISTANT_V1` path already binds the Run to its persisted Runtime Grant and wraps the outbound HTTPX transport; it remains unchanged.

`opspilot.config.require_legacy_provider_authorization()` now requires both `OPSPILOT_ASSISTANT_PROVIDER_ENABLED=1` and the independent `OPSPILOT_LEGACY_PROVIDER_ENABLED=1` for legacy Provider paths. The formal Worker checks before dispatch, and `run_investigation()` also checks before constructing ChatOpenAI so direct/CLI use cannot bypass the Worker. Default absence fails closed. The independent switch preserves explicit legacy operation; it does not pretend those legacy calls are recorded in the Runtime spend pool.

The existing spend-pool module now offers `resume_spend_pool()`, a local audited operation. It can clear only a stale Provider/price-configuration pause after the exact persisted Grant configuration is restored or revised, its current version/history and validity are checked, and current ledger totals are validated using the existing `_effective_spend()` accounting. It refuses Usage violations, active send authority, insufficient remaining balance, missing/mismatched Grant history, or stale configuration. UNKNOWN rows retain their original status and reservation; the operation validates their historic price/bounds and includes them in the effective balance. The audit records operator, evidence reference/digest, previous reason, balance, UNKNOWN reservation, and pool version. `spend_summary()` now exposes that version for compare-and-update recovery.

## Evidence

- Targeted red/green suite and existing Runtime Grant tests: 31/31 passed.
- Legacy Investigator, D2, S1/S2, D4/M1 recovery regressions: final rerun 97/97 passed after offline test fixtures explicitly declared the legacy path authorization.
- D5 Context, M1 Worker, AR-02 journey, and Runtime live-scope regressions: 28/28 passed.
- M4 C1 follow-up classifier regression: 13/13 passed, including the existing payload/currentness check.
- `TEST_LOG.txt` records the final commands, stdout summaries, and exit codes. Full raw `.log` outputs remain locally under the Git-ignored `logs/` directory; `FAILURES.md` records the preserved RED and intermediate fixture failures.

## Scope and effects

- Real Provider requests: 0.
- Browser runs: 0.
- External MCP calls: 0.
- External/production business writes: 0.
- Isolated regression tests may execute existing local Demo DB D3 side effects; no production database or external business system was used.
- Full repository pytest was not run.

No historical experiment Claim, UNKNOWN spend, evidence, Gold, or main branch was modified. No schema migration or new service was added. The remaining operational constraint is that a trusted local operator must verify the real current provider price/config before invoking pool recovery; see `FAILURES.md`.
