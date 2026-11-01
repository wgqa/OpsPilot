# AR-02-REAL-JOURNEY-01 — bounded live execution

**Submission status:** `ACCEPTANCE_CANDIDATE`
**Experiment result:** `UNKNOWN_STOPPED`
**Repository/branch:** `wgqa/OpsPilot` / `codex/ar02-live-01`
**Execution base:** `69e7267de03f13651f3e54aaf956a919284be845`

## Frozen journey

The run uses the existing, unchanged S01/S02 contract by reference:

- `docs/evidence/ar-02/hf-01/SMOKE_INPUTS.md`, blob `ee9b1623a2296905c425449709a2f9ae6563caca`.
- `docs/evidence/ar-02/real-journey/CASES.json`, blob `0b8411942ec99724d9aa10d45faa50a58676836b`.

S01 is a separate Session asking whether HTTP 202 proves callback processing. S02 is one Session with the five frozen turns: untrusted E1 log, authorized protocol lookup, authenticated order selection, current same-event Receiver check, and sourced explanation draft. No input or Gold was changed.

The only live execution authorized here is one attempt at each of those six turns, in order, through FastAPI → one local Worker → `ASSISTANT_V1` → DeepSeek → MCP/Domain → persisted Session answer. No direct CLI Completion, browser, REPAIR, DELIVER, Approval, ticket submission, or external business write is in scope.

## Frozen limits

- `deepseek-flash`, non-thinking, `max_tokens=2048`, `tool_choice=auto` when tools are offered, `parallel_tool_calls=false`.
- 30 second model timeout, zero SDK/HTTPX retries.
- Maximum 16 Provider dispatches, 12 MCP `tools/call` attempts, USD 10.50 application budget.
- Reserve USD 0.645600 before each Provider dispatch; preserve the reserve for unknown outcomes.
- Fresh isolated Domain and Checkpoint databases; one Worker; stop after any UNKNOWN, protocol/config mismatch, authorization anomaly, timeout, usage anomaly, or budget limit.

The run stopped after its first Provider dispatch. S01 was not completed and S02 was not started. See `RESULTS.json`, `FAILURES.md`, and the immutable attempt logs under `attempt-01/`, `attempt-02/`, and `attempt-03/`.
