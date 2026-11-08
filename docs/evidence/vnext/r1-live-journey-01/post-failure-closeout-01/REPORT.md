# R1-LIVE-JOURNEY-01 POST-FAILURE-CLOSEOUT-01

**Result: ACCEPTANCE_CANDIDATE**

**Base:** `d3735d3738c7769a7406f03b43ade29d5eb51d35`
**Branch:** `codex/r1-live-journey-01`

## User-facing outcome

The saved real model decisions were replayed offline through the formal Assistant path. J1-01's single protocol lookup succeeded. J2-01's three captured proposals (protocol discovery, Delivery, Receiver) all executed through MCP. The bound local fixture returned the same `event-current` Delivery as HTTP 202/ACKNOWLEDGED and Receiver as PROCESSED, with current Evidence/Observation IDs. The next model request included those tool responses. Its final answer was a deterministic offline Fixture, not a real model answer.

## What we learned

1. **Original failure root cause:** not fully confirmed. We confirmed an error-classification defect: saved responses with valid Usage remained `RESPONSE_STORED`, while Assistant recorded `UNKNOWN` and showed the user an incorrect charge-unknown notice. The original exception cause was not stored, so the historical reason ToolNode never ran remains unknown.
2. **Captured tools through MCP:** yes. Exact captured tool-call IDs and arguments matched the private Provider response and the public trace. One-tool and three-tool proposals ran through current Assistant/ToolNode/MCP/Domain. All four captured responses were audited; J1-01 and J2-01 were replayed. Gzip decoding was exercised by synthetically gzipping the captured JSON body; the old capture did not retain Content-Encoding, so live gzip is not established.
3. **State and user notice:** known Usage plus SDK response-processing failure is now `assistant_calls=FAILED`, with exception class/cause-type names, while Runtime remains `RESPONSE_STORED` and its settlement is preserved. The notice says the response and Usage were recorded, the Assistant did not finish, and no retry will occur. UNKNOWN remains `UNKNOWN`, keeps its reserve, and receives an explicit no-retry notice. Not-sent and Usage-over-bound have distinct notices.
4. **Remaining blockers before a new real run:** this closeout provides offline evidence only. The historical raw capture lacks Content-Encoding and the original exception chain; a new real Provider campaign needs separate user authorization and must record those fields before transport/result processing. The actual model's continuation after MCP and final user answer were not replayed as real model behavior.
5. **Minimum next authorization:** one explicitly identified new isolated campaign, with model and frozen task input, request and spend caps, timeout, zero retry, unique Runtime Grant/ledger/database, and hard stop on UNKNOWN/Usage invalidity. No old claim or campaign ledger should be reused. If the goal is only to confirm the transport symptom, authorize a single bounded request; if the goal is product outcome, authorize the specific complete user journey and its capped calls instead.

## Code and evidence

`opspilot/assistant.py` classifies failures from the durable Runtime dispatch state instead of mapping every stored response-processing exception to UNKNOWN. It preserves UNKNOWN spend and does not retry. `tests/test_r1_live_failure_closeout.py` replays captured proposals through formal API/Worker/Assistant/ToolNode/MCP with MockTransport and checks the resulting local observations, budget states, notices, and zero business side effects.

- Targeted closeout: 9/9 passed.
- Runtime Grant and R1 J1/J2 regression: 44/44 passed.
- Full repository pytest: not run.
- New real Provider requests: 0; browser runs: 0; external business writes: 0.
- Original live ledger and raw trace hashes: unchanged; see `CAPTURE_AUDIT.md`.
- Start SHA and North Star/AGENTS/Skill Blob record: see `PREFLIGHT.md`.

The old campaign remains `PARTIAL`; this report does not turn it into a live PASS. The original failed Runs were not edited.
