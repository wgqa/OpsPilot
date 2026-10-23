# M4-03-HF-01 Frozen Acceptance Plan

Baseline: `main@30b1b466fbdd2c58e36c90b510ba04f7ee6af3d0`

This file and the paired RED tests freeze the HF-01 acceptance surface before
implementation. The work is limited to S3 authorization currentness, S3 SLA
currentness, and races at the existing S3 handoff transaction boundary.

## Authorization contract

1. S3 resource discovery, first TaskBinding selection, and every later read use
   one Domain authorization decision over current principal status, credential
   relationship, route Scope Policy, Principal Grant, and their versions.
2. Missing, malformed, or insufficient authorization state fails closed.
   Current Evidence versions include Scope Policy and Grant versions; a policy
   or grant version change invalidates existing Evidence even if access is later
   restored.
3. MCP order, delivery, and receiver facts; current diagnosis; Chat current
   facts; Web resource reads; and new handoff submission must not expose or use
   restricted facts after authorization is revoked.
4. A historical accepted HandoffReceipt is immutable. Only an independent
   same-tenant APPROVER audit read may retrieve it after S3 authorization is
   revoked. Such a read is historical and cannot create or execute a handoff.
5. Restoring authorization does not revive Evidence from the prior grant or
   policy version; the Task must collect new current Evidence before handoff.

## SLA contract

1. `WAIT_FOR_RECEIVER_PROCESSING` is current only before the frozen receiver
   processing SLA deadline. Evidence TTL does not extend this deadline.
2. At/after the deadline, the persisted immutable WAIT diagnosis is reported as
   invalidated, Web/Chat expose no handoff eligibility, and submission using it
   is rejected without Queue, Receipt, command, or Outbox writes.
3. A fresh investigation at the current time over trusted current facts yields
   `CONTACT_RECEIVER_OPERATOR` and may be submitted through the existing
   owner-confirmed transaction.
4. Tests inject a deterministic clock; no wall-clock sleep is an acceptance
   method.

## Concurrency and recovery matrix

For each race, use independent SQLite connections and accept only a legal
serialized result: either handoff commits first and the competing mutation is
rejected, or the correction/abort/revocation commits first and handoff is
rejected. No losing path may leave a partial Queue, Receipt, command, or Outbox.

- Handoff versus `CORRECT_TASK_INPUT`.
- Handoff versus Task cancellation.
- Handoff versus Scope Grant revocation.
- Same request retry and different operation IDs produce one immutable receipt.
- A committed response-loss retry replays the existing receipt only.
- An old page diagnosis submitted after the SLA deadline is rejected.

## Verification commands and boundaries

- Freeze+RED: `.venv/Scripts/python.exe -m pytest -q tests/test_m4_03_hf_01.py`
- GREEN: the same focused suite, existing S3/M4-02 regressions, S1/S2 security
  regressions, then the complete `pytest` suite.
- At least one TestClient HTTP route and one in-process MCP tool call must show
  authorization denial after revocation. No paid model call is needed or
  permitted for HF-01 acceptance.
- Preserve the historical M4-03 Gold, reports, receipts, and prior experiment
  directories. No business scenario, Knowledge/Memory feature, or authorization
  framework is added.
