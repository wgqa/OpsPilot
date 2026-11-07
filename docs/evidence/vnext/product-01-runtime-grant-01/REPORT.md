# PRODUCT-01-RUNTIME-GRANT-01 report

**Status: `ACCEPTANCE_CANDIDATE` — awaiting independent review.**

## Result

The ordinary `ASSISTANT_V1` path now has an opt-in, deployment-level Runtime Grant and persistent shared spend pool. It can use the formal API → Worker → Assistant → ChatOpenAI path without an AR/P01 experiment ID or one-shot claim, provided an operator has explicitly provisioned a valid Grant, the normal runtime and Provider flags are enabled, credentials are present, and the configured model/endpoint/price versions match the persisted Grant.

No Grant, budget amount, or real-provider enablement is created by database initialization. API-key presence alone does not authorize a call. The only supported production model in this implementation remains `deepseek-flash` at the DeepSeek endpoint.

## User-visible path and controls

`FastAPI create_app` reads the explicit runtime enable flag and passes it to the single Worker. Before constructing the Provider client, the Worker binds the `ASSISTANT_V1` Run to the current Grant version and fixed Domain database identity. The Assistant reserves a worst-case amount before entering HTTPX. The HTTPX wrapper checks the actual serialized request and obtains a durable, one-use `SEND_GRANTED` record immediately before transport. The raw response, safe response headers, Completion ID, Usage, and settlement are committed before the response is returned to LangChain. The Assistant verifies that durable record before persisting/delivering the result.

Answer calls and Context Compression use the same pool. UNKNOWN sends retain their full reservation and cannot be resent; other sessions may continue only if their complete reserve still fits. A trusted local reconciliation records its operator, supplied evidence reference/digest, and idempotency key; it can settle an UNKNOWN record but never trigger a resend. It does not automatically verify an external provider invoice. Stale provider/price configuration, invalid bounds, actual Usage overrun, or ledger integrity problems pause the pool.

The grant authorizes model spend only. TaskBinding and the existing read-only MCP authorization still govern business facts. The Assistant's existing MODEL/MCP limits and business-write protocols remain in force.

## Evidence

- New targeted tests: 18/18 passed.
- Applicable regression command: see `TEST_LOG.txt`; 70/70 passed, exit code 0.
- Covered: empty initialization; explicit grant and DB identity; shared allowance/concurrency; restart UNKNOWN; Usage missing and over-bound; audited reconciliation and revision replay; grant expiry/revocation/config drift; send recovery from a durable response; request/Run binding; Compression and answer spending from one pool; formal API/Worker/ASSISTANT_V1/ChatOpenAI with explicit MockTransport; disabled/missing authorization; absence of experiment ledger initialization and business-write side effects.
- Real Provider HTTP: 0. External MCP calls: 0. Browser runs: 0. External business writes: 0.
- Full suite: not run. See `RESULTS.json` and `FAILURES.md` for scope and limitations.

## Modified files

- Added `opspilot/domain/assistant_runtime_grant.py` and `opspilot/runtime_provider.py`.
- Updated Domain initialization, Assistant call recovery, formal Assistant/Worker wiring, and one existing Provider authorization assertion.
- Added `tests/test_product_01_runtime_grant_01.py` and this evidence directory.
- `assistant_experiment.py`, its historical schema/records, S1/S2/D3 business authorization, Web UI, and `main` were not changed.

## Remaining review points

No real Grant or production amount is approved here. Before live use, an operator must select and verify a current model price/config version, provision an explicit audited Grant against the deployment DB identity, set the explicit runtime and Provider enable flags, and obtain separate real-Provider authorization if required. Provisioning, revision, and reconciliation are local Python operations, not authenticated Web/admin endpoints; the recorded operator identity is trusted operator input, so access to the deployment process and database must remain restricted. The estimator and billing limitation are documented in `FAILURES.md`; this offline slice does not claim a supplier-enforced hard spend cap.

No main merge, browser automation, real Provider request, or external business action was performed.
