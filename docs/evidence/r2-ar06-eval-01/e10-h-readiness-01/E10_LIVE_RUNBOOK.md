# E10-H First Live Runbook (Proposal Only)

**Authorization in this task:** offline only. This document does not create a Grant or authorize a Provider request.

## Prepared offline Runtime

The isolated Runtime used for the final offline API/Worker evidence is:

`user-demo-r2-e10h-readiness-02`

It was initialized only because the path was absent, using the existing `r2-e07-queued` fixture initializer. It contains synthetic source Sessions/Tasks, an ACTIVE confirmed A, a formally REVOKED B, and an ACTIVE source-invalid variant. It has a separate Domain DB and Checkpoint DB, no Runtime Grant, zero Provider requests, and zero spend. It is an offline fixture environment, not a scored Live result.

The final test service was an in-process FastAPI `TestClient` with the Worker and deterministic Fixture Model injected. The earlier offline iteration `user-demo-r2-e10h-readiness-01` is also preserved and was not reset; final evidence is from `-02`. Do not claim the normal User Demo launcher was used. The normal launcher creates the configured model factory and does not inject this test Fixture Model.

## Preconditions for any future Live execution

1. Main Agent accepts this offline candidate and explicitly authorizes a single E10-H Live Run and its application-cost ceiling.
2. Recheck the exact working code SHA, E10 frozen-input SHA, Runbook, and whether the prepared Runtime has been changed since this evidence was collected.
3. Confirm no active API/Worker process is using `user-demo-r2-e10h-readiness-02`. Do not reset it. Preserve its fixture rows, source refs and events.
4. Confirm the only effective target Memory is A. B remains REVOKED at version 2; the source-invalid variant remains excluded. Inspect the current Context Manifest before authorizing the target Run.
5. Confirm target SUPPORT identity `tenant-a / support-a`; current observations must be obtained only through the newly created target TaskBinding and local read-only MCP tools.
6. Review DeepSeek's official current pricing and the local `deepseek-flash` endpoint/model/price version at execution time. Calculate the application maximum from actual per-call input/output caps, existing per-Run dispatch cap, and a single-run Grant. Do not reuse another Runtime's Grant or spend pool.
7. Only after separate authorization, use the existing `runtime_admin.py configure` interactive confirmation for this Runtime. Do not bypass its confirmation. Run the normal Live Preflight and require Runtime/Grant/path agreement, zero prior provider sends, zero UNKNOWN, and adequate remaining balance.
8. Start with `Start-UserDemo.ps1 -Profile S1 -Mode Live -RuntimeName user-demo-r2-e10h-readiness-02`; this is a proposed command and was **not** run in this task. Stop safely with the existing `Stop-UserDemo.ps1 -RuntimeName user-demo-r2-e10h-readiness-02` after evidence export.
9. Create a new target Session and submit the exact frozen E10-H text once through the formal Assistant API/UI. Never replay it after UNKNOWN or an unclear submission outcome. Do not send scoring labels, expected outcomes, or the Fixture Model's response policy.
10. Export the target Session Trace using the existing redacted Live evidence exporter. Record input SHA, Session/Task/Run IDs, selected/excluded Memory IDs and versions, actual model wire, MCP observations, Event/Task association, provider Response IDs, usage, spend, and final answer.

## Stop conditions

Stop before sending if identity, Runtime path, Grant, model configuration, current Memory lifecycle, TaskBinding or fixture facts differ from the accepted evidence. Stop after the first send on UNKNOWN, timeout, unclear HTTP submission, budget/usage inconsistency, source invalidation, or any unauthorized action. Preserve all database, Checkpoint, Grant, spend and Trace records; do not retry.

## Readiness limitation

The offline evidence proves a fresh Runtime can hold the correct data and that the formal TestClient/Worker/MCP route composes correctly. It does not verify `Start-UserDemo.ps1 -Mode Live`, Live Preflight, a Runtime Grant, real DeepSeek input/usage, or manual browser interaction. Those checks and a separate cost authorization remain required. The fixture-only temp passwords used by the test harness are not reported; use the prepared Runtime's local credentials, not the TestClient fixture values.
