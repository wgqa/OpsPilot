# AR-02-REAL-JOURNEY-02 Plan

Status: authorized, execution not started.

## Frozen scope

- Repository: `wgqa/OpsPilot`
- Branch: `codex/ar02-real-journey-02`
- Starting local Base: `cf0203136643965150eada39d1fecb5827c0f1b7`
- Live remote SHA: `REMOTE_UNVERIFIED` (GitHub fetch was unavailable during preparation)
- North Star Blob: `1f737712c7a36ceb34433ac09c3fbba3c3305542`
- AGENTS Blob: `32c45506cceeaa8c76a5c56bf8360ff476b58856`
- Skill Blob: `d405c8d413d633824b279202cc1503dab4cf0b03`
- Frozen S01/S02 inputs: `SMOKE_INPUTS.md` Blob `ee9b1623a2296905c425449709a2f9ae6563caca`
- Frozen six-turn case contract: `CASES.json` Blob `0b8411942ec99724d9aa10d45faa50a58676836b`
- New isolated experiment identity: `AR-02-REAL-JOURNEY-02`

## User journey

S01 is one independent Session asking whether HTTP 202 Accepted proves the callback was processed. With no TaskBinding, the answer may explain protocol semantics or query permitted Knowledge, but cannot invent current order/Event/Receiver state.

S02 uses one other Session for the five frozen turns: an untrusted E1/202 example and protocol question; authorized protocol retrieval; trusted API confirmation of `ar02-order` binding; current same-Event Delivery/Receiver investigation; and a sourced support-note draft that names unknowns without claiming a ticket was submitted.

The model chooses among exposed legal read tools and may answer, clarify, continue, or stop. This plan does not prescribe a tool order. Fixture preparation is separate from Agent observations. No Repair, approval, delivery, ticket write, browser automation, or external business write is permitted.

## Frozen provider and budget boundary

- Model `deepseek-flash`, thinking disabled, `max_tokens=2048`, `stream=false`.
- Tool requests explicitly use `tool_choice=auto`, `parallel_tool_calls=false`.
- Endpoint must be `https://api.deepseek.com/chat/completions`.
- Timeout 30 seconds; SDK and HTTPX retries 0; one provider request in flight.
- At most 16 Provider dispatches and 12 MCP `tools/call` attempts.
- At most USD 10.50 application budget; each Provider request reserves USD 0.645600 before send; 16 reservations total USD 10.329600.
- An unknown request result, missing/invalid Usage, budget anomaly, security anomaly, or unexpected write stops the experiment. No retry, route/model switch, or second experiment identity is permitted.
- This reservation is an application control, not a guarantee of the provider's invoice.

Official price/protocol references checked for the run date:

- https://api-docs.deepseek.com/quick_start/pricing/
- https://api-docs.deepseek.com/api/create-chat-completion/
- https://api-docs.deepseek.com/guides/thinking_mode/

## Execution shape

Use the existing formal FastAPI API, a single Worker, `ASSISTANT_V1`, the existing Assistant MCP/Domain path, and isolated Domain/Checkpoint SQLite files under `.runtime/ar02-real-journey-02-20261101/`. Reuse the prior formal runner, with only new identity, new runtime paths, frozen blob checks, exact endpoint preflight, and current checkout validation changed.

The old `AR-02-REAL-JOURNEY-01` UNKNOWN dispatch and USD 0.645600 reservation, and the independent CONN-01 UNKNOWN reservation, are historical read-only evidence. This run uses new files and a new ID; it neither reads nor mutates those ledgers.

## Stop line

Run one frozen S01/S02 journey only. Preserve all outputs and failures. Do not modify `main`, the AR-03 branch, frozen inputs, historical results, or run a connectivity probe.
