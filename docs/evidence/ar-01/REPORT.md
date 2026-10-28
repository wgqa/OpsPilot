# AR-01 implementation handoff

**Status: ACCEPTANCE_CANDIDATE_LOCAL_ONLY.** Implementation is complete in the
isolated experiment; deterministic validation passed within the declared scope;
real-model effectiveness is NOT_RUN / NOT_VERIFIED. No architecture winner.

Repo `wgqa/OpsPilot`; branch `codex/ar01-free-agent`; Base
`ec8c3582f6d145eec9979c43607302731411ead8`; freeze commit
`a59f6a9f84e698014e756d44a9e4f1ee2abe21ce`; initial implementation commit
`722e5d8c6f256e559ea2e3b16b7e7d42d07b6fa3`; final source/Trace identity fix
`d2cd59a96dda71ebda5a9dc1b963c2eb9f88fbab`.
Final evidence HEAD is reported in the task handoff. No merge/main push is allowed.

## What can actually run

`python -m experiments.ar01_free_agent --output <new-directory>` runs the frozen
9 paired cases with a deterministic model, real MCP stdio and existing local
Domain/HTTP. The existing A policy and standard B loop receive independent copies
of exactly the same prepared business state. Each group gets its own Task/Run,
model object, Attempt/Evidence store and protocol child process.

For the same “I think callback delivery failed” question, actual 202 led the test
model to receiver processing, while 503 led it to delivery-triage methodology.
For target event-e1, an event-e2 successful send and PROCESSED snapshot still led
to target UNKNOWN. The scoped-denial case refused an outside Event and then read
the legal bound order. These are observed deterministic mechanics, not evidence
that a real LLM chose better.

The production UI, Investigator, tool definitions, Domain schemas/Gates, approvals,
TaskControl, Ledger and historical evidence were not changed. This adds a candidate
to inspect and compare, not a product feature or migration.

## Implementation and fairness

`agent.py` uses the installed `create_agent()` graph with six StructuredTool
adapters and middleware around model/tool edges. Runtime business facts come only
through the existing bound MCP server. Existing Domain APIs recheck authorization,
current versions, Run-scoped Observations and source validity. Existing Attempt,
Observation and Context Provenance tables audit dispatches. No new business table
or general Runtime/Planner is introduced.

The runner verifies original model-facing tool names/descriptions/schemas exactly,
including the actual bound schemas, and initial business snapshot digests match
in all final pairs. Native BaseTool conversion removes only display titles; the
original specs are passed at the B model boundary. Denied and legitimate queries
are both exercised, including legal within-order historical Events.

Important differences are retained in PARITY.md:

- A invokes unchanged S3Nodes strategy A investigate/execute/gate/next_step. The
  adapter omits production intake, Worker/Checkpoint and formal report/Diagnosis
  writer. It is a **decision-policy comparison**, not the whole production entry
  or end-to-end business outcome. This omission is not a claim of full A Runtime
  equivalence and may favor A by avoiding entry restrictions.
- A uses its original structured Prompt/Context and candidate reconsideration;
  B uses a shorter system instruction/native message history. Prompt/Context are
  not equal, so a future observed difference cannot be attributed solely to the
  loop architecture. A's Prompt was not weakened or rewritten.
- Both fresh initial Runs are bounded at 8 MODEL / 6 MCP, 30/12-second individual
  timeouts, a 60-second experiment invocation and the existing 12k estimated-input
  profile / 512 reserved output. B's experiment limit also caps cumulative usage
  at 8/6; full CONT-UX 24/18 allocation across multiple Runs is not matched. Neither
  adapter exercises production active-time heartbeat or recovery.
- Same-instance native history is checked by digest and current source pins;
  invalidated sources or restarted/tampered history stop explicitly. This is not
  a new Context platform or a demonstration of cross-Run product continuity.
- Both ask for parallel calls disabled. If a model emits a batch anyway, native
  B serializes that batch while A retains its existing redecision behavior. The
  normal comparison cases use one proposal; a negative test verifies slot limits.
- A has Memory disabled and the fresh DB has no approved Memory; B has no Memory
  channel. Both have the same versioned MCP Knowledge/Skill capability.
- Candidate output is experiment-only. Typed unsupported processing and structured
  fake Receipt fields are rejected; ordinary language remains untrusted. No
  natural-language validator can be inferred from the local tests.

## Fresh validation

| Check | Actual result | Evidence |
|---|---|---|
| Frozen local pairs | 9/9 met allowed local assertions; 18 group executions | runs/local-08/local-results.json |
| Model/tool activity | 46 deterministic model decisions, 28 MCP attempts; all six tools used | actual A/B .trace.jsonl files |
| Business invariants | 18/18 protected business snapshots unchanged after Agent execution | per-group result and runtime assertions |
| Candidate boundaries | 20 passed, including timeout/error/empty/fake receipt, budget/re-entry, history, revoke/reauthorize, parallel slot, repeat-asset and identity redaction cases | runs/pytest-07.log; runs/unit-traces-07/ |
| Existing safety | 72 passed: S1/D3, S2 facts/diagnosis, S3 HF01/HF02/TTL integrity | runs/safety-01.log |
| Dependency/source compatibility | Existing pinned dependencies; compileall exit 0 | DEPENDENCIES.json |

The scope case correctly remains PARTIAL for the restricted subgoal; it is not
counted as full user-goal completion. Actual Provider tokens are unavailable and
recorded null. Provider calls and Provider cost are zero. These numbers are not
real-model accuracy or a comparative win. Complete commands/exit codes are in
RESULTS.json. TRACE_INDEX.json indexes real saved events by hash; it contains no
fabricated calls. Fixture preparation HTTP POSTs are labeled separately from
Agent read-only calls.
Raw runs and the source patch use local `-text` attributes so Git cannot change
their line endings; indexed Trace hashes are checked against staged Git blobs.

All build/simulation failures are retained. In particular local-04 exited 0 after
the pipeline ran but had a shared test-model TypeError and an insufficient readiness
label. It is explicitly NOT rubric PASS; local-05/06/07 reruns preserve the same
Gold and check the missing assertions. A later audit found over-redaction of task
IDs in pre-local-08 Trace files. They remain unchanged; final identity-correlation
proof uses local-08/unit-traces-07 after a narrowly scoped experimental redaction
fix and a dedicated assertion. See FAILURES.md and raw logs.

## Not proved / next decision

No real Provider, browser, full pytest, production Worker recovery, new Task type,
general tool platform or cross-Run goal continuity was run or implemented. The
browser STOP remains. Stage B HOLD is not changed. Existing obsolete C1 Intent
RED and historical 402-count results are not relabeled as fresh results.

Tool/resource equivalence has been established for these fresh initial-Run cases.
Whole production entry/Context and lifecycle equivalence has not. If Main Agent
requires a full Investigator comparison, that adapter boundary must be settled
before a paid trial. No source migration or superiority follows from this work.

REAL_MODEL_PLAN.md proposes the same deepseek-flash model/mode, 9 variants x 2
groups x 2 repeats, at most 288 Provider requests, and USD 1.50 reservation, with
single in-flight accounting and explicit preflight/stop conditions. It is a
proposal, not authorization or an implemented cost guarantee. No live request ran.

## Six-question implementation statement

1. **User change:** an independently runnable standard-loop candidate and inspectable
   comparison are available; the production user journey has not changed.
2. **Agent decisions:** the B model interface can choose tools, explanation,
   clarification, continuation and stopping; actual real-LLM decisions remain unverified.
3. **Observation-driven:** actual 202 vs 503 and same/different Event observations
   led the deterministic test policy to different justified actions/conclusions.
4. **Constraints:** current binding/Scope, source pins and finite existing attempts
   protect data and resources; direct/legitimate queries, within-order Event reads,
   fresh reauthorization and no-tool answers also pass. History restoration is limited.
5. **Simplification:** reuse create_agent plus existing MCP/Domain audit; no old
   production conditions were deleted and no Planner/Guard/Memory service was added.
6. **Evidence and stop:** local candidate, 20 tests, 72 safety tests and 9 pairs have
   actual artifacts; paid effects/whole Runtime parity remain unverified. Stop on
   the isolated branch for independent review; do not merge main or enter AR-02.
