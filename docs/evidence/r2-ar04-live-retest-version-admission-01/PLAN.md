# R2-AR04 Live Retest Version Admission

**Status:** `ACCEPTANCE_CANDIDATE`
**Execution scope:** isolated offline preparation only
**Base:** `92c8823c9853a23f2cdb2fee7f0fec985d230399`

## Frozen scope

- Cases: `Q02-B`, then `Q06-B`.
- Production `opspilot/domain/chat.py` Blob: `6a57360de6f5579fa65dc008de4fcf37148c43f0`.
- Production `opspilot/assistant.py` Blob: `288559c6e9b77549939501f4cedb1a8097a79918`.
- Reuse the accepted Assistant/Domain integration and strict remaining-live gate.
- Keep the earlier live runner, Gold, Rubric, source Traces, Cost Ledgers and failure records unchanged.

## Offline acceptance

Each Case starts from its frozen 29-message history in its own isolated Domain, Checkpoint, Session, Assistant Run and temporary Runtime Grant. The accepted runtime and Domain path executes two summary attempts and one answer attempt per Case. The HTTP boundary is `httpx.MockTransport`; the test process installs the existing external-network audit guard.

The canonical Mock is in `mock_run_02/`. Its six MockTransport sends comprise four summaries and two answers. The historical first-summary replies are trace-, request-, response-ID- and digest-bound. Later summary projections and final answers are marked synthetic. The old invalid Q06-B second-round response is not replayed.

## Authorization boundary

No valid paid authorization was created and no Live execution was invoked. The retained Live path still uses the existing strict manifest validator, now bound to this task's unique Task ID, Base, Runner digest, Mock digest, source manifest and production Blobs. A future run needs new explicit user authorization and a fresh official model/price snapshot. The current preflight is technical readiness only; it is not permission to send.
