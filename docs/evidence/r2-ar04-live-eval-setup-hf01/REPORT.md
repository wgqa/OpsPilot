# R2-AR04-LIVE-EVAL-SETUP-HF-01

**Implementer status: `ACCEPTANCE_CANDIDATE`**

**Scope: isolated offline preparation only. Real Provider calls: 0. Real cost: $0.**

## 開工核验 / baseline

| Item | Verified value |
|---|---|
| Repository / reused Worktree | `wgqa/OpsPilot` / `.worktrees/ar04a-context-journey-01` |
| Base SHA | `e6db85e17681a9aa6f6bf6e8b1b01bdef400c49e` |
| Candidate branch | `codex/r2-ar04-live-eval-setup-hf01` |
| Worktrees created | 0 |
| `PROJECT_NORTH_STAR.md` Blob at Base | `43dabda468506717c6956e676dfad4304c4f38e6` |
| `AGENTS.md` Blob at Base | `807b928686a4dd2cac7b15b3c354b9943c93c910` |
| Review Skill Blob at Base | `.agents/skills/opspilot-slice-review/SKILL.md` — `d405c8d413d633824b279202cc1503dab4cf0b03` |
| Candidate start | Clean at Base, except pre-existing untracked `.pytest-tmp/` (preserved) |
| Remote refs | Initial preflight `git ls-remote` did not return and was interrupted. After the first candidate push, refs were verified: `origin/main` `60eee87bfe3cca522011316cb4cd2c0064ad291b`; Base branch `origin/codex/r2-ar04-live-semantic-pilot-01` `e6db85e17681a9aa6f6bf6e8b1b01bdef400c49e`; candidate first-push SHA `3a5b98d5d95eb2fec3efb7453a47e7e2b08af273`. |

The target Base's North Star, AGENTS instructions, Review Skill, applicable runtime/context contracts, deferred gates and previous live-pilot evidence were opened and checked. Recorded contract/evidence Blobs: `vNext-product-baseline-candidate.md` `52323facbebc6e466f226c87bc67a3b9004a7bc4`; `ACCESS_MATRIX.md` `9d62359c3a97a2fe78678b178889288e551b3d7c`; `STATE_TRANSITIONS.md` `cb34e6402cf3ce795260414b9b652f31b49f4de1`; M2-01 deferred gates `2e65870acb26a7c1383fdd96b5b8619748dda6b9`; M2-02 deferred gates `2536030b5b942bf9e3765e0916607549fa919934`; Runtime Grant prior report `dcd228603d9f1e603346021feb1c760e500f2ce7` and HF01 report `794b88cc071467d068f200607eb6e21ec44e819d`; previous pilot `RESULTS.json` Blob `96ac4ed32c68dada1dd506d62e2e948a84e2a23b`.

No separate signed main-agent verdict for the prior live pilot was found in this checkout. Its partial-stop result remains an implementer candidate and is treated as historical evidence, not as an acceptance decision.

The North Star fit is an **evaluation and learning slice**, not a new user capability: establish a reproducible chain from context-compression design, to current Runtime implementation, to isolated mock traces, to a future separately authorized live comparison. No live semantic benefit is claimed here.

## Changes

- Added an optional `tool_choice_override` to the Assistant Runtime. Only `none` and `auto` are accepted; the normal default remains unset, and current production callers continue to use the existing automatic tool choice. Track 1 uses the explicit option to suppress tool calls while preserving the same actual Assistant tool schema, Runtime Grant validation, request reservation, token accounting and context construction.
- Added the isolated 24-case Mock harness, raw request/response trace, machine results, scoring attribution erratum/supplement, track design and run record under this directory.
- No production compression strategy, summary logic, Gold, prior trace, Provider answer, C06 RED, historical test, production database or `main` branch was changed.

Diff scope: one 17-line runtime plumbing diff in `opspilot/assistant.py`, plus this new evidence directory. `git diff --check` is clean. The historical input hashes and protected output hashes are pinned in `TEST_RESULTS.json`; all match.

## Six review questions

1. **User change:** no new end-user task is completed in this slice. It removes an evaluation setup blocker so a separately authorized run can compare historical recall and autonomous investigation without confusing the two.
2. **Agent decision:** Track 1 deliberately removes tool choice from the question; Track 2 preserves `auto`. The mock Track 2 model selected a known read-only protocol-document lookup, but that fixture choice is not evidence of real model autonomy or quality.
3. **Observation driven:** an answerable history-only question should be answered or safely abstained from in Track 1; a question requiring current documentation may justify a read-only lookup in Track 2. This slice tests the separated request paths with fixtures only.
4. **Constraints:** no Grant check is bypassed. Every path remains bound to an isolated Runtime Grant; the `none` override retains the same tool schema and only affects explicit evaluation calls. The `auto` path is also exercised and selects the local read-only tool.
5. **Simpler alternative:** the existing Grant, context and assistant dispatch code are reused. No second authorization/ledger system, new worktree or evaluation platform was added. The only runtime compatibility addition is the opt-in tool-choice parameter required by Track 1.
6. **Evidence and stop line:** 24 separate mock Assistant Runs, 59 captured MockTransport request/response pairs, six existing Grant/source fail-closed regressions, zero real sends and $0. Historical hashes match. Stop here; real semantic scoring requires a new authorization and current Provider/price preflight.

## Results

`TEST_RESULTS.json` reports T01–T09 as `PASS` for this offline setup slice. The main experiment executed 21 history-recall runs (seven questions × A/B/C) with `tool_choice=none` and three Q06 investigation runs with `auto`. A and B each persisted two source-linked summary batches per run and then answered through the Mock Provider path; C made no compression call. All 24 Assistant Runs completed. The 59 outbound model payloads were captured through explicit `httpx.MockTransport`.

Every strategy comparison used the exact same 29-row recreated history, question text, system Prompt prefix, model ID, tool schema digest and configured 12,000-token input cap. Because the Assistant reserves trusted system/context/tool overhead, the effective history budget was lower (about 8,180 tokens) and varied by 1–9 tokens across A/B/C; exact per-case values and context manifests are recorded rather than hidden. Every actual mock input estimate remained under the Grant's 12,000-token cap. Answers were deterministic fixture strings and are marked `NOT_SCORED_MOCK_OUTPUT`.

The three Track 2 mock responses each selected `list_scoped_protocol_documents`; the local stdio Assistant MCP queried only the isolated Domain. The tool is annotated read-only. No remote MCP or business action was used. This verifies wiring only, not whether a real model should make that choice.

T04's seven targeted pre-existing test cases passed: missing Grant, database-copy identity mismatch, expired Grant/invalid zero-price, successful and insufficient Runtime-pool budgets, explicit `RUNTIME_BUDGET_EXHAUSTED`, and source invalidation before provider I/O. `TEST_RUN.txt` preserves the commands, all pass counts, the early pytest temp-directory ACL error, the corrected effective-budget assertion, and the corrected hash-pin transcription failure. The test databases from the targeted pytest commands remain in two task-local hidden basetemp directories and are excluded from the candidate commit; the environment rejected the cleanup command. The pre-existing root `.pytest-tmp/` was not touched.

## Scoring ownership correction

The prior `score_live_results.py` authored two fields labeled `REVIEWED_BY_MAIN_AGENT`; that attribution was unsupported. The previous `RESULTS.json`, scorer, request bodies, responses and test history remain unchanged. `SCORING_ERRATUM.md` explains the issue, while `score_preliminary.py` produces a separate two-row supplement with distinct deterministic and semantic fields, `IMPLEMENTER_PRELIMINARY_REVIEW`, and `independent_main_agent_review: NOT_PERFORMED`. The new scorer contains no operation that emits a main-agent approval.

## Evidence limits and disposition

Evidence is **Fixture**, **Mock Provider transport**, existing isolated pytest regression, and deterministic offline validation. There is no live Provider evidence, semantic quality score, independent main-agent review, or successful remote-ref verification. The previous partial paid run remains unchanged. C06 RED and all frozen history/answer hashes remain unchanged.

**Implementer disposition:** `ACCEPTANCE_CANDIDATE` for offline setup only. No main merge or production release is requested. A future live semantic run needs a separate explicit authorization and current budget/model/credential preflight; the historical live allowance does not carry forward.
