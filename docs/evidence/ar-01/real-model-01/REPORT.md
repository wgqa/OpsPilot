# AR-01-RM-01 P0 handoff

**Status: ACCEPTANCE_CANDIDATE (P0 only); P1/P2 NOT_RUN.**
The optional real-model adapter and local validation are implemented. Real-model
quality, remote compatibility and actual billing remain unverified. Production
Agent behavior has not changed; no new user-facing capability is claimed.

## Review preflight (implementer's handoff, not independent acceptance)

- Repo `wgqa/OpsPilot`, branch `codex/ar01-free-agent`.
- Base `55d3dd6f3671755621905d3d1437bd7a8dce053e`.
- Freeze `749ad4926aac59de949dfc3556ee419e388582ba`.
- Implementation `47e2bd4b05c66cf134904999dcb0e76ac88496e6`.
- Evidence commit: the commit containing this report; final SHA supplied in handoff.
- Refetched main `ec8c3582f6d145eec9979c43607302731411ead8` and remote experiment
  head `55d3dd6f3671755621905d3d1437bd7a8dce053e` before evidence submission.
- Diff Base..candidate: isolated experiment and this new evidence subdirectory
  only; no merge commits, production implementation, governance-file or old Gold
  edits. Original dirty main checkout/user files untouched.
- Actual target-rule reads: North Star blob
  `1f737712c7a36ceb34433ac09c3fbba3c3305542`, AGENTS
  `32c45506cceeaa8c76a5c56bf8360ff476b58856`, Skill
  `d405c8d413d633824b279202cc1503dab4cf0b03`. Skill A/B used at freeze;
  C and North Star §8 reread for handoff. See SKILL_EXECUTION.md.
- Original CASES blob `1fd348d93d160ec7b9a4bde21d06fb5c762bd576`, PARITY blob
  `00674d730c75efbee8742a0b3e213a94f5009934`; unchanged. RM task narrows the
  proposed paid sample to five variants and 80 requests, not the older 36-Run plan.
- Stage B HOLD, browser STOP and M2 deferred safety contracts retained. No
  browser, paid Provider, AR-02, business writes or main merge authorized.
- Evidence level: implementer personally executed free tests and examined actual
  local HTTP/MCP/SQLite traces. Main Agent independent review/rerun: NOT_RUN here.

## Implementation and scope

| File | Change |
|---|---|
| experiments/ar01_free_agent/real_model.py | Shared optional LangChain adapter, exact wire/config checks, raw metadata/Usage capture, first-pair gate, fixed batch and offline-default CLI. |
| experiments/ar01_free_agent/provider_budget.py | Experiment-only durable request/fee reservations, atomic single-flight/count/cost checks, backend pin and sticky unresolved/error halt. No Domain schema migration. |
| experiments/ar01_free_agent/harness.py | Optional model factory/model ID; retain group traces/results on error; close clients. A policy methods and B create_agent loop unchanged. |
| experiments/ar01_free_agent/tests/local_provider.py | Test-only literal-loopback protocol fixture, including failures. |
| experiments/ar01_free_agent/tests/test_real_model.py | Frozen readiness, budget, HTTP wire, response, restart/cancellation, comparison parity tests. |

No production `investigator.py`, S3Nodes, Domain, Web, Context or budget constants
changed. The ledger lives in experimental output, not the business DB. Both arms
reuse the six existing restricted MCP tools and TaskBinding/current authorization.
Protected fact/control/approval/intent/ledger/diagnosis/queue/receipt/outbox snapshots
remain identical before/after every local paired execution. Source diff also proves
production writers and original Agent loop files were untouched.

Unknown settings fail; no hidden retries, model/mode switch or post-error parameter
repair. Extra_body explicitly uses the vendor token field. Known Usage settles
conservatively, unknown responses retain all exposure. An OS crash before/after
SENT cannot free or reset it. An incomplete first group remains inspectable rather
than being discarded to finish the sample. See PREFLIGHT for monetary limitations.

## Fresh execution

Windows, Python 3.14.0; installed pinned langchain 1.4.1, langchain-core 1.6.12,
langchain-openai 1.7.2, langgraph 1.2.16, mcp 2.3.0, pydantic 2.14.1,
openai 3.33.0, httpx 0.28.1, pytest 9.1.1. No dependency changes.
Use `.venv-stageb/Scripts/python.exe`; exact environment/commands/results are in
RESULTS.json and numbered raw logs. Basetemp directories are unique and confined
to the experimental checkout, with the required parent created beforehand.

- Final candidate experiment suite: **48 passed**, 72.22s, raw `runs/14-release-all-tests.log`.
- Fresh S1/S2/S3/approval/HF/TTL safety subset: **72 passed**, 83.18s, raw
  `runs/11-safety-regression.log`. These are not inherited AR-01 results.
- Full repository pytest: **NOT_RUN** (unchanged production; necessary subset
  run). Do not advertise 120 as a full-suite total. Obsolete C1 RED is untouched.
- Offline preflight: exit 0 with ready=false and zero requests. This is a
  successfully enforced refusal, not a completed real-model experiment.
- Real paid model requests: **0**. Real DeepSeek model behavior/Usage: NOT_RUN.
- Browser: NOT_RUN / standing STOP. Stage B HOLD unchanged.

The final fixed local sample has 10 Runs, 26 fake-Provider HTTP requests and 16
actual local MCP attempts (A: 13/8; B: 13/8). It includes real local HTTP business
facts, independent equal initial snapshots, exact actual wire schemas and safe
scope rejection followed by legal bound-order reading. Its 2,600/520 input/output
Tokens are **fixture values**; the ledger's USD 0.001404 is synthetic accounting,
not measured vendor spend or a cost prediction. Paid spend is zero.

Raw correlation: `TRACE/release-47e2bd4/five-pair-local/*/{A,B}.trace.jsonl`
contains Task/Run/Attempt/call/Observation/Evidence IDs, full sanitized outgoing
messages/schema, actual local HTTP requests/responses, fingerprint/IDs/Usage,
tool results and final delivery. Per-group result JSON and batch-results.json
retain the same identities. TRACE/INDEX.json is generated by reading these files,
not by constructing pretend model calls. Test database files remain local/ignored;
the repository contains sanitized JSON observations, not credentials or live DBs.
INDEX keeps both original-byte and normalized-LF hashes because Git autocrlf can
normalize line endings. Whole evidence `git diff --check` reports trailing spaces
in raw pytest traceback logs; they are preserved rather than edited. The same
check excluding only `runs/*.log` passes for source, documents and JSON evidence.

## Limitations and next decision

P1 lacks explicit paid authorization. Independently, the conservative USD 0.786432
reservation exceeds the proposed USD 0.50 target. Correct local wire serialization
does not establish remote compliance. We did not increase the live cap, omit an
unsupported field or run a paid probe. A reviewed tighter bound or separately
authorized conservative probe would require a new explicit decision; this report
does not ask to execute it automatically. Current live readiness is BLOCKED.

The SDK/vendor's actual support for parallel_tool_calls=false, request ID header,
model string/fingerprint, requested mode and Usage remain unverified. A response
contract mismatch will stop instead of producing comparison scores. A missing ID
may conservatively reject a valid vendor reply; local positive and negative paths
prove mechanics, not that this vendor metadata will always be provided.

A/B prompts and Context differ, as do multiple-candidate handling and retained
source rebuilding. This compares two configurations, not the isolated causal
effect of Agent Loop. Product multi-Run/Worker/checkpoint continuation and natural
language semantic correctness are not established. No relative superiority claim.

## Learning and interview

Principle: Agent tool decisions, transport reliability, trusted tool authority
and experiment accounting are separate responsibilities. A reservation records
possible cost **before** I/O; a timeout is unknown, not a free retry. Raw wire and
strict returned Usage are needed because SDK option names and Token estimates are
not billing evidence. Landings: MeteredModel._agenerate / request_hook and
ExperimentBudget.reserve / sent / settle / unknown. The actual failed runtime-map
and tool-message-name experiments are in FAILURES, not just idealized diagrams.

Interview: “Why not compare successful run counts immediately?” — This release
only proves both adapters can exercise the same authorized tools under deterministic
responses. Real autonomous choices require a separately authorized real model;
Prompt/context differences and deterministic fallback must be separated from loop
effects, and all failures/partial goals remain in the denominator.

## Skill C six-line handoff

**用户变化：** 获得可审计、默认关闭的真实模型实验适配；无新增生产能力或智能收益声明。

**Agent 决策：** 保留 A/B 自身工具、继续、澄清和结束决策；本轮只有确定性模型验证。

**观察驱动：** 本地 202/503、不同 Event、越域拒绝后合法查询已关联真实 MCP；真实模型响应仍未验证。

**新增约束：** 阻止未授权、重复、未知费用及超额发送；本地合法预留/结算、相同范围查询有正例。

**简化结果：** 同一 Provider 适配供两组使用；复用已有 Runner/工具/事务模式，无生产 Guard、Runtime 或规则删除。

**证据与停止线：** 实施者新鲜 48 + 72 测试、原始失败、免费 HTTP/MCP Trace；P1/P2/浏览器/全量 pytest 未运行。分支提交后停止。

**Implementation status: ACCEPTANCE_CANDIDATE (P0 only).** Main Agent independent
verdict pending. P1 authorization/cost readiness BLOCKED; no merge or next phase.
