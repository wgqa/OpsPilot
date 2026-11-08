# R1-LIVE-JOURNEY-01 POST-FAILURE-CLOSEOUT-01

**Base:** `d3735d3738c7769a7406f03b43ade29d5eb51d35`

**Branch:** `codex/r1-live-journey-01`
**Scope:** offline-only replay and state-reporting correction. No new real Provider request, browser run, or external business write is authorized.

## Frozen boundary

- Keep the four original HTTP 200 responses, campaign ledger, original failures, and raw trace unchanged.
- Replay only captured J1-01 and J2-01 tool proposals through the existing Runtime HTTPX wrapper, ChatOpenAI, Assistant ToolNode, MCP, and local Domain path.
- Mark any follow-up model response produced by a deterministic fixture as offline fixture output.
- Correct Assistant error classification from the persistent Runtime spend state; preserve real UNKNOWN reserves and prohibit retry.

## Acceptance evidence

1. Raw request/response record hashes and captured tool calls match the public sanitized trace.
2. Single and multi-tool calls pass the real local MCP/Domain execution path; observations appear in the next model request.
3. Gzip and plain JSON transport decoding are covered without claiming the historical live response used gzip.
4. Known stored Usage, not-sent, Usage violation, and UNKNOWN states have distinct user-safe notices; UNKNOWN retains its reserve.
5. Runtime Grant, campaign budget, and R1 J1/J2 offline regressions pass.
