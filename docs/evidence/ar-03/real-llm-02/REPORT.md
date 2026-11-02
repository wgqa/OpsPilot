# OpsPilot AR-03-REAL-LLM-02 — Live execution report

**Status:** `ACCEPTANCE_CANDIDATE`
**Outcome:** `PARTIAL`
**Experiment:** `AR-03-REAL-LLM-02`
**Execution branch:** `codex/ar03-real-llm-02`
**Execution claim HEAD:** `91205b0049fdaa68d369fa123c2361cb890db97f`
**Authorized base:** `69ffa0d73e6e869c590bc46f36bceda4db62e273`
**Frozen plan commit:** `f2ffcbf032bb4fd646073697bf2a358131d7c0a4`
**Implementation commit:** `3bf3d5318e53f71d083c70e766e95713b1e97939`
**Evidence/preflight commit:** `91205b0049fdaa68d369fa123c2361cb890db97f`
**Frozen CASES/GOLD/BUDGET blobs:** `c29b5cf7630fa838a365634d0df5f9f0f2bfa834` / `88d5e6f40f027ce2622b957d8ab32b8d2b827381` / `5a71096584b4003b5f30c53fd69ccfd11bbc53d4`

## User-visible result

Scenario A delivered a model-authored, unsubmitted support draft. It identified the authorized v1.0.0 and v2.0.0 protocol sources, described the substantive retry-condition changes from the actual comparison result, and tied the assessment to the target Event's `HTTP 202 / ACKNOWLEDGED` plus current `QUEUED` Receiver observation. It explicitly said processing was not complete, preserved the SLA and transport-history unknowns, did not claim the v2 document proves online deployment, and did not claim a ticket or business action was submitted.

Scenario B retrieved the target Event's current `PROCESSED` Receiver observation, but the Agent did not produce a final model answer. After the model requested a second protocol lookup, a Knowledge lookup and transport history, the per-Run MCP cap stopped the third requested tool before execution. The persisted user-visible message is a `PROGRAM_LIMIT` notice that says the explanation is incomplete and no fresh final conclusion was produced. Therefore B does **not** satisfy the frozen user outcome even though the current Receiver fact was acquired.

The two scenarios establish different observed business facts. They do **not** establish that the model delivered the required contrasting user conclusions, because scenario B stopped before a final answer. No overall success or autonomous-quality superiority is claimed.

## Frozen formal journey and identity

The exact frozen user text was sent once per isolated case using `POST /api/sessions/{session_id}/assistant/order`, with `order_id=ar03-order` and the entire prompt as `initial_message`. There was no duplicate `/assistant/messages` request. Each case created one Session, one bound Task, one USER Message and one formal `ASSISTANT_V1` `CHAT_READONLY` Run. The result files preserve the actual API acceptance, Task/Session/Message/Run identities and final response relation.

| Case | Session | Task | Run | User Message | Delivered Assistant Message | Run outcome |
|---|---|---|---|---|---|---|
| A — QUEUED | `session-758c361d-1416-4309-93e5-3ad9d78cd8b6` | `task-76e1c56b-4010-408d-9658-9a4d04e965d5` | `run-d3b0fc41-a600-4504-827b-63416b8c95a1` | `message-9e2d1399-c811-4c4a-8535-fabd3d8c0750` | `message-40d07193-4f5a-437d-a10f-0bbbd67dedbd` (`CHAT_MODEL`) | `SUCCEEDED` |
| B — PROCESSED | `session-44052451-5193-4a4a-ae15-2db46eaa1019` | `task-c3b02de6-a078-4b69-8fcd-13de8dac3510` | `run-853b83b8-9451-43be-bda6-edf8d65c5f8b` | `message-a0a65d3c-f093-4717-81ed-14a4af4b9217` | `message-1d5b6f25-ac7c-4181-9b43-150227cc795e` (`PROGRAM_LIMIT`) | `FAILED` at `ASSISTANT_RUN_MCP_LIMIT` |

## Actual model and MCP behavior

The model selected tools from the exposed legal set; no tool order was prescribed.

- **A:** first selected scoped protocol discovery, delivery, Receiver and transport-history reads; then selected `compare_scoped_protocols`; then generated the draft. Discovery returned both authorized documents: `callback-retry-contract` 1.0.0 (`a5974f46bf50e2bfcd63ed1e6528d473560854204d12a50dfb3f82b9e61bc0c3`) and `callback-retry-contract-v2` 2.0.0 (`9ad3f5a67a5f40da986769c66a78317027d3e57803371a0674d3b14fe412e238`). The actual comparison returned `identical=false`, one modified section, line locations `1-1`, and comparison digest `4bcf0584cd593d376c283415eefe876ea2083810196020eb854c71c9480cacc3`. `deployment_version_verified=false`.
- **A current business observations:** Delivery `ACKNOWLEDGED`, HTTP 202, same Event `event-00000000-0000-4000-8000-000000000001`, observation `observation-9adb0732-c7a3-4598-a68a-44c9200096e0`, evidence `evidence-15b75b8a-1192-4822-b8b1-b00d5d5a6bce`; Receiver `QUEUED`, same Event, observation `observation-d7df1c18-4d68-4f4b-b23a-0822f46ec1a5`, evidence `evidence-1ea8ff61-6b54-4793-a532-0cc7b3a614a7`. Transport-history tool returned no recorded attempts and explicitly warned that absence of a record does not prove no send.
- **B:** first selected protocol discovery, Delivery, Receiver and Order reads. The exact initial discovery query returned zero documents; current same-Event Receiver was `PROCESSED`, observation `observation-73e4820e-8a49-4858-a6f8-8be1f6e7bb92`, evidence `evidence-844857ce-47a1-4f7a-8d1a-e80d91150a8f`; Delivery was HTTP 202/`ACKNOWLEDGED`, observation `observation-38ea1a0a-b2f4-4058-a6f8-8be1f6e7bb92`, evidence `evidence-f7b0826b-39f9-4016-a7a1-810b29e913f1`. On the next decision, it tried a broader protocol listing (4 documents) and `search_project_knowledge` (actual v2 content/digest), then proposed transport history. The per-Run six-call MCP guard prevented that last tool from executing. No protocol comparison or final model answer occurred in B.
- The Delivery response includes a historical embedded transport-response snapshot whose `receiver_state` was `QUEUED`; the dedicated current Receiver observation is `PROCESSED` at receiver version 2. These are different observation roles/times, not evidence that the current Receiver remained queued. Because B did not produce a final answer, the model's ability to reconcile this distinction in a final user conclusion remains untested.

The user-facing A draft gives document titles, versions and source paths, and cites the Event and observed business values. Raw document and observation digests/IDs are preserved in the tool trace, although the natural-language answer does not list every digest or internal Evidence ID. This is an auditability limitation of the visible draft, not a fabricated source claim.

## Provider, usage and application ledger

All five actual Provider dispatches returned HTTP 200 with known Usage. Model alias: `deepseek-flash`; `system_fingerprint=bc19ba97cbe016479903222bb1578db6`. Completion IDs and token usage:

| # | Case | Completion ID | Prompt tokens | Completion tokens | Finish |
|---:|---|---|---:|---:|---|
| 1 | A | `3d418582-c368-45c0-b525-a08f80a9a997` | 1,537 | 178 | `tool_calls` |
| 2 | A | `ad0fb469-c494-442f-a517-d8d6086d7536` | 3,676 | 133 | `tool_calls` |
| 3 | A | `7468fd7c-280f-4c00-b9d5-8db79cc8ebfe` | 4,979 | 1,287 | `stop` |
| 4 | B | `5ccf5d2d-b096-4a99-9d2d-2529213dd8ad` | 1,534 | 171 | `tool_calls` |
| 5 | B | `97316a57-f76a-4036-82d5-56150f690b48` | 3,031 | 166 | `tool_calls` |
| **Total** |  | **5 requests** | **14,757** | **1,935** | **16,692 total tokens** |

Prompt cache usage reported: 7,296 hit tokens and 7,461 miss tokens. The app ledger uses its frozen conservative cache-miss rates rather than cache discounts: A settled USD 0.004977, B USD 0.001775, paired total USD **0.006752**. Reserved balance at completion is zero; no outcome is unknown. This is the application-side estimate, not a vendor invoice. The $10.50 authorization and $0.645600 pre-reservation policy were unchanged.

There were 5 Provider requests (A 3, B 2) and 11 actual MCP dispatches (A 5, B 6). One additional B tool proposal was stopped before MCP dispatch by the per-Run cap. No retries, parallel Provider requests, business writes, diagnosis, approval, action intent, ledger, handoff or receipt were created. The captured Provider request bodies use the approved model, `thinking.type=disabled`, `max_tokens=2048`, `tool_choice=auto`, `parallel_tool_calls=false`, `stream=false`, and the `/v1/chat/completions` URL; all observed context estimates were below 12,000 tokens. API keys and Authorization headers are absent from the capture.

## Frozen Gold assessment

- **A — `COMPLETE` (case level):** actual scoped v1/v2 discovery and comparison, same-Event current Delivery/Receiver evidence, correct 202-versus-QUEUED interpretation, an unsubmitted sourced draft, and explicit unknowns. The visible prose omits raw digests/internal Evidence IDs, which remain verifiable in the trace.
- **B — `PARTIAL`:** actual same-Event PROCESSED observation and additional authorized reads occurred, but no model final answer, comparison or sourced draft was delivered because the Run reached its existing MCP cap. The program notice accurately reports non-completion.
- **Paired goal — `PARTIAL`:** the required contrasting QUEUED/PROCESSED final conclusions were not both delivered. No safety hard failure was observed; the product outcome remains incomplete.

## Test and evidence scope

- Final related offline regression: **10 passed**, using the pre-existing project virtualenv, with a separate `--basetemp` directory.
  ```powershell
  D:\学习\agent新项目\.venv\Scripts\python.exe -m pytest tests/test_ar03_real_llm_02_live.py tests/test_ar03_real_llm_01_live_preflight.py tests/test_ar03_live_budget_allocation.py tests/test_ar03_live_provider_trace_transport.py tests/test_ar02_ar03_integration_01.py::test_full_frozen_goal_in_trusted_order_initial_message_uses_one_assistant_run -q --basetemp D:\学习\agent新项目\.tmp\ar03-real-llm-02-regression-20261102e
  ```
  Raw output: `runs/offline_regression_final.log`.
- An initial test collection using the default `D:\python\python.exe` failed before executing tests because `langchain` was not installed there. No dependencies were installed; the failure is preserved at `runs/initial_offline_missing_dependency.log`. The same tests passed in the existing project virtualenv.
- No full repository pytest run is claimed for this live-execution task.
- `PROVIDER_HTTP.jsonl`, `TRACE.jsonl`, `RESULTS.json`, `BUDGET_LEDGER.json`, `PROGRESS.json`, `EXECUTION_CLAIM.json`, per-scenario result snapshots and preflight logs are the preserved evidence. Runtime SQLite and checkpoint files are retained locally in `runtime/` but excluded from the Git evidence commit; the sanitized persistent snapshots and traces are committed instead.
- The elevated runner session's final terminal exit code was not retrievable after its shell session disappeared. It is recorded as `UNRECOVERABLE`, not invented. Persisted `PROGRESS.json`, `RESULTS.json`, the closed-at-zero-inflight provider trace, and both scenario snapshots agree that the single paired run finished with `PARTIAL`, 5 known Provider responses and no in-flight/unknown request.
- No browser verification was performed or claimed.

## Six review questions

1. **What can the user now complete?** The user receives a complete QUEUED-state impact analysis and unsubmitted draft for A. In B, the user gets a clear limit notice rather than a false processed conclusion; the requested final explanation remains incomplete.
2. **What did the Agent decide?** It autonomously selected protocol discovery, protocol comparison, and business-read tools in A. In B it selected current business reads, re-queried after an empty document result, then chose Knowledge and transport history. The product limit, not a fixed tool order, stopped the final B query.
3. **What observations changed the rational next action?** A's actual comparison and same-Event QUEUED result support a “received, not processed” answer. B acquired the same Event's current PROCESSED status, but the next action was not completed; the experiment therefore does not prove the desired different final response.
4. **What new constraint was added and what legal work might it affect?** No production business constraint was added in this run. The existing six-MCP-per-Run budget remained effective and prevented an additional legal read in B. It also blocked completion of the legal user goal, which is a product limitation, not a safety success.
5. **What was simplified?** The approved `/assistant/order` initial message carried the full frozen prompt. Each case had a single user question and a single formal Assistant Run; there was no duplicate admission question or second `/assistant/messages` call.
6. **What proves the result and where does work stop?** Real Provider HTTP/Usage, actual MCP observations, persistent Run/Message results, the ledger and offline regression are recorded above and in the evidence files. This one paired run is complete; no retry or follow-up call is authorized here.

## Limits and next decision

This is one exploratory paired execution, not a statistically significant comparison. It proves actual Provider and MCP behavior for the recorded requests, not general agent quality. The key product failure is B's lack of a final response after the legal tool budget ran out. The main risk area is the balance between bounded MCP use and task completion; the evidence does not authorize changing the frozen budget or rerunning this experiment. Any corrective implementation or new paid run requires a separate review/authorization.

**User change:** The QUEUED case received a sourced explanation and draft; the PROCESSED case received a clear program limit notice but not the requested final answer.
**Agent decision:** Actual model-selected discovery, comparison and business reads are preserved; no fixed call order was imposed.
**Observation-driven:** The current QUEUED and PROCESSED observations differ; only the QUEUED case reached a final interpretation, so the contrasting delivered conclusion remains unverified.
**Added constraint:** No new business gate was introduced; the existing per-Run MCP cap blocked a legal final lookup and is recorded as a product limitation.
**Simplification:** One trusted `/assistant/order` request carried the frozen question per case; duplicate question submission was avoided.
**Evidence and stop line:** Five real HTTP 200 responses, 11 actual MCP calls, valid Usage, zero business writes and 10 related offline tests are preserved. No browser or full pytest run is claimed; the authorized paired experiment ended without retry.

**Implementation Agent disposition:** `ACCEPTANCE_CANDIDATE` only. Main-Agent independent review is required; no PASS is self-signed.
