# AR-03-MATERIAL-LIVE-01 Runner Recovery 02

Status: `ACCEPTANCE_CANDIDATE` (free runner repair only)

## Frozen boundary

- Base branch: `codex/ar03-material-live-01-exec-prep`
- Base SHA: `f3614df65f436b86b19069b6248e3b8a401f2a8a`
- Main SHA at verification: `ec8c3582f6d145eec9979c43607302731411ead8`
- Original paid experiment `AR-03-MATERIAL-LIVE-01-RESUME-01` remains terminated. Its one-shot claim is consumed and must not be reused.
- No new claim, paid Provider request, browser action, business write, Gold change, or main merge is in scope.

## Frozen checks

1. `_CampaignState.begin()` reads `PRICE_VERSION` from `opspilot.domain.assistant_experiment` and still rejects a mismatched persisted budget version.
2. `_audit_case()` works against the real `assistant_calls` schema, reports absent `error_code` as unknown, and retains the Run failure reason without fabricating a code.
3. An isolated formal FastAPI/Worker/Assistant run reaches explicit HTTPX `MockTransport` only after durable dispatch and assistant-call reservations are visible.
4. A synthetic transport failure remains auditable and keeps the temporary experiment reservation unknown; the audit error must not replace the original Run failure.
5. An invalid serialized request is rejected before the MockTransport handler.
6. The prior experiment claim, ledger, runtime DB/checkpoint, Trace, and original failure artifacts remain unchanged.

Tests use fresh temporary SQLite/checkpoint files. The mock formal-run harness locally stubs only the paid one-shot predicate so it can exercise the authorized runner path without creating or consuming a paid claim. No real network client is used.
