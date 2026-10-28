# AR-01-RM-01-HF-01 handoff

**Candidate outcome: READY_FOR_AUTHORIZED_PROBE.** Only an explicitly approved
single-request protocol probe becomes eligible for independent review. This is
not paid authorization, not P1/P2 readiness, and not a main-Agent PASS.

## Skill C preflight

- Repo/branch: wgqa/OpsPilot / codex/ar01-free-agent.
- Base: `458a5f02f31b1ad0b056d3d0466a0bf73fd076a2`.
- Freeze: `edbbab1b087d6024837f7e22474593c5cc1459cc`.
- Source: `bac7d57219c8317cee693d0a82adc44ceff65bab`.
- Final evidence SHA: commit containing this report, supplied in final handoff.
- Remote main checked at start: `ec8c3582f6d145eec9979c43607302731411ead8`;
  remote experiment Base matched. Existing untracked test directories preserved.
- Actual reads at target Base: North Star blob
  `1f737712c7a36ceb34433ac09c3fbba3c3305542`, AGENTS
  `32c45506cceeaa8c76a5c56bf8360ff476b58856`, project Skill
  `d405c8d413d633824b279202cc1503dab4cf0b03`. A/B applied at start/freeze;
  C applied for handoff, not merely Skill discovery.
- Read P0 PLAN/PREFLIGHT/REPORT/RESULTS/FAILURES, both budget/adapter modules,
  Stage B HOLD/browser STOP, M2-01/M2-02 DEFERRED_GATES, prior fee meter and actual
  normalized history. User supplies P0 ACCEPT_WITH_LIMITS; this implementation
  does not reissue independent acceptance.
- Diff Base..candidate: this new evidence subdirectory and four experimental
  source/test files only, no merges, governance changes, old test/Gold edits or
  production code. Original main worktree/modified AGENTS left untouched.
- Evidence: implementer personally ran free SQLite/process/local HTTP/MCP tests,
  read source/history and official docs. Actual paid Provider, browser, full
  repository pytest, main-Agent independent rerun: NOT_RUN.

## What changed

The old refusal was mathematically correct for its chosen reservation. We do not
change it retroactively. An explicit `REQUEST_WIRE_V1` profile now validates the
installed SDK's actual prepared body and ties it to the HTTP body before send.
All input (including six schemas and server framing) keeps the full model-context
ceiling; only the documented, correctly serialized output max narrows to 512.
Per-request reserve is `ceil(1048576*0.30 + 512*1.20)` microUSD = USD 0.315188.
No character ratio, tokenizer estimate or 12,000-token approximation is used as a
strict financial bound. No schema, Context or user goal is removed to reduce fees.

| Source | Minimal responsibility |
|---|---|
| experiments/ar01_free_agent/provider_budget.py | Pure request-contract validation/bound; opt-in ledger identity and bound_json; atomic reservations using the computed amount; actual-body digest check; input/output/mode Usage violation halt. |
| experiments/ar01_free_agent/real_model.py | Prepare installed SDK body and verify at existing HTTP hook; opt-in Completion-ID correlation fallback; separate exact-wire one-request paid-authorization gate; offline request preflight. |
| experiments/ar01_free_agent/tests/local_provider.py | New negative fixture modes only; no old response-policy or Gold changes. |
| experiments/ar01_free_agent/tests/test_fee_hf01.py | 29 new bidirectional tests, two real OS processes, restart, protocol and body mutation, paired MCP runs and paid-construction refusal. |

Legacy policy/defaults and ledger metadata identity remain; no auto migration of
old rows. The new profile adds nullable bound_json to its experiment-only requests
table inside initialization transaction. Attempting a different policy on an old
ledger refuses/rolls back before relabelling it. No Domain schema migration.
No production Investigator, Agent Loop, TaskControl, Gate, Web, permissions, receipt
or business write code changed. Existing Runner is unchanged in this patch.

Compatibility: `parallel_tool_calls=false` stays identically on both arms; acceptance
is unknown and rejection stops without retry. Optional HTTP header correlation can
use the actual returned Completion ID under the new profile, preserving null header
and explicit correlation kind. Model/fingerprint, critical Usage and finish reason
still stop on missing/drift/invalid data. Main-Agent review of this opt-in header
policy is pending, not claimed approved. See PREFLIGHT classification matrix.

## Actual free verification

Final experimental directory: **77/77 passed** (original **48 unchanged**, new
**29**), 112.49s. Fresh S1/S2/S3/approval/HF/TTL subset: **72/72 passed**, 100.39s.
Full repository pytest NOT_RUN; these totals are not a substitute for it.
Exact commands, environments, exit-code files and raw logs are in RESULTS/runs.
No dependency changes: Python 3.14.0, langchain 1.4.1, langchain-core 1.6.12,
langchain-openai 1.7.2, langgraph 1.2.16, mcp 2.3.0, openai 3.33.0,
httpx 0.28.1, pydantic 2.14.1, pytest 9.1.1.

Five frozen pairs, under the unchanged USD 0.50 local ledger: 10 Agent Runs,
26 loopback fake-Provider requests, 16 actual local MCP attempts. Original six
schemas, model settings and equal business initial-state digests match A/B.
All protected business snapshots remain unchanged. Stub Usage/derived charge
only test arithmetic, not real model performance or vendor expense.

HF01-01..10 coverage: valid request/legacy refusal; unbounded/unknown body reject;
settled+next cost boundary; timeout/unknown retention; two-process race/reopen/
duplicate logic; malformed/excess/mode Usage; actual A/B body/schema/scope parity;
legal continuation; unapproved/P1-only auth never constructs a paid client; old
48 plus necessary safety tests. The sole positive authorization gate replaces the
factory with a stub, constructing no paid client and sending nothing.

Actual traces in TRACE/final-01 include per-request bound_json, body/digest,
reservation ID, Task/Run/Attempt/Observation/Evidence, Usage, real local HTTP/MCP
and explicit correlation kind. Offline preflight uses the recorded six-tool body:
ready=true, paid_authorized=false, requests=0. Default legacy still refuses.
Raw RED, early local runs and negative simulations are retained in FAILURES.
SOURCE_DIFF.patch is byte-exact Git output (the repository marks patches -text).
Source/docs/JSON diff checks pass excluding only raw runs/*.log and this derived
patch: pytest traceback trailing spaces and patch context prefixes are preserved,
not silently cleaned to produce a whole-artifact whitespace PASS.

## Proven vs conditional vs unverified

**Proven locally:** actual current SDK wire has correct field/mode/schemas; monetary
arithmetic and durable single-flight/count/unknown/cost checks; exact-body authorization;
legacy compatibility; existing safety regressions. Source/history/doc inspection
is separately labelled, never a fresh paid observation.

**Document-dependent:** vendor context ceiling, max_tokens limit, non-thinking
contract and prices. The new bound includes all framing by using full capacity;
it is deliberately loose rather than pretending the inspected text tokenizer covers
server serialization. BOUND_ANALYSIS records the actual archive hash/limitations.

**Unverified remote:** acceptance of parallel flag/schema/mode, actual usage/output
limit and model/fingerprint metadata. Historical 87 nominal overruns have no raw
HTTP request archive; current SDK conversion is one plausible cause, not a proven
explanation of those earlier requests. No paid probe was used to settle this.

An adversarial local response reports USD 0.786432 after ignoring limits. We retain
that amount and stop; **we did not prevent the already-sent request's excess**.
Thus readiness is conditional on documented vendor behavior, not an absolute
billing guarantee. Requiring protection against that contract violation would
retain HOLD. No test result is used to hide this financial assumption.

## Stop and next decision

Main Agent may review the opt-in bound/header profile and then request explicit
user authorization for one fixed protocol request, at most USD 0.50, reserve
USD 0.315188, no retries or tool execution. The new paid factory requires scope
ONE_REQUEST_PROTOCOL_PROBE, limit=1, exact config and wire digest; P1 authorization
does not substitute. Batch CLI does not execute it. No approved authorization file
is delivered. P1/P2/AR02/main merge/browser remain unauthorized and NOT_RUN.

## Learning and Skill C six-line close

SDK arguments, wire fields, token estimates, contractual ceilings and actual Usage
are different evidence layers. A credible token estimate is not a proven upper
bound; a conservative capacity bound can instead use an explicit output contract.
Timeout is unknown exposure, not permission to retry. Interview example: explain
the 878/785 historical Usage without claiming a missing raw request proves a
Provider bug; cite the exact-wire check and limits of after-the-fact accounting.

**用户变化：** 实验获得可审计的单请求预检候选；生产能力不变。

**Agent 决策：** A/B 自主决策策略未修改，不声称智能提升。

**观察驱动：** 免费成对 HTTP/MCP 事实与原案例保留；真实模型行为未验证。

**新增约束：** 实际请求体与预留绑定、单次探测单独授权；拒绝危险路径并保留合法调查，已有双向证据。

**简化结果：** 复用现有预算表/事务/适配，不建 Tokenizer 或 Cost Service；仅 opt-in 收窄保守输出预留、合并实际请求关联。

**证据与停止线：** 77 项实验及 72 项安全新鲜通过；保留条件性费用风险、旧失败及未运行项；提交候选后停止。

**Implementation candidate only: READY_FOR_AUTHORIZED_PROBE.** No main-Agent
PASS, paid approval, full A/B launch or merge is implied.
