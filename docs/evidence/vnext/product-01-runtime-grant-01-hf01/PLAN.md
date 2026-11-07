# PRODUCT-01-RUNTIME-GRANT-01 · HF-01 Plan

**State:** `ACCEPTANCE_CANDIDATE`

**Base:** `codex/product-01-runtime-grant-01@20cdc22a10c1a443059e96f5b126c5b7c7b959c9`

**Implementation branch:** `codex/product-01-runtime-grant-01-hf01`

## Frozen scope

1. Prevent legacy `CHAT_READONLY` and Investigator Provider paths from sending unless both the global Provider switch and a separate legacy-path authorization are explicitly enabled. Preserve those paths when explicitly authorized.
2. Add a local, audited way to resume the existing Runtime spend pool only after a recoverable stale-configuration pause has been corrected and the existing ledger has been revalidated.

## Explicitly out of scope

No real Provider request, browser run, external business write, main merge, new ledger, new admin API, schema migration, or change to historical experiment records. Existing Runtime Grant, dispatch accounting, UNKNOWN retention, Context Compression, and experiment contracts remain authoritative.

## Acceptance evidence

- Offline HTTPX MockTransport RED/GREEN for old Chat and Investigator paths.
- Existing formal API/Worker `ASSISTANT_V1` Runtime Grant tests remain green.
- Pool recovery rejects unrepaired configuration, invalid/nonrecoverable pauses, exhausted balances, and audit-key conflicts; successful recovery preserves UNKNOWN reservations and records an idempotent audit event.
- Applicable legacy Investigator and TaskControl regressions pass with test-only explicit legacy authorization.
