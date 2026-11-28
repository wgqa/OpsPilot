# R2-AR04-SUMMARY-FACT-RETENTION-HF-01 Plan

## Scope and frozen baseline

- Base: `1cba32753f22e0a610aa7654ab5dc6cddd94ccf2`
- Candidate branch: `codex/r2-ar04-summary-fact-retention-hf01`
- Worktree: reused `D:/学习/agent新项目/.worktrees/ar04a-context-journey-01`; no new worktree.
- Baseline HEAD at start: Base above; tracked tree clean. Existing unrelated `.pytest-tmp/` directories were preserved.
- Remote main observed at start: `60eee87bfe3cca522011316cb4cd2c0064ad291b`; candidate remote branch was absent.
- Scope: minimally change `opspilot/domain/chat.py` summary selection, add deterministic regressions and evidence. No live provider calls, charges, external MCP, production database writes, Gold edits, main merge, or changes to historical Trace/RESULTS/ledger/C06 RED.
- User journey: preserve source-backed details across repeated chat summarization so later read-only questions can use earlier configuration and formal corrections. This is an application-context retention fix, not a claim of improved model reasoning or L3 live semantics.

## Required start-of-work evidence

Read from the target Base checkout:

| File | Blob SHA | Read |
|---|---|---|
| `PROJECT_NORTH_STAR.md` | `43dabda468506717c6956e676dfad4304c4f38e6` | Yes |
| `AGENTS.md` | `807b928686a4dd2cac7b15b3c354b9943c93c910` | Yes |
| `.agents/skills/opspilot-slice-review/SKILL.md` | `d405c8d413d633824b279202cc1503dab4cf0b03` | Yes |

The active task card authorized offline implementation. The previous ABC live report, raw Trace, currentness/Grant tests and C06 RED evidence were reviewed. No additional applicable R2 deferred gate was found; the R2 design review is historical and not a current implementation contract. The relevant locked safety behavior remains source-currentness validation before summary use.

## Change

The existing `_compact_summary_document()` used recency/category ordering and bounded clipping. Replace that selection order with a small source-aware anchor pass for earliest user assertion, earliest formal correction, a self-contained timeline item, constraints, and unresolved work. Fill remaining space through the existing bounded category round-robin. Mark clipped text with an ellipsis; if a valid required anchor cannot fit the unchanged 512-token cap, raise `CONTEXT_SUMMARY_FACT_RETENTION_BUDGET_EXCEEDED`. Derive optional summary `sequence` from validated source sequence references in `_validate_summary_document()` rather than accepting a model-authored value.

The JSON fields, existing summary persistence/currentness rules, Runtime invocation contract, compaction strategies and output cap remain in place. No domain-specific values such as `/callback`, `req-483`, or `v1.3` are matched by production code. There is no new summary store, Memory service, embedding index or retry loop.

## Six-question slice review (Skill B)

1. **User change:** the application should carry an early callback setting and version/correction facts through repeated summaries so a later user question can receive a source-backed answer. The patch changes historical context retention only; this run proves deterministic L2 visibility, not live semantic improvement.
2. **Agent decision:** the model still writes summaries and decides what to answer or whether to abstain. The application now reserves bounded space for source-linked categories; it does not prescribe a tool sequence or answer.
3. **Observation-driven:** with a valid source containing an early endpoint, retain that assertion; after source invalidation, do not send it. With a formal correction, preserve old value, replacement and reason; with only a new observation, do not fabricate the missing history.
4. **Constraint dual check:** preserve the unchanged 512-token cap and validated source scope. Positive evidence: required facts survive two persisted summary rounds and appear in the final prompt. Negative evidence: an impossible anchor budget raises an explicit error and source invalidation prevents summary use.
5. **Ownership and simplification:** this is an existing `domain.chat` projection/persistence responsibility. The change replaces newest-item-first selection in that helper; it adds no parallel workflow, store or authorization gate. Existing source invalidation, tenant/session scoping, and runtime grant behavior remain covered by targeted regressions.
6. **Evidence and stop line:** freeze the actual 21-request live Trace, historical results, ledger, scoring files, pre-fix reconstruction and C06 RED. Stop after T01–T10 plus related context/currentness/grant/assistant tests. No new Provider round is authorized.

## Acceptance limits

Evidence levels are separated in `RESULTS.json`: frozen Provider-output replay through current application code (L2), isolated Domain Fixture (L2 deterministic), automated source/currentness tests, and source review. There is no post-fix live model result. Repeated summarization remains lossy for non-anchor details; the current schema has no per-fact omission ledger, so this is submitted as `ACCEPTANCE_CANDIDATE_WITH_LIMITS`, not as general-purpose or lossless fact retention.
