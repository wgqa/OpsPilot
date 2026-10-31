# AR-02-SMOKE-01 Result

**Overall:** `HOLD / REAL_S01_S02_NOT_RUN`
**Free adapter:** `PASS`
**Paid model behavior:** `NOT_RUN`
**Main:** unchanged by this work.

## 1. Real conversation

No real S01 or S02 conversation was run. The worktree had no `.env` or model credentials/configuration, the provider opt-in was off, and this task did not authorize paid requests. The frozen input was not rewritten: [S01/S02](../hf-01/SMOKE_INPUTS.md).

The executed 40-test AR-02 regression includes a deterministic-model journey through the real local API, Worker, `ASSISTANT_V1`, MCP, HTTP and SQLite (`tests/test_ar02_runtime.py`). That is continuity and wiring evidence only. It does not establish real model understanding, tool selection, drafting quality, or user-visible success for this smoke.

## 2. Model's actual choices

There is no real model choice to report. The only newly captured outbound body is from a local `httpx.MockTransport`; it contains the test prompt/tool schema and the exact DeepSeek-compatible `max_tokens: 2048` field. It is not a Provider trace and did not run an MCP tool. See `TRACE/provider-wire-mock.json` and `runs/green-provider-wire-mock-05.log`.

One earlier protocol RED showed that `ChatOpenAI(max_tokens=2048)` serialized as `max_completion_tokens`, while the current DeepSeek API reference specifies `max_tokens`. The adapter now emits the documented top-level field for DeepSeek model IDs and retains standard `ChatOpenAI` behavior for other model IDs. The official API also says thinking defaults on when both thinking controls are omitted; the current local body omits them, so this remains a preflight decision for a future paid run. [DeepSeek API](https://api-docs.deepseek.com/api/create-chat-completion/)

## 3. User result

The user did not receive a new S01/S02 answer, diagnosis, or draft from this slice. The code now wires the official Web server to the existing `ASSISTANT_V1` factory, disabled by default; missing enabled configuration fails before dispatch. Existing business authority remains in MCP/Domain, and no business-write path was added.

Actual cost for model completions: no Usage was reported because none completed. One accidental authentication failure is documented in [FAILURES.md](FAILURES.md); billing for that 401 was not independently checked.

## 4. Most important failure and correction

The most consequential intended failure was the outbound token parameter mismatch. The first local capture showed `max_completion_tokens`, not DeepSeek's `max_tokens`. The fix is limited to the existing factory and middleware: DeepSeek uses a top-level `max_tokens` via `extra_body`, and the middleware no longer injects the incompatible alias. A final local `MockTransport` capture confirmed one request with `max_tokens=2048`, `max_completion_tokens` absent, `tool_choice=auto`, `parallel_tool_calls=false`, and the expected tool schema.

The first attempt to localize that test accidentally reused a cached network client and emitted one placeholder-key HTTP request that returned 401. The harness now injects the mock transport when constructing the model. This failure is preserved; the corrected local test and final 40-test regression pass.

## Evidence and remaining gate

- Final focused free tests: 7 passed.
- Final related free regression: 40 passed.
- Raw logs and historical REDs: `runs/`.
- Local-only request capture: `TRACE/provider-wire-mock.json`.
- Official peak DeepSeek Flash price was checked at [Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/). At documented limits, the conservative per-call calculation is USD 0.3018432 if the 2048 output cap is honored, or USD 0.6456 if it is not but the published context/output bounds hold.
- Existing per-Run and Task counters do not provide a durable S01/S02 experiment-wide USD/Provider/MCP cap. The proposed later authorization envelope is 16 Provider requests, 12 MCP attempts, and USD 10.50 with a narrow durable reservation ledger and no retries; it is a proposal, not approval.
- Browser B-11 remains `NOT_RUN / BLOCKED_BY_PRIOR_STOP`.
- No real Provider completion, S01, S02, or browser run is claimed.

The implementation SHA is recorded in the final handoff accompanying this report. The task remains a hold pending independent review, a verifiable global budget mechanism, provider config, and separate paid-call authorization.
