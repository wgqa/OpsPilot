# AR-03-REAL-LLM-01 — Offline preflight

**Status:** `READY_FOR_LIVE_AUTHORIZATION` (preparation candidate only; no live request is authorized)

## Checkout and governing records

- Repository: `wgqa/OpsPilot`
- Branch: `codex/ar03-real-llm-01`
- Requested base: `11e86b4606074495ab448630b3017f14a3e0f6dd`
- Freeze commit: `6f9074e84c185553cfeab0f225e81640b8b525f0`
- Implementation commit: `1f557ecd124a6ae9ac1ff9ccdba1dad0b4cc9284`
- `PROJECT_NORTH_STAR.md` Blob: `1f737712c7a36ceb34433ac09c3fbba3c3305542` (read)
- `AGENTS.md` Blob: `32c45506cceeaa8c76a5c56bf8360ff476b58856` (read)
- `.agents/skills/opspilot-slice-review/SKILL.md` Blob: `d405c8d413d633824b279202cc1503dab4cf0b03` (read and applied at start/closeout)
- Read-only remote query failed to connect to GitHub port 443. Remote `main` and candidate branch are `UNVERIFIED`; no remote SHA is inferred.
- Historical `docs/evidence/ar-02/real-journey-03/REPORT.md` remains `PARTIAL`; it was not changed.

## Provider and API/Worker path

The test invokes the formal path: FastAPI → Worker → `ASSISTANT_V1` → `ChatOpenAI` → HTTPX. The model factory receives explicit `httpx.MockTransport` instances for both clients. The captured URL is `https://api.deepseek.com/v1/chat/completions`; no real transport is constructed in this test and the API key is a dummy placeholder.

Captured serialized body fields:

- model: `deepseek-flash`
- `thinking.type`: `disabled`
- `max_tokens`: `2048`; `max_completion_tokens` absent
- `tool_choice`: `auto`
- `parallel_tool_calls`: `false`
- `stream`: `false`
- offered tools without TaskBinding: `list_scoped_protocol_documents`, `compare_scoped_protocols`, `search_project_knowledge`
- order/delivery/receiver tools are absent without a trusted binding
- the persisted model-call context estimate is within 12,000 tokens

The mock returned one local synthetic Completion and synthetic Usage of 71 input + 28 output tokens. The temporary test ledger recorded one mock dispatch, settled 55 micro-USD under the existing test accounting, remained `OPEN`, and did not initialize the historical experiment ID. These values are test data, not Provider Usage, a real charge, or a price guarantee.

## Paired business fixture evidence

Two fresh Domain databases, Checkpoint databases, Sessions and Tasks used the same order and fixed target Event ID `event-00000000-0000-4000-8000-000000000001`. The task binding was accepted through the existing trusted Assistant order API. The only intended business-state difference was the target Receiver status.

The test Worker called the existing MCP tools for protocol discovery/comparison and current order, delivery and receiver facts. Trace shows, for the same target Event in each case:

- Delivery: HTTP `202`, `ACKNOWLEDGED`.
- Case QUEUED: current Receiver Observation `QUEUED`; the answer says processing completion is not confirmed.
- Case PROCESSED: current Receiver Observation `PROCESSED`; the answer confirms only this Event was processed.

The fixture preparation is explicitly setup, not Agent evidence. A local loopback receiver accepted the fixture POST; the PROCESSED variant was then set in the isolated test database before the Worker investigation. The Agent's observations came from its actual local MCP calls, not from the fixture helper's returned object.

Both answers identify that protocol documents do not prove online deployment and that the support note is an unsubmitted draft. No diagnosis, plan approval, action permission, action intent/ledger, handoff or receipt is created. These are deterministic fixture-model checks, not evidence of real model autonomy.

## Budget and execution boundary

The proposed cap is recorded in `BUDGET.md`: 16 Provider requests, 12 MCP calls, USD 10.50 application ledger, USD 0.645600 per-request reserve, zero retries, 30-second timeout, one in-flight Provider request, and 12,000-token input limit. No limit was increased in code. The current dated price version was **not** revalidated against current official pricing in this offline task; that remains a required paid-execution gate.

Provider real requests: **0**. Browser actions: **0**. External business writes: **0**. No old experiment ledger was opened or modified. Local fixture writes and trusted binding occurred only in temporary test databases.

The provider switch remains off by default; having an API key alone still returns no model. The new experiment ID is only an allowlisted ledger identity and is not a live-call authorization. Paid execution, official price recheck, and any final DeepSeek preflight require separate Main Agent and user approval.

## Remote delivery

`git ls-remote` could not reach GitHub from this environment. Local commits are available on the isolated branch, but push/delivery to the remote is not verified. This does not affect offline test results and must be resolved before remote independent review.
