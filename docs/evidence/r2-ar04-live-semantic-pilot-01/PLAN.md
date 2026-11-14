# R2-AR04-LIVE-SEMANTIC-PILOT-01 — execution plan

**Status:** `AUTHORIZED_FOR_BOUNDED_LIVE_EXECUTION`; executable scope is limited by the preflight result below.
**Repository:** `wgqa/OpsPilot`
**Frozen Base:** `fd941299966f6cc54ae35be3102f071d2be29acc`
**Candidate branch:** `codex/r2-ar04-live-semantic-pilot-01`
**Worktree:** existing `.worktrees/ar04a-context-journey-01`; no new Worktree.

## Start-of-slice review

The target Base was checked before edits. `HEAD` equalled the frozen Base; the prior remote candidate ref also pointed at that Base. The only pre-existing worktree item was untracked `.pytest-tmp/`; it is preserved and excluded from this candidate.

Files actually read from the target Base:

| File | Blob at Base |
|---|---|
| `PROJECT_NORTH_STAR.md` | `43dabda468506717c6956e676dfad4304c4f38e6` |
| `AGENTS.md` | `807b928686a4dd2cac7b15b3c354b9943c93c910` |
| `.agents/skills/opspilot-slice-review/SKILL.md` | `d405c8d413d633824b279202cc1503dab4cf0b03` |
| `docs/evidence/vnext/m2-01/DEFERRED_GATES.md` | `2e65870acb26a7c1383fdd96b5b8619748dda6b9` |
| `docs/evidence/vnext/m2-02/DEFERRED_GATES.md` | `2536030b5b942bf9e3765e0916607549fa919934` |

The North Star §8 and review skill gates apply: keep the result evidence-backed and bounded, preserve the independent acceptance decision, and report blocked/unverified work as such. The task is an offline-prepared synthetic evaluation with specifically authorized Provider calls; it does not authorize Grant creation, production changes, business writes, MCP calls, Gold edits, or main merge.

## Frozen inputs and experiment

Phase A files were read from `docs/evidence/r2-ar04-long-context-journey-01/`:

| Input | SHA-256 |
|---|---|
| `QUESTIONS.json` | `ea3d6554eafa433d1617dc5a5ba9f140471f3cb95f8ae10bcd25b807a4e7afe2` |
| `RESULTS.json` | `4b04f3d574028099f13748091d4d421c7654b15bed4d25be13b40c413b8699c4` |
| `HISTORY_SNAPSHOT.json` | `356512f611b046a04e33506a0fb1a88c6a08af93517b2134125dd6771b282c16` |
| `MODEL_REQUESTS.jsonl.gz` | `96efd85b7d29d54938b1a4932321eff74bca7e8e56565c978f58a1e57d9a1792` |
| `run_long_context_eval.py` | `b2d5b1415c3759a5a8b1e0c1c33d406b61984e5914f8a7256b1ab25e3d89c2b0` |
| `LIVE_EVAL_PROPOSAL.md` | `729368f8a6b2e1d577bfbe1d0051878383ff9c7af7ecf6d4982299a8fd01c94e` |

The prior proposal described 168 calls, three repeats, and a USD 1.25 ceiling. This task card supersedes those values: one repeat, at most 56 Provider requests, at most USD 0.50. Phase A remains unchanged: it used the deterministic fixture, made zero Provider requests, and marked L3 live semantic quality `NOT_EVALUATED`.

The same 29-message synthetic pre-question history is used independently for each fixed question. Gold and scoring instructions remain offline. The frozen question set is Q02, Q03, Q06, Q07, Q08, Q10, Q12; each is crossed with A/B/C/D once. No live answer is added to any later question.

| Group | Strategy | Input budget | Context window | Live behavior |
|---|---|---:|---:|---|
| A | `HYBRID` | 12,000 | 16,384 | Runtime Grant path; live summary then live answer |
| B | `ROLLING_SUMMARY` | 12,000 | 16,384 | Runtime Grant path; live summary then live answer |
| C | `RECENT_WINDOW` | 12,000 | 16,384 | Runtime Grant path; answer only, no summary |
| D | `FULL_HISTORY_REFERENCE` | 60,000 | 65,536 | Direct evaluation reference only, with independent budget ledger and no tool dispatch |

All requests use model alias `deepseek-flash`, thinking disabled, temperature 0, and `max_tokens=512`. The fixed tool schema digest is `f6c75eaa3b2a807c95258e0df2428d046b4fe545d5a5a15a83384d3880415c12`. Any returned tool call is recorded and stops the run; this evaluator has no tool dispatcher.

## Live authorization and cost envelope

Current official DeepSeek documentation was checked before the first request:

- Model/prices: [Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)
- Supported request fields: [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)
- Thinking control: [Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)
- Model list: [List Models](https://api-docs.deepseek.com/api/list-models/)

The checked alias resolves to the current DeepSeek V4.1 Flash family. Peak cache-miss rates are USD 0.30 per million input tokens and USD 1.20 per million output tokens. The full authorized envelope is 1,008,000 input tokens and 28,672 output tokens, giving a conservative no-cache upper estimate of **USD 0.3368064**, below the hard USD 0.50 cap. Each request is reserved before sending at its maximum input/output cost.

The existing isolated worktree has no `.env`, runtime database, or complete Assistant Runtime configuration. The persisted Runtime Grant path cannot bind A/B/C in this worktree, and no Grant will be created. Therefore A/B/C are `BLOCKED_BEFORE_PROVIDER_SEND`. The locally available official API credential is used only for the task-card-authorized D reference path, whose 7-request maximum is tracked independently as `DIRECT_EVAL_REFERENCE`; its full no-cache reserve is USD 0.1303008. The credential value is never written to evidence or Git.

## Preflight and scoring

Before D sends, the prepared evidence records the exact input request digest per question, confirms the current question matches the frozen prompt, confirms Gold and scoring groups are absent, checks the D context has no summary, and verifies the tool schema digest. The direct sender stores the complete request/response JSON without authorization headers, reserves each worst-case cost durably, makes one serial request per logical question, and never executes tools. Any unknown send state, Provider error, missing usage, truncation, tool call, version drift, or budget anomaly stops subsequent sends with the reservation retained when spend is uncertain.

For each actual answer, record deterministic checks and a separate manual semantic assessment using `CORRECT_SUPPORTED`, `CORRECT_UNSUPPORTED`, `SAFE_ABSTENTION`, `INCORRECT_OR_UNSAFE`, or a non-completion status. Lack of `/callback` in visible evidence cannot count as supported recall even if guessed correctly. No paid evaluator model is used. The 21 blocked A/B/C slots remain in the denominator and are not treated as model answers.

## Six review questions

1. **User-visible result:** this slice measures live semantic use of earlier facts for a synthetic long journey; it adds no product capability.
2. **Agent choice:** it observes whether a real model answers, abstains, or chooses a safe read-only next step from the visible context.
3. **Observation-driven redirection:** Q10/Q12 test whether `202`/`QUEUED` remains incomplete and whether the model asks for a trusted completion observation.
4. **New hard constraints:** no tools execute, no business state changes, no new Grant, no user/customer data, and no Gold or score leakage.
5. **Responsibility and simplification:** reuse frozen Phase A prompts, history, question set, manifests, and schema; the only new sender is under this evidence directory for the D reference carve-out.
6. **Evidence and stop line:** stop at 7 D calls or earlier on any anomaly; no retries, no follow-up round, and no tuning to match Phase A results.

The candidate remains `ACCEPTANCE_CANDIDATE` pending the independent reviewer’s Base, diff, source, and safety check.
