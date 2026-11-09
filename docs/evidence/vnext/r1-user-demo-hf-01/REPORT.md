# R1 User Demo HF-01 — Candidate Report

## Scope and result

Base: `20c12276045e6a68e8de029f71c64a0cc90e2c3e`

Branch: `codex/r1-user-demo-hf-01`

North Star blob at base: `43dabda468506717c6956e676dfad4304c4f38e6`

AGENTS blob at base: `807b928686a4dd2cac7b15b3c354b9943c93c910`

Review Skill blob at base: `d405c8d413d633824b279202cc1503dab4cf0b03`
Implementation status: `ACCEPTANCE_CANDIDATE` (pending independent review)

This candidate makes three bounded changes:

1. The user-demo launcher now configures the browser page origin as `http://127.0.0.1:5173`, while the Vite proxy target remains `http://127.0.0.1:8000`. Origin and CSRF checks remain enabled.
2. Before each model dispatch, the Assistant rebuilds the historical message prefix from the current Domain context projection. The checkpoint is retained for execution, but stale historical content is not trusted as Provider input. Current-Run tool proposals and their paired ToolMessages are appended unchanged, preserving tool-call IDs.
3. Runtime Grant `claim_send` now checks the current Worker owner/epoch and the live Assistant Run / TaskControl state inside the same SQLite write transaction that grants send authority. Taskless `ASSISTANT_V1` Runs remain supported. A reservation without `SEND_GRANTED` closes as `NOT_DISPATCHED`; a request that already received send authority retains existing UNKNOWN / stored-response handling.

## Evidence

- RED reproductions are preserved in `ORIGIN_RED.txt`, `SEND_AUTHORITY_RED.txt`, and `CHECKPOINT_CONTEXT_RED.txt`.
- The final slice tests pass 4/4, including valid 5173-origin login/session/message, rejection of the 8000 origin, CSRF rejection, aborted-Task and stale-Worker send denial, and stale checkpoint-summary removal with current tool-call correlation preserved.
- The ordered Runtime Grant / legacy isolation / campaign budget selection passes 78/78. A separate R1 Journey plus stored-response failure-closeout selection passes 14/14. The existing AR-04A invalidated-summary test passes 1/1.
- These are offline tests using isolated SQLite and mock/fixture transports. They are not browser or live-provider acceptance.

## Third-party reproduction artifact

The task card's separate third-party raw capture was not present in the candidate checkout. `ORIGINAL_FINDING.md` records this as `UNVERIFIED`; it was not reconstructed. Existing project failure history is cited there by SHA-256 and was left unchanged.

## Execution limits

Real Provider HTTP: `0`. Browser automation: `0`. External business writes: `0`. No main-branch changes or merges were made. The candidate does not claim live browser validation.

See `RESULTS.json`, `TEST_LOG.txt`, and the individual raw test logs for command-level results and the incomplete initial combined run.

## Six review dimensions

1. **User change:** a browser served at 5173 can use the existing API proxy and perform the normal login/session/message sequence without misconfiguring the trusted origin.
2. **Agent choice:** the change does not prescribe Knowledge/MCP/Skill order or alter the model's legal tool-selection space.
3. **Observation and source:** Provider history is rebuilt from the fresh Domain projection; same-Run tool calls and returned observations remain linked by their original call IDs.
4. **Constraint:** Origin/CSRF checks, TaskBinding, TaskControl, Worker fencing, persistent reservation, and UNKNOWN handling remain enforced.
5. **Simplification:** no new Context subsystem or Provider gateway was added; the existing Domain projection, Runtime Grant ledger, and Worker lease are reused.
6. **Evidence and stop:** only offline tests ran; the missing third-party raw capture, incomplete early run, and absence of browser/live-provider evidence are stated without claiming broader acceptance.
