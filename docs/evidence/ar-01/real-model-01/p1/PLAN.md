# AR-01-RM-01-P1 frozen execution plan

User authorization: AUTHORIZED_FOR_BOUNDED_P1, current conversation 2026-10-28.
Repo wgqa/OpsPilot, branch codex/ar01-free-agent, Base
`88e8e8ab7577e02b960a27667950515e7c5e0c5a`; fetched branch matches,
remote main `ec8c3582f6d145eec9979c43607302731411ead8`; tracked worktree clean.
Primary dirty checkout and existing untracked directories stay untouched.

Actual Skill A/B and rules read. North Star / AGENTS / Skill blobs:
`1f737712c7a36ceb34433ac09c3fbba3c3305542` /
`32c45506cceeaa8c76a5c56bf8360ff476b58856` /
`d405c8d413d633824b279202cc1503dab4cf0b03`.
Original CASES/Gold, PARITY, HF bound, real PROBE-01 truncation and deferred
safety/Stage B HOLD/browser STOP retained. No old evidence rewrite.

## Conditions and parameter-only adaptation

Create P1_2048_V1 config and REQUEST_WIRE_P1_2048 ledger policy. Same DeepSeek
Flash endpoint, non-thinking, auto tools, parallel=false, output max_tokens=2048,
30s/model, 12s/tool, 60s/policy invocation, no retries. Keep 8 MODEL/6 MCP per
initial Run. Full input capacity upper bound (including all tools/framing)
1,048,576; reserve ceil(1048576*0.30+2048*1.20) microUSD = **USD 0.317031**.
Global cap **USD 0.50**, **80 Provider reservations**, **60 MCP attempts**,
**10 initial Runs**, one Provider in flight. Known Usage releases unused exposure;
unknown/failed/unresolved results remain counted, never auto-resend/reset.
The monetary bound remains conditional on documented vendor compliance, not an
unconditional guarantee against vendor violations. No budget/limit escalation.

The existing B middleware's output setting becomes a trusted optional parameter,
default 512 preserved, P1 passes 2048. A uses the same shared P1 Provider config.
No Prompt/context/description/policy rule changes. Reuse existing meter/Runner/MCP;
no cost service, new Agent framework, production change or formal business writer.

## Fixed sample, once each, A then B

1. AR01-01/material
2. AR01-03/acknowledged
3. AR01-03/failed
4. AR01-04/different-event
5. AR01-06/scope

Use original CASES.json verbatim, independent equivalent cloned facts per pair.
Six actual raw schemas/descriptions/permissions identical. No fixed tool order.
First pair must execute fully with normal model delivery and protocol/Usage/wire
audit before later pairs. After that, goal/policy failures remain in results;
healthy protocol does not require a model win. Any protocol/cost integrity error,
unknown cost, global cap, unauthorized fact read or unexpected business write
stops the batch, retaining completed and incomplete groups. length is a protocol
failure, not a success or reason to change output size/retry.

## Minimal free checks before any paid request

- Old 512 policies remain unchanged; P1 reserve/settle/unknown and authorization
  are separately identified. No paid SDK client without matching P1 authorization.
- Actual local A/B wire uses 2048 and exact six schemas. Test full explanation,
  tool/observation loop and length rejection with fake Provider only.
- Run old experiment tests and necessary S1/S2/S3 safety subset without rewriting
  old tests/Gold. Do not use local simulated performance as real intelligence.

## Evaluation / stop

Save actual model-visible messages, tools/args, raw sanitized Provider metadata,
Usage/IDs/fingerprint, MCP observations, protected-state snapshots, final answer,
fallback/stop, Tokens/cost/time. Model delivery, guard actions and fallback are
separate. Offline review of each original goal: completion, factual/decision
correctness, 202/503 redirection, Event identity, useful/wasted calls, safety and
cost. No unique-tool-sequence grading, no additional paid evaluator. Retain all
partials/failures, including missing pairs if hard stop occurs. Prompt/Context and
multi-call handling are known confounds; five pairs are exploratory, not a causal
or statistical architecture claim. Only offline A/B/C/D recommendation, no migration.

Skill B: user gets first real A/B decision evidence; existing Agent choices remain
free; paired observations may change actions/conclusions; quota/auth checks protect
resources while legal queries remain tested; reuse existing experiment components;
stop after five pairs or first hard condition, branch commit/push for independent review.
