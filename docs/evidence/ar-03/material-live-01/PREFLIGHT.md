# AR-03-MATERIAL-LIVE-01 Provider and budget preflight

Status before the paid run: `OFFLINE_CHECKS_READY`; no real Provider request has been sent.

## Identity and evidence freeze

- Repository worktree: `D:/学习/agent新项目/.worktrees/ar03-material-01-public`
- Branch: `codex/ar03-material-01-public`
- Freeze commit: `434a8b027f0072036b46bc624d1defab8703b775`
- Frozen cases: `docs/evidence/ar-03/material-01/CASES.json`, blob `faf16fbb857278e98f8afbe179fe327855132967`
- Project North Star blob: `1f737712c7a36ceb34433ac09c3fbba3c3305542`
- `AGENTS.md` blob: `32c45506cceeaa8c76a5c56bf8360ff476b58856`
- Project Skill blob: `d405c8d413d633824b279202cc1503dab4cf0b03`
- Remote `main` and candidate: `UNVERIFIED`; the initial GitHub `ls-remote` attempt failed to connect. The local remote-tracking candidate ref was `3ec06caa6a2d8ef370592d33164be3077a0a5f6f`; it is not represented as a freshly verified remote SHA.
- Original task Base: `3ec06caa6a2d8ef370592d33164be3077a0a5f6f`; authorized freeze commit is its descendant.

## Provider protocol and price

Official DeepSeek documentation was rechecked on 2026-11-03:

- Model name: `deepseek-flash`; current listed model version: `DeepSeek-V4.1-Flash-1017`.
- Peak cache-miss rates: input USD 0.30 / 1M tokens; output USD 1.20 / 1M tokens. The experiment uses peak rates and takes no cache discount.
- The Chat Completions API supports `thinking.type=disabled`, `max_tokens`, tools, and `tool_choice=auto`; the documented maximum `max_tokens` is 384K. Tool choice defaults to `auto` when tools are present, but the frozen wire contract requires it explicitly.
- The existing adapter's `base_url` is `https://api.deepseek.com/v1`; MockTransport confirms the serialized endpoint is `https://api.deepseek.com/v1/chat/completions`. DeepSeek official integrations also document `/v1/chat/completions`; no real connectivity probe is part of this task.
- Frozen request fields: `deepseek-flash`, `thinking.type=disabled`, `max_tokens=2048`, `tool_choice=auto` when tools are present, `parallel_tool_calls=false`, `stream=false`, 30-second timeout, SDK retries 0, HTTPX transport retries 0.

The unchanged reservation is USD 0.645600 per Provider dispatch. Sixteen reservations total USD 10.329600, below the USD 10.50 campaign limit. Even the documented 1M input context at peak cache-miss price plus the requested 2,048 output tokens estimates to USD 0.3024576; the per-call reserve is larger. This is an application reservation, not a guarantee against a Provider billing beyond a documented request limit. Any missing, invalid, over-limit, or unknown Usage stops the campaign and retains the reservation.

The shared durable ledger, not separate per-case limits, is the aggregate authority. One fresh Domain DB is shared by the seven isolated Sessions/Tasks so every case uses the same persisted campaign counter; Checkpoint and identity remain per-task/session as provided by the existing API. Run limits are scoped to this experiment ID at 16 MODEL / 10 MCP. Bound Task D2 limits are configured through the trusted setup API at 16 / 10 while the existing 300,000 ms task deadline remains unchanged. Tests confirm legacy experiment IDs retain their 8 / 6 defaults.

## Free checks completed

- Freeze tests committed before implementation; their initial four failures are retained in `runs/red-01-budget-scope.log`.
- Final campaign-specific deterministic/API/Worker/MockTransport suite: 11 passed (`runs/green-12-final-targeted.log`, exit code 0); this includes the final Runner pre-send budget-row checks.
- AR-03 material, protocol comparison, and scoped comparison regressions: 53 passed (`runs/green-07-ar03-material-and-comparison.log`, exit code 0).
- AR-02 Assistant and AR-02/AR-03 integration regressions: 28 passed (`runs/green-08-ar02-ar03-integration.log`, exit code 0).
- Python compilation and `git diff --check` passed.
- MockTransport captured the actual Assistant SDK request at `/v1/chat/completions` with the required model, thinking, tool-choice, output, non-parallel and non-stream fields; no real Provider request was made by that test.
- Tests cover nine legal MCP reads followed by a final answer, ten model calls, separate tasks for the same registered order, unchanged D2 active-time limit, Skill OFF/ON tool visibility, the shared ten-call durable MCP cap across two real persisted Assistant Runs, and a MockTransport-only wire response.

## Live-send gate

The repository's `run_live.py --preflight-only` is the required final pre-send check. It verifies the target branch and ancestry, frozen CASES blob, clean tracked/index state, environment model/key presence without printing credentials, disabled inherited Provider opt-in, official endpoint shape, reservation and campaign constants, empty output/runtime locations, and exact seven-case ordering. It makes no Provider call. Its raw machine output and exit code will be saved under `runs/` after the implementation commit. If it does not return `PREFLIGHT_READY`, no paid request will be sent.

After a successful preflight, the one-shot Runner creates an exclusive execution claim and fresh isolated SQLite/Checkpoint state. Before every HTTPX Provider dispatch it requires exactly one matching durable campaign reservation and Assistant reservation, validates the final serialized request, context estimate, allowed tools, aggregate caps, and single-flight condition. Unknown transport results, invalid Usage, writes, source/scope anomalies, or cap breaches stop all remaining cases; there are no retries.

## Evidence levels

At this point real Provider requests = 0; real campaign MCP calls = 0; business write actions = 0; browser = `NOT_RUN`. Offline API/Worker/MockTransport tests establish only wiring and safety conditions, not DeepSeek decision quality.
