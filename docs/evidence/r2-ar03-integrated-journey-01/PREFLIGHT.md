# R2-AR03 Integrated Journey 01 — Preflight and Capability Matrix

## Start-of-work verification

- Repo: wgqa/OpsPilot, local checkout D:/OpsPilot-LIVE-02-FIX-01-HF02.
- Base: 91f55f6520b0333359d29482472aebd9f3fe3fb0; local HEAD and origin/codex/live-02-fix-01-hf02 matched before branch creation.
- Candidate: codex/r2-ar03-integrated-journey-01, created inside the existing HF02 worktree at the same Base. No new worktree was created.
- The HF02 worktree was clean before branch creation. No OpsPilot listener was present on ports 8000, 5173, 5174, or 8080; the only process path match was the current PowerShell check. The protected LIVE-02 data worktree remains D:/OpsPilot-C01-B2-LIVE-01-HF02; it was not opened or modified.
- Remote read: origin/main=60eee87bfe3cca522011316cb4cd2c0064ad291b; origin/codex/live-02-fix-01-hf02=91f55f6520b0333359d29482472aebd9f3fe3fb0. No main operation is authorized or performed.
- The initial inventory contained 76 worktrees; WORKTREE_INVENTORY.md records their paths, branches and HEADs. Default/new worktrees: 0.
- Tests and local services: NOT_RUN at this preflight snapshot.

## Target commit files actually read

| File | Blob | Use |
|---|---|---|
| PROJECT_NORTH_STAR.md | 43dabda468506717c6956e676dfad4304c4f38e6 | Read full current file and section 8; user-journey priority, R2 route, six questions, bidirectional restrictions, history/failure preservation. |
| AGENTS.md | 807b928686a4dd2cac7b15b3c354b9943c93c910 | Read current root instructions; trusted binding, MCP, no business writes, v1.2 route controls scope. |
| .agents/skills/opspilot-slice-review/SKILL.md | d405c8d413d633824b279202cc1503dab4cf0b03 | Actually read and applied A; formal scope and evidence handled under B/section 8. |
| TASKS.md | 1f08ee3a8e538d7ece4d2b2841c7c53e25737b7c | Read current v1.2 route and PRODUCT-01 journey reuse direction. |
| User task card | supplied in this turn | Frozen J1-J3, stop lines, worktree limit, no paid Provider/browser/write/main. |
| docs/evidence/vnext/m2-01/DEFERRED_GATES.md | target file read | S2 handoff/Receipt/Outbox and protected-write boundaries remain outside scope. |
| docs/evidence/vnext/m2-02/DEFERRED_GATES.md | target file read | No S2 handoff, Memory/Summary expansion or TaskControl boundary change. |

## Existing capability matrix (source + test/evidence review)

| Classification | Capability and evidence | Limit |
|---|---|---|
| Already connected | Session message admission and formal Worker/Assistant loop: opspilot/assistant.py::run_assistant, Loop; API routes in opspilot/web/app.py; Assistant MCP registration in opspilot/assistant_mcp.py::run. | This is the offline formal app path; no new live Provider claim. |
| Already connected | Raw user config/log enters current model context as untrusted material: opspilot/assistant.py::SYSTEM; tests/test_ar03_material_01.py::test_formal_assistant_reads_authorized_text_and_keeps_pasted_material_untrusted; existing material report/trace. | User material is an assertion, not current business evidence. |
| Already connected | Scoped protocol discovery, comparison, exact bounded excerpt and source revalidation: assistant_mcp.py protocol tools; domain/scoped_protocol_comparison.py::{list_scoped_protocols,compare_scoped_protocols,read_scoped_protocol_excerpt,scoped_protocol_excerpt_is_current}; domain/assistant_knowledge.py::{search,sources_current}; existing AR-03 tests. | Project documents do not establish the deployed version. |
| Already connected | Optional protocol-upgrade Skill: assistant_mcp.py::load_protocol_upgrade_skill; skill_assets.py::{load_applicable_skill,skill_asset_is_current}; material-live OFF/ON evidence. | Method guidance only; not required to load each turn. |
| Already connected | TaskBinding-scoped current Delivery/Receiver reads: S3 MCP from assistant_mcp.py::run, backed by domain/s3_mcp.py and Domain currentness checks; AR-03 same-Event QUEUED/PROCESSED tests. | Requires trusted binding and a fresh observation; no write tool is part of this route. |
| Already connected | Historical/current source distinction in domain/assistant.py::{history_sources,source_context_for_model} and domain/chat.py Context assembly. | A real AR-04C Provider turn nevertheless falsely described historical data as reread; real-model behavior remains a known quality failure. |
| Connected, but with a known boundary | Tool budget is persisted and reserved in domain/execution_budget.py and domain/task_control.py; task budget schema defaults are 8 model / 6 MCP calls. AR-03-REAL-LLM-02's separate frozen 8/6-per-scenario run completed QUEUED but stopped the PROCESSED case after six MCP calls and before final answer. | Later AR-03-MATERIAL-REMAINDER-LIVE-01 completed its narrower authorized cases with a different isolated campaign budget (8 Provider requests, 12 MCP calls overall; no low count MCP gate). These are different experiments, not authorization to change or reuse either paid budget. This task keeps existing limits and tests whether the composed journey fits. |
| Already available, not yet composed into this frozen outcome | J1 materials + diff + exact source + checklist, J2 same-Session binding/current state, and J3 denied cross-Tenant binding followed by legal document analysis are each represented by existing API/Worker/MCP capabilities or component tests. | No existing frozen case combines the exact required artifacts and deliverable in a single J1-J3 journey; new coverage and persisted fixture evidence are the gap. |
| Explicitly missing / not claimed | Real Provider quality for this exact integrated user goal and held-out wording; browser-visible acceptance. | User task does not authorize either. |

## Historical evidence retained

- docs/evidence/ar-03/real-llm-02/REPORT.md: Scenario A (QUEUED) delivered; Scenario B (PROCESSED) obtained current facts but reached ASSISTANT_RUN_MCP_LIMIT after six calls without a final answer. The paired result is PARTIAL; 5 real Provider requests and 11 MCP calls belong to that past experiment only.
- docs/evidence/ar-03/material-remainder-live-01/campaign-01/REPORT.md and FAILURES.md: narrower MAT-05 and Skill cases were run with a separate one-shot campaign; no MCP count gate in that campaign; do not combine its budget/quality evidence with the prior pair.
- docs/evidence/ar-04c/live-exec-01/REPORT.md: a real J4 response with zero MCP/Observation claimed “本轮已重新读取确认过”; preserved as G7 FAIL, no fix or rerun claimed here.
- docs/evidence/live-02-fix-01-hf-01/VERIFICATION.md and docs/evidence/live-02-fix-01-hf-02/VERIFICATION.md: profile recall work and constraints are prior evidence; no memory behavior is changed here.
- Existing AR-03/MAT Gold, real traces, and failure logs are not modified.

## Six scope questions

1. User change: complete a same-Session protocol/material analysis, then attach trusted current business state and deliver a sourced engineering checklist.
2. Agent decisions: freely choose doc discovery/comparison/excerpt, optional Skill, authorized current reads, clarification, or stop; programs enforce trusted Session, Tenant and TaskBinding scope.
3. Observation pair: same Event Receiver QUEUED means processing is not proven; same Event PROCESSED supports completion for that Event only.
4. New hard limits: none; reuse existing authorization, source currentness, budget, and no-write boundaries, with both allowed/unbound and denied/cross-Tenant paths tested.
5. Simpler option: no production subsystem appears missing from source review; preserve current responsibilities and add only frozen journey coverage/evidence unless a base failure proves a minimal code defect.
6. Evidence/stop line: J1-J3 plus one held-out wording, local API/Worker/MCP Fixture traces, targeted AR-03 and security/source regressions; no real Provider/browser/business write; stop at candidate for independent review.

## Frontend and user-visible projection checked

- `frontend/src/api.ts::MessageItem` carries the server-projected `answer_visibility` and `source_status` labels.
- `frontend/src/App.vue::refreshSession` reloads server-sanitized messages before marking the session history ready; `refreshAssistantSource` fences Session/generation responses and refuses to treat historical answers as current evidence.
- `frontend/src/App.vue` renders the `HISTORICAL_SNAPSHOT` banner and omits the source-inspection disclosure for historical answers.
- `frontend/src/conversation.ts` masks answers pending revalidation and excludes non-current answers from active assistant source projection.
- `frontend/src/AssistantRunActivity.vue` renders persisted context, model, tool, and answer-save activity stages.
- No frontend file is changed. Browser automation and Vue build are not run because this candidate changes only offline journey tests/evidence and the task forbids real-browser acceptance.

## Existing user-demo launch surface checked

- `scripts/user-demo/Start-UserDemo.ps1` and `Stop-UserDemo.ps1` are present; live mode requires a local `.env` plus Runtime preflight, while offline mode disables provider/runtime calls.
- The existing launcher accepts S1/S2 profiles; this task did not verify that it provisions a clean `orders-async-demo` dataset for the exact R2 manual journey. Do not point it at or reset the protected LIVE-02 database as part of this candidate.
