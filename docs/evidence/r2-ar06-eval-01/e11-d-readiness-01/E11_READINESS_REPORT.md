# E11-D readiness report

## Result

`ACCEPTANCE_CANDIDATE` for offline readiness evidence only. This is not a Gold score or a real-model pass. Live status: `NOT_READY_FOR_LIVE`.

## Offline journey evidence

- Exact frozen question loaded from CASES.json; SHA256 `721177e0c907421ab13927c9ac10bb23ba5b568c365d4ff58ef33ad2887a39be` matches trace.
- Ordinary CHAT_READONLY: Run `run-3eaf196b-1997-49cf-842a-1194d05361c0` = `SUCCEEDED`; durable `CHAT_MODEL` answer linked to source message `message-2a8cbe74-005b-4ba4-9eea-01a31b493306`. No task or handoff existed before the controlled Task API step.
- Investigation: Run `run-73b8727d-4e77-4ab5-a9ff-474573c7bfda` = `SUCCEEDED`; tenant `tenant-a`, actor `support-a`, role SUPPORT, service `orders-demo`, integration `integration-a`, principal `principal-a`.
- Current local Probe/Authz share Request ID `6d4315795a9b9bb7`. Probe 403; Authz DENY / SCOPE_INSUFFICIENT, current. Gate creates one DIAGNOSED receipt and one frozen HANDOFF_READY draft.
- Before the test-client explicit submit: queue/receipt/outbox `0/0/0`, submitted false. After simulated confirmation: `SCOPE_ESCALATED / PENDING_REVIEW`, exactly one receipt/queue/outbox, `scope_authorized=false`, `recovered=false`. Scope/Policy snapshot unchanged.
- Fixture model invocations: 4; local MCP calls: 2; fixture-only Usage metadata: 362 tokens total; Provider HTTP: 0; Grants: 0; external writes: 0.

## Limits and remaining review

- Fixture responses prove wiring and deterministic boundaries only; they do not prove model autonomy or semantic diagnosis.
- The handoff draft has no dedicated risk-summary field verified, and UI risk rendering was not tested.
- Live Investigator path remains behind a legacy opt-in with no demonstrated Runtime Grant/Spend integration; do not enable it for a live run.
- The task card's asserted independent E10 PARTIAL verdict was not located as a signed independent verdict in this checkout; provenance remains UNVERIFIED, while the frozen partial ceiling is preserved.
- E11 readiness does not authorize real handoff, scope change, grant creation, or Provider spend.

The complete model-visible messages, tool schema digests, Fixture decisions, and usage metadata are embedded in `E11_ASSISTANT_AND_TASK_TRACE.json`. See also `E11_TEST_LOG.txt`, `E11_NEGATIVE_BOUNDARY_RESULT.json`, and `E11_EVIDENCE_INDEX.json`.
