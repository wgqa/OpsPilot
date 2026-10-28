# Updated candidate preflight

**Candidate outcome: READY_FOR_AUTHORIZED_PROBE, conditional on documented
contract assumptions and main-Agent acceptance. No paid authorization exists.**
This does not release P1/P2 or permit five-pair execution.

## Classified compatibility contract (HF-C)

| Item | Class | Candidate handling |
|---|---|---|
| Trusted TaskBinding / six tools / Domain auth | Safety | Unchanged; no new fact/write channel. |
| Correct non-thinking max_tokens and bound actual body | Cost safety | Strict; unsupported/unknown fields/mode/limits reject before I/O. |
| No retry / single-flight / cap / durable unknown | Cost safety | Retained for both policies; SDK and transport retries zero; no automatic repair/retry. |
| Usage integers, totals, input/output bound, no unexpected reasoning | Cost and audit | Missing/malformed/overrun stops; unresolved full reservation persists. |
| Actual Completion ID and reservation ID | Audit necessary | Nonempty real returned ID required, never generated from a local Run ID. |
| Model and system_fingerprint | Comparison audit | Required; pin and stop on drift. Missing fingerprint prevents accepting the probe/comparison, not new Domain authorization. |
| finish_reason | Delivery/audit | Require stop or tool_calls. Missing, length, interrupted/unknown completion stops normal delivery; known Usage still retained. |
| HTTP x-request-id | Implementation preference | Not required by checked API schema. Opt-in mode accepts real Completion ID as correlation, keeps header null and records COMPLETION_ID kind. Legacy mode unchanged. |
| parallel_tool_calls=false | Scheduling preference | Retained identically in actual A/B bodies. Not explicitly listed for Chat Completions. Acceptance requires authorized probe; never remove/retry after rejection. Not trusted as permission/attempt control. |
| tool_choice=auto / raw JSON schemas | Model-choice contract | Documented auto permits answer or tools; exact schema parity checked. No enforced order or schema reduction. |

The separate Responses API guide says its parallel field is ignored. That is not
evidence for Chat Completions; no switch to Responses or Anthropic is made here.
SDK nominal max_tokens renaming is explicitly handled with extra_body, not a silent
post-error workaround. max_retries=0, no redirects/proxy, and actual pre-send JSON
verification remain. See local traces for actual request/response bytes and Usage.

Header compatibility change is a proposal in the new opt-in policy, with headerless
positive and missing-completion negative tests; it is not claimed already accepted
by the main Agent. Fingerprint, real remote model version, Usage/mode/output-limit
compliance and the parallel field remain **REQUIRES_AUTHORIZED_PROVIDER_PROBE**.
They are not established by fake Provider responses.

## No automatic P1 authority

Default CLI remains offline. New --request-bound / --wire-body performs an offline
one-request preflight with cap USD 0.50. No SDK/key lookup is needed. No body means
no bound/ready result. Existing --live batch entry refuses the request-bound mode;
the old legacy batch remains blocked by its original conservative monetary bound.

The library adapter can construct a candidate paid client only after all of:

- live=True plus explicit human approval reference, not a test fixture or old P1 plan;
- scope ONE_REQUEST_PROTOCOL_PROBE and REQUEST_WIRE_V1 explicitly approved;
- exact model config digest, exact authorized wire digest and six schemas;
- ledger request_limit=1 and cap USD 0.50, no prior/unresolved/unknown request;
- actual runtime prepared body matches that authorized body before reservation;
- actual HTTP body matches the durable reservation before sending.

The sole positive paid-factory gate test replaces the factory with a stub: it
constructs no paid SDK/client and sends nothing. No authorization artifact with
authorized=true is supplied as a runnable approval. Ledger deletion/manual policy
tampering is not a supported reset/retry mechanism.

## Proposed future probe (NOT AUTHORIZED / NOT RUN)

After independent review and explicit user authorization only: one non-thinking
DeepSeek Flash request, exact frozen material-case body and the same six schemas,
no tool execution or full Agent loop, max_tokens 512, 30s, no retry; cap USD 0.50,
reserve USD 0.315188. Record actual model/fingerprint/completion/request IDs,
parameters, Usage/cache/reasoning, finish_reason and elapsed time. Stop on any
error or unknown; do not automatically start B or the remaining pairs.

This tests protocol acceptance/compliance for one body, not intelligence or all
possible cost behavior. If it fails, preserve response/uncertainty and return HOLD.
Subsequent A/B paid runs still require a separate release/authorization decision.
