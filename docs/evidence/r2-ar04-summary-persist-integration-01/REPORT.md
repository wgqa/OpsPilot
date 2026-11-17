# R2-AR04 Summary Persistence Integration Gate

**Status:** `ACCEPTANCE_CANDIDATE`

**Scope:** zero-cost isolated integration only

**Source base:** `ba146c8c6707ff60673d62b6375248e1551a2796`

**Required production chat Blob:** `6a57360de6f5579fa65dc008de4fcf37148c43f0`

## Result

The fixed `chat.py` passed an isolated Assistant/Domain execution path for Q02-B and Q06-B. Each case started from the same frozen 29-message synthetic history in its own temporary SQLite Domain, Session, Checkpoint and Assistant Run. The actual `assistant.run_assistant()` orchestration, context builder, compression attempts, Domain summary validation/persistence, answer manifest path and final prompt construction ran. The model boundary was injected with a deterministic offline `BaseChatModel` fixture; Q02-B's first summary body was replayed from the already-saved Live 02 response. No model or Provider was contacted in this task.

| Case | Run | Summary persistence | Final current summary fact | Source | Final prompt local estimate |
|---|---|---|---|---|---:|
| Q02-B | `SUCCEEDED` | 2/2 attempts succeeded; first summary `SUPERSEDED`, second `CURRENT` | `endpoint=/callback` and the earlier `max_attempts=3` assertion remain visible | frozen history seq 3, validated against its message ID and Domain scope | 6,658 tokens |
| Q06-B | `SUCCEEDED` | 2/2 attempts succeeded; first summary `SUPERSEDED`, second `CURRENT` | `v1.2 → v1.3`, `max_attempts 3 → 5`, deployment version unknown; earlier seq 3 remains explicitly `max_attempts=…` | transition from frozen history seq 11; partial assertion from seq 3 | 6,557 tokens |

There were 6 offline fixture dispatches: 4 summary calls and 2 answer calls. These numbers are fixture invocations, not Provider requests. The local estimates and fixture usage metadata are not billable Provider Usage. The final serialized prompts sent to the injected fixture are preserved in `offline_run_02/FINAL_PROMPTS.json`; the full structured run results and source checks are in `offline_run_02/RESULTS.json`.

Q02-B's first saved DeepSeek response is trace-bound and hash-checked before replay. Q02-B's second summary and Q06-B's first summary use responses from the pinned historical Mock trace. The final Q06-B second-round fixture is an explicitly synthetic, context-bound document that cites only sequence references available in that round. Neither synthetic summary nor either synthetic answer is evidence of model semantic recall. L3 is `NOT_RUN`.

## Provenance and Scope Checks

The Q02-B first persisted compact projection uses `source_sequences`; the Q06-B first persisted projection uses `source_message_ids`. This is the observed current representation, not an assumed common schema. The test separately forged the Q02-B sequence-to-message map to point at a different tenant, another Session, and another Task. All three were rejected by `_summary_sequence_source_ids()` (`3/3`), using the production Domain resolver and an isolated disposable database. The current summary facts in both final prompts were also resolved to allowed source message IDs in the same tenant, Session, Task scope and frozen sequence.

The final prompts contain the read-only system policy, current task/evidence blocks, persisted summary and the frozen question. Gold, rubric and scoring fields are not loaded into the fixture request. The Assistant tool choice is `none`; no MCP call or business/action write was recorded. Final answer text is tagged `SYNTHETIC_FIXTURE_ONLY` and is not scored.

The test injects the fixture at the Assistant model interface. It validates the normal Assistant orchestration and Domain persistence, but deliberately does not instantiate a real Provider adapter or Runtime Grant; no grant or send authorization was created. Therefore this result does not validate provider transport, grant charging, or live-send readiness.

## Negative Fixture Replay

Replaying the old Q06-B second-summary Mock response unchanged failed during Domain validation with `CONTEXT_SUMMARY_SOURCE_INVALID`. That response cited sequence 15, but the second-round source map admitted only the currently supplied summary dependencies and new messages; sequence 15 was not available. The check correctly stopped before writing the second summary or producing an answer. The final integration therefore uses a separately labeled context-bound fixture and retains the failed replay as a harness observation. This is not a change to production behavior and does not claim the old Mock response is reusable under a different source manifest.

## Version and Rollback Limits

The current source is fixed to the `chat.py` and `assistant.py` Blobs recorded in `FROZEN_INPUTS.json`. The old Live Runner remains unchanged and still pins its pre-fix `chat.py` version; it must not be reused for a future run without a new strict version binding. The historical source code has `_summary_source_message_ids()` but lacks the current `_summary_sequence_source_ids()` resolver. A rollback that encounters compact summaries persisted with sequence citations is therefore **not verified as compatible**. Do not treat database rollback/reuse as safe; a future rollback plan must recreate the summary from raw history or add and validate a compatible migration/reconstruction path.

`verify_frozen_inputs.py` is an offline integrity check only. It checks the accepted source base is an ancestor, exact production/governance Git Blobs in `HEAD`, the index and working tree, frozen input/evidence SHA-256 values, and the generated offline artifacts. It does not load `.env`, create a Grant, authorize Live, or make network requests. Any future semantic retest needs its own version-adapted runner/manifest and new explicit bounded authorization.

## Safety and Change Scope

- Provider requests: **0**; cost: **USD 0**.
- Valid paid authorization created: **No**.
- External MCP calls: **0**; business/action writes: **0**.
- Production code, Gold, historical Live Trace, Ledger and prior failed records: **unchanged**.
- Changes are limited to this evidence folder and its offline integration test.

See `TEST_RUN.txt` for command lines, exit codes, the negative fixture observation and selected regression results. This is an implementation candidate for independent review, not authorization for a Live retest and not AR-04 semantic PASS.
