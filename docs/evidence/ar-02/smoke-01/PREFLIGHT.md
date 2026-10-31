# AR-02-SMOKE-01 Provider and Cost Preflight

**Decision:** `REAL_S01_S02=HOLD_NOT_RUN`; free adapter verification is complete.

## Runtime configuration

This worktree had no `.env`; the process had no model API key, model ID, or base URL, and `OPSPILOT_ASSISTANT_PROVIDER_ENABLED` was not set. Only presence flags were inspected; secret values were not read or recorded. Real S01/S02 therefore could not be run, even apart from the absence of paid-call authorization.

The formal server entry now passes the fail-closed factory to `create_app`. With the opt-in absent, the factory returns `None`; with opt-in present but required configuration absent, it raises before a run can call a Provider. Constructing a configured model object performs no I/O.

## Request protocol

The frozen DeepSeek Flash candidate is `deepseek-flash`. The current official Chat Completions reference names the output cap `max_tokens`, limits it to 384K, and states the 1M context constraint applies to input plus generated output. It also says thinking is enabled by default when both `thinking` and `reasoning_effort` are omitted. [DeepSeek Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)

The pinned `langchain-openai==1.7.2` maps its `ChatOpenAI(max_tokens=...)` field to `max_completion_tokens`. A failing local wire capture proved the mismatch. For model IDs beginning with `deepseek-`, the factory now passes `extra_body={"max_tokens": 2048}`; the OpenAI SDK merges this into the top-level JSON body. The Assistant middleware no longer re-adds `max_tokens`, which would create the incompatible alias. A local `httpx.MockTransport` captured exactly one request with `max_tokens: 2048`, no `max_completion_tokens`, `tool_choice: auto`, `parallel_tool_calls: false`, and the bound tool schema. See `TRACE/provider-wire-mock.json` and `runs/green-provider-preflight-final.log`.

The local capture omitted `thinking` and `reasoning_effort`; consequently the eventual DeepSeek mode is not explicitly frozen by this adapter. Before any paid run, the authorizing plan should explicitly settle the mode. A proposed continuation consistent with the earlier Flash non-thinking experiment is `thinking: {"type":"disabled"}`; it was **not** added or tested against the real Provider in this slice.

The factory sets `timeout=30`, `max_retries=0`, `temperature=0`, and usage capture. The local wire test does not establish that DeepSeek accepts every response/header behavior or returns usage as expected.

## Existing budgets and the missing global envelope

- Assistant reservations persist before dispatch and count unknown outcomes; each Assistant Run allows at most 8 MODEL calls and 6 MCP attempts.
- A Task with `CONTUX_S3_V1` has 24 investigator MODEL / 18 MCP attempts, and an 8-call auxiliary Provider cap. Assistant MODEL calls for a bound Task consume that auxiliary cap. Unbound Assistant Runs have no shared Task auxiliary counter.
- The frozen S02 has two requests before the user confirms an order binding. For one S01 Run plus five S02 message Runs, assuming binding occurs before S02 step 3, current ceilings can permit up to 32 MODEL calls and 36 MCP attempts: S01 8/6; the two unbound S02 Runs 16/12; and the bound S02 Runs up to 8 auxiliary MODEL / 18 Task MCP. Actual actions may consume fewer calls. There is no durable experiment-wide 16-call / 12-MCP ledger and no USD reservation/settlement ledger. The frozen suggested 16/12 limits are therefore not enforceable by the current product path.
- The 12,000-token context estimate is not a strict maximum and is not used as a hard cost bound.

## Current official cost calculation

As checked on 2026-10-31, DeepSeek lists Flash peak cache-miss input at USD 0.30 / 1M tokens, output at USD 1.20 / 1M, a 1M context, and a 384K maximum output. Prices can change. [DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)

If the documented 2048-token output cap is honored, a context-sized worst-case request is:

`(997,952 × 0.30 + 2,048 × 1.20) / 1,000,000 = USD 0.3018432`.

If the output cap is ignored but the documented context and 384K output limits hold, the most expensive distribution is 616K input + 384K output:

`(616,000 × 0.30 + 384,000 × 1.20) / 1,000,000 = USD 0.6456`.

These are model-token calculations at the listed peak price, not guarantees against provider price changes, provider limit violations, or account-side billing behavior. Existing limits do not enforce a global USD cap. No paid request was authorized in this task.

## One concrete proposal for a later, separately authorized run

Before any real S01/S02 request, add only an experiment-scoped durable reservation ledger with a global cap of **16 Provider dispatches, 12 MCP attempts, and USD 10.50**. Reserve USD 0.6456 before each Provider send using current peak rates and documented context/output bounds; retain the whole reservation for failures and unknown outcomes; do not retry; settle against returned usage; reject before send if the remaining cap is insufficient. Recheck current prices immediately before authorization. If a provider-account hard spend limit is available, set it to the same USD 10.50. The request must also explicitly set the approved thinking mode. This proposal is not implemented and does not authorize spending. If no enforceable account ceiling or durable reservation can be established, keep the paid smoke blocked.
