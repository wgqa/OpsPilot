# Preflight (before the real journey)

Status at 2026-11-01: **offline checks passed; real Provider journey not yet sent**.

## Checkout and frozen inputs

- Local branch: `codex/ar02-real-journey-02`
- Starting Base: `cf0203136643965150eada39d1fecb5827c0f1b7`
- GitHub `origin` is configured, but live `ls-remote` could not be verified; do not treat the cached remote refs as fresh.
- `PROJECT_NORTH_STAR.md` Blob: `1f737712c7a36ceb34433ac09c3fbba3c3305542`
- `AGENTS.md` Blob: `32c45506cceeaa8c76a5c56bf8360ff476b58856`
- `.agents/skills/opspilot-slice-review/SKILL.md` Blob: `d405c8d413d633824b279202cc1503dab4cf0b03`
- Frozen `SMOKE_INPUTS.md` Blob: `ee9b1623a2296905c425449709a2f9ae6563caca`
- Frozen `CASES.json` Blob: `0b8411942ec99724d9aa10d45faa50a58676836b`

The task's exact S01/S02 prompts are loaded from the frozen case file. The execution runner validates both frozen blobs, branch, expected implementation SHA, one allowed evidence prefix, the new experiment identity, and absence of its new Domain/Checkpoint files before creating anything.

## Provider and SDK configuration

Package versions from the D-drive project environment:

| Package | Version |
| --- | --- |
| Python | 3.14.0 |
| `langchain` | 1.4.1 |
| `langchain-openai` | 1.7.2 |
| `langgraph` | 1.2.16 |
| `httpx` | 0.28.1 |
| `openai` | 3.33.0 |
| `mcp` | 2.3.0 |
| `fastapi` | 0.137.1 |

The local environment file has the required API key and model setting; only presence was checked. Its configured base path is `/v1`, but the authorized run will set the process-only base to `https://api.deepseek.com`, yielding the required `/chat/completions` path. The file is not edited and no key value is printed or copied. Provider opt-in was absent in the ordinary process and will be set only for the one explicitly authorized runner process.

The actual `create_assistant_model()` factory is guarded by the new experiment ID and used explicit HTTPX `MockTransport` for the offline wire check. It emitted one mocked POST to `https://api.deepseek.com/chat/completions` with `deepseek-flash`, `thinking.type=disabled`, `max_tokens=2048`, explicit `tool_choice=auto`, `parallel_tool_calls=false`, `stream=false`, the legal function schema, and no `max_completion_tokens` alias. No network request was made by this test.

The retained GREEN command ran the new ID/app/wire preflight and related AR-02 budget, Assistant, Worker, MCP, and prior safety regressions: **80 passed**; the live runner and source/test modules also passed `py_compile`. Earlier REDs remain saved separately.

## Fees and hard limits

The official DeepSeek pricing page was checked on 2026-11-01. Flash peak cache-miss rates used by the existing ledger are input USD 0.30 / 1M tokens and output USD 1.20 / 1M tokens. The fixed conservative reserve is `616000 * 0.30 / 1000000 + 384000 * 1.20 / 1000000 = USD 0.645600` per Provider dispatch. Sixteen reserves total USD 10.329600, leaving USD 0.170400 under the application's USD 10.50 limit. The reserve is an application-side stop control, not a guarantee of the supplier invoice.

Frozen runtime limits: 16 Provider dispatches, 12 MCP `tools/call`, 30 seconds per request, zero automatic retries, one in-flight Provider request, non-thinking Flash, output cap 2048. Unknown outcomes and invalid/missing Usage stop the new campaign and retain the reservation. No separate paid connectivity check is planned.

Official references:

- https://api-docs.deepseek.com/quick_start/pricing/
- https://api-docs.deepseek.com/api/create-chat-completion/
- https://api-docs.deepseek.com/guides/thinking_mode/

## Execution isolation

The only live runner starts the formal FastAPI app with one Worker, `ASSISTANT_V1`, existing MCP and Domain, and new local files `.runtime/ar02-real-journey-02-20261101/domain.sqlite3` and `checkpoints.sqlite3`. It does not open prior campaign DBs. The new campaign is initialized with the 16/12/USD 10.50 limits and is required to have zero dispatches before S01. Existing write-count guards prohibit Approval, REPAIR, DELIVER, ActionIntent/Ledger, Handoff Receipt/Queue changes.

The normal sandbox had network disabled. If the approved network-enabled execution context is unavailable for the formal Worker, the runner must stop and record the blocker; a standalone network sender will not be substituted.
