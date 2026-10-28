# Proposed real-model trial — NOT AUTHORIZED / NOT RUN

No live Provider constructor/CLI has been added. Obtain explicit approval for this
plan and the finite cost preflight before creating any real request.

Model proposal: both groups use the same `deepseek-flash` endpoint/model version,
recording actual response model/fingerprint on every request. Proposed settings:
non-thinking (`extra_body.thinking.type=disabled`), output `max_tokens=512`,
timeout 30 s, max_retries=0, auto tool choice, parallel_tool_calls=false; omit
unsupported sampling overrides identically. The installed LangChain interfaces
have been checked locally, but actual Provider acceptance/settings/Usage remain
unverified. Do not silently switch model/mode on failure.

Official sources checked 2026-10-28:
[Models and Pricing](https://api-docs.deepseek.com/quick_start/pricing/) lists the
current `deepseek-flash` alias and peak uncached input USD 0.30/M, output USD 1.20/M;
[Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/) documents the
explicit disabled setting. Recheck price/version immediately before authorization
is exercised; alias upgrades and cache behavior are confounds.

## Sample and upper bounds proposed for approval

- Keep all 9 frozen case variants; 2 paired repetitions, alternating A/B execution
  order: 36 initial Task/Run invocations. Fresh independent equivalent initial
  states per pair. No prompt tuning against measured repeats; new exploratory
  instances need a separate release, not overwritten Gold.
- 8 model calls / 6 MCP attempts each: global maximum 288 Provider requests and
  216 MCP attempts, failures and unknown requests included; one Provider request
  in flight. Existing Task limits do not authorize exceeding these global limits.
- Per-request application input budget 12,000 estimated tokens and output 512.
  At peak non-cache rates, the planning arithmetic is
  `288 * (12000*0.30 + 512*1.20)/1e6 = USD 1.2137472`.
  Propose USD 1.50 maximum reservation for the whole trial. This estimate is not
  a proven money cap: preflight must check tokenizer bias, actual max_tokens
  semantics, Usage, thinking mode, and request reservation release. If it cannot
  bound cost, stop without sending. No automatic retries or extra success runs.
- The local deterministic suite used 46 model decisions total for one repeat;
  2 repeats at that count would be 92 calls, at most USD 0.3877248 under the same
  planning token assumptions. This predicts neither real completion nor latency.

Before each request, check settled charge + unresolved reservation + next worst
request reservation against USD 1.50. Keep timeout/unknown reservations unresolved
until provider accounting is available. Reuse the project's finite experiment
ledger approach; no new cost service is part of AR-01.

## Recording and scoring

Persist release SHA, complete actual outbound messages/spec digests, model ID and
settings, request/response IDs, reported input/output/cache/reasoning Usage where
available, estimated tokens separately, timestamps, tool calls and observations,
source versions, request/Event identity, final answer and fallback reason. Keep
all failures and partials. Do not collect hidden reasoning as an evaluation target.

Score blinded to group: user-goal completion, justified current facts, useful
clarification, observation-driven change, Knowledge use, Event identity correctness,
unauthorized read/write count, tool errors, total requests, Usage and elapsed cost.
Report normal model delivery separately from deterministic fallback. Initial and
cross-Run product authority remain outside this policy-only trial.

Stop on any safety violation, model/version drift, unsupported settings, missing
critical Usage/accounting, USD/request cap, or repeated protocol failure. Report
incomplete pairs; do not drop failures. Two repetitions are exploratory, not a
statistical or general superiority claim. Approval does not authorize AR-02,
production migration, browser automation, or business writes.
