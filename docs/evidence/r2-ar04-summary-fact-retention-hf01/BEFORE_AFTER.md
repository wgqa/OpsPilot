# Before / after

## Frozen live facts and candidate application replay

The “before” cells below are visibility in the original first Provider summary after the Base application compactor. “Old final” is visibility in the actual frozen final-answer request. “Candidate” is a deterministic replay of the same first frozen Provider summary through the candidate compactor and its second application projection. It does not reuse the old model answer as if it answered a new prompt.

| Fact | Case | First Provider output | Base first persistence | Old final request | Candidate after two app projections |
|---|---|---:|---:|---:|---:|
| `endpoint=/callback` (seq3) | Q02-A | present | absent | absent | present |
| `endpoint=/callback` (seq3) | Q02-B | present | absent | absent | present |
| formal `req-482 → req-483` + reason (seq7) | Q02-B | present | absent | incomplete (`req-483` only) | present |
| `v1.2 → v1.3`, `max_attempts 3 → 5` (seq11) | Q02-A | present | absent | absent | present |
| `v1.2 → v1.3`, `max_attempts 3 → 5` (seq11) | Q06-B | present | absent | absent | present |
| formal correction (seq7) | Q03-A / Q03-B | present | present | present | present |
| version/parameter change (seq11) | Q02-B / Q03-A / Q03-B / Q06-A | present | present | present in actual wire | present |
| deployment version unknown (seq11) | all six | present | present | present where checked | present |

Candidate replay token estimates by case, under the existing 512-token cap:

| Case | Candidate projected summary estimate |
|---|---:|
| Q02-A | 504 |
| Q02-B | 500 |
| Q03-A | 506 |
| Q03-B | 499 |
| Q06-A | 502 |
| Q06-B | 509 |

These are application estimator counts, not Provider billing counts. Full source sequences, per-stage flags, request digests, response IDs, summary content and context blocks are in `TRACE_RECONSTRUCTION_BEFORE.json` and `TRACE_RECONSTRUCTION_AFTER.json`.

## Deterministic Domain Fixture

For both `HYBRID` and `ROLLING_SUMMARY`, the test uses an isolated Domain fixture, performs two persisted summary rounds, inspects the actual second summary input's `previous_summary`, then prepares a real application answer request and inspects its actual `messages`. It asserts that the final request contains `/callback`, `max_attempts=3`, both request IDs and their correction reason, `v1.2 → v1.3`, `max_attempts 3 → 5`, and `Deployment version unknown`. It also verifies that the final summary maps seq 1/3/5/11 to persisted message IDs, the summary versions are `SUPERSEDED` then `CURRENT`, source currentness passes, and estimated answer input stays at or below the fixture's 1,800-token budget.

Evidence grade: deterministic Fixture and Domain application path (L2). This demonstrates application-visible information preservation. It does **not** establish that a live Provider will produce the same second summary or answer correctly; that requires a separately authorized L3 evaluation.

## Implementation shape

The candidate keeps the existing summary schema and output cap. It selects bounded source-linked category anchors before optional detail, uses a visible ellipsis for clipped text, and fails explicitly if an anchor cannot fit. Source sequence metadata is derived from validated references. The selection uses categories and source order, with no string-specific rules for the audited facts. Existing source invalidation remains in force.

Limit: the schema does not record a per-fact omission ledger. Facts not selected among the bounded anchors or optional items can still be absent without a structured omission reason. The candidate therefore establishes retention for the tested fact set, not general lossless retention.
