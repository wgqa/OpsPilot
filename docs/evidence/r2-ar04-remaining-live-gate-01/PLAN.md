# R2-AR04-REMAINING-LIVE-GATE-01

- **Candidate status:** `ACCEPTANCE_CANDIDATE` pending independent review
- **Base:** `fa4cd8a7ea6dd36babccbbfc5fcdb7a179729fd3`
- **Branch:** `codex/r2-ar04-remaining-live-gate-01`
- **Worktree:** reused `ar04a-context-journey-01`; no new Worktree
- **Provider requests in this task:** 0
- **Provider cost in this task:** USD 0

## Scope

Prepare a version-bound, authorization-gated runner for two historical-recall cases. The production summarizer, Memory, Gold, previous experiment results and `main` are outside the change scope. The candidate changes only this evidence directory.

| Case | Strategy | Final-prompt target |
|---|---|---|
| Q02-B | ROLLING_SUMMARY | `endpoint=/callback`, source sequence 3 |
| Q06-B | ROLLING_SUMMARY | `v1.2 -> v1.3` and `max_attempts 3 -> 5`, source sequence 11 |

Each Case gets its own 29-row history recreation, Session, Domain database, Checkpoint, Assistant Run and Runtime Grant. Gold and scoring rules stay outside model requests. `tool_choice=none`; no external MCP action is available.

## Token and request contract

- Maximum input: 12,000 tokens per request.
- Summary generation: 1,024 tokens per request.
- Runtime Grant output ceiling: 1,024 tokens.
- Ordinary answer request: 512 tokens.
- Persisted Domain summary: 512 tokens.
- Four summary requests, two answer requests, six Provider requests maximum.
- No automatic retries; first failed Case stops the matrix; UNKNOWN remains reserved and stops later cases.
- Task hard cap for any future authorization: USD 0.06.

The accepted production code creates the answer model using the Runtime Grant's output ceiling, then separately binds the compressor to the summary ceiling. This Runner applies a local adapter after Grant validation: the base answer model remains at 512 and `_compression_model` independently binds summary requests to 1,024. A purpose-aware transport rejects any wire request whose `max_tokens` differs from its purpose contract. No production file was changed.

## Six review questions

1. **User-visible behavior:** this is a bounded learning and readiness task, not a new business capability claim.
2. **Agent decision space:** the future history-recall requests can answer or abstain; tools remain disabled only for this recall experiment.
3. **Observation and next action:** the Runner checks the actual final prompt and source sequence; missing target facts block readiness instead of being inferred from Mock answers.
4. **Hard boundaries:** stale authorization, changed Blob/source, excess request/output budget, revoked source and UNKNOWN status must stop before an unauthorized or duplicate send.
5. **Reuse and deletion:** the accepted V2 source validator, frozen reply validator, Assistant Runtime Grant, Domain persistence, shared budget ledger and stop behavior are reused. No second business runtime or Memory store is introduced.
6. **Evidence and stop line:** two full Mock cases plus the truncation, source-invalidation, cap, stale-authorization and UNKNOWN gates may establish `READY_FOR_NEW_LIVE_AUTHORIZATION`; only a later separately authorized run can establish live L2/L3 quality.

## Governance freeze

The actual Base checkout was read before implementation. Blob inventory:

| File | Blob |
|---|---|
| `PROJECT_NORTH_STAR.md` | `43dabda468506717c6956e676dfad4304c4f38e6` |
| `AGENTS.md` | `807b928686a4dd2cac7b15b3c354b9943c93c910` |
| `.agents/skills/opspilot-slice-review/SKILL.md` | `d405c8d413d633824b279202cc1503dab4cf0b03` |
| `docs/baseline/v1.0-implementation-baseline.md` | `30e18d7ddbade7cdf7712d035d6fd8488bcb9676` |
| `opspilot/domain/chat.py` | `f78ff94586af56b94b9585c5e7f8abeb5b006ad6` |
| `opspilot/assistant.py` | `288559c6e9b77549939501f4cedb1a8097a79918` |

No AR-04 Deferred Gate applies to this isolated runner task. Existing C06 RED and historical experiment artifacts remain frozen and are checked by the reused V2 validator.

## Stop and evidence boundary

The 2026-11-15 official pricing snapshot is reused only for conservative offline arithmetic; this task does not claim current price verification. Any future live send must attach a fresh official DeepSeek price snapshot and a new authorization for this exact task/base/case matrix. No authorization file is produced here. Mock outputs do not constitute L3 evidence.
