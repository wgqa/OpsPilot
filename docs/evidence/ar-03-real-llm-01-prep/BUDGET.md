# AR-03-REAL-LLM-01 — Proposed Live Budget (Not Authorized Yet)

This is an execution proposal only. It does not authorize a Provider request or enable the real Provider during the preparation run.

| Limit | Proposed cap | Accounting rule |
|---|---:|---|
| DeepSeek Flash Provider dispatches | 16 total across both paired cases | Count every reserved/dispatched/unknown request; zero retries and zero reruns |
| MCP `tools/call` | 12 total | Count each call, including refused/failed calls according to the existing ledger contract |
| App-reserved cost | USD 10.50 total | Existing isolated dispatch ledger only; not a vendor billing guarantee |
| Reservation per model dispatch | USD 0.645600 | Preserve the reviewed AR-02-REAL-JOURNEY-03 peak-envelope reservation until independently rechecked |
| Maximum planned reservation | USD 10.329600 | 16 × 0.645600; leaves USD 0.170400 below the app cap |
| Provider concurrency | 1 | One request in flight |
| Request timeout | 30 s | Timeout/unknown retains reservation and stops the experiment |
| Retries | 0 | SDK, HTTPX and operator; no manual retry after unknown |
| Input context cap | 12,000 tokens | Existing production guard unchanged |
| Model request output parameter | `max_tokens=2048` | Exact serialized wire field; no `max_completion_tokens` alias |
| Provider/model mode | `deepseek-flash`, thinking disabled | Revalidate current official price/protocol before any paid execution authorization |

The existing code uses a 16 Provider / 12 MCP / USD 10.50 envelope and a USD 0.645600 reservation, based on a dated 2026-11-01 peak-price/context calculation. Price and model alias are time-sensitive; a live run must recheck official documentation and must stop if the frozen reservation no longer covers the approved envelope. Do not reduce reservation, increase caps, or rely on cache discounts to pass preflight.

## Run allocation and unknown outcomes

The proposal is one trusted order-binding operation and one Assistant run for each isolated scenario, with existing per-run ceilings of 8 MODEL / 6 MCP. The experiment-level ledger caps both scenarios together at 16 / 12. Binding is established by the trusted API before the model's run; the chat text itself does not grant it. If the API's bound-order admission run consumes a Provider dispatch in the actual route, that dispatch counts against the same experiment budget. Do not assume a hidden free run.

Before any live request, the approved experiment ID must be isolated in fresh Domain and Checkpoint databases. Old UNKNOWN rows and reserves remain untouched. Unknown response, missing/invalid Usage, budget violation, authorization anomaly or unexpected write stops the entire paired experiment; no later request may be sent.

No cost is expected or charged in this prep. MockTransport Usage is synthetic and must not be reported as actual Provider Usage or cost.
