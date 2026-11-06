# AR-05-S1-D3-CLOSE-01

## Scope

Offline implementation and deterministic local verification of the post-approval S1/D3 closeout. The user-visible path is one Assistant Session through trusted S1 investigation, independent approval, approval-time fact revalidation, CAS repair, same-identity local HTTP verification, frozen report, independent delivery, and Session outcome readback.

## Frozen boundaries

- Base candidate: `ca7706d14f155bda237fcb4057dae8606b78c41f` on `codex/ar05-s1-session-bridge-01`.
- Isolated work branch: `codex/ar05-s1-d3-close-01`.
- Main remains `60eee87bfe3cca522011316cb4cd2c0064ad291b`.
- Preserve TaskBinding, independent approver/executor identities, ActionIntent, CAS, VerificationReceipt, report and delivery contracts.
- No paid Provider request, production write, browser automation, or main merge.
- Browser remains `NOT_RUN` under the existing STOP.

## Evidence plan

1. Freeze the old missing-revalidation RED.
2. Prove fresh facts can proceed and stale, drifted, disabled, and UNKNOWN facts cannot create a REPAIR intent or ledger.
3. Run the same-Session local API/Worker/MCP/HTTP/SQLite journey through both reapproval and final delivery.
4. Run the affected backend regression set and frontend type/build checks.

This verifies the approved local demo path; it does not claim live Provider or browser acceptance.
