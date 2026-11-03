# AR-03-MATERIAL-LIVE-01-RESUME-02

## Frozen execution identity

- Authorized source base: `d4addd403ba0722d4acb4c1a33d1cd655599c97c`
- Branch: `codex/ar03-material-live-01-resume-02`
- Experiment ID: `AR-03-MATERIAL-LIVE-01-RESUME-02`
- Frozen cases: `docs/evidence/ar-03/material-01/CASES.json`
- Frozen cases blob: `faf16fbb857278e98f8afbe179fe327855132967`
- Freeze commit: `434a8b027f0072036b46bc624d1defab8703b775`

The seven conditions remain MAT-01 through MAT-05 and MAT-06 Skill OFF/ON. The accepted Runner, formal FastAPI/Worker/Assistant path, MCP, Domain, Context and safety contracts remain the execution path. No prompt, Gold, case order, or model tool sequence is changed.

## Authorized limits

- DeepSeek `deepseek-flash`, non-thinking mode.
- `max_tokens=2048`, `tool_choice=auto` when tools are present, `parallel_tool_calls=false`, `stream=false`.
- Context input at most 12,000 tokens; timeout 30 seconds; one Provider request in flight; zero retries.
- Campaign at most 16 Provider dispatches and 10 MCP `tools/call` attempts.
- Application ledger at most USD 10.50; reserve USD 0.645600 per Provider dispatch; maximum reservation USD 10.329600.
- Campaign wall-clock limit 60 minutes; business writes disabled.

This card authorizes one execution only after every preflight condition passes. The Runner's private one-shot claim is created atomically only after preflight. The static prepared-claim record is not a consumed claim.

## Isolation and stop rules

The experiment has separate Domain SQLite, Checkpoint SQLite, runtime, raw evidence directory, authorization ID and one-shot claim path. RESUME-01's claim and the original historical claim are read by SHA only; neither is reusable or writable from this Runner. Raw execution artifacts are ignored by Git and remain local.

Any unknown Provider result/Usage, invalid source or Event association, unauthorized tool, business write, budget violation, timeout, or unhandled Runner exception stops the campaign with no retry. A preflight failure creates no claim and sends no request.
