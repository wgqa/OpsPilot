# R2-AR04-LIVE-RECHECK-V2-FINAL-01

## Scope and freeze

- Task Base: `1f0b27b9f14686a4c33bd33c212bb5d7a007280e`.
- Candidate branch: `codex/r2-ar04-live-recheck-v2-final-01`.
- Product/learning question: after the summary persistence fixes, do the three frozen historical recall cases deliver the required facts in the real final model input and answer them correctly?
- This delivery is preparation only. Provider sends are **0**, provider cost is **USD 0**, no external MCP is called, and no live answer is claimed.
- The final task will not edit production Context code, add Memory, change Gold, expand the matrix, reuse an old Grant, or merge `main`.

## Frozen matrix

| Case | Strategy | Required fact |
|---|---|---|
| Q02-A | HYBRID | Early `endpoint=/callback` |
| Q02-B | ROLLING_SUMMARY | Early `endpoint=/callback` |
| Q06-B | ROLLING_SUMMARY | `v1.2 → v1.3`; `max_attempts 3 → 5` |

Each case starts from its own copy of the 29-message frozen synthetic history, with independent Domain, Checkpoint, Session, Assistant Run and isolated Runtime Grant. Gold and rubric remain outside every model request. The response source table is the corrected V2 table; Q02-A uses the exact frozen response ID `c3435ff4-fc27-4ffb-b053-bbfcabc600e0`. Source IDs, Trace digest and response body digest are validated before Mock dispatch.

## Future live limits

- DeepSeek `deepseek-flash`; `DeepSeek-V4.1-Flash-1017`; non-thinking; temperature 0; `tool_choice=none`.
- Up to 6 summary requests + 3 answer requests; 9 total; no automatic retries; stop on first failed Case; never auto-continue unused slots.
- One shared persistent ledger across all three temporary Grants, with a USD 0.06 hard cap. A worst-case request reserves 4,215 microdollars (12,000 input tokens at $0.30/M plus 512 output tokens at $1.20/M); nine requests reserve at most USD 0.037935, below the cap.
- Price/model snapshot is from official DeepSeek documentation checked 2026-11-15: [pricing](https://api-docs.deepseek.com/quick_start/pricing/). Recheck model and price immediately before any later live send. The snapshot is not carried forward as price authorization.
- A new, exact-scope authorization manifest for this task is required. Old retention/ABC/V2 authorization values are rejected. No authorization manifest was created for this preparation.

## Six review questions

1. **User change:** no new business behavior is claimed; this makes a bounded context-recall learning experiment auditable and ready for a separate authorized live run.
2. **Agent decisions:** production autonomy is unchanged. The live recall track is configured for direct answer or safe abstention, without tool use.
3. **Observation-driven action:** when the current final prompt has a sourced `/callback`, a supported answer is possible; if the required fact is absent, the model must say it cannot establish the endpoint. L2 evidence and L3 answer quality are scored separately.
4. **New constraints:** authorization freshness, fixed case/model/price/usage bounds and UNKNOWN stop behavior prevent unauthorized spending, matrix drift and duplicate sends while leaving a valid one-shot answer path available.
5. **Simplification:** the accepted V2 validator, Assistant Runtime Grant, Domain path and global budget ledger are reused. No second business runtime, Memory store or general evaluation platform is added.
6. **Evidence and stop:** 3/3 full-path Mock, source provenance, zero-cost Grant preflight and failure-stop tests are run. Stop at `READY_FOR_LIVE_AUTHORIZATION`; actual L2/L3 and AR-04 closure remain unverified.

## Governance and evidence level

The target Base files were reopened and read: `PROJECT_NORTH_STAR.md` Blob `43dabda468506717c6956e676dfad4304c4f38e6`, `AGENTS.md` Blob `807b928686a4dd2cac7b15b3c354b9943c93c910`, Review Skill Blob `d405c8d413d633824b279202cc1503dab4cf0b03`, and applicable v1.0 baseline Blob `30e18d7ddbade7cdf7712d035d6fd8488bcb9676`. No AR-04 Deferred Gate was found; unrelated vNext Deferred Gates do not apply. The current production pins are `chat.py` `d10f495cadc4c2006504ecd87e5c02947f87e80b` and `assistant.py` `4fa1aaa7059cf6478fce4c262b8c1876df9a7dcb`.

Mock results prove only the deterministic fixture and Assistant/Domain path. The zero-cost preflight proves local environment presence, isolated Grant binding and construction with Mock transport; it does not authenticate the Provider or prove model quality. Live L2, live L3 and independent Main Agent review are `NOT_RUN`.
