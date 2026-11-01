# Preflight and actual wire comparison

## Checkout and contracts

| Item | Verified value |
|---|---|
| Repo / branch | `wgqa/OpsPilot` / `codex/ar02-live-01` |
| Local base HEAD | `69e7267de03f13651f3e54aaf956a919284be845` |
| Initial local worktree | clean before this evidence directory was created |
| Candidate remote tracking ref | local `origin/codex/ar02-live-01` pointed at the base SHA |
| Live GitHub ref check | `UNVERIFIED`; `git ls-remote` failed to connect to `github.com:443` |
| `PROJECT_NORTH_STAR.md` blob | `1f737712c7a36ceb34433ac09c3fbba3c3305542` |
| `AGENTS.md` blob | `32c45506cceeaa8c76a5c56bf8360ff476b58856` |
| `.agents/skills/opspilot-slice-review/SKILL.md` blob | `d405c8d413d633824b279202cc1503dab4cf0b03` |
| Frozen S01/S02 input blob | `ee9b1623a2296905c425449709a2f9ae6563caca` |
| Frozen six-case JSON blob | `0b8411942ec99724d9aa10d45faa50a58676836b` |

The Skill and both root rules were actually opened from this checkout. `PROJECT_NORTH_STAR.md` §§0, 2–8 and `AGENTS.md` were read. Stage B remains `HOLD`; the browser STOP remains active and was not touched.

The isolated process loaded only the existing model credential/config values in memory from the user-local environment file; no secret value was printed, passed into the MCP child, or written to evidence. The process-only provider opt-in and exact experiment ID were set for this authorized run; no `.env` file was modified. `trust_env=false`, HTTPX retries `0`, SDK `max_retries=0`, timeout `30s`, model `deepseek-flash`, `max_tokens=2048`, and `thinking.type=disabled` were verified on a no-I/O client construction. The new ledger began empty with provider limit 16, MCP limit 12, USD 10.50 cap.

Runtime versions: Python 3.14.0, LangChain 1.4.1, `langchain-core` 1.6.12, `langchain-openai` 1.7.2, LangGraph 1.2.16, `langgraph-checkpoint-sqlite` 3.1.2, HTTPX 0.28.1, FastAPI 0.137.1, MCP 2.3.0.

## Price and app reservation

The official DeepSeek pricing page was checked on 2026-11-01. The conservative peak cache-miss rates used by the frozen budget are USD 0.30/M input and USD 1.20/M output. With the documented 1M context and 384K maximum output, the per-call reserve is:

`616K × $0.30/M + 384K × $1.20/M = $0.645600`

Sixteen full reservations total USD 10.329600, below the USD 10.50 **application ledger** cap. This is not an account-level provider hard cap. [Official pricing](https://api-docs.deepseek.com/quick_start/pricing/) · [Chat Completions parameters](https://api-docs.deepseek.com/api/create-chat-completion/) · [Thinking mode field](https://api-docs.deepseek.com/guides/thinking_mode/).

## Isolated preparation

The live run used `.runtime/ar02-real-journey-01-20261101-attempt-03/domain.sqlite3` and `checkpoints.sqlite3`. `reset_fixture(S1_POS)` and `prepare_s3_fixture(DELIVERED_PENDING, order_id=ar02-order, contract_version=2)` were local preparation only. The target fixture's local receiver returned HTTP 202; that is setup evidence, not an Agent observation. Before user input, the DB had zero Task Runs, assistant Runs, or TaskBindings; the experiment ledger was OPEN with zero dispatches. FastAPI health reported one running Worker.

Prepared target fixture IDs were Event `event-c8373229-a9dc-4db4-a33f-3e765d29ec6f` and transport request `transport-73606233-b67c-4ef1-8f94-6fd71105c3af`. The setup-only response recorded Receiver `QUEUED`; these IDs were never observed by the Agent because S01 has no TaskBinding.

Two earlier local-only runner starts did not send any request. Their failures are preserved exactly. Attempt 03 is the only run that admitted a user message.

## Actual request: frozen-parameter deviations found

The one recorded HTTPX outbound request was a POST to:

`https://api.deepseek.com/v1/chat/completions`

The previous successful CONN-02 contract records `https://api.deepseek.com/chat/completions`. The actual body also offered one Knowledge tool but **omitted** the `tool_choice` field, despite the frozen requirement to send `auto` when tools are offered. `parallel_tool_calls=false`, `max_tokens=2048`, `thinking.type=disabled`, and `stream=false` were present. The request included no authorization header in the saved trace.

No HTTP response hook fired: status code, Completion ID, model fingerprint, Usage, and billed amount are unavailable. The SDK surfaced `OpenAIConnectionError: Connection error.` The underlying DNS/TCP/TLS/proxy phase is unknown. Both the endpoint-path discrepancy and omitted `tool_choice` are protocol/config deviations; the task's stop rule prohibits correcting and retrying after this outbound attempt.
