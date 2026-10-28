# Bound analysis — observed / assumed / unknown

## HF-A: why the old refusal was correct

Base provider_budget.py fixes both input and output to the model-wide capacities:
1,048,576 input and 393,216 output. Peak no-cache accounting gives USD 0.786432.
The legacy reserve method never inspects actual max_tokens, so USD 0.50 correctly
refuses every request. The initial policy was deliberately conservative because
earlier SDK nominal 512 was exceeded. This is not a newly discovered business bug.

## Official contract actually read, 2026-10-28

[Pricing](https://api-docs.deepseek.com/quick_start/pricing/) identifies
deepseek-flash / DeepSeek-V4.1-Flash-1017, 1M context and maximum output 384K.
Use peak uncached input USD 0.30/M and output USD 1.20/M. No discounts assumed.
[Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)
defines max_tokens as generated-output limit, valid 1..393216, with input plus
output constrained by context. thinking.type=disabled selects non-thinking mode.
Usage distinguishes prompt/completion totals and reasoning/cache detail.
These are protocol facts from documentation, not fresh paid behavior observations.

[Token Usage](https://api-docs.deepseek.com/quick_start/token_usage/) provides
approximate character ratios and a downloadable offline tokenizer. It does not
certify those ratios as a billable upper bound. The inspected official archive
has SHA256 `e7310d1dafe0a86d8a5629fe78a7c763760f651db9b8682718a1781dcd6fe495`.
Its config says model_max_length=16384; its template does not reference tool
definitions, and no current server-side six-tool serialization specification or
Flash-1017 equivalence certificate accompanies it. Its demo uses transformers
trust_remote_code=True; we only inspected JSON/source, did not execute that code,
install packages or treat plain-text counts as full API input counts. No token-
count endpoint was documented in the checked Chat/Anthropic/token-usage pages.
This is limited negative documentation evidence, not proof none could exist.

## Actual wire and historical anomaly

The current installed SDK changes nominal max_tokens to max_completion_tokens.
An offline preparation comparison records that transformation. The current adapter
instead merges documented max_tokens=512 via extra_body. Actual received local
HTTP bodies verify disabled thinking, max_tokens, all six raw schemas and messages.
Prepared body digest is now rechecked at the actual HTTP edge; mutation refuses
before sending. Byte lengths are audit data, never a token-conversion guarantee.

The unchanged VS01 PROVIDER_LEDGER.jsonl contains 160 reservations/completions,
87 normalized output Usage values >512. All 87 include nonzero reasoning; 57
also have (output minus reported reasoning) >512. Example request
`a5d4fa36-d319-4e5f-8334-1b89daad1b30`: 878 output / 785 reasoning, nominal
reserve 512, assistant text empty but a tool call present. Text length alone
cannot measure tool/reasoning output. The ledger has no raw HTTP body. Its hash
and actual selected records are in research/history-observations.json.

| Candidate explanation | Evidence / unresolved point |
|---|---|
| SDK renamed the field | Verified for installed pinned SDK; old constructor uses max_tokens=512. Historical SDK raw wire was not archived, so exact past dispatch is unproven. |
| Correct wire output limit absent | Plausible consequence of renaming; cannot prove from old ledger alone. |
| Provider ignored a correctly sent max_tokens | Not established. Requires an authorized remote probe; local fake failures cannot establish vendor behavior. |
| Usage includes hidden reasoning / tool output | Present in all 87 examples; cannot explain every overrun solely by reasoning subtraction. No independent tokenizer/billing reconciliation of those responses. |

Thus the new code does not claim to fix a demonstrated Provider bug or retrospectively
change old costs/results. Non-thinking mode and actual wire differ from the older
nominal configuration. Residual vendor-compliance uncertainty is retained.

## HF-B: limited request-contract reservation

Opt-in REQUEST_WIRE_V1 uses the **full documented context capacity** for input,
including messages, tool schemas and hidden server framing. It does not claim a
tight per-text input bound, and does not use the application's 12,000 estimate.
Only the output bound narrows to the actual, validated documented parameter 512.

`reserve_microUSD = ceil(input_upper * 0.30 + output_upper * 1.20)`

For every accepted fixed-configuration body: `ceil(1048576*0.30 + 512*1.20)`
= 315188 microUSD = **USD 0.315188**. This overcounts the joint context limit.
A small six-tool request and a larger valid text request share that conservative
capacity bound; byte/schema counts differ but do not silently lower it. Unknown
models, modes, modalities, fields and output limits reject. We do not shrink
questions/tools/Context, nor depend on cache/off-peak rates.

This bound relies on the vendor honoring its output/context/mode contract. It is
not a mathematical or invoice guarantee against vendor violations. On reported
input/output excess, unexpected reasoning, malformed Usage or unknown outcome,
stop subsequent requests; record known charge or keep the full unknown reserve.
Two unresolved 315188 reserves cannot fit USD 0.50. A known-small settlement
releases unused exposure; prior requests and single-flight checks persist on restart.

Default legacy policy and old Ledger identities are preserved. New policy cannot
open/relabel an old ledger; its per-request bound_json and body digest are durable.
This is an opt-in experiment candidate, not an automatic P1 rollout.
