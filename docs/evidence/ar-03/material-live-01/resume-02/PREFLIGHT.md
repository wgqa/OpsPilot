# RESUME-02 preflight

## Contract checks

- Project baseline and frozen case blob match the task card.
- The new experiment ID has its own supported schema identity, awaiting-authorization set, and fixed 16/10 campaign limits.
- Provider construction requires the exact RESUME-02 authorization record, private claim, experiment ID and matching one-shot token digest. An API key and allowlist entry alone are insufficient.
- The one-shot token is removed from the MCP subprocess environment.
- Runner audit distinguishes a persisted model answer from `PROGRAM_LIMIT`, unresolved Provider result, unverified non-model text, and no answer/no execution. A model answer requires a successful Run, exact Run/source-message association, completion ID, matching call/dispatch Usage, and the persisted model content.
- MockTransport checks the actual SDK request before its handler returns a response. The formal Worker persists the campaign reservation before the handler observes the request.
- Existing Recovery 02 failure path still retains the UNKNOWN dispatch and USD 0.645600 reservation.

## Official Provider facts checked 2026-11-04

DeepSeek's current pricing page lists `deepseek-flash` as model version `DeepSeek-V4.1-Flash-1017`, with 1M context, maximum 384K output, peak cache-miss input at USD 0.30/M tokens, and peak output at USD 1.20/M tokens. The frozen reserve remains USD 0.645600 per request, based on the existing conservative 616K input + 384K output envelope. Sixteen reserves total USD 10.329600, below the USD 10.50 campaign cap. This is an application-side ceiling under the frozen reservation model, not a guarantee about provider billing if the provider violates the documented output limit.

The Chat Completions API docs describe `/chat/completions`, the `max_tokens` parameter, and `tool_choice=auto`. The implementation continues to use the accepted OpenAI-compatible base URL and exact offline-verified serialized request.

Sources: [DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/), [DeepSeek Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/).

## Actual local preflight outcome

The first `--preflight-only` attempt was made while the authorized code changes were still uncommitted. It correctly returned `BLOCKED_BEFORE_PROVIDER_SEND / WORKTREE_OR_INDEX_NOT_CLEAN`. It did not create a one-shot claim or send a request.

The configured shared environment file at the worktree's parent workspace is present. Safe presence-only checks confirmed the API key is configured, the model is `deepseek-flash`, and the endpoint host is `api.deepseek.com`; credential contents were not read into output. Provider opt-in, experiment ID, and RESUME-02 token were not preset. A final clean-worktree preflight remains necessary after the implementation commit; only a READY result can authorize claim creation under the approved task card.
