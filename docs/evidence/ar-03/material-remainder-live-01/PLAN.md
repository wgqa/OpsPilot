# AR-03-MATERIAL-REMAINDER-LIVE-01

## Frozen execution plan

- Authorized Base: `abd25e20b308df3c95f81c4039295908f399ef71`
- Execution branch: `codex/ar03-material-remainder-01-live`
- Experiment ID: `AR-03-MATERIAL-REMAINDER-01`
- Frozen MAT cases: `docs/evidence/ar-03/material-01/CASES.json` at blob `faf16fbb857278e98f8afbe179fe327855132967`
- Exact user authorization is recorded in `PAID_AUTHORIZATION.json`; its source task-card SHA-256 is recorded there.
- Only the following conditions run, once, in order: `MAT-05-BOUND-PROCESSED`, `MAT-06-SKILL-OFF`, `MAT-06-SKILL-ON`.

## User result and decision space

The model may choose authorized Knowledge, protocol discovery/comparison, Skill, and—only for the bound MAT-05 task—same-Event read tools. It may clarify, answer, continue or stop. No tool order is prescribed. MAT-06 OFF removes only the Skill loader; MAT-06 ON exposes it without injecting Skill text. A visible loader is not evidence of actual use.

MAT-05 reuses the exact MAT-04 frozen question and a new trusted `tenant-a / support-a / ar03-order` binding. Fixture preparation sets the same target Event to `PROCESSED` with its `HTTP 202 / ACKNOWLEDGED` delivery before the Run; this is local test setup, not an Agent action. The final answer must remain limited to the current same-Event observation and must not infer deployment state or other Event outcomes.

## Execution envelope

| Control | Frozen value |
| --- | ---: |
| Model / mode | DeepSeek `deepseek-flash`, thinking disabled |
| Output / context | 2048 output tokens; 12,000 input tokens |
| Tool protocol | `tool_choice=auto` when tools supplied; `parallel_tool_calls=false`; non-streaming |
| Provider calls | 16 total; one in flight; 30-second timeout; zero retries |
| MCP calls | No count ceiling; every attempt remains persisted and audited; 12-second handler timeout |
| Application budget | USD 10.50; USD 0.645600 durable reservation before each Provider dispatch |
| Other bounds | 60-second Run; 300,000 ms Task active time; recursion 36; 3,600-second Campaign wall clock |
| Writes | Zero business writes; no approval, repair, handoff, ticket submission or deployment |

At 16 requests the maximum reservation is USD 10.329600, within the application cap. The reservation is not a provider invoice. Current official DeepSeek peak cache-miss rates are USD 0.30/M input and USD 1.20/M output; the frozen reservation is based on the documented 1M context / 384K output envelope and remains more conservative than the authorized 12K / 2048 request. This was checked 2026-11-04; no paid probe was sent.

## Isolation and stop rules

The campaign gets a new private runtime, Domain DB, shared Campaign ledger, one-shot claim and three separate checkpoint files. The earlier RESUME-01/02 claims, ledgers, UNKNOWN reservations, raw databases and traces are not opened for writing. A provider UNKNOWN/timeout, invalid Usage, source or authorization anomaly, cross-Task/Event association, business-write attempt, budget/deadline limit or runner-integrity error stops the entire campaign. No retry or rerun is authorized.

Private raw Provider HTTP, DB, Checkpoint and execution logs stay under the ignored `.runtime/ar03-material-remainder-live-01-live/` directory. The repository evidence directory contains only reviewed summaries, hashes, offline test logs and the exact non-secret authorization record.

## Official protocol references

- [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/)
- [Chat Completions request/response](https://api-docs.deepseek.com/api/create-chat-completion/)
- [Thinking Mode parameters](https://api-docs.deepseek.com/guides/thinking_mode/)
