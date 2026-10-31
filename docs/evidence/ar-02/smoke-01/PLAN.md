# AR-02-SMOKE-01 Free Wiring and Preflight Plan

**Status:** `FREE_ADAPTER_AND_PREFLIGHT_ONLY`; paid requests are not authorized.

## Baseline and scope

- Repository: `wgqa/OpsPilot`
- Expected and observed task branch: `codex/ar02-hf-01`
- Base / current HEAD at start: `d2d53796811691a2ac90f76dce9f140165f1f2b8`
- Remote `main` observed: `ec8c3582f6d145eec9979c43607302731411ead8`
- The D-drive main checkout has separate user changes and is not modified.
- Existing untracked `.tmp/` data in the task worktree is preserved.

## User journey and unchanged Gold

Use the existing S01/S02 verbatim from `../hf-01/SMOKE_INPUTS.md`. This slice only prepares the production API/Worker path and verifies its fail-closed model factory. It does not execute either paid journey.

The intended path remains Session/API → persisted Run → single Worker → `ASSISTANT_V1` → LangChain `create_agent` → real MCP client/server → trusted Domain → original Session answer. Existing per-Run model/MCP reservations, `max_retries=0`, source checks, and no-business-write boundary remain in force.

## Frozen free checks

1. The formal `server.main()` injects a server-side factory into `create_app`; no HTTP/model request is made during app startup or factory construction.
2. The factory returns no model by default, even when model credentials exist, preserving `ASSISTANT_PROVIDER_AUTHORIZATION_REQUIRED` until an explicit local operator enable is set.
3. Enabling without the existing model/key settings fails closed.
4. With explicit enable and fake test-only credentials, construct the existing `ChatOpenAI` adapter with model settings matching the actual Assistant Loop cap (`max_tokens=2048`, `timeout=30`, `max_retries=0`, `temperature=0`, usage enabled); constructing it performs no network I/O.
5. The existing HTTP/Worker deterministic-model integration remains the evidence for API → Worker → `ASSISTANT_V1` → MCP/Domain. It is not real Provider evidence.
6. Cost preflight must report official current pricing, observed request/output configuration, actual enforceable per-Run limits, and whether a durable global USD cap exists. If the USD 0.20 candidate cannot be enforced, stop before any paid request and provide one concrete revised budget/control proposal.

## Stop line

No real Provider request, no real S01/S02, no browser automation, no merge to `main`, and no change to S01/S02 Gold. Deliver the free adapter checks and an honest cost/authorization blocker, then stop for independent review and separate paid authorization.
