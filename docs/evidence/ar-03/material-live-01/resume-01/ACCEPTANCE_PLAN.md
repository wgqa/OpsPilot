# AR-03-MATERIAL-LIVE-01 Resume 01 — Execution Preparation Freeze

Status: `FREEZE_FOR_OFFLINE_PREPARATION`

## Baseline and scope

- Accepted source candidate: `codex/ar03-material-live-01-safe@ff956ea71b90448d40229c57b8f8619c997b5cbd`.
- Working branch: `codex/ar03-material-live-01-exec-prep`.
- New isolated execution identity: `AR-03-MATERIAL-LIVE-01-RESUME-01`.
- Frozen MAT-01–MAT-06 inputs and Gold remain the originals at `docs/evidence/ar-03/material-01/CASES.json` and `GOLD.md`.
- Prior `AR-03-MATERIAL-LIVE-01` claim, databases, ledger, failures, and traces are immutable inputs and must not be reused or rewritten.
- This slice authorizes free preparation and offline/local verification only. It does not authorize a Provider request, campaign execution, business write, browser use, or main merge.

## Frozen limits and execution identity

The new identity must reuse the existing campaign contract without increasing it: 16 Provider dispatches, 10 MCP `tools/call` attempts, USD 10.50 application reservation cap, USD 0.645600 per Provider reservation, 12,000 input-token cap, 30-second request timeout, one in-flight Provider call, and zero retries. Ordinary Run defaults remain 8 MODEL / 6 MCP; only the scoped campaign identity may use 16 / 10.

The new identity uses a separate evidence directory, pending authorization record, Domain DB path, and Checkpoint DB path. During this preparation, its claim state is `WAITING_FOR_EXPLICIT_PAID_AUTHORIZATION`; it is not a consumed or executable paid one-shot claim. The named runtime files must remain absent until a separately authorized execution.

## Acceptance cases

1. The new identity is accepted by the fresh campaign schema and receives exactly the frozen 16/10 campaign caps; normal unscoped runs remain 8/6.
2. A fresh isolated database can bootstrap trusted demo principals, initialize an empty new campaign ledger, prepare `ar03-order` with a same-Event `202/ACKNOWLEDGED` Delivery and `QUEUED` Receiver, and complete a deterministic formal API/Worker/MCP read-only preview.
3. No Provider HTTP is made; fixture model dispatch counts are explicitly distinguished from Provider transport requests; protected business-write tables remain empty.
4. The new preflight is bound to the accepted safe base, the new branch, frozen Cases blob, new evidence path, and new runtime paths. Wrong branch, an existing execution claim/output, or any existing new runtime DB/checkpoint artifact fails closed.
5. `create_assistant_model()` rejects the prepared identity even if global Provider opt-in and local credentials are present. The new Runner's `--execute-once` command refuses before creating a paid claim or runtime.
6. The old experiment claim, old budget ledger/results/traces, old runtime files, frozen Gold, and `main` remain unchanged.

## Evidence and stop line

Use deterministic models, local SQLite, existing trusted bootstrap/API/Worker/MCP and HTTPX MockTransport only. Save full raw test/preflight logs in the local private evidence directory; publish only a redacted summary without local paths, credentials, raw browser state, or private runtime data. Do not send a real Provider request. Stop after the isolated preflight reports ready with paid execution disabled; request a separate authorization before any paid dispatch.

## Six-question check

1. **User change:** No new user-facing capability is added; this removes an obsolete branch/identity binding that prevented the already approved material-investigation campaign from reaching a safe preflight.
2. **Agent decision:** No Agent policy or tool-choice behavior changes; the future model remains free to choose any authorized read-only action under the frozen Gold.
3. **Observation-driven behavior:** Not exercised with a real model here; the free preview only confirms the current same-Event fixture is readable through the formal path.
4. **Constraints:** The pending identity must block premature paid execution; the positive fresh-database and formal Worker preview proves authorized preparation is not accidentally rejected. Existing campaign caps and zero-write rules stay fixed.
5. **Simplification:** Reuse the existing Runner, campaign ledger, bootstrap, Assistant, MCP, and Domain checks; only parameterize the path/identity binding and add the smallest per-ID allowlist entry.
6. **Evidence and stop:** RED/GREEN tests, zero-cost formal preview, exact final preflight output, historical hash checks, and the final Diff are required. Stop at `PREFLIGHT_READY_AWAITING_PAID_AUTHORIZATION`.
