# P0 preflight — 2026-10-28

**Paid P1: NOT_AUTHORIZED / NOT_RUN. Default live readiness: BLOCKED.**
Offline CLI output is in `TRACE/offline-preflight-01/preflight.json` and
`runs/12-offline-preflight.log`: zero request reservations, zero cost exposure,
`ready=false`, next conservative reservation USD 0.786432.

## Same adapter / actual wire contract

Both groups use the same `MeteredModel` / installed `ChatOpenAI`, config digest,
six original MCP JSON schemas and non-thinking `deepseek-flash` proposal.
No Provider constructor is used by the original deterministic CLI. The separate
real_model CLI defaults to offline preflight; `--live` also requires explicit
human-authorization metadata matching the frozen cases, model config and limits.
This repository contains **no valid paid authorization**. A test-only fabricated
authorization demonstrates that even `--live` cannot bypass the cost preflight.

The installed SDK maps its nominal max_tokens option to a different wire field.
This adapter deliberately sends the vendor-documented `max_tokens:512` through
extra_body, plus `thinking:{type:disabled}`, stream=false, parallel=false.
This is an explicit adapter mapping, not silent parameter removal after rejection.
LangChain create_agent's unspecified tool_choice=None sentinel maps explicitly
to the common auto setting. Unknown settings reject before sending.
The actual HTTP hook checks every body field, endpoint and raw schema before
marking a reservation SENT. Actual loopback-server received bodies are compared,
not just the arguments recorded by bind_tools.

`max_retries=0`, transport retries=0, redirects disabled, environment proxy
discovery disabled, socket-options SDK injection disabled explicitly. Model
timeout 30s, tool 12s, policy invocation 60s; fixture/server setup is outside the
policy invocation timer and included in reported group elapsed time. Existing
context budgets are unchanged. Both fresh initial Runs retain 8 MODEL / 6 MCP.
The fixed 10-group batch therefore has a 60-MCP bound; persisted group claims
prevent a restart from sending the same group again. No cross-Run product
budget equivalence is claimed (see original PARITY.md).

## Monetary and request preflight

Official sources actually checked this session:
[pricing](https://api-docs.deepseek.com/quick_start/pricing/),
[completion contract](https://api-docs.deepseek.com/api/create-chat-completion/).
The checked alias is listed as DeepSeek-V4.1-Flash-1017. This is a documentation
observation; no actual DeepSeek response/version was obtained this round.
The request cap is 80, fixed sample 5 pairs, one request in flight. Nonthinking,
auto tools and output 512 are requested identically. parallel_tool_calls is not
listed on the checked vendor completion page: vendor acceptance remains unverified;
if rejected, stop instead of deleting it or changing the model.

The historical meter `opspilot/smokes/m4_continuous.py:71` records output above
nominal SDK 512. Its raw history has not been changed or claimed independently
reproduced. Correct wire serialization removes a plausible ambiguity but cannot
prove that the remote vendor honors the bound. Use conservative peak no-cache
input/output prices, ignoring cache discounts. The input ceiling uses the larger
binary interpretation of 1M, 1,048,576; output ceiling 393,216. The reservation is
`(1048576*0.30 + 393216*1.20)/1e6 = 0.786432 USD`.
Overcounting the joint context ceiling is intentional. **This bound is too coarse
for USD 0.50; it does not prove a USD 0.50 experiment is intrinsically impossible.**
No request is sent at the proposed target; no actual dollar cap is claimed proven.
No user spending approval has been granted.

The finite SQLite ledger is experiment-only and follows the older reservation /
settlement / unresolved-exposure pattern. BEGIN IMMEDIATE protects both global
request count and `settled upper charge + unresolved reservations + next reserve`.
Known strict Usage releases unused exposure; peak uncached charge is an upper
estimate, not the Provider's invoice. Reserved, failed, unknown, timeout or lost
responses remain counted; unresolved reservations block restart. Duplicate logical
requests/group claims never cause automatic resend. No reset/reconciliation endpoint.
Local tests use cap USD 2 solely to exercise reserve/settle positive paths against
literal 127.0.0.1; build_live_model refuses that test cap.

## Response and stop contract

Persist actual received completion ID, whitelisted HTTP request-ID header,
model string, fingerprint, Usage including cache counts if supplied, content,
tool proposals and timestamps. Hidden reasoning and credentials are omitted.
Missing critical IDs/Usage, malformed totals, requested output overrun, backend
drift, unfinished completion, HTTP error, budget exhaustion or unknown result
halt the whole batch. The first material A/B pair must deliver normally before
later pairs start. An incomplete A-only group retains its trace/result on disk.

Before any future live authorization is exercised, recheck official price/model,
freeze a justified monetary bound and explicit budget authorization. Current code
does not automatically relax the conservative reservation. A change would require
review; no live probe is authorized by P0. P1 and P2 stop here.
