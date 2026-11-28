# AR-04 compaction algorithm audit

**Status:** `ACCEPTANCE_CANDIDATE` evidence draft  
**Source checkout:** `codex/r2-ar04-compaction-audit-01` at `d8e30bcb82557e370f8fec664803a952b8d06e14`  
**Mode:** offline synthetic Domain + SQLite checkpoint + deterministic fixture model. No paid Provider, production write, or frozen Gold change.

## Source baseline actually read

At the base commit, the audit re-read and recorded these Git blobs:

| File | Blob at base |
|---|---|
| `PROJECT_NORTH_STAR.md` | `43dabda468506717c6956e676dfad4304c4f38e6` |
| `AGENTS.md` | `807b928686a4dd2cac7b15b3c354b9943c93c910` |
| `.agents/skills/opspilot-slice-review/SKILL.md` | `d405c8d413d633824b279202cc1503dab4cf0b03` |

The audit read `opspilot/domain/chat.py`, `opspilot/domain/context_engineering.py`, `opspilot/assistant.py` and the AR-04A journey, budget, and cancellation/recovery test sources from the same commit. This slice measures whether the existing behavior can be reproduced and what it retains; it makes no claim of increased Agent autonomy or real-model memory quality.

## Call graph

```text
POST /api/sessions/{session_id}/assistant/messages
  -> web.app.post_assistant_message
  -> task_control.admit_task_message (durable CHAT_READONLY Run/source row)
  -> web.worker._dispatch_run
  -> assistant.run_assistant / _run_assistant
       -> MCP stdio Client.list_tools
       -> reserve input space for tools, system policy, WORK_CONTEXT, tool results
       -> Loop.context preflight -> chat._prepare_context
            -> evaluate trigger and build a candidate summary batch
            -> C06 can raise ContextBudgetExceeded here before an attempt is persisted
       -> _prepare_assistant_context [before first answer attempt]
            -> chat.prepare_chat_compression_attempt [loop]
                 -> chat._prepare_context
                      -> validate source Run, Task scope and current dependencies
                      -> load all source-valid history after current summary cursor
                      -> choose strategy/window and compute token estimates
                      -> if required, choose oldest contiguous eligible history batch
                 -> persist RESERVED context_compression_attempt
                 -> assert_chat_compression_sources_current
                 -> invoke model with CONTEXT_COMPRESSION prompt (512 output cap)
                 -> complete_chat_compression_attempt
                      -> validate exact JSON schema/source sequence citations
                      -> compact to bounded summary; persist version and dependencies
            -> repeat until no compression is due (or fail/attempt budget)
       -> Loop.context / create_agent with SQLite checkpointer
       -> Loop middleware rebuilds current context and source manifest before dispatch
       -> fit tool-result projections if needed; persist actual model request wire
```

The summary lives in Domain SQLite as a derivative `context_summaries` row plus `context_summary_dependencies`; it is not stored as the only copy of the conversation. Original user messages, assistant answers, MCP calls/results, and the graph checkpoint remain separate records. A later source-currentness check can invalidate a summary; invalid summaries are not injected. The session history is re-read when no usable current summary exists, including when a prior summary was invalidated.

## Budget and trigger equations

Let the model profile have context window `W`, configured input limit `L`, output reserve `O`, and safety margin `M`:

```text
profile_input_budget B = min(L, max(0, W - O - M))
reserved_tokens R     = max(0, tool_schema + system + WORK_CONTEXT + tool_result_reserve)
effective_budget E    = max(0, B - R)
full_estimate F       = estimate(full candidate context before priority allocation)
eligible_old H        = source-valid history prefix before the latest 12 history rows,
                        excluding rows already covered by the current summary

HYBRID trigger          = (F > E) AND (H is non-empty)
ROLLING_SUMMARY trigger = (H is non-empty)
RECENT_WINDOW trigger   = false
```

The default and `deepseek-flash` profile are `W=16,384`, `L=12,000`, `O=512`, `M=1,024`; thus `B=min(12,000,14,848)=12,000`. Environment overrides are `OPSPILOT_CONTEXT_WINDOW_TOKENS`, `OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS`, `OPSPILOT_CONTEXT_OUTPUT_RESERVE_TOKENS`, and `OPSPILOT_CONTEXT_SAFETY_MARGIN_TOKENS`. Strategy is `OPSPILOT_CONTEXT_STRATEGY` (`HYBRID` by default).

`R` on the assistant path is estimated from the canonical serialized MCP tool schemas, fixed assistant system prompt, current `WORK_CONTEXT` payload, and a 1,024-token tool-result reserve whenever tool schemas exist. Those tokens are reserved before context selection; the final model-wire budget check also estimates the actual serialized messages and tool schemas against the profile input budget.

Text token estimation is `tiktoken` `cl100k_base`, pinned in code as `tiktoken:cl100k_base:0.14.0`. A message-list estimate starts with 2 tokens and adds 4 per message plus tokenized role and content (non-string content uses stable JSON). Provider usage, when present, is separately recorded; it is not substituted for this local estimate.

## Selection and batching

1. Candidate history is rebuilt from the current session and trusted Run scope. User rows must be `CHAT_READONLY`; assistant rows must have a current saved answer and valid source dependencies. Task intent anchors are retained verbatim when a Task is bound.
2. `RECENT_WINDOW` truncates the visible history candidate to its newest 12 rows before optional block selection. Anchors and the current message are then added back. There is no summary prompt, summary call, or summary record for this strategy.
3. When compression is due, the eligible prefix is walked oldest first. The compressor source is a contiguous prefix; the next row is not skipped when it does not fit.
4. Compression input cap is `min(6,000, E)` tokens. A user row that cannot fit as the first source fails with `SUMMARY_SOURCE_EXCEEDS_COMPRESSION_BUDGET`. An oversized historical assistant answer can be request-only excerpted using roughly two thirds from the head, one third from the tail, with an explicit omitted-text marker. The stored original assistant message is not edited. If a later row will not fit after a prefix was selected, the current batch ends and the next pass may cover that row.
5. A compressor call can return up to 512 output tokens. Summary JSON is validated against exact keys and source sequence membership, then compacted under a 512-token cap. A compression plus answer share the three-attempt run limit, so a run can settle at most two compression calls and one answer call.
6. With no further compression due, required blocks (trusted control, trusted task state, current authorized facts, current user input, and task-input anchors) are allocated first. Optional blocks are sorted by descending priority then `block_id`, and greedily included if they fit. Anything else is explicitly marked `INPUT_TOKEN_BUDGET`; required overflow fails closed.

## Summary contract

The persisted JSON has exactly these keys:

```json
{
  "initial_goal": {"text": "...", "source_message_ids": ["..."]},
  "constraints": [],
  "user_assertions": [],
  "corrections": [],
  "rejected_hypotheses": [],
  "unresolved_items": [],
  "timeline": []
}
```

On the compressor wire, message IDs are projected to `source_sequences`; on commit they are mapped back to source message IDs. Every array item must have non-empty source sequence citations present in the current prompt. Initial goal and entries are normalized and compacted; category entries are capped at three retained short items per category and the whole summary at 512 cl100k tokens. A prompt projection can include the current parent summary and its source-linked sequence map.

Summary currentness checks scope (tenant/session/task), row state, digest, every declared dependency and version, source user-message digest, assistant-answer source validity, successful model attempt, Task state, current evidence, memory, Knowledge/Skill versions, and recursive parent-summary currentness. Invalid/superseded summaries remain auditable but are excluded from prompt injection. Summary creation does not delete or overwrite raw history.

## Strategy distinction

| Strategy | What it does | Creates a summary? | Main tradeoff |
|---|---|---:|---|
| `HYBRID` | Keeps the latest 12 history rows as the protected recent region; compresses eligible older rows only when the full candidate estimate exceeds the effective budget. | Yes, on trigger | Saves summary calls for short sessions, but old material may remain uncompressed until a budget crossing. |
| `ROLLING_SUMMARY` | Compresses eligible old history as soon as it falls outside the latest 12 rows, even when the full prompt still fits. Later batches include a parent-summary projection. | Yes, proactively | Keeps old history bounded earlier, at the cost of extra compressor model calls and lossy summary dependence. |
| `RECENT_WINDOW` | Sends only the recent window (plus anchors/current and required trusted context); older rows are omitted from the selected context. | No | Lowest compression cost, but no semantic summary carries older details forward. The raw Domain history remains available for another strategy/re-read. |

`ROLLING_SUMMARY` is not merely a larger fixed window and `RECENT_WINDOW` is not a summary algorithm. Both exclude older material from the answer prompt, but only the first asks a model to produce a structured, source-cited summary.

## Failure and cancellation semantics

AR-04A tests use a fixture model or `httpx.MockTransport`, not a paid request. They verify compression is counted as a model attempt, output cap and usage ledger behavior, stale-source invalidation, provider/spend limit refusal, timeout outcome `UNKNOWN` with no resend, replay reuse, pre-dispatch cancellation cleanup, and cancellation after dispatch preserving `UNKNOWN`. The two-batch cancellation case keeps a settled first attempt while leaving the in-flight second call unknown. No generated fixture summary constitutes evidence that a real model would preserve the same facts.

## Known uncertainty

`tiktoken` estimates are local selection estimates, not a promise of provider token accounting. Context manifests and persisted model `request_json` establish what the application selected and dispatched. Fixture runs establish boundary mechanics only. Natural-language fidelity, whether citations correctly support each paraphrase, and early-fact recall by a real model remain `NEEDS_LIVE_SEMANTIC_EVAL` and are outside this offline authorization.

## RED: oversized first user source is fail-closed but loses its error detail

`C06_USER_OVERSIZE` has 14 turns, so eligible old history exists. With `ROLLING_SUMMARY`, the trigger is true. The captured candidate estimate is 7,572 tokens; source envelope plus compressor prompt require 6,176 tokens against the 6,000-token compression cap. In `_run_assistant`, the initial `Loop.context()` preflight calls `_prepare_context`; the latter decides compression is required and raises while constructing the first batch, before `_prepare_assistant_context` persists an attempt. No model call occurs. The run ends as public `WORKER_RUN_FAILED`, while the captured internal error is `ContextBudgetExceeded: SUMMARY_SOURCE_EXCEEDS_COMPRESSION_BUDGET (6176 > 6000 tokens)`.

**Minimal repair candidate for separate review:** catch/map this typed budget exception at the initial assistant preflight boundary in `opspilot/assistant.py` and persist a stable user-visible failure code. Keep the run fail-closed and make zero model calls; do not excerpt or silently drop the oversized user source. **Risk:** a broad catch could hide unrelated programming errors or accidentally continue with a partial context. Limit handling to this exception type and preserve the exact no-provider-call property. This audit does not implement the repair.

The trace evidence records `trigger=true` as a source-order-derived value: the exception is raised inside the first-batch builder after the source computes `compression_required`. The preparation wrapper did not return a manifest, so `B`, `E`, `R`, and final `estimated_after` remain unobserved for this case.

## Candidate self-review

> **用户变化：** No production capability change; the learning outcome is a reproducible account of compression triggers, context selection, and measurable information loss.
> **Agent 决策：** No Agent decision behavior was changed or claimed.
> **观察驱动：** C03's one-token boundary, C04's eligible history under a high budget, C05's no-summary window, and C08's expanded schema produce different legitimate preparation choices.
> **新增约束：** None; only isolated offline fixtures were run. Existing source invalidation and over-budget fail-closed regression cases passed.
> **简化结果：** No production conditions were deleted or changed. The audit distinguishes existing summary and window paths without introducing a new context service.
> **证据与停止线：** Fixed-base sources, saved traces, actual fixture inputs, and 14 AR-04A Fixture/Mock tests are recorded. Semantic quality remains `NEEDS_LIVE_SEMANTIC_EVAL`; no paid Provider or live MCP was used. Stop after independent candidate review; no merge or follow-on scope is requested.

**Submission status:** `ACCEPTANCE_CANDIDATE` with C06 `RED`; the main Agent must make the acceptance decision.
