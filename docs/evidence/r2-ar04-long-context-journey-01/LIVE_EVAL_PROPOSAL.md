# Phase B proposal: live semantic evaluation

**Status: `NOT_RUN`.** This proposal does not authorize or perform a Provider request. A separate user approval is required before any paid call or key/grant setup.

## Goal and sample

Evaluate whether a real model understands information that was visible in each final prompt and correctly abstains or chooses a safe next step. Use only the synthetic WP3 conversation and these seven fixed questions:

- Q02 initial `/callback` endpoint;
- Q03 formal Request ID correction;
- Q06 protocol version change;
- Q07 `max_attempts` change;
- Q08 deployed version unknown;
- Q10 HTTP 202 / ACCEPTED is not completion;
- Q12 safe next action under unresolved status.

Run A `HYBRID`, B `ROLLING_SUMMARY`, C `RECENT_WINDOW`, and D full-history reference with 3 independent repeats each. This yields 84 answer outputs for blinded scoring. D remains a higher-budget reference, not a same-budget winner. Every question-run starts from the same isolated pre-question snapshot; Gold and scoring rules stay out of prompts.

## Proposed Provider and request controls

Use the DeepSeek Chat Completions API with model alias `deepseek-flash`; the official Models & Pricing page currently maps it to `DeepSeek-V4.1-Flash-1017` and lists a 1M context window. Record the returned model/version for every call and stop if the model identity changes during the experiment. Pin the API request format and archive the non-secret request parameters.

Proposed parameters: non-thinking mode (`thinking: {"type":"disabled"}`), `temperature=0`, `max_tokens=512`, fixed `SYSTEM` prompt digest `46267d783298bcb2c64957de58d4d117b760151323ae9e1bf5a5434b9a37163b`, and fixed tool-schema digest `f6c75eaa3b2a807c95258e0df2428d046b4fe545d5a5a15a83384d3880415c12`. Keep the same A/B/C and D budgets as Phase A: 12,000 input tokens for A/B/C and 60,000 for D; each compression request is capped at 12,000 input tokens. Keep the 512-token output cap for each compression and answer request. DeepSeek documents the model alias, current version, context length and prices on its [Models & Pricing page](https://api-docs.deepseek.com/quick_start/pricing/), and documents the non-thinking flag, `max_tokens`, and temperature on the [Chat Completions API page](https://api-docs.deepseek.com/api/create-chat-completion/).

No web-search, web-fetch, real MCP, or business-action tool is enabled. If the fixed tool schema is included for prompt parity, any returned tool call is recorded but never dispatched. No external side effect is possible through this evaluation harness.

## Maximum request and token budget

No retries. A failed response consumes its request slot and budget. Stop after any identity change, unexpected tool request, output overrun, malformed evidence, or cap breach.

| Request type | Maximum calls | Input cap per call | Output cap per call | Maximum token total |
|---|---:|---:|---:|---:|
| A/B compression | 84 | 12,000 | 512 | 1,008,000 input + 43,008 output |
| A/B/C answers | 63 | 12,000 | 512 | 756,000 input + 32,256 output |
| D answers | 21 | 60,000 | 512 | 1,260,000 input + 10,752 output |
| **Total** | **168** | — | — | **3,024,000 input + 86,016 output** |

At the currently published peak, cache-miss price of $0.30 per million input tokens and $1.20 per million output tokens, this worst-case token envelope is **$1.0104192** before taxes or non-token charges. Set a hard client-side spend ceiling of **$1.25**. Before each request, reserve the maximum cost for that request using the peak no-cache rate; stop before the next request if the remaining ceiling cannot cover it. Do not use DeepSeek Search/Fetch, which the official pricing page bills separately. Actual billing is based on Provider-reported input/output usage and may be lower due to caching; record that separately from local estimates.

## Scoring plan

Gold remains in offline scorer files only. First run deterministic checks for exact identifiers (`/callback`, `req-483`, `evt-731`), version direction (`v1.2 → v1.3`), numeric change (`3 → 5`), explicit unknown for the deployed version, refusal to label HTTP 202 as completion, and preservation of no-write constraints. Score whether Q12 proposes an authorized read-only status check or asks for a trusted completion receipt without claiming it happened.

Two reviewers, blinded to strategy and repeat number, independently rate each of the 84 answer outputs for meaning, correction handling, uncertainty, non-completion reasoning, and safe next step. Resolve disagreements with an adjudicator. Report deterministic fact checks separately from human ratings; do not turn exact-string checks into a semantic accuracy score. Keep each answer's input Manifest and source citations with its rating record.

## Data handling and authorization

- Use only the synthetic WP3 trace and the seven fixed question texts; do not add real user, customer, credential, account, or business records.
- Keep Gold and answer labels out of model prompts and Provider logs. Store the minimal request/response evidence needed for reproducibility, with API keys in a secret store/environment variable and never in source control.
- Do not create a Grant or use project business credentials. Do not call external MCP or business systems.
- Obtain a separate explicit authorization before creating credentials, making Provider requests, or spending up to the proposed $1.25 cap.

## Limits

Three repeats do not eliminate model sampling or backend variation. Temperature zero is a control, not a determinism guarantee. The provider alias can move; record returned model identity and stop on drift. The proposal tests this one synthetic journey and cannot prove performance on production conversations.
