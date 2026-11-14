# R2-AR04-LIVE-SEMANTIC-ABC-01 — Execution Plan and Disposition

**Implementer status:** `ACCEPTANCE_CANDIDATE`<br>
**Execution status:** `BLOCKED_BEFORE_PROVIDER_SEND`<br>
**Provider requests:** 0<br>
**Provider cost:** USD 0.00<br>
**Frozen Base:** `dad59337aed6cf8ec828f38ab2a87f2df8097887`<br>
**Branch:** `codex/r2-ar04-live-semantic-abc-01`<br>
**Worktree:** existing `.worktrees/ar04a-context-journey-01`; no new Worktree.

## Start-of-slice verification

At start, `HEAD` was exactly the authorized Base. `origin/codex/r2-ar04-live-eval-setup-hf01` was at the Base, `origin/main` was `60eee87bfe3cca522011316cb4cd2c0064ad291b`, and the new candidate branch did not exist remotely. The only pre-existing untracked paths were `.pytest-tmp/` and `docs/evidence/r2-ar04-live-eval-setup-hf01/.pytest-basetemp-budget/`; they were preserved and excluded.

| File or contract | Blob at Base | Read status / priority |
|---|---|---|
| `PROJECT_NORTH_STAR.md` | `43dabda468506717c6956e676dfad4304c4f38e6` | Read; authoritative product and review protocol |
| `AGENTS.md` | `807b928686a4dd2cac7b15b3c354b9943c93c910` | Read; safety and project rules |
| `.agents/skills/opspilot-slice-review/SKILL.md` | `d405c8d413d633824b279202cc1503dab4cf0b03` | Read; required workflow entrypoint |
| `docs/baseline/vNext-product-baseline-candidate.md` | `52323facbebc6e466f226c87bc67a3b9004a7bc4` | Read as context; candidate baseline is not itself an acceptance decision |
| `docs/baseline/ACCESS_MATRIX.md` | `9d62359c3a97a2fe78678b178889288e551b3d7c` | Read; trusted authority boundaries |
| `docs/baseline/STATE_TRANSITIONS.md` | `cb34e6402cf3ce795260414b9b652f31b49f4de1` | Read; business state boundaries |
| `docs/evidence/vnext/m2-01/DEFERRED_GATES.md` | `2e65870acb26a7c1383fdd96b5b8619748dda6b9` | Read; frozen M2-01 gates, no new business-write scope here |
| `docs/evidence/vnext/m2-02/DEFERRED_GATES.md` | `2536030b5b942bf9e3765e0916607549fa919934` | Read; frozen M2-02 gates, no new business-write scope here |
| Runtime Grant report | `dcd228603d9f1e603346021feb1c760e500f2ce7` | Read; existing persistent Grant/pool contract |
| Runtime Grant HF01 report | `794b88cc071467d068f200607eb6e21ec44e819d` | Read; legacy provider paths remain separately gated |
| `docs/evidence/r2-ar04-compaction-audit-01/ALGORITHM.md` | `d1018ca3035151195feaa4ed1d6c7dc79aaa588d` | Read; frozen context strategy and source behavior |
| Setup-HF01 `REPORT.md` | `32eba765c89621197471b78dcece2fbb0bb24ce6` | Read; offline A/B/C preparation only |
| Setup-HF01 `RUNTIME_READINESS.md` | `984917df1cff3ee312b2c9843b3d57eac97da514` | Read; isolated Mock Grant proof, not live authorization |
| Setup-HF01 `EXPERIMENT_TRACKS.md` | `246ad0df677d61abeb9567dcaeac7e43b06797a8` | Read; Track 1/Track 2 separation |
| Prior live pilot `RESULTS.json` | `96ac4ed32c68dada1dd506d62e2e948a84e2a23b` | Read; 3 old D requests, stopped at Q06 tool call |

No standalone signed main-agent verdict for the prior pilot was found in the checkout. Setup-HF01 records `independent_main_agent_review: NOT_PERFORMED`; prior answers and their historical scoring remain unchanged and are not pooled into this run.

## Frozen experiment

| Group | Strategy | Questions | Answer slots | Summary cap |
|---|---|---|---:|---:|
| A | `HYBRID` | Q02, Q03, Q06 | 3 | 6 |
| B | `ROLLING_SUMMARY` | Q02, Q03, Q06 | 3 | 6 |
| C | `RECENT_WINDOW` | Q02, Q03, Q06 | 3 | 0 |
| **Total** | — | 3 fixed questions | **9** | **12** |

Question text and the 29-row synthetic history are frozen in Phase A. Every question/strategy case would use its own temporary Domain database, checkpoint, Session, and Run. Gold and scoring rules remain offline. Track 1 uses the same Assistant Tool Schema with `tool_choice=none`; no model-proposed tool is executed.

Provider parameters are the official DeepSeek endpoint `https://api.deepseek.com`, alias `deepseek-flash`, current documented version `DeepSeek-V4.1-Flash-1017`, `thinking={"type":"disabled"}`, temperature 0, 12,000 input tokens, and at most 512 output tokens. Automatic retry is disabled. The official model and current peak prices were checked before the run; source links and arithmetic are in `PREFLIGHT.json`.

The maximum schedule is 21 requests: up to 12 summaries and 9 answers. At the peak cache-miss input price of USD 0.30/M and output price of USD 1.20/M, the per-request reserve is USD 0.0042144 and the full schedule ceiling is USD 0.0885024, below the separate hard cap of USD 0.15. The USD 0.15 cap does not authorize requests beyond the frozen matrix.

## Preflight stop

After loading the repository's normal local environment mechanism, `OPSPILOT_MODEL_API_KEY` was absent; `.env` was also absent. The required model, endpoint, model-config version, price version, and service identity were not configured in the process. No bindable live Runtime Grant/configuration was proven or used; the default Domain and checkpoint databases were absent. Since there is no approved local API credential, the live Runtime configuration cannot be bound and validated. No temporary live Grant was provisioned, no database was opened for Grant creation, and no Provider request was attempted. Do not request a key in chat or place one in Git.

The executable scope therefore stops at zero-cost evidence checks. This is an environment/configuration block, not an algorithm result and not evidence of summary loss. All nine slots remain explicitly blocked in `LIVE_RESULTS.json`; the request archive is empty and the cost ledger has zero reservations and zero sends.

## Schema and parity findings

Phase A's captured tool-schema digest is `f6c75eaa3b2a807c95258e0df2428d046b4fe545d5a5a15a83384d3880415c12`; the Setup-HF01 Assistant Runtime digest is `555cd385857aadce03e567c27886a49b3f6db6734c25c310a3c5bb3a07dbcec7`. The two captures have the same eight tool names, but they are **not byte/content-identical schema objects**: the Runtime representation omits JSON Schema `title` annotations, trims some trailing description newlines, and omits `additionalProperties: false` from the `memory_remember` argument schema. This is more than an encoding-only digest change. No production schema was modified to recreate the old digest.

The Setup-HF01 Mock trace independently shows that for each of Q02/Q03/Q06, A/B/C share the same current schema digest, the same fixed trusted system-prompt-prefix digest (`46267d783298bcb2c64957de58d4d117b760151323ae9e1bf5a5434b9a37163b`), model alias, and `tool_choice=none`. Thus the within-experiment parity gate is satisfied at the Mock-evidence level. The difference from Phase A is recorded as a limitation; no live A/B/C call occurred.

## Six review questions

1. **User change:** A completed run would answer whether early endpoint, corrected Request ID, and protocol-version facts survive real summarization and are correctly recalled. This attempt produced no new user capability or semantic result because the local credential prerequisite was missing.
2. **Agent decision:** The model would answer or abstain using the selected history; this is Track 1, so it cannot choose tools. No real model decision was observed in this attempt.
3. **Observation driven:** Q02 depends on the earliest `/callback` configuration, Q03 on the formal `req-483` correction rather than `req-482`, and Q06 on the `v1.2 → v1.3` change. Different visible evidence supports different answers; the answer would not authorize a business action.
4. **Constraints:** `tool_choice=none` prevents a tool dispatch while preserving direct answer/abstention; the 12k/512 caps and existing Runtime Grant guard bound spend. Offline traces confirm request construction and parity, but this attempt cannot supply the live positive path. Unknown or missing authorization remains a stop condition.
5. **Simpler alternative:** Reuse the existing Assistant context and Runtime Grant mechanisms, as in Setup-HF01; do not add a Grant/ledger subsystem or change production compression. No production code was changed. The cross-DB global counter would be implemented only within the authorized experiment sender if live execution were possible.
6. **Evidence and stop line:** The frozen inputs, official pricing, environment check, schema comparison, current A/B/C Mock parity, and prior trace status are recorded. Stop before all Provider I/O when the approved credential is absent. Do not convert Mock outputs or the previous D pilot into A/B/C semantic evidence.

## Final disposition

The deliverable is a reproducible `BLOCKED_BEFORE_PROVIDER_SEND` record with `ACCEPTANCE_CANDIDATE` status. Real semantic scoring is `NOT_RUN`; no independent main-agent review or acceptance is claimed. No production compression code, Gold, historical Trace, previous Provider answers, business data, Grant, or `main` was changed.
