# AR-01 frozen local experiment

Status: FROZEN_BEFORE_IMPLEMENTATION. Authorization: user's AR-01 card, local/free only.

Base `ec8c3582f6d145eec9979c43607302731411ead8`; branch `codex/ar01-free-agent`. The existing isolated worktree is reused; primary checkout and pre-existing untracked artifacts are untouched. This task explicitly overrides the usual direct-main workflow. No main push or merge.

Actual reads at Base: North Star blob `1f737712c7a36ceb34433ac09c3fbba3c3305542`, AGENTS `32c45506cceeaa8c76a5c56bf8360ff476b58856`, review Skill `d405c8d413d633824b279202cc1503dab4cf0b03`. Read S3Nodes, MCP Server, D2 Attempt/Observation, TaskControl, Context estimator, current CONT-UX Gold, Stage B acceptance/closeout reports and M2-01/02 deferred gates. The user's current Stage B HOLD remains; this experiment is not Stage B acceptance. Historical Gold/RED/Trace and all Domain safety contracts remain immutable.

## Question and controlled conditions

Compare A: unchanged S3Nodes strategy A decision/execution/gate/continuation methods; B: installed `langchain.agents.create_agent()` standard loop. A's production report writer is not invoked: this is an investigation-policy experiment, with shared read-only final-answer verification, no formal Diagnosis. No production code changes.

Both use six identical MCP tool names, descriptions and JSON schemas, the same model ID/settings and fresh independent models, Task/Run budgets, trusted binding, knowledge version, and an exact copy of one prepared SQLite business initial state. Independent Tasks/Runs/DBs prevent evidence contamination. A initial prompt stays unchanged; B has a shorter system prompt and native ToolMessages, so Prompt/Context are NOT identical. Neither group has approved Memory initially; A memory selection is disabled explicitly for parity.

Budget: initial Run 8 MODEL / 6 MCP; new S3 Task 24/18 cumulative; no resets. Both model timeout 30 s, tool timeout 12 s, total experiment invocation 60 s, existing Context input profile 12,000 estimated tokens and reserved output 512 (application limits). Native-message serialization is included in B estimation. No retries. Failed/reserved/unknown external attempts remain counted. Lower test limits may be used only for failure tests and must be labeled.

## Frozen local acceptance

- Installed versions and create_agent signature compatible; no dependency update.
- Six tools reach actual existing MCP protocol and Domain/HTTP, with exactly equal model-facing schema/description capability. Tools cannot accept arbitrary task, tenant, URL or credential.
- Frozen cases in CASES.json have no prescribed unique tool order. Deterministic simulation policy lives outside the candidate, observes actual tool results, and is not an intelligence score.
- Same descriptions/different facts change the simulated next action; different wording/same facts keeps allowable conclusions. All six tools exercised across suite, direct-answer and clarification supported.
- Cross-order Event and forged tenant/resource arguments denied; legal bound-order historical Event and ordinary reads continue. Revoke Scope -> no further restricted read/model dispatch. Other Event success does not establish target Event success.
- Model/tool budgets, timeout, provider error, empty answer, Context overflow and repeated calls stop with nonempty partial/error delivery and honest reason. Continuation uses remaining persisted budget, not a new allowance.
- Domain protected business tables and TaskControl are unchanged by either decision-policy run. Only audit/Attempt/Evidence storage is allowed. No official Receipt or business success generated.
- Necessary S1/S2/S3 safety regressions; full pytest status explicit. No browser or paid Provider.

## Six questions and stop line

User change: obtain a runnable isolated standard-loop candidate, not a new workbench feature. Agent decisions: tool choice, continuation, clarification and stopping are model outputs. Different processing vs callback failure observations may justify different next tools. Limits protect Scope/currentness and finite resources; legal queries and direct answers must remain possible. Reuse create_agent and existing Domain/MCP, no new Planner/Runtime. Stop after local implementation, parity evidence, failure records and branch commit. True model gain and broader/open-ended/cross-Run product goals remain unverified. AR-02, production migration and paid calls require new authorization.
