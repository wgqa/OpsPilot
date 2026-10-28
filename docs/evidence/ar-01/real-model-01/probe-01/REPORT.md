# PROBE-01 — one real request, truncated completion, stopped

**Observed result: HTTP 200, finish_reason=length, 512 output Tokens.**
The existing adapter rejected the incomplete completion and exited 2. No retry,
parameter repair, extra explanation call, MCP execution or P1 run followed.

## Preflight / Skill execution

Repo/branch wgqa/OpsPilot / codex/ar01-free-agent. Approved Base actually checked:
`6c61a5cc5f19800b10d10bb50e23a2dfce49f243`; remote branch matched, tracked tree
clean. Remote main `ec8c3582f6d145eec9979c43607302731411ead8` unchanged.
North Star, AGENTS and project Skill actually opened at this Base; blobs:
`1f737712c7a36ceb34433ac09c3fbba3c3305542`,
`32c45506cceeaa8c76a5c56bf8360ff476b58856`,
`d405c8d413d633824b279202cc1503dab4cf0b03`. Skill A/B preflight and C handoff
applied; this is implementation evidence, not main-Agent independent acceptance.
Current explicit user message grants exactly PROBE-01, not P1/P2. Browser STOP
and Stage B HOLD remain. Primary worktree/env file were read only, not modified.

Frozen body blob `71854592cc914d080fc2a61053818defdbeb2c86` and semantic digest
`e9f088776d73e414238fc393c9d06659fa029280c064bac4c2d2361955521f8f` matched the
approved Git version and actual outgoing body. All six original schemas remained.
Official [pricing](https://api-docs.deepseek.com/quick_start/pricing/) and
[completion contract](https://api-docs.deepseek.com/api/create-chat-completion/)
were rechecked on 2026-10-28; no price/config change from the reviewed profile.
API Key was available in the primary project's local .env, read without printing
or retaining the value. Endpoint/model/config came from the approved frozen profile.

## Actual observation

| Field | Saved observation |
|---|---|
| Local start | 2026-10-28 19:25:23 Asia/Shanghai (UTC 11:25:23) |
| Model endpoint | POST https://api.deepseek.com/chat/completions |
| Model requested / returned | deepseek-flash / deepseek-flash |
| Thinking / output requested | disabled / max_tokens=512 |
| Actual HTTP | 200, application/json |
| Completion ID | cc60efa0-bd65-4aee-9990-98ce116b2509 |
| Fingerprint | bc19ba97cbe016479903222bb1578db6 |
| HTTP request-ID header | Absent; real Completion ID retained for audit correlation |
| Usage | prompt 2388, completion 512, total 2900; cache hit 0 / miss 2388 |
| finish_reason | length |
| Tool calls proposed / executed | none / 0 |
| Measured elapsed | 5.2970204 seconds |
| Reservations / transport attempts | 1 / 1 |
| Program outcome | ProviderStopped: INCOMPLETE_OR_INVALID_COMPLETION, exit 2 |

The response supplies the model alias and fingerprint, not an independently
attested detailed backend version. The checked pricing page maps the alias to
DeepSeek-V4.1-Flash-1017; that documentation fact is distinct from the returned
alias. Raw Usage has no reasoning-token breakdown. No reasoning_content field
was exposed in the saved message; this does not prove internal implementation.

## Cost accounting

REQUEST_WIRE_V1 reserved USD 0.315188 under a USD 0.50 cap, limit=1. Actual reported
Usage is known and consistent, so the ledger settled to the conservative peak,
no-cache upper charge, rounded up to microUSD: **USD 0.001331**.
Exact peak estimate: `(2388*0.30 + 512*1.20)/1e6 = USD 0.0013308`.
The observed response time is outside the documented UTC peak windows; using
off-peak no-cache rates gives **USD 0.0006654**. This is a schedule-based estimate,
not a verified invoice; no balance/billing API was queried.

The ledger remains halted after the completion error. This is a known Usage
settlement, not an unknown-cost timeout. Neither this successful accounting nor
one limit-consistent response proves an absolute cap against vendor violations.

## What this proves and does not prove

- The exact six-schema request reached the real endpoint and received a 200 JSON
  response with model, fingerprint, real Completion ID and valid Usage.
- Reported output equals the requested 512 and finish_reason explicitly says
  length. That is consistent with the limit for this request, not a general guarantee.
- No field rejection occurred. Acceptance of the body does not establish that
  parallel_tool_calls=false or every schema annotation is semantically honored;
  no tool was proposed or executed here.
- The missing HTTP request-ID header was not the rejection cause. Raw Completion
  ID is available for audit; final successful AIMessage correlation metadata was
  not reached because finish_reason stopped the adapter earlier.
- A complete normal answer was **not** accepted. Do not score this as Agent goal
  completion, P1 readiness or evidence that one architecture is better.

No parameter was changed after failure and no second request was attempted.
The authorization is spent. Further paid execution requires a new explicit decision.

## Evidence and scope

RUN_STARTED.json is exclusive and prevents replay. PREFLIGHT.json records config,
packages, key availability (not value), price basis and reservation. REQUEST_BODY
and HTTP_REQUEST preserve the frozen/actual body; HTTP_RESPONSE preserves actual
sanitized response, hashes and whitelisted headers. Hidden reasoning and secrets
are omitted explicitly. TRACE.jsonl is flushed/fsynced per actual event. RESULTS
contains the full ledger snapshot; ANALYSIS.json distinguishes the truncated known
response from unknown billing and includes file integrity hashes.

Entry: `.venv-stageb/Scripts/python.exe -m experiments.ar01_free_agent.probe01`.
It uses existing build_live_model and REQUEST_WIRE_V1. Only the fixed execution
entry and new evidence files are added; approved adapter, budgets, Agent Loop,
production logic and old evidence are unchanged. Compile check ran before sending.
Full pytest was **NOT_RUN** this probe; previous 77/72 results are historical and
not presented as newly rerun. Browser/MCP/business writes/P1/P2: NOT_RUN or zero.

## Skill C close

**用户变化：** 获得一次真实协议与费用观察；没有新增生产能力。

**Agent 决策：** 模型输出文本、未请求工具；答复被截断，不能认定完整回答成功。

**观察驱动：** length/512 的真实响应触发现有停止合同；不做下一轮调查比较。

**新增约束：** 无新业务约束；本次使用单次授权、固定摘要和已有费用/重试守卫。

**简化结果：** 复用既有适配器与账本，仅加固定执行入口和审计记录。

**证据与停止线：** 1 次真实 POST、0 MCP、0 重试，原始截断保留；停止并交主 Agent。

**Submission: ACCEPTANCE_CANDIDATE — completed one-probe execution with incomplete
completion. P1 remains HOLD / NOT_AUTHORIZED. No main-Agent PASS or main merge.**
