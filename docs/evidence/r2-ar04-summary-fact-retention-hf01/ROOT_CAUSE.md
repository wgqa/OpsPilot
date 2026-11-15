# Root-cause reconstruction

## Method and evidence boundary

The source of truth is the immutable `abc-live-env-unblock-01/live_run_02/` request/response trace and its paired results. It contains 42 trace records: 21 `SEND_STARTED` and 21 `RESPONSE_RECEIVED`. This task made zero provider requests. The trace's original input sequence 3 contains `endpoint=/callback`, `max_attempts=3`, `req-482`, and `evt-731`; sequence 7 formally corrects `req-482` to `req-483` because of an entry error; sequence 11 states protocol `v1.2 → v1.3`, `max_attempts 3 → 5`, and that deployment version is unknown.

The complete pre-fix reconstruction is retained unchanged in `TRACE_RECONSTRUCTION_BEFORE.json`. Its SHA-256 is `e68924d3652306b7edd81a7f273d8dcda2ef55bbe8d587a183c83453953d3c26`. The replayable script `reconstruct_live_trace.py` pairs request/response IDs and checks the original summary, application projection, next summary request, provider summary, and final answer request. `TRACE_RECONSTRUCTION_AFTER.json` adds a candidate-code replay while keeping the historical baseline wire separate. Candidate replay means frozen Provider output passed through current application code; it does not claim the old second Provider request was re-run.

## Causal path

```text
source messages (seq 3 / 7 / 11)
  → first summary request
  → first frozen Provider summary
  → Base _compact_summary_document before persistence
  → persisted previous_summary projection
  → second frozen Provider summary request and response
  → final answer request/context selection
```

The first Provider summary contains the endpoint, correction relation, protocol/parameter change and unknown deployment version in all six cases. The first extraction step is therefore not the common failure. On Base, `_compact_summary_document()` gave newest entries within categories priority, capped each category, and clipped text to fixed lengths without indicating truncation. It could discard an older but still valid entry before persistence. The second summary request then received an already incomplete `previous_summary`; the second model output did not restore content absent from that input. This is an application persistence compaction loss, not evidence that the model had never extracted the facts.

## Per-case stage findings

Facts below are checked from the frozen wire body, not inferred from the answer. “First persisted” is the original first Provider summary after the Base helper. “Second request/summary” refers to the frozen original provider cycle. “Final” is the actual frozen final-answer request. The historic classification column is copied verbatim from the preserved BEFORE artifact; the fact-level fields are independently rechecked from the frozen raw request bodies by the updated reconstructor.

| Case | First Provider summary | Base first persistence / previous summary | Frozen second summary | Frozen final prompt | Historic classification |
|---|---|---|---|---|---|
| Q02-A | endpoint, correction, version/parameter change present | `/callback` and `v1.2 → v1.3` lost; correction and deployment-unknown remain | same key losses remain | `/callback` and protocol/parameter facts absent | endpoint and protocol: `PERSISTENCE_COMPACTION`; correction retained |
| Q02-B | all three primary facts present | `/callback` and full correction relation lost; protocol/version and `max_attempts=3→5` remain | same loss; second response does not restore endpoint/correction | `/callback`, `req-482` absent; `req-483` alone remains; protocol/parameter transition remains | endpoint/correction: `PERSISTENCE_COMPACTION`; protocol labeled `FINAL_CONTEXT_SELECTION` in frozen taxonomy |
| Q03-A | all present | endpoint lost; correction and version/parameter facts remain | same | correction and complete version/parameter transition present; endpoint absent | endpoint: `PERSISTENCE_COMPACTION`; correction retained; protocol labeled `FINAL_CONTEXT_SELECTION` |
| Q03-B | all present | endpoint lost; correction and version/parameter facts remain | same | correction and complete version/parameter transition present; endpoint absent | same as Q03-A |
| Q06-A | all present | endpoint lost; correction and version/parameter facts remain | same | `v1.2`, `v1.3`, `max_attempts=3`, `max_attempts=5`, and deployment unknown are present; endpoint absent | endpoint: `PERSISTENCE_COMPACTION`; protocol label says `FINAL_CONTEXT_SELECTION`, but rechecked final wire contains the complete requested version/parameter change |
| Q06-B | all present | endpoint and protocol/parameter change lost; correction and deployment-unknown remain | same; second model output does not restore version transition | endpoint and protocol/parameter facts absent; deployment unknown remains | endpoint and protocol: `PERSISTENCE_COMPACTION`; correction retained |

The frozen classification label for Q06-A is broader than its individual wire fact flags. The rechecked original final prompt contains both version strings and the 3-to-5 parameter change, consistent with the prior ABC report's successful Q06-A result. The unchanged BEFORE artifact is preserved for historical audit; its label is not used to override the actual request body. Similarly, `FINAL_CONTEXT_SELECTION` labels in other cases describe the old reconstruction's category-level classification, while this report states each value separately.

## What the failure means

- Q02-A and Q02-B: the user asked about an early endpoint, but `/callback` was already absent from the next summary input and final answer request. The safe abstentions match the evidence available to the model.
- Q06-B: the complete version change was already absent before the second Provider summarization. Its safe abstention is not proof of a model memory failure.
- Q02-B: the formal correction relation was also lost during persistence, though the latest value `req-483` survived. An isolated replacement ID is not equivalent to retaining the correction and its source.
- Q03-A/B and Q06-A: corrected/version facts reached the old final requests. This contrasts with the lost endpoint and Q06-B version chain.
- Deployment-version-unknown at seq11 was preserved in the old summary requests/final input where checked. It is a negative/unknown fact and must not be converted into a guessed deployment version.

`TRACE_RECONSTRUCTION_AFTER.json` also replays each frozen first Provider summary through the candidate helper twice: all target facts and source references remain visible and the serialized summary estimate is 499–509 tokens (under the unchanged 512-token cap). The new Domain Fixture tests then exercise actual persistence and final context construction; no post-fix Provider output or semantic answer is claimed.
