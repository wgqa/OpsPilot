# R2-AR03-Integrated-Journey-01 — Acceptance Candidate

## Result

**Status: `ACCEPTANCE_CANDIDATE`**

This task exposed no missing production interface in the locked Base. The existing Assistant, protocol Knowledge, Skill, scoped S3 MCP, source projection and Worker can complete the frozen J1-J3 paths. I therefore made **no production-code, API, schema, runtime, UI or dependency changes**. The implementation diff is new offline journey coverage and persisted test evidence only; this fills the missing end-to-end acceptance case without adding another execution path.

The Fixture Model makes deterministic choices and produces synthetic Usage metadata. Passing these cases proves that the real local API/Worker/MCP/Domain path can carry the required inputs and observations; it does **not** prove that a real LLM will choose the same tools or produce equivalent quality. No paid Provider call, real-browser run, customer-data read, or external business write was made.

## Branch and worktree

- Repository: `wgqa/OpsPilot`
- Reused worktree: `D:\OpsPilot-LIVE-02-FIX-01-HF02`
- Candidate branch: `codex/r2-ar03-integrated-journey-01`
- Base: `91f55f6520b0333359d29482472aebd9f3fe3fb0`
- HEAD at evidence capture: the Base SHA above; the task-only candidate commit is created after this report.
- Initial worktree inventory: 76 existing worktrees; 0 added. The original dirty `D:\学习\agent新项目` tree and protected LIVE-02 data directory were not switched, reset, or modified.
- Initial target tree was clean and matched `origin/codex/live-02-fix-01-hf02`. No service listener was running on 8000, 5173, 5174 or 8080 at preflight.

Start-of-work SHA, file Blob IDs, branch/worktree inventory, previous experiments, six scope questions, and capability matrix are recorded in [PREFLIGHT.md](PREFLIGHT.md) and [WORKTREE_INVENTORY.md](WORKTREE_INVENTORY.md). The frozen synthetic cases and held-out wording are in [GOLD.md](GOLD.md).

## Capability matrix

| Classification | Finding | Source / evidence |
|---|---|---|
| Already connected | Session admission, durable Messages/Runs, Worker and Assistant loop | `opspilot/domain/chat.py`; `opspilot/web/app.py`; `opspilot/web/worker.py`; `opspilot/assistant.py::run_assistant` and `Loop` |
| Already connected | User-provided JSON/log are present as untrusted current-message material | `opspilot/assistant.py::SYSTEM`; `opspilot/domain/chat.py`; J1 trace records the exact fixture message in the model request |
| Already connected | Scoped protocol discovery, version comparison and bounded exact excerpt with source checks | `opspilot/assistant_mcp.py::run`; `opspilot/domain/assistant_knowledge.py`; `opspilot/domain/scoped_protocol_comparison.py`; existing AR-03 protocol/material tests |
| Already connected | Optional, method-only protocol Skill | `opspilot/assistant_mcp.py::load_protocol_upgrade_skill`; `opspilot/skill_assets.py`; J1 loads it, the held-out materials case omits it, and the simple HTTP 202 question makes no MCP call |
| Already connected | Bound same-order Delivery/Receiver reads with per-Run Observation/Evidence identity | `opspilot/assistant_mcp.py`; `opspilot/domain/s3_mcp.py`; `opspilot/domain/s3.py`; J2-QUEUED and J2-PROCESSED traces |
| Already connected | Historical/current source distinction in model Context and Web projection | `opspilot/domain/assistant.py::source_context_for_model`; `opspilot/web/app.py` session message route; `frontend/src/api.ts`, `frontend/src/App.vue`, `frontend/src/conversation.ts` |
| Existing components not previously frozen together | Full user materials + protocol comparison + checklist; same-Session follow-up after trusted binding; cross-Tenant denial followed by legal analysis | New J1-J3 tests and JSONL traces; no production interface was missing |
| Explicitly unverified | Real model's tool choice, wording quality, exact live-provider context and browser display of this integrated journey | Real Provider and browser automation were not authorized; no claim of real-LLM acceptance |

## Frozen offline journey results

All runs use isolated pytest databases, `TestClient`, the formal `create_app(..., start_worker=True)` Worker, the actual Assistant tool registration/dispatch, and the existing local Domain/MCP adapters. Protocol and business fixtures are synthetic. No production code or fixture Gold was changed.

| Case | Result and checks | Persisted run/tool evidence |
|---|---|---|
| J1, unbound materials | PASS. Exact configured `api_version=v1`, `max_attempts=5`, `backoff=fixed` and sample log fields are treated as user claims. The answer cites the actual scoped v1/v2 comparison and a versioned line excerpt, states deployment version/current order state are unknown, and provides a sourced checklist. No S3 tools or TaskBinding are available. Optional Skill was loaded. | Run `run-3396165f-bf7a-464e-a0af-868442ff9b40`, `SUCCEEDED`; 4 protocol/Skill MCP calls; largest context estimate 6,605 tokens. |
| J2-QUEUED, same Session | PASS. The second Run uses the first Run's still-selected user materials. After trusted order binding, the actual current Observation pair has the same Event ID; `HTTP 202 / ACKNOWLEDGED` is acceptance and Receiver `QUEUED` is not completed processing. The prior protocol answer is identified as historical, not reread. | Material Run `run-1b662823-9b1b-41d1-bc2a-25ee824ac597`; bound Run `run-345e04b8-f279-4080-bde8-9525f23c6b4e`; current Receiver/Delivery calls carry Evidence and Observation IDs in the trace; 2 current-run MCP calls; largest bound context estimate 7,762 tokens. |
| J2-PROCESSED, same Event | PASS. Same protocol with the same synthetic Event now returns current Receiver `PROCESSED`; final conclusion changes to processed. The paired Delivery/Receiver Evidence and Observation IDs are distinct current reads, not copied from J1. | Material Run `run-21c178ff-cda0-4251-abbf-58bd31cf9074`; bound Run `run-6e449c32-3b57-412e-9686-1a94eece0493`; 2 current-run MCP calls; largest bound context estimate 7,708 tokens. |
| J3, cross-Tenant binding denied | PASS. The tenant-a SUPPORT request to bind tenant-b's synthetic order returns 422 and creates no TaskBinding. A later legal unbound materials request in that same Session succeeds without seeing the other Tenant's order. | Run `run-22ede1ec-eb61-4dd8-81dc-bdbc1a53ee52`, `SUCCEEDED`; 3 scoped protocol MCP calls; no S3 business call. |
| Held-out wording + simple question | PASS. The held-out retry-configuration wording completes with sourced docs/checklist without Skill. A subsequent plain HTTP 202 explanation is answered without any MCP call. | Both persisted runs and calls are in the JSONL trace. |
| Historical answer follow-up without new Observation | PASS. The second model request has an empty `current_run.business_observations` list and the source-time instruction; it returns current status as unknown rather than claiming a fresh business read. | Both persisted runs and source payload are in the JSONL trace. |

Across the six journey records all Runs are `SUCCEEDED`, all fixture-database provider spend rows are 0, and every protected diagnosis/approval/action/receipt table count is 0. The two bound J2 Tasks show the actual `CONTUX_S3_V1` policy: 24 Investigator MODEL attempts, 18 MCP attempts, and an 8-call Assistant auxiliary cap. The J2 bound Run made 3 Fixture MODEL calls and 2 MCP calls. This differs from the historical AR-03-REAL-LLM-02 campaign's explicit 8/6 per-scenario cap; those are separate policies/experiments. No limit was changed.

The complete persisted trace (input messages, visible tool schemas, actual calls/results, source/Evidence/Observation references, answer links, Runs, elapsed time, Context estimate, Task budget and zero-spend/protected-write checks) is [J1-J3-FIXTURE-TRACE-FINAL.jsonl](runs/J1-J3-FIXTURE-TRACE-FINAL.jsonl). Fixture Usage values are not provider Token Usage.

## RED/GREEN and regression evidence

There is no production RED to fix: the frozen journeys pass on the target Base without a runtime diff. The initial drafts of the new test helper exposed its own incorrect SQLite column names and an obsolete 8/6 expectation; those harness issues were corrected. They are not reported as product failures. The final journey suite is **6 passed** in [FIXTURE-INTEGRATED-FINAL.log](runs/FIXTURE-INTEGRATED-FINAL.log).

The offline regression command used explicit provider/runtime-off flags and an isolated basetemp:

```powershell
$env:OPSPILOT_ASSISTANT_PROVIDER_ENABLED='0'
$env:OPSPILOT_LEGACY_PROVIDER_ENABLED='0'
$env:OPSPILOT_ASSISTANT_RUNTIME_ENABLED='0'
$env:OPSPILOT_MODEL_API_KEY='offline-only'
$env:OPENAI_API_KEY='offline-only'
$env:LANGSMITH_TRACING='false'
$env:LANGCHAIN_TRACING_V2='false'
$env:OPSPILOT_ASSISTANT_EXPERIMENT_ID=''
& 'D:\学习\agent新项目\.venv\Scripts\python.exe' -m pytest `
  tests/test_r2_ar03_integrated_journey_01.py `
  tests/test_ar03_material_01.py `
  tests/test_ar03_02_scoped_protocol_comparison.py `
  tests/test_ar02_ar03_integration_01.py `
  tests/test_ar03_material_live_01.py `
  tests/test_live_02_fix_01_history.py `
  tests/test_live_02_fix_01_memory.py `
  tests/test_live_02_fix_01_sla.py `
  tests/test_ar04c_f01_context_currentness.py `
  tests/test_c01_a_session_context.py `
  tests/test_r1_user_demo_hf02_sse.py `
  -q --basetemp "$env:TEMP\r2-ar03-regression"
```

Result: **95 passed, 2 failed** across these existing regressions plus the new journey. Both failures are on the unchanged Base implementation/test files and require main-Agent adjudication; neither was edited:

1. `test_product_01_same_event_queued_to_processed_uses_new_observation` expects the old fixed invalidation placeholder. The current dedicated LIVE-02 history contract preserves authorized historical answer text with `HISTORICAL_SNAPSHOT` / `S3_BUSINESS_VERSION_CHANGED`, while forbidding it from current model Context. This older assertion conflicts with `tests/test_live_02_fix_01_history.py::test_business_version_change_keeps_snapshot_and_fresh_query`, which passed.
2. `test_zero_tool_followup_can_explain_valid_historical_snapshot` expects a `current_run.completed_tools` field. Current source projection instead exposes `business_observations`; the new regression checks that this list is empty and history is not claimed as a current read. This is the known AR04C assertion mismatch, not a runtime code regression.

The separate offline AR04C compatibility run was **5 passed, 1 failed**. `test_ar04c_formal_worker_mock_pair_keeps_current_queued_facts_and_memory_only_diff` stops in `_ar04c_create_one_shot_claim()` with `AR04C_ONE_SHOT_AUTHORIZATION_INVALID`, before any model transport call. The other five cases passed. See [AR04C-REGRESSION.log](runs/AR04C-REGRESSION.log). No claim auth, Provider or paid authorization was created.

The full targeted log is [TARGETED-REGRESSION.log](runs/TARGETED-REGRESSION.log). Previous AR-03 and AR-04C real-model findings remain in their original evidence folders and were not overwritten. In particular, the historical PROCESSED run that reached `ASSISTANT_RUN_MCP_LIMIT` and the zero-Observation false reread claim remain unresolved real-model quality evidence.

## Implementation Diff

- Added `tests/test_r2_ar03_integrated_journey_01.py`: isolated local API/Worker journey cases, deterministic Fixture Model, source/currentness checks, current Task budget verification, zero spend/protected-write assertions.
- Added this evidence directory's preflight, frozen synthetic Gold, worktree inventory, run logs and trace.
- **No production code, Schema, frozen contracts, frontend, Runtime Grant, MCP interface or dependency changed.**

The file under test intentionally preserves the free-form Assistant tool contract; tests assert the tools/results used but do not enforce tool-call ordering in production. The Fixture Model itself is deterministic and is not autonomy evidence.

## Browser/User-Test Readiness

**`USER_TEST_READINESS_CANDIDATE`: NO / UNVERIFIED.** The candidate demonstrates offline API/Worker/MCP composition, not that the actual configured model will autonomously deliver the user goal. No browser automation or live Provider call was made by authorization. The existing `Start-UserDemo.ps1` is present but its S1/S2 profiles were not validated as a clean R2 `orders-async-demo` test dataset. Do not point it at or reset `D:\OpsPilot-C01-B2-LIVE-01-HF02` data.

For a later user-led check after independent acceptance:

- Start only from an explicitly isolated Demo directory with fresh domain and checkpoint SQLite files, a SUPPORT test user, one synthetic registered order/Event, and an authorized local protocol document scope for both v1 and v2.
- The user can paste the frozen prompt and sample JSON/log from [GOLD.md](GOLD.md), first without a TaskBinding, then bind the synthetic order through the UI and ask: “请结合刚才的材料，核对这个订单当前同一 Event 的处理状态。” Repeat once with same-Event Receiver QUEUED and once PROCESSED.
- A live run must inspect the actual redacted model input, calls, Usage/spend and user-visible answer. It must not infer success from this Fixture suite or from HTTP 202 alone.
- Existing PowerShell syntax is `.\scripts\user-demo\Start-UserDemo.ps1 -Profile S1 -Mode Live` (or `S2`); stop with `.\scripts\user-demo\Stop-UserDemo.ps1`. Live mode performs Runtime preflight and requires this worktree's local `.env`. The launcher maps S1/S2 to `orders-demo`/`orders-demo-s2`; this task's bound R2 fixture uses `orders-async-demo`, and no matching clean manual-test profile or grant was prepared. Do not run those commands for this journey as if they had been validated. No start/stop command is represented as tested readiness.

## Source learning map

1. **User request → Session/Message/Run:** `frontend/src/App.vue` calls the session API; `opspilot/web/app.py` accepts the message/binding; `opspilot/domain/chat.py` persists user Messages, Run and trusted Task scope.
2. **Context:** `opspilot/domain/chat.py` assembles current user material and history; `opspilot/domain/assistant.py::source_context_for_model` distinguishes current observations from historical source snapshots.
3. **Agent decisions:** `opspilot/assistant.py::run_assistant` and `Loop` call the injected model with available tools and continue on tool results. The current model chooses whether to answer, query docs, load Skill, or use bound business reads; application scope remains trusted code.
4. **Knowledge/Skill/MCP:** `opspilot/assistant_mcp.py::run` registers the tools; `assistant_knowledge.py` and `scoped_protocol_comparison.py` return versioned sourced material; `skill_assets.py` loads optional method-only guidance; `s3_mcp.py` reads only current TaskBinding-scoped business facts.
5. **Observation → final delivery:** local MCP calls persist call/result and source links to `assistant_calls`, D2 Observation/Evidence records and `chat_run_answers`/Messages. `web/app.py` projects current vs historical source visibility; Vue `conversation.ts` and `App.vue` render that projection and activity.

## Limits

- No real Provider requests: **0**. No real browser runs: **0**. No external business writes: **0**.
- Vue build: `NOT_RUN` (no frontend changes). Live user acceptance: `NOT_RUN`.
- Full repository suite: `NOT_RUN`.
- Historical failures above remain open; this task does not modify them or claim a real-model fix.

One local evidence-cleanup command for intermediate harness logs was rejected by the command policy. Those intermediate files are not staged; only the final named logs/trace and report are included in the candidate commit.
