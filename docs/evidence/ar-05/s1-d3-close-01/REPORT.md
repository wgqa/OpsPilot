# AR-05-S1-D3-CLOSE-01 — implementation report

**Status: `ACCEPTANCE_CANDIDATE`**

## User-visible result

The deterministic local journey starts from the user's original Assistant question in one Session, creates and runs the trusted S1 investigation, obtains an independent approval, and rechecks the approved Plan before any repair. The first recheck detects changed configuration facts and returns `REAPPROVAL_REQUIRED`; after a new Plan and independent approval, the second recheck returns `VALID`. The existing D3 path then commits one local CAS repair, verifies the same demo business identity through HTTP 200, freezes a report, performs a separate delivery, and reads back `DELIVERED` in the original Session.

The saved trace links the original message, Task, investigation Run, both approval-resume Runs, revalidation receipts, action ledgers, verification, delivery receipt, and Session readback: [TRACE.json](TRACE.json). It is a deterministic fixture/model run through the formal API/Worker, local MCP/HTTP, and SQLite path—not a live model run or browser acceptance.

## Implementation

- Added an additive `d3_revalidation_receipts` table. Approval resume now re-reads TaskBinding-scoped integration, principal, auth policy, and endpoint facts, stores fresh observations/evidence, reevaluates the Gate, and records a digest-protected receipt.
- A still-valid Plan receives `VALID`; changed facts produce a replacement Plan and require a new independent approval; stale evidence without an eligible resume Run, invalid facts, source failure, or unknown results do not authorize REPAIR.
- Both ActionIntent creation and `execute_repair` require a recent, matching `VALID` receipt, current evidence digests and versions, and the existing executor/approval/Plan checks. Existing committed repair replay continues from its original pre-write validation receipt.
- The existing Investigator graph runs revalidation after approval and before repair. The existing TaskControl approval-resume path reuses the original checkpoint thread for reapproval; it does not introduce a second workflow or write path.
- The existing Session outcome projection now reports revalidation blocked, unknown, reapproval required, repair committed, recovered-not-delivered, and delivered without deriving business state from Assistant prose.
- Updated direct D3 tests to satisfy the new approved-write contract by explicitly revalidating first. No Gold or historical RED was changed.

## Verification

- New revalidation negatives: 6/6 passed, including expired source, drifted configuration, disabled principal, missing approval-time validation, and injected source failure resulting in `UNKNOWN` with zero repair intent/ledger.
- Relevant backend regression: 68/68 passed across the AR-05 Session bridge, D2 investigation, D3 actions, TaskControl, and web approval tests. Command and raw output: [backend-revalidation-final-02.txt](logs/backend-revalidation-final-02.txt).
- Frontend `npm run build` (including vue-tsc) passed; changed-file ESLint passed; Node bridge unit tests passed 4 with 1 trace-dependent skip. Full ESLint remains blocked by the two unrelated existing errors documented in [FAILURES.md](FAILURES.md).
- Source/test `git diff --check` passed before raw logs were staged. Captured runner logs are kept unchanged and contain normal trailing whitespace from Python source/traceback output.

## Authorization and effects

- Real Provider requests: **0**.
- Browser automation: **NOT_RUN_HISTORICAL_STOP**.
- External/production business writes: **0**.
- Isolated demo effects: one CAS repair and one ticket entry, both represented by existing D3 ledgers and receipts.
- Main was not modified or merged.

## Six review questions

1. **User change:** The user can now continue from an approved-but-not-yet-repaired result to a verified and delivered local S1 outcome in the original Session.
2. **Agent decision:** The formal Investigator still chooses its allowed read-only tools during investigation. Approval, revalidation, repair, verification, and delivery remain trusted program/domain responsibilities; no real model decision-quality improvement is claimed.
3. **Observation driven:** A changed configuration after the first approval changed the next safe action to a new Plan and reapproval. A subsequent matching fresh read allowed the existing write path. Drift, disabled principal, expiry, and UNKNOWN are negative cases.
4. **New constraint:** The new gate is specifically approval-time evidence revalidation before REPAIR. It blocks unsafe stale/changed/unknown facts while the fresh unchanged path passes. Existing TaskBinding, approval, CAS, idempotency, and action boundaries remain active.
5. **Reuse/simplification:** Reused D2 fact readers, existing TaskControl approval resume, Investigator, D3 ActionIntent/CAS/verifier/delivery, and Session outcome APIs. Added one receipt table because no persistent revalidation receipt existed; no new Agent, graph, service, or business write API.
6. **Evidence/stop:** Offline deterministic local evidence and targeted regressions are available. Full pytest, live Provider, browser, and production write acceptance are not claimed. Stop here for independent review; do not merge main or start the next slice.

## Remaining limits

The evidence proves the deterministic local closure and code-level fail-closed paths. Browser display is still unverified under the historical STOP. The implementation is not accepted until the main agent independently reviews the exact candidate diff, trace, and evidence.
