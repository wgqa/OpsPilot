# AR-03-MATERIAL-LIVE-01-RESUME-02 preflight and execution record

**Final status:** one authorized campaign executed once; `PARTIAL_STOPPED` after a Runner audit exception. No further send is permitted under the consumed one-shot claim.

## Frozen checks before sending

- Branch: `codex/ar03-material-live-01-resume-02`; the committed implementation SHA was `8df557dabb6f7440b371828c39974239363ee6d9`.
- Base: `d4addd403ba0722d4acb4c1a33d1cd655599c97c`.
- Frozen MAT cases Blob: `faf16fbb857278e98f8afbe179fe327855132967`.
- Current price page identified `deepseek-flash` as DeepSeek-V4.1-Flash-1017 and listed peak cache-miss input at $0.30/M, cache-hit at $0.006/M, and output at $1.20/M. The app-side cost estimate conservatively used the full peak cache-miss rate for every prompt token.
- Offline HTTPX MockTransport verified the serialized request and persisted reservation path before the mock response. The request used `thinking.type=disabled`, `max_tokens=2048`, `tool_choice=auto` when tools were supplied, `parallel_tool_calls=false`, and `stream=false`.
- The preflight verified a 12,000-token context cap, 30-second timeout, one in-flight Provider request, zero retry configuration, and 16 Provider / 10 MCP / $10.50 Campaign limits. The maximum 16-request reserve was $10.329600.
- Each scenario used the new isolated RESUME-02 Domain DB and checkpoint path; the Runner did not target the old RESUME-01 paths. The new claim was created only after the committed clean-worktree preflight returned `PREFLIGHT_READY_AUTHORIZED_ONE_SHOT`.

## Preflight history

The first preflight was correctly blocked while the worktree was dirty: `WORKTREE_OR_INDEX_NOT_CLEAN`; it created no claim and made no Provider/MCP calls. The later clean-worktree preflight passed. Its report recorded only credential presence and model/host configuration; no key value was read or emitted.

## After the one-time campaign

- The RESUME-02 claim is `CLAIMED_ONE_SHOT_NO_RETRY` and consumed. Nine Provider responses were received and settled; no result is UNKNOWN. Do not rerun.
- The Provider ledger has $0 remaining reserve, $0.013253 estimated settled cost, and $10.486747 remaining under the app cap; the independent MCP allowance reached 10/10.
- All seven Gold outcomes are in `RESULTS.json`. MAT-05 and MAT-06 OFF/ON were not run after the stop.
- No Approval, Plan, ActionIntent, ActionLedger, Delivery, verification receipt, diagnosis, handoff, or external business write was recorded.
- The paid campaign stopped because `_audit_case()` raised `KeyError('run_id')` after MAT-04 persisted; the exact cause and case treatment are in `REPORT.md` and `FAILURES.md`.

## Official references

- [DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)
- [DeepSeek Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)
