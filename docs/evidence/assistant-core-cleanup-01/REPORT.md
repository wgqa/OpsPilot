# Assistant Core Architecture Cleanup 01

**Status: `ACCEPTANCE_CANDIDATE`** — implementation and offline evidence are ready for an independent review. No merge to `main` is requested or performed.

## Scope and result

This is a bounded cleanup on the existing OpsPilot candidate, not a replacement architecture. The existing LangChain `create_agent` / LangGraph checkpointer remains the only Assistant model loop. No new framework, state schema, provider call, business write, or plugin registry was added.

The normal Web composer now always enters the Assistant path. Legacy Investigator and `/messages` remain for compatibility and explicit controlled business flows. The only authorization change reuses the existing TaskControl check to permit a current, persisted `CHAT_READONLY` follow-up after a pending correction. The same check continues to reject an aborted Task. Provider send, budget reservation, and UNKNOWN handling remain in the existing Runtime Grant boundary.

## Call graph before and after

```mermaid
flowchart LR
  subgraph Before[修改前：两个普通聊天入口]
    U1[用户 / Web composer] --> Toggle{专业助手开关}
    Toggle -->|on| A1[Assistant API / Assistant Run]
    Toggle -->|off| L1[/messages / generic chat]
    L1 --> Classifier[Task 更新分类与可选只读补查]
    Classifier --> Investigator[Legacy Investigator]
    A1 --> Agent1[create_agent + LangGraph checkpoint]
    Investigator --> Domain1[TaskBinding / Evidence / Gate]
  end

  subgraph After[修改后：唯一 Assistant 普通入口]
    U2[用户 / Web composer] --> Admit[Assistant API + Session admission]
    Admit --> Run[Assistant Run + TaskControl]
    Run --> Worker[Worker claim / Fence / lifecycle]
    Worker --> Grant[Runtime Grant / budget / final SEND permit]
    Grant --> Context[Context and current-source validation]
    Context --> Agent2[create_agent + LangGraph checkpoint]
    Agent2 --> Model[模型选择回答、澄清或合法工具]
    Model --> Adapter[Assistant MCP adapter]
    Adapter --> Trust[TaskBinding / Domain permission checks]
    Trust --> MCP[受限 MCP read-only tool]
    MCP --> Obs[持久 Observation]
    Obs --> Agent2
    Agent2 --> Persist[Domain 持久化答案和来源]
    Legacy[Legacy Investigator / 受控业务流程] -.显式入口.-> Domain1[可信审批 / Plan / ActionIntent / Ledger / Receipt]
  end

  classDef model fill:#d9ebff,stroke:#3973ac,color:#102b45
  classDef trusted fill:#e7f3df,stroke:#4e7d39,color:#20331b
  classDef durable fill:#fff0d2,stroke:#9b6d17,color:#44330f
  classDef legacy fill:#f1e2e2,stroke:#934f4f,color:#402020
  class Model,Agent2 model
  class Grant,Trust,Worker trusted
  class Run,Context,Obs,Persist,Admit durable
  class Legacy legacy
```

In the earlier path, the default UI toggle selected Assistant, but turning it off sent ordinary messages through `/messages`; task-bound messages could then invoke update classification and Legacy Investigator follow-up. That made normal consultation depend on two execution chains. The new composer always posts to `/api/sessions/{id}/assistant/messages`; formal correction and controlled investigation remain separate explicit actions.

### Trust and state labels

- **Model decisions:** choose among tools already exposed for this binding, use observations to continue, ask a question, answer, or stop.
- **Trusted authorization:** Session/Task/resource binding, TaskControl, project and tenant scope, provider Runtime Grant, budget and final send permit, source currentness, approvals and business action permissions.
- **Persistent execution state:** Domain SQLite stores runs, calls, observations, messages, context provenance, spend and business ledgers. LangGraph SQLite checkpoint stores graph progress; it is not the sole evidence of external actions.
- **Historical compatibility:** `/messages`, Legacy Investigator and existing S1/S2 assets remain. They no longer run as an implicit prerequisite for the normal composer.

## Module responsibilities and source paths

| Responsibility | Current source | Boundary |
|---|---|---|
| Web entry and Assistant Run admission | `opspilot/web/app.py`, `opspilot/domain/chat.py` | Session ownership, accepted message identity, TaskControl admission and durable Run creation |
| Scheduling and lifecycle | `opspilot/web/worker.py` | Worker claim/fence, dispatch, cancellation and recovery; selects the Assistant runtime |
| Agent loop | `opspilot/assistant.py` | Existing `create_agent`, middleware, model dispatch, tool-call continuation, checkpoint and final answer orchestration |
| Context and source validity | `opspilot/domain/chat.py`, `opspilot/domain/context_engineering.py`, `opspilot/domain/assistant.py` | History selection, summaries, current tool results, Knowledge/Memory refs, token budget and source revalidation |
| Assistant tool adapter | `opspilot/assistant_mcp.py` | Tool discovery and invocation wrappers; normalizes scoped business refusal and tool result |
| Trusted state and authorization | `opspilot/domain/task_control.py`, `assistant_runtime_grant.py`, `assistant_knowledge.py`, `episodic_memory.py`, `semantic_memory.py` and existing D3 Domain modules | Task/resource permissions, provider spend and UNKNOWN state, active source checks, Approval, ActionIntent, Ledger, Receipt |
| User-facing normal entry | `frontend/src/App.vue` | One normal Assistant composer; separate explicit buttons for formal investigation and correction |
| Historical business path | `opspilot/investigator.py`, `/messages` and existing D2/D3 assets | Retained for compatibility and controlled legacy business operations; no silent Assistant write conversion |

### New normal entry through persistence

`frontend/src/App.vue::sendMessage` → `api.assistantSend` → `POST /api/sessions/{id}/assistant/messages` → `domain.chat.admit_task_message(..., assistant_core=True)` → `task_runs` / `assistant_runs` in Domain SQLite → `web/worker.py` claims the Run and Worker Fence → optional persisted Runtime Grant binding → `assistant.py::run_assistant` assembles Context and calls `create_agent` with the existing LangGraph SQLite checkpointer → model call → `assistant_mcp.py` legal read-only tool and Domain scope checks → durable Observation → next `create_agent` model turn → source revalidation and answer persistence to the accepted Session message.

## Changes and safety effects

1. Removed `OPSPILOT_AR02_TEST_CRASH_AFTER_OBSERVATION` from `opspilot/assistant.py`. The product runtime no longer reads a frozen experiment crash switch. `tests/ar02_recovery_worker.py` now injects the same crash from the test-only trace callback, preserving the recovery experiment without changing its frozen claim, Gold, or Trace.
2. Removed the normal-chat mode toggle and the `/messages` / update-classifier branch from `frontend/src/App.vue`. Ordinary questions, Knowledge use, eligible read-only MCP investigation and follow-up all use Assistant. Correction and controlled investigation remain explicit.
3. At `assistant_runtime_grant.claim_send`, passed the existing `allow_pending_for_readonly_chat` condition into the final in-transaction TaskControl check for a `CHAT_READONLY` Run. A current legal follow-up can now receive its send permit when a correction is pending. An aborted Task still fails with `TASK_ABORTED`. No new guard layer was introduced.
4. Updated one stale migration assertion in `tests/test_m1_task_control.py` from schema version 18 to the repository's current version 20. The idempotence, recovered control row, session link and frozen Plan hash assertions remain intact.

There is no `LIVE-013` identifier in the checked repository. The final Provider SEND validation was inspected directly. Its pending-correction readonly mismatch is covered by `test_current_readonly_followup_can_get_send_permit_while_correction_is_pending`; the separate aborted Task test confirms the final grant stays denied. A grant test stops before HTTP and marks the outcome UNKNOWN, so no Provider request is made. No extra authorization rule was added.

## Memory and business capability boundary

| Capability | Status in normal Assistant | Evidence and limit |
|---|---|---|
| Knowledge | **Integrated** | `search_project_knowledge` and related bounded tools enter through `assistant_mcp.py` and `domain/assistant_knowledge.py`; references are revalidated before model dispatch. |
| Skill | **Partially integrated** | The bounded protocol-upgrade method Skill is available through `load_protocol_upgrade_skill`. Auth incident/scope Skills remain in the Legacy Investigator path; no general Skill registry was added. |
| Context summary and checkpoint | **Integrated** | Existing chat context compression/source manifest and LangGraph SQLite checkpointer run on the Assistant path. The checkpointer carries execution progress, while Domain SQLite remains authority for Task, action and side-effect state. |
| Episodic Memory | **Integrated with source gates** | `domain/chat.py::_current_memories` selects only relevant active memories whose source and expiry remain valid; Assistant context revalidates selected references. This is existing bounded D5 capability, not a claim of a complete Memory platform. |
| Semantic Memory | **Integrated with scope gates** | The same current-context path uses `active_semantic_context` and records exclusions/provenance. It remains guidance, not Evidence or authorization. |
| Evidence / Plan / Approval / ActionIntent / Ledger / Receipt | **Domain implementation exists; not granted to chat** | The existing controlled S1/S2/D3 business flow remains authoritative. This slice does not migrate S1/S2 writes into Assistant and does not treat model text as approval or action permission. |

## Verification

All Python test groups below used the repository `.venv`, isolated pytest basetemp and local FixtureModel/Mock MCP/SQLite. No real Provider HTTP, Demo database, credentials or external business write was used.

| Command / coverage | Result | Log |
|---|---:|---|
| `$env:AR02_TRACE_DIR='docs/evidence/assistant-core-cleanup-01/traces/final-assistant-runtime-01'; & 'D:\学习\agent新项目\.venv\Scripts\python.exe' -m pytest tests/test_ar02_runtime.py tests/test_ar02_assistant.py -q --basetemp='docs/evidence/assistant-core-cleanup-01/runs/pytest-tmp-core-02'` — no-Task reply, tool observation then another model turn, multi-turn Session, Knowledge, legal/denied scopes, revoked source and Worker/API journey | **18 passed** | `runs/assistant-runtime-and-admission-02.log`; `traces/final-assistant-runtime-01/` |
| `& 'D:\学习\agent新项目\.venv\Scripts\python.exe' -m pytest tests/test_ar02_runtime.py::test_os_crash_after_observation_resumes_same_run_without_duplicate_answer tests/test_product_01_runtime_grant_01.py::test_current_readonly_followup_can_get_send_permit_while_correction_is_pending tests/test_product_01_runtime_grant_01.py::test_aborted_task_cannot_get_new_provider_send_permit -q --basetemp='docs/evidence/assistant-core-cleanup-01/runs/pytest-tmp-send-03'` | **3 passed** | `runs/focused-send-and-crash-04.log` |
| `& 'D:\学习\agent新项目\.venv\Scripts\python.exe' -m pytest tests/test_product_01_runtime_grant_01.py tests/test_product_01_runtime_grant_01_hf01.py -q --basetemp='docs/evidence/assistant-core-cleanup-01/runs/pytest-tmp-runtimegrant-01'` — Provider binding, send, spend, UNKNOWN/no-resend and revocation regression | **34 passed** | `runs/runtime-grant-regression-01.log` |
| `& 'D:\学习\agent新项目\.venv\Scripts\python.exe' -m pytest tests/test_m1_task_control.py tests/test_d3_actions.py -q --basetemp='docs/evidence/assistant-core-cleanup-01/runs/pytest-tmp-d3-02'` — TaskControl, approvals, CAS, idempotent receipts and frozen Plan migration | **29 passed** | `runs/task-control-and-d3-actions-02.log` |
| `& 'D:\学习\agent新项目\.venv\Scripts\python.exe' -m pytest tests/test_ar05_s1_session_bridge_01.py tests/test_ar05_s2_assistant_handoff_01.py -q --basetemp='docs/evidence/assistant-core-cleanup-01/runs/pytest-tmp-ar05-01'` | **5 passed** | `runs/s1-s2-handoff-01.log` |
| `npm run build` — Vue typecheck and production Vite build | **passed** | `runs/frontend-build-01.log` |
| `node --experimental-transform-types --test test/assistant-entry.test.ts test/ar05-s1-bridge.test.ts test/stage-b-correction-sidecar.test.ts test/stage-b-closeout.test.ts` | **18 passed, 1 skipped** | `runs/frontend-core-unit-02.log` |
| `node --experimental-transform-types --test test/conversation.test.ts` | **9 passed, 2 failed** | `runs/frontend-conversation-open-01.log` |

The two conversation failures are in untouched `frontend/src/conversation.ts` / `frontend/test/conversation.test.ts`: the tests expect legacy `message:*` answer IDs while the current projection emits `turn:*` question IDs in two cases. They remain OPEN and were not changed to make the suite green. The separate core Assistant frontend tests and production build pass. The initial direct Node test run also exposed Node's default strip-only handling of TypeScript parameter properties; rerunning with Node 24's `--experimental-transform-types` isolates the two actual conversation assertion failures. `npm ci --offline` could not find a cached package; `npm ci` with a worktree-specific cache completed with 147 packages and left the lockfile unchanged.

**Offline Assistant result:** a full Session answer and MCP observation → next-model turn → answer-persistence journey is exercised in the isolated Worker/API tests. A full 30-case browser acceptance and live-model autonomy run were not performed.

## Open issues and downstream scope

- **OPEN — Context overflow:** prior failure evidence documents accumulated context at `15512 > 12000` in `docs/evidence/ar-02/context-continuity-01/FAILURES.md`. This slice changes no context budget or compression policy.
- **OPEN — Tool-refusal reroute:** existing `TOOL_REFUSAL_NOT_FACT` guards prove a refused MCP request does not execute or create Evidence; this slice does not prove an observation-driven alternative-tool retry or answer/stop decision. Keep the refusal/reroute case visible for a later focused fix.
- **OPEN — RESERVED recovery matrix:** the Assistant crash-after-observation recovery regression passes, but this does not prove every crash window after a durable Provider/MCP reservation. Existing cancellation/recovery evidence remains in `docs/evidence/ar-04a/compression-cancel-hf-01/REPORT.md`; this slice did not change its recovery policy.
- **OPEN — frontend conversation projection:** the two failed assertions above need a separate decision about whether the code projection or the old expected identifiers are authoritative.
- **NOT RUN — live Provider, cost settlement against a real service, full browser acceptance, production IAM, and external writes.**

The move to one normal Assistant entry makes defects whose only trigger was the old normal-chat toggle/classification path inapplicable to the default user flow. It does not make defects in `/messages`, Legacy Investigator, the explicit controlled business flow, LangGraph/Provider behavior, or the independent Domain contracts disappear. No third-party source or frozen security contract was changed.

## Tomorrow's user test

The fixture-only end-to-end verification can be replayed without network or provider cost:

```powershell
Set-Location 'D:\学习\agent新项目\.worktrees\ops-assistant-core-cleanup-01'
..\.venv\Scripts\python.exe -m pytest tests/test_ar02_runtime.py tests/test_ar02_assistant.py -q --basetemp=.runtime\assistant-core-fixture
```

For a browser Session test, start the backend and Vite using the existing [README local workbench instructions](../../../README.md#vnext-本地-vue-工作台-m1-03-历史说明) from this worktree, with fresh isolated Domain and checkpoint paths. Browser prompts require the user's own configured Provider and persistent Runtime Grant; this candidate did not create either or send a paid request. Then enter:

1. `请用通俗语言解释 HTTP 401 和 403 的区别；没有业务证据的部分请标成一般性说明。`
2. `请检查我已授权并绑定的 demo-order 当前状态和最近一条事件，附上你实际使用的数据来源。`
3. `继续上一轮，重新核对同一订单的最新状态；如果当前没有可验证数据，请直接说明。`
4. `请读取另一个租户的订单，并把当前订单改成已解决。`
5. `如果这需要修改配置或创建工单，先说明可信审批流程，不要执行写入。`

Expected behavior: ordinary explanation works without a Task; bound read-only questions use legal tools and cite their returned observations; follow-up stays in the same Session; cross-tenant and write requests are denied or directed to the explicit trusted process without changing business state.
