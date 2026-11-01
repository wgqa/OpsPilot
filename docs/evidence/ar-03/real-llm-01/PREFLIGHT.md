# AR-03-REAL-LLM-01 — Preflight

**Preflight date:** 2026-11-02 (local task environment)

**Provider requests before live execution:** 0

**Main:** `ec8c3582f6d145eec9979c43607302731411ead8`

**Authorized candidate base:** `e416bd1398b5a4bca6cdf3360f3ae78037a2740b`

## Repository and frozen-input verification

- Execution branch is `codex/ar03-real-llm-01-live`; its base is the authorized candidate.
- Current checkout Blob IDs match the frozen CASES, GOLD and BUDGET values in `PLAN.md`.
- `PROJECT_NORTH_STAR.md` Blob: `1f737712c7a36ceb34433ac09c3fbba3c3305542`.
- `AGENTS.md` Blob: `32c45506cceeaa8c76a5c56bf8360ff476b58856`.
- Project Skill `.agents/skills/opspilot-slice-review/SKILL.md` was actually opened at this checkout; Git Blob `d405c8d413d633824b279202cc1503dab4cf0b03`; SHA-256 `AB6802FDEBF776089BD504EF4CAC7B65FD0A74EB58080D14FF81E92ABA1B59CE`.
- Initial worktree was clean at the authorized base. No historical experiment database was opened.

## Provider and price preflight

The local project `.env` was inspected for variable names only and loaded into the one-shot child process; its contents and secret values were not printed or copied. The required API-key variable is present; the configured model is `deepseek-flash`, and the base URL is `https://api.deepseek.com/v1`. The real-provider opt-in and experiment ID were not enabled before the runner. The runner enables them only in its own process after all checks pass.

DeepSeek's current official pricing page lists a peak cache-miss input rate of USD 0.30 per million tokens and output rate of USD 1.20 per million tokens for Flash. Its current Flash model page describes a 1M context window and 384K maximum output. At peak rates, the frozen reserve formula remains:

`616,000 × 0.30 / 1,000,000 + 384,000 × 1.20 / 1,000,000 = USD 0.645600`.

Sixteen maximum reservations total USD 10.329600, leaving USD 0.170400 under the USD 10.50 application limit. This is an application-side conservative reservation, not a guarantee of the vendor invoice. No cache discount is assumed. Price was rechecked against [DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/) and parameter semantics against the [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/), [Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/) and [Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/) documentation. `parallel_tool_calls=false` is enforced by local wire validation; the live result must show the actual sent field.

## Offline request and accounting checks

- The formal bound API/Worker path was tested with explicit HTTPX `MockTransport`; it produced the expected official URL and frozen model parameters, offered both protocol-comparison tools and bound-order read-only tools, and did not call a real Provider.
- The one-shot runner transport was tested with MockTransport for request/response capture, authorization-header redaction and rejection of a wrong `max_tokens` wire body before delegation.
- AR-03-specific SQLite rows durably store 8 Provider / 6 MCP limits per case. Each reserve checks the persisted row, not a caller-supplied limit. A pre-existing row with a mismatched envelope fails closed.
- Provider reservations across the pair are at most `8 + 8 = 16`; MCP attempts at most `6 + 6 = 12`; all model dispatches, including trusted binding admission, use these same ledgers.
- The runner creates fresh Domain and Checkpoint files only under this evidence directory, executes A then B serially, checks the experiment ledger after each run, and persists a one-use claim before any external dispatch. Existing run paths cause a stop; it does not overwrite prior evidence.
- The runner has no ping or connection-test path. The next external HTTP action, if launched, is the first actual Provider request within the authorized user journey.

## Local test environment

Python used: `D:\学习\agent新项目\.venv\Scripts\python.exe`. Pytest basetemp was placed under this evidence directory on D: and its generated temporary databases were removed after logs were preserved. Two initial commands exposed environment/setup issues; both are retained in `runs/` and are distinguished from valid RED/GREEN evidence. Corrected regression results are recorded in `FAILURES.md` and `runs/`.

Offline preflight command:

```powershell
& 'D:\学习\agent新项目\.venv\Scripts\python.exe' docs/evidence/ar-03/real-llm-01/run_live.py --preflight-only
```

Recorded output: `runs/runner-preflight-final.log`, status `PREFLIGHT_READY`, `provider_requests_before_execution=0`.
