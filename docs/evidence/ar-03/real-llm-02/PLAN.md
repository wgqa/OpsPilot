# OpsPilot AR-03-REAL-LLM-02 — Frozen Live Execution Plan

**State before any new Provider request:** `PREPARING`
**Experiment:** `AR-03-REAL-LLM-02`
**Branch:** `codex/ar03-real-llm-02`
**Authorized base:** `codex/ar03-live-hf-01@69ffa0d73e6e869c590bc46f36bceda4db62e273`
**Remote main observed at start:** `ec8c3582f6d145eec9979c43607302731411ead8`

This is one newly authorized paired execution. It is not a retry of AR-03-REAL-LLM-01 and must not reuse its databases, Checkpoints, one-shot claim, budget ledger, or Provider authorization rows.

## Frozen user journey

The exact prompt is loaded from `docs/evidence/ar-03-real-llm-01-prep/CASES.json` (Blob `c29b5cf7630fa838a365634d0df5f9f0f2bfa834`); the frozen Gold is `GOLD.md` (Blob `88d5e6f40f027ce2622b957d8ab32b8d2b827381`). Neither file is changed. Both isolated scenarios use the identical user prompt and trusted `tenant-a / support-a` binding to `ar03-order`, the same target Event, Delivery `HTTP 202 / ACKNOWLEDGED`, and the authorized old/new protocol documents.

- **A — QUEUED:** current Receiver state for the same target Event is `QUEUED`. The answer must distinguish transport acceptance from processing completion and preserve unknowns.
- **B — PROCESSED:** current Receiver state for that same Event is `PROCESSED`. The answer may confirm this Event only; it cannot establish live protocol deployment or other Event outcomes.

Each scenario uses a fresh Session, Task, Domain SQLite file, Checkpoint file, and persisted experiment budget. One trusted `POST /api/sessions/{session_id}/assistant/order` carries the full frozen prompt as `initial_message` and creates the investigation Run. No second `/assistant/messages` business request is sent. The model chooses its own legal tool sequence.

## Frozen live envelope

| Limit | Aggregate cap | Per-scenario persistent cap |
|---|---:|---:|
| DeepSeek Provider requests | 16 | 8 |
| MCP `tools/call` attempts | 12 | 6 |
| Application reservation budget | USD 10.50 | USD 10.50 ledger row, with 8-request allocation |
| Reservation per Provider attempt | USD 0.645600 | USD 0.645600 |
| Maximum combined reservations | USD 10.329600 | USD 5.164800 |
| Retries | 0 | 0 |
| Provider concurrency | 1 | 1 |
| Timeout | 30 seconds | 30 seconds |
| Context input cap | 12,000 tokens | 12,000 tokens |
| Output | `max_tokens=2048` | `max_tokens=2048` |

Provider settings: `deepseek-flash`, non-thinking (`thinking.type=disabled`), `tool_choice=auto` when tools are present, `parallel_tool_calls=false`, `stream=false`. The existing peak reservation remains unchanged. The paired allocation gives `16 × 0.645600 = USD 10.329600`, below the USD 10.50 cap by USD 0.170400.

## Stop and evidence rules

An unknown Provider result, timeout, missing/invalid Usage, reservation or aggregate-count mismatch, unauthorized access, cross-Task/Event evidence, or any protected business write stops the entire paired experiment. A content-only partial result may proceed to the next frozen scenario only if Usage is valid, the ledger remains open, and no safety or protocol stop condition occurred. No quality rerun is permitted.

Fixture setup is recorded as setup, never as Agent Observation. The only executable business tools are the existing authorized read-only Assistant/MCP capabilities. No Approval, REPAIR, DELIVER, handoff, ticket submission, browser action, or main merge is authorized.

## Current official provider check (2026-11-02)

DeepSeek's official pricing page lists `deepseek-flash` as DeepSeek-V4.1-Flash-1017 and lists peak cache-miss input at USD 0.30 / 1M tokens and output at USD 1.20 / 1M tokens. At the frozen 12,000 input / 2,048 output caps, the visible request-envelope calculation is USD 0.0060576; the much larger approved USD 0.645600 reservation is retained unchanged. The maximum model context/output envelope underlying that reservation is also sufficient at current published peak rates.

Official Chat Completions documentation supports the `deepseek-flash` alias, non-thinking via `thinking.type=disabled`, `max_tokens`, function tools and `tool_choice=auto`. The current Chat Completions schema page does not document `parallel_tool_calls`; it remains in this frozen outbound contract and will be captured exactly, but this report will not claim the provider honors its semantics unless observed. Prior AR-03-REAL-LLM-01 traffic used the same endpoint and parameter and received HTTP 200 responses; that is historical compatibility evidence, not a guarantee.

Official references:

- https://api-docs.deepseek.com/quick_start/pricing/
- https://api-docs.deepseek.com/api/create-chat-completion/
- https://api-docs.deepseek.com/guides/thinking_mode/

No Provider request has been made for this experiment as this plan is frozen.
