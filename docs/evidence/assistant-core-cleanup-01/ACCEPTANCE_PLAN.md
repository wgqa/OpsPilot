# Assistant Core Architecture Cleanup 01

**Status:** implementation complete; `ACCEPTANCE_CANDIDATE` for independent review. This is not a final acceptance result.

## Baseline and authority

- Repository: `wgqa/OpsPilot`
- Branch / starting HEAD: `codex/ops-assistant-core-cleanup-01` / `56cb1a8034753970ad07d56bdfbde2058d4a5512`
- `origin/main`: `60eee87bfe3cca522011316cb4cd2c0064ad291b`; the candidate is 58 commits ahead and 0 commits behind. The candidate worktree was clean before this plan.
- `PROJECT_NORTH_STAR.md` read at start SHA; Blob `43dabda468506717c6956e676dfad4304c4f38e6`.
- `AGENTS.md` read at start SHA; Blob `807b928686a4dd2cac7b15b3c354b9943c93c910`.
- Project Skill `.agents/skills/opspilot-slice-review/SKILL.md` read at start SHA; Blob `d405c8d413d633824b279202cc1503dab4cf0b03`.
- User task card in this conversation is the active slice authorization. `TASKS.md` Blob `1f08ee3a8e538d7ece4d2b2841c7c53e25737b7c` is roadmap context, not a substitute for the card.
- Frozen contracts: `docs/baseline/v1.0-implementation-baseline.md` Blob `30e18d7ddbade7cdf7712d035d6fd8488bcb9676`; `docs/baseline/STATE_TRANSITIONS.md` Blob `cb34e6402cf3ce795260414b9b652f31b49f4de1`; `docs/baseline/ACCESS_MATRIX.md` Blob `9d62359c3a97a2fe78678b178889288e551b3d7c`; `docs/evidence/vnext/m2-02/DEFERRED_GATES.md` Blob `2536030b5b942bf9e3765e0916607549fa919934`.
- Prior runtime/provider decisions read as context: `docs/evidence/vnext/product-01-runtime-grant-01/REPORT.md` Blob `dcd228603d9f1e603346021feb1c760e500f2ce7`; HF-01 report Blob `794b88cc071467d068f200607eb6e21ec44e819d`.
- Open-source Agent reference read: `docs/learning/OPEN_SOURCE_AGENT_REFERENCES.md` Blob `5c422316164e20a922ad0596233070716225be07`; its Ragent/Pi source review is static guidance only.
- No literal `LIVE-013` identifier was present in the target tree. The final Provider SEND check was inspected directly; the concrete discrepancy is documented below.

## Slice and stop line

The default Web chat will use the existing `ASSISTANT_V1` entry for ordinary conversation, Knowledge, authorized read-only MCP investigation and follow-up. The existing LangChain `create_agent` loop, Worker fence, Runtime Grant, Domain task control, provider-send ledger and legacy Investigator business assets remain in place. Formal legacy business investigation remains an explicit, separate user action; this slice does not turn chat text into a write permission.

The model chooses among exposed legal tools and may answer, continue or stop based on observations. Domain remains authoritative for Session/Task binding, TaskControl, current source checks, approvals, ActionIntent/Ledger/receipts, budget reservations, and unknown Provider results.

The confirmed code changes are bounded to (1) remove the legacy crash environment switch from product runtime while retaining crash recovery through the test worker's trace callback, (2) make the main chat composer use Assistant without a legacy mode toggle, and (3) align Runtime Grant's final send check with the existing TaskControl rule for a persisted current `CHAT_READONLY` follow-up after a pending correction. No fourth authorization layer, schema migration, new model loop, real Provider call, or external business write is in scope.

## Current route after implementation (source trace)

```text
Web composer (single normal-chat entry)
  -> POST /api/sessions/{id}/assistant/messages
  -> domain.chat.admit_task_message(..., assistant_core=True)
  -> task_runs + assistant_runs marker in Domain SQLite
  -> single Worker claims Run and Worker Fence
  -> _dispatch_run selects ASSISTANT_V1
  -> optional persisted Runtime Grant bind + model factory (no key-only authority)
  -> run_assistant / Loop prepares Context + source validity
  -> LangChain create_agent (LangGraph checkpoint)
  -> model call recorded in Domain; Runtime Grant SEND permit at HTTPX edge if enabled
  -> exposed read-only MCP calls pass assistant adapter, Domain TaskBinding and MCP server checks
  -> persisted Observation is returned to the same agent loop; model may choose another tool or answer
  -> Domain revalidates sources and persists answer to the exact source message

The normal composer no longer toggles to /messages or calls the legacy
investigation-update classifier. `/messages`, Legacy Investigator and its business
assets remain available to compatibility and explicit controlled-investigation
routes; formal correction/approval/action still use their trusted Domain flow.
```

Final evidence and the before/after diagram are in [REPORT.md](REPORT.md). Raw test
logs and the Assistant trace are retained under `runs/` and `traces/`.

## Six checks

1. **User change:** ordinary Session questions and eligible read-only follow-ups enter the persisted Assistant path without requiring Legacy Investigator classification. Task/Plan/action state does not change for chat.
2. **Agent decisions:** the existing model chooses legal tools, follow-up queries, clarification or stopping; this slice does not claim an autonomy improvement beyond the newly reachable default path.
3. **Observation:** distinct fixture MCP observations must be returned to the model loop; a legal same-Task read after a pending correction may continue, while a stale/aborted/boundary-crossing request is stopped.
4. **Constraints:** preserve current TaskControl, grant, source, spend, and unknown-send guards. Verify both legal readonly acceptance and unauthorized/stale rejection; no business write authority is added.
5. **Simplification:** remove only the UI route switch that exposes Legacy as normal chat and the production read of the historical crash variable. Preserve the independent legacy API/Worker/Investigator and frozen business logic. Reuse the existing final TaskControl predicate instead of adding a new guard layer.
6. **Evidence/stop:** run FixtureModel + local MCP/SQLite session and recovery tests, focused TaskControl/Runtime Grant/D3 regressions, and frontend unit/build checks. Do not call real Providers or production systems. Leave known context-overflow, refusal-reroute and RESERVED-recovery gaps open unless their existing focused regression proves otherwise.

## Evidence scope

Implementation will save exact commands and stdout/exit codes under `runs/`, along with a deterministic trace from the Assistant flow. PASS is limited to the named offline routes and tests. Browser-wide acceptance, real Provider behavior/cost, production IAM, and external side effects remain `NOT_RUN`.
