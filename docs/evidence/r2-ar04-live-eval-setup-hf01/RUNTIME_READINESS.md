# Isolated Runtime Grant readiness

## Status

`MOCK_READY_FOR_FUTURE_BOUNDED_SETUP`; no live Provider readiness or approval is implied. Evidence in this file is source inspection plus temporary Domain/Checkpoint fixtures and `httpx.MockTransport` calls. Real Provider requests: **0**; real cost: **$0**.

## Existing authorization path

The offline harness uses the existing `assistant_runtime_grant.py` path:

1. `reset_fixture()` creates a temporary test Domain database. The normal test identity `support-a` creates a new Session and each frozen history row through the existing chat Domain APIs.
2. `provision_default_grant()` creates a test-only Grant inside that temporary database; no Grant is created in a user, production, or persistent runtime database.
3. `bind_run()` binds the active Assistant Run. `validate_run_binding()` re-reads the binding and verifies it against that database's persisted identity and the current model/service configuration.
4. `create_assistant_model(runtime_grant_binding=...)` validates the binding. Assistant compression and answer requests use the existing persistent reserve, send, store, deliver, and spend-settlement path. Both async and sync HTTP transports are explicitly `MockTransport`; the sync transport raises if used.
5. Each question/strategy/track gets its own temporary Domain database and LangGraph checkpoint. Temporary DBs are discarded after the test; the mock request and response bodies and context evidence are preserved in `MOCK_TRACE.jsonl.gz` and `TEST_RESULTS.json`.

The local fixture Grant pins `deepseek-flash`, the official DeepSeek endpoint, test-only config/price versions, a 12,000-token input cap, a 512-token output cap, nonzero test-only fixture rates, a one-day validity window, and an isolated one-dollar-equivalent micro-USD ledger ceiling. The API key is the literal test value `offline-only-not-a-real-key`; it is sent only to MockTransport and never written to evidence. The per-case ledger amount is simulated reservation/settlement evidence, not Provider billing.

## A/B/C path result

`A/HYBRID` and `B/ROLLING_SUMMARY` ran the real Assistant context preparation and compression code, sent a schema-valid fixture summary through the Grant-bound model call path, persisted the source-linked summary, then completed a Grant-bound mock answer. `C/RECENT_WINDOW` completed a Grant-bound mock answer without creating a compression attempt. Each run persisted and validated a separate Grant binding.

The configured model input cap is 12,000 tokens and the Grant cap is 12,000. The Assistant reserves its system prompt, trusted context and tool/result overhead before selecting chat history, so its reported effective history budget is lower and can differ slightly by strategy. The exact configured and effective values, manifest blocks, selected message IDs and actual Mock request token estimates are retained per case in `TEST_RESULTS.json` and `MOCK_TRACE.jsonl.gz`. This is not reported as a flat 12,000-token history allowance.

## Fail-closed cases

The targeted existing regressions run against isolated pytest databases:

| Case | Existing guard | Expected outcome |
|---|---|---|
| No Grant | `bind_run` without provisioned authority | `RUNTIME_GRANT_NOT_PROVISIONED` |
| Expired Grant | Bind an expired Grant | `RUNTIME_GRANT_EXPIRED_OR_NOT_YET_VALID` |
| Wrong DB identity | Copy a database and reuse its Grant | `RUNTIME_DB_IDENTITY_MISMATCH` |
| Budget exhausted | Two isolated requests compete for the remaining shared pool | One reservation succeeds and one is denied with `RUNTIME_BUDGET_EXHAUSTED` |
| Invalidated summary source | Change source digest after compression reservation | Attempt becomes `INVALIDATED`; no provider response or summary is stored |

The recorded pytest command and pass count are in `TEST_RUN.txt`. These fixtures validate denial boundaries; they do not create durable authorization.

The 24-case harness cleans its temporary databases/checkpoints automatically. Two additional task-local pytest basetemp directories contain only the isolated DB fixtures from the targeted existing tests; they remain untracked because the environment rejected the cleanup command. They are not part of the candidate commit. The pre-existing root `.pytest-tmp/` is unchanged.

## Requirements for any later live run

- Re-read the then-current Runtime Grant contracts and verify the exact temporary DB identity; do not reuse the test Grant or any historical authorization.
- Supply non-secret model/config/price/service identity values for the isolated runtime and a separately authorized Grant whose model, endpoint, expiry, input/output caps, maximum spend, permissions and run binding match that experiment.
- Store the live API key only in the approved secret mechanism. Do not copy it into evidence, logs, command output or Git.
- Use one Domain and checkpoint per question/strategy/track; ensure the only transport is the approved Provider client and preserve the dispatch ledger.
- Reconfirm Provider/model/pricing and the live request cap before the first send. This setup task authorizes no real send; previous live-test request or budget authorization does not carry forward.

No Grant check was disabled, and the isolated run did not access an existing production database.
