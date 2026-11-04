# R1-INTEGRATION-WEB-JOURNEY-01 — Acceptance Plan

**Delivery status:** `ACCEPTANCE_CANDIDATE`
**R1-ENGINE:** `PARTIAL`
**R1-INTERACTIVE:** `HOLD / NOT_RUN / BLOCKED_BY_TOOL_ENVIRONMENT`

## Baseline and authority

- Repository: `wgqa/OpsPilot`
- Base branch / SHA: `codex/ar03-material-remainder-01-live` / `bb8dcb7518bc908f5ad1a731a8c0afaa8f621202`
- Candidate branch: `codex/r1-integration-web-journey-01`
- `main` at start: `ec8c3582f6d145eec9979c43607302731411ead8`
- North Star blob: `1f737712c7a36ceb34433ac09c3fbba3c3305542`
- AGENTS blob: `32c45506cceeaa8c76a5c56bf8360ff476b58856`
- Skill blob: `d405c8d413d633824b279202cc1503dab4cf0b03`
- At start, the candidate branch did not exist remotely. Source branch and `main` matched the task card's observed SHAs. The worktree was clean before the new branch and task evidence were created.
- The project Skill was actually read from this checkout. `PROJECT_NORTH_STAR.md` §8 remains the authority; the Skill organizes the check and review.
- The attached task card is the frozen R1 contract. No CASES, Gold, prior provider run, private trace, historical failure, receipt, or `main` content was modified.

## Product scope

Verify the existing single product path can carry one same-Session journey through:

1. Unbound protocol consultation (J1).
2. A user-supplied JSON configuration follow-up (J2).
3. Trusted `ar03-order` binding followed by current same-Event Delivery/Receiver reads (J3).
4. A same-Task follow-up and stable persisted message rereads (J4).

The new check uses the formal FastAPI API, Worker, `ASSISTANT_V1`, local MCP server and Domain. A deterministic FixtureModel chooses calls and answers. Its tool order is test setup, not a product constraint and not evidence of real model autonomy. It does not operate a browser and it does not send a Provider request.

## Frozen safety and evidence boundaries

- No real DeepSeek/other Provider request; no external business write, approval, repair, delivery, handoff, or ticket submission.
- Test fixtures establish the demo tenant/order and the current `ar03-order` facts. Fixture setup is not Agent action or production evidence.
- No chat text creates a TaskBinding. Only the trusted order API establishes the binding.
- Current business facts must be read through the current Task's MCP/Domain path and match the same Event.
- No model/tool ordering is required by the Gold.
- The existing Computer Use stop remains active. Do not use CUA, Playwright, or another browser automation path. The browser portion is blocked, not replaced by a non-browser claim.

## Verification matrix

| Area | Evidence required | Result boundary |
|---|---|---|
| J1 | Authorized protocol discovery and version comparison without TaskBinding; deployment stays unverified | Deterministic API/Worker/MCP fixture only |
| J2 | Current config JSON is in actual outbound model context and user answer; user material is not a trusted deployment fact | Deterministic fixture only |
| J3 | Trusted API binds `ar03-order`; Delivery 202/ACKNOWLEDGED and Receiver QUEUED are same Event, same Task, with persisted Observation/Evidence IDs | Deterministic fixture through real local MCP/Domain path |
| J4 | New same-Task Run obtains current same-Event observations; repeated `/messages` reads preserve IDs and body | API persistence check, not browser refresh/SSE |
| Cross-cutting | Protected business-write table counts stay zero; Provider HTTP count is zero | Isolated demo database |
| UI | Real DOM, screenshots, browser sending, SSE/reconnect, source expansion | `NOT_RUN / BLOCKED_BY_TOOL_ENVIRONMENT` |
| Real Agent | Real DeepSeek choice and user-visible R1 answer | `NOT_RUN`; no paid authorization in this task |

## Test commands

Use the existing project virtualenv at `D:\学习\agent新项目\.venv\Scripts\python.exe`; the system Python at `D:\python\python.exe` lacks `langchain_core`. Every successful pytest run used a new `--basetemp` on D:. Raw logs and exit codes are in `runs/`.

The final engine regression covers AR-02 journey/context continuity, HF01/HF02, AR-02/AR-03 integration, AR-03 material remainder/protocol comparison, and the new R1 API/Worker test. The full repository pytest suite was not run.
